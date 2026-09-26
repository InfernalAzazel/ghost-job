"""求职配置表模型（全局只有一份）。"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Field, SQLModel, select

from job.boss.filters import Defaults

# 匹配度过滤的默认最低分
DEFAULT_MIN_SCORE = 60


def _session():
    from job.models import db_session

    return db_session()


def _loads_list(raw: str) -> list[str]:
    """把库里存的 JSON 数组字符串解析成 list。"""
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]


def _loads_dict(raw: str) -> dict[str, Any]:
    """把库里存的 JSON 对象字符串解析成 dict。"""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _dumps_list(values: Sequence[str] | None) -> str:
    """把多选标签列表序列化进库。"""
    return json.dumps(list(values or []), ensure_ascii=False)


# 多选字段名；库里各存为 ``<字段>_json``（JSON 标签列表）
LIST_FIELDS = (
    "cities",
    "experience",
    "education",
    "funding",
    "scale",
    "industry",
    "include_keywords",
    "exclude_keywords",
    "include_companies",
    "exclude_companies",
)


def _list_field(label: str) -> Any:
    """多选字段列：默认空列表。"""
    return Field(default="[]", description=f"{label}（JSON 标签列表）")


class SearchConfigRow(SQLModel, table=True):
    """求职配置：搜索条件、筛选、投递节奏与简历。"""

    __tablename__ = "search_config"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    query: str = Field(default="", description="岗位关键词")
    job_type: str = Field(default="", description="求职类型编码")
    salary: str = Field(default="", description="薪资范围编码")
    cities_json: str = _list_field("目标城市（按顺序依次投递）")
    experience_json: str = _list_field("经验要求")
    education_json: str = _list_field("学历要求")
    funding_json: str = _list_field("融资阶段")
    scale_json: str = _list_field("企业规模")
    industry_json: str = _list_field("行业")
    include_keywords_json: str = _list_field("职位名包含关键词")
    exclude_keywords_json: str = _list_field("职位名排除关键词")
    include_companies_json: str = _list_field("公司名包含关键词")
    exclude_companies_json: str = _list_field("公司名排除关键词")
    pace: str = Field(
        default=Defaults.PACE, description="投递速率码（slow / normal / fast / custom）"
    )
    pace_json: str = Field(default="{}", description="自定义速率明细参数（JSON 对象）")
    ai_review: bool = Field(default=False, description="是否开启 AI 岗位意图复核")
    ai_requirement: str = Field(default="", description="AI 复核用的目标岗位要求")
    resume_match: bool = Field(
        default=False, description="是否用大模型比对岗位详情与简历技术，不匹配则跳过"
    )
    score_filter: bool = Field(
        default=False, description="是否按匹配度过滤（需开启简历技术匹配）"
    )
    min_score: int = Field(
        default=DEFAULT_MIN_SCORE, description="最低匹配度 0–100，低于它的岗位跳过"
    )
    resume_path: str = Field(default="", description="简历 PDF 本地路径")
    resume_text: str = Field(default="", description="简历文本（从 PDF 解析，可手动修改）")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="最后更新时间（UTC）",
    )

    def to_dict(self) -> dict[str, Any]:
        """转为配置页 / URL 拼装用的字典（多选已展开为 list）。"""
        return {
            "query": self.query,
            "job_type": self.job_type,
            "salary": self.salary,
            **{f: _loads_list(getattr(self, f"{f}_json")) for f in LIST_FIELDS},
            "pace": self.pace,
            "pace_params": _loads_dict(self.pace_json),
            "ai_review": self.ai_review,
            "ai_requirement": self.ai_requirement,
            "resume_match": self.resume_match,
            "score_filter": self.score_filter,
            "min_score": self.min_score,
            "resume_path": self.resume_path,
            "resume_text": self.resume_text,
        }

    @classmethod
    def ensure(cls) -> SearchConfigRow:
        """取唯一的配置行；没有就写入默认配置。"""
        with _session() as session:
            row = session.exec(select(cls)).first()
            if row is None:
                row = cls(
                    query=Defaults.QUERY,
                    job_type=Defaults.JOB_TYPE,
                    salary=Defaults.SALARY,
                    cities_json=_dumps_list(Defaults.CITIES),
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return row

    @classmethod
    def load(cls) -> dict[str, Any]:
        """读取求职配置。"""
        return cls.ensure().to_dict()

    @classmethod
    def save(
        cls,
        *,
        query: str | None = None,
        job_type: str | None = None,
        salary: str | None = None,
        pace: str | None = None,
        pace_params: dict[str, float] | None = None,
        ai_review: bool | None = None,
        ai_requirement: str | None = None,
        resume_match: bool | None = None,
        score_filter: bool | None = None,
        min_score: int | None = None,
        resume_path: str | None = None,
        resume_text: str | None = None,
        **lists: list[str] | None,
    ) -> dict[str, Any]:
        """更新求职配置；未传的参数保持原值。

        ``lists`` 为多选字段（见 ``LIST_FIELDS``），如 ``cities=["广州", "深圳"]``。
        """
        unknown = set(lists) - set(LIST_FIELDS)
        if unknown:
            raise TypeError(f"unknown config fields: {sorted(unknown)}")
        row_id = cls.ensure().id
        with _session() as session:
            row = session.get(cls, row_id)
            assert row is not None
            scalars = {
                "query": query,
                "job_type": job_type,
                "salary": salary,
                "pace": pace,
                "ai_review": ai_review,
                "ai_requirement": ai_requirement,
                "resume_match": resume_match,
                "score_filter": score_filter,
                "resume_path": resume_path,
                "resume_text": resume_text,
            }
            for field, value in scalars.items():
                if value is not None:
                    setattr(row, field, value)
            for field, values in lists.items():
                if values is not None:
                    setattr(row, f"{field}_json", _dumps_list(values))
            if pace_params is not None:
                row.pace_json = json.dumps(pace_params)
            if min_score is not None:
                row.min_score = max(0, min(100, min_score))
            row.updated_at = datetime.now(UTC)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.to_dict()
