"""求职方案表模型与增删查改。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Field, SQLModel, col, select

from job.boss.filters import Defaults


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


class SearchPlanRow(SQLModel, table=True):
    """求职方案：筛选条件 + 当前/默认标记。"""

    __tablename__ = "search_plan"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    name: str = Field(index=True, description="方案名称")
    is_default: bool = Field(default=False, description="是否默认方案（全局唯一语义）")
    is_active: bool = Field(default=False, description="是否当前选用（抓取用这份）")
    query: str = Field(default="", description="岗位关键词")
    city_code: str = Field(default="", description="城市编码")
    job_type: str = Field(default="", description="求职类型编码")
    salary: str = Field(default="", description="薪资范围编码")
    experience_json: str = Field(default="[]", description="经验要求（JSON 标签列表）")
    education_json: str = Field(default="[]", description="学历要求（JSON 标签列表）")
    funding_json: str = Field(default="[]", description="融资阶段（JSON 标签列表）")
    scale_json: str = Field(default="[]", description="企业规模（JSON 标签列表）")
    pace: str = Field(
        default=Defaults.PACE,
        sa_column_kwargs={"server_default": Defaults.PACE},
        description="抓取速率码（slow / normal / fast / custom）",
    )
    pace_json: str = Field(
        default="{}",
        sa_column_kwargs={"server_default": "{}"},
        description="自定义速率明细参数（JSON 对象）",
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
            "experience": _loads_list(self.experience_json),
            "education": _loads_list(self.education_json),
            "funding": _loads_list(self.funding_json),
            "scale": _loads_list(self.scale_json),
            "pace": self.pace,
            "pace_params": _loads_dict(self.pace_json),
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
                experience_json="[]",
                education_json="[]",
                funding_json="[]",
                scale_json="[]",
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
        experience: list[str] | None = None,
        education: list[str] | None = None,
        funding: list[str] | None = None,
        scale: list[str] | None = None,
        pace: str | None = None,
        pace_params: dict[str, float] | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """更新筛选字段或名称；未传的参数保持原值。"""
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
            if experience is not None:
                row.experience_json = _dumps_list(experience)
            if education is not None:
                row.education_json = _dumps_list(education)
            if funding is not None:
                row.funding_json = _dumps_list(funding)
            if scale is not None:
                row.scale_json = _dumps_list(scale)
            if pace is not None:
                row.pace = pace
            if pace_params is not None:
                row.pace_json = json.dumps(pace_params)
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
                experience_json=src.experience_json if src else "[]",
                education_json=src.education_json if src else "[]",
                funding_json=src.funding_json if src else "[]",
                scale_json=src.scale_json if src else "[]",
                pace=src.pace if src else Defaults.PACE,
                pace_json=src.pace_json if src else "{}",
                updated_at=datetime.now(UTC),
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
        """切换当前方案（抓取与配置页编辑这份）。"""
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
