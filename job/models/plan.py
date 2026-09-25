"""求职方案表模型与增删查改。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Field, SQLModel, col, select

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


def _dumps_list(values: list[str] | None) -> str:
    """把多选标签列表序列化进库。"""
    return json.dumps(list(values or []), ensure_ascii=False)


# 多选字段名；库里各存为 ``<字段>_json``（JSON 标签列表）
LIST_FIELDS = (
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


def _list_columns() -> list[str]:
    """多选字段对应的库列名。"""
    return [f"{f}_json" for f in LIST_FIELDS]


def _list_field(label: str) -> Any:
    """多选字段列：默认空列表，老库补列时也填空列表。"""
    return Field(
        default="[]",
        sa_column_kwargs={"server_default": "[]"},
        description=f"{label}（JSON 标签列表）",
    )


class SearchPlanRow(SQLModel, table=True):
    """求职方案：筛选条件 + 当前/默认标记。"""

    __tablename__ = "search_plan"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    name: str = Field(index=True, description="方案名称")
    is_default: bool = Field(default=False, description="是否默认方案（全局唯一语义）")
    is_active: bool = Field(default=False, description="是否当前选用（投递用这份）")
    query: str = Field(default="", description="岗位关键词")
    city_code: str = Field(default="", description="城市编码")
    job_type: str = Field(default="", description="求职类型编码")
    salary: str = Field(default="", description="薪资范围编码")
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
        default=Defaults.PACE,
        sa_column_kwargs={"server_default": Defaults.PACE},
        description="投递速率码（slow / normal / fast / custom）",
    )
    pace_json: str = Field(
        default="{}",
        sa_column_kwargs={"server_default": "{}"},
        description="自定义速率明细参数（JSON 对象）",
    )
    ai_review: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
        description="是否开启 AI 岗位意图复核",
    )
    ai_requirement: str = Field(
        default="",
        sa_column_kwargs={"server_default": ""},
        description="AI 复核用的目标岗位要求",
    )
    resume_match: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
        description="是否用大模型比对岗位详情与简历技术，不匹配则跳过",
    )
    score_filter: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
        description="是否按匹配度过滤（需开启简历技术匹配）",
    )
    min_score: int = Field(
        default=DEFAULT_MIN_SCORE,
        sa_column_kwargs={"server_default": str(DEFAULT_MIN_SCORE)},
        description="最低匹配度 0–100，低于它的岗位跳过",
    )
    resume_path: str = Field(
        default="",
        sa_column_kwargs={"server_default": ""},
        description="简历 PDF 本地路径",
    )
    resume_text: str = Field(
        default="",
        sa_column_kwargs={"server_default": ""},
        description="简历文本（从 PDF 解析，可手动修改）",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
        description="最后更新时间（UTC）",
    )

    def to_dict(self) -> dict[str, Any]:
        """转为配置页 / URL 拼装用的字典（多选已展开为 list）。"""
        return {
            "id": self.id,
            "name": self.name,
            "is_default": self.is_default,
            "is_active": self.is_active,
            "query": self.query,
            "city_code": self.city_code,
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
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }

    @classmethod
    def ensure_default(cls) -> SearchPlanRow:
        """无方案时写入默认方案；有方案但无 active 时自动补上。"""
        with _session() as session:
            existing = session.exec(select(cls).limit(1)).first()
            if existing is not None:
                active = session.exec(
                    select(cls).where(col(cls.is_active).is_(True))
                ).first()
                if active is None:
                    first = session.exec(select(cls)).first()
                    assert first is not None
                    first.is_active = True
                    session.add(first)
                    session.commit()
                    session.refresh(first)
                    return first
                return active
            row = cls(
                name="默认方案",
                is_default=True,
                is_active=True,
                query=Defaults.QUERY,
                city_code=Defaults.CITY_CODE,
                job_type=Defaults.JOB_TYPE,
                salary=Defaults.SALARY,
                updated_at=datetime.now(UTC),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    @classmethod
    def list_dicts(cls) -> list[dict[str, Any]]:
        """列出全部方案（最近更新的在前）。"""
        with _session() as session:
            rows = session.exec(select(cls).order_by(col(cls.updated_at).desc())).all()
        return [r.to_dict() for r in rows]

    @classmethod
    def get_dict(cls, plan_id: str) -> dict[str, Any] | None:
        """按 id 取方案；不存在返回 None。"""
        with _session() as session:
            row = session.get(cls, plan_id)
            if row is None:
                return None
            return row.to_dict()

    @classmethod
    def get_active_dict(cls) -> dict[str, Any]:
        """取当前激活方案（保证库里至少有默认方案）。"""
        row = cls.ensure_default()
        with _session() as session:
            active = session.exec(
                select(cls).where(col(cls.is_active).is_(True))
            ).first()
            if active is None:
                active = session.get(cls, row.id)
            assert active is not None
            return active.to_dict()

    @classmethod
    def update_filters(
        cls,
        plan_id: str,
        *,
        query: str | None = None,
        city_code: str | None = None,
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
        name: str | None = None,
        **lists: list[str] | None,
    ) -> dict[str, Any]:
        """更新筛选字段或名称；未传的参数保持原值。

        ``lists`` 为多选字段（见 ``LIST_FIELDS``），如 ``industry=["互联网"]``。
        """
        unknown = set(lists) - set(LIST_FIELDS)
        if unknown:
            raise TypeError(f"unknown plan fields: {sorted(unknown)}")
        with _session() as session:
            row = session.get(cls, plan_id)
            if row is None:
                raise KeyError(f"plan not found: {plan_id}")
            if name is not None:
                row.name = name.strip() or row.name
            if query is not None:
                row.query = query
            if city_code is not None:
                row.city_code = city_code
            if job_type is not None:
                row.job_type = job_type
            if salary is not None:
                row.salary = salary
            for field, values in lists.items():
                if values is not None:
                    setattr(row, f"{field}_json", _dumps_list(values))
            if pace is not None:
                row.pace = pace
            if pace_params is not None:
                row.pace_json = json.dumps(pace_params)
            if ai_review is not None:
                row.ai_review = ai_review
            if ai_requirement is not None:
                row.ai_requirement = ai_requirement
            if resume_match is not None:
                row.resume_match = resume_match
            if score_filter is not None:
                row.score_filter = score_filter
            if min_score is not None:
                row.min_score = max(0, min(100, min_score))
            if resume_path is not None:
                row.resume_path = resume_path
            if resume_text is not None:
                row.resume_text = resume_text
            row.updated_at = datetime.now(UTC)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.to_dict()

    @classmethod
    def create(
        cls,
        name: str = "新方案",
        *,
        copy_from_id: str | None = None,
    ) -> dict[str, Any]:
        """新建方案并设为当前；可从指定/当前方案复制筛选条件，名称自动去重。"""
        with _session() as session:
            src: SearchPlanRow | None = None
            if copy_from_id:
                src = session.get(cls, copy_from_id)
            if src is None:
                src = session.exec(
                    select(cls).where(col(cls.is_active).is_(True))
                ).first()

            existing_names = {r.name for r in session.exec(select(cls)).all()}
            base = name.strip() or "新方案"
            final_name = base
            suffix = 2
            while final_name in existing_names:
                final_name = f"{base} {suffix}"
                suffix += 1

            for r in session.exec(select(cls)).all():
                if r.is_active:
                    r.is_active = False
                    session.add(r)

            row = cls(
                name=final_name,
                is_default=False,
                is_active=True,
                query=src.query if src else Defaults.QUERY,
                city_code=src.city_code if src else Defaults.CITY_CODE,
                job_type=src.job_type if src else Defaults.JOB_TYPE,
                salary=src.salary if src else Defaults.SALARY,
                pace=src.pace if src else Defaults.PACE,
                pace_json=src.pace_json if src else "{}",
                ai_review=src.ai_review if src else False,
                ai_requirement=src.ai_requirement if src else "",
                resume_match=src.resume_match if src else False,
                score_filter=src.score_filter if src else False,
                min_score=src.min_score if src else DEFAULT_MIN_SCORE,
                resume_path=src.resume_path if src else "",
                resume_text=src.resume_text if src else "",
                updated_at=datetime.now(UTC),
                **({c: getattr(src, c) for c in _list_columns()} if src else {}),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.to_dict()

    @classmethod
    def rename(cls, plan_id: str, name: str) -> dict[str, Any]:
        """重命名方案。"""
        return cls.update_filters(plan_id, name=name)

    @classmethod
    def duplicate(cls, plan_id: str) -> dict[str, Any]:
        """复制方案（名称加「副本」），并切到新方案。"""
        with _session() as session:
            src = session.get(cls, plan_id)
            if src is None:
                raise KeyError(f"plan not found: {plan_id}")
            base_name = f"{src.name} 副本"
        return cls.create(base_name, copy_from_id=plan_id)

    @classmethod
    def delete(cls, plan_id: str) -> dict[str, Any]:
        """删除方案；至少保留一条。返回删除后的当前方案。"""
        with _session() as session:
            rows = list(session.exec(select(cls)).all())
            if len(rows) <= 1:
                raise ValueError("至少保留一个求职方案")
            target = session.get(cls, plan_id)
            if target is None:
                raise KeyError(f"plan not found: {plan_id}")
            was_active = target.is_active
            was_default = target.is_default
            session.delete(target)
            session.commit()

            remaining = list(session.exec(select(cls)).all())
            if was_default:
                remaining[0].is_default = True
                session.add(remaining[0])
            if was_active or not any(r.is_active for r in remaining):
                for r in remaining:
                    r.is_active = False
                    session.add(r)
                pick = next((r for r in remaining if r.is_default), remaining[0])
                pick.is_active = True
                session.add(pick)
            session.commit()
            active = session.exec(
                select(cls).where(col(cls.is_active).is_(True))
            ).first()
            assert active is not None
            return active.to_dict()

    @classmethod
    def set_default(cls, plan_id: str) -> dict[str, Any]:
        """设为默认方案（同时清掉其它方案的默认标记）。"""
        with _session() as session:
            target = session.get(cls, plan_id)
            if target is None:
                raise KeyError(f"plan not found: {plan_id}")
            for r in session.exec(select(cls)).all():
                r.is_default = r.id == plan_id
                session.add(r)
            session.commit()
            session.refresh(target)
            return target.to_dict()

    @classmethod
    def set_active(cls, plan_id: str) -> dict[str, Any]:
        """切换当前方案（投递与配置页编辑这份）。"""
        with _session() as session:
            target = session.get(cls, plan_id)
            if target is None:
                raise KeyError(f"plan not found: {plan_id}")
            for r in session.exec(select(cls)).all():
                r.is_active = r.id == plan_id
                session.add(r)
            target.updated_at = datetime.now(UTC)
            session.add(target)
            session.commit()
            session.refresh(target)
            return target.to_dict()
