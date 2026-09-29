"""公司查询结果：工商信息、网上搜到的资料与 AI 风险评估，按 BOSS 公司 ID 保存。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, col, select


def _now() -> datetime:
    return datetime.now(UTC)


class CompanyRow(SQLModel, table=True):
    """点「查企业」得到的结果；同一家公司的岗位和会话共用。"""

    __tablename__ = "company"  # pyright: ignore[reportAssignmentType]

    RISK_LABELS: ClassVar[dict[str, str]] = {
        "low": "低风险",
        "medium": "中风险",
        "high": "高风险",
        "unknown": "信息不足",
    }

    brand_id: str = Field(primary_key=True, description="BOSS 公司 ID")
    name: str = Field(default="", description="BOSS 上的公司简称")
    full_name: str = Field(default="", description="工商登记的企业名称；没取到为空")
    info: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON), description="工商信息：字段名 → 值"
    )
    hits: list[dict[str, str]] = Field(
        default_factory=list, sa_column=Column(JSON), description="搜索结果：[{title, href, body, query}]"
    )
    risk: str = Field(default="unknown", description="风险等级，见 RISK_LABELS")
    summary: str = Field(default="", description="AI 一句话结论")
    points: list[dict[str, str]] = Field(
        default_factory=list, sa_column=Column(JSON), description="AI 给出的依据：[{text, href}]"
    )
    checked_at: datetime = Field(default_factory=_now, description="查询时间（UTC）")

    @classmethod
    def save(
        cls,
        brand_id: str,
        *,
        name: str,
        full_name: str,
        info: dict[str, str],
        hits: list[dict[str, str]],
        risk: str,
        summary: str,
        points: list[dict[str, str]],
    ) -> None:
        from job.models import db_session

        row = cls(
            brand_id=brand_id,
            name=name,
            full_name=full_name,
            info=info,
            hits=hits,
            risk=risk,
            summary=summary,
            points=points,
        )
        with db_session() as session:
            session.merge(row)
            session.commit()

    @classmethod
    def get_dict(cls, brand_id: str) -> dict[str, Any] | None:
        """给弹窗用：工商信息转成 [{label, value}]，时间为本地时间。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, brand_id)
        if row is None:
            return None
        checked = row.checked_at.replace(tzinfo=row.checked_at.tzinfo or UTC).astimezone()
        return {
            "brand_id": row.brand_id,
            "name": row.name,
            "full_name": row.full_name,
            "info": [{"label": k, "value": v} for k, v in row.info.items()],
            "hits": row.hits,
            "risk": row.risk,
            "risk_label": cls.RISK_LABELS.get(row.risk, ""),
            "summary": row.summary,
            "points": row.points,
            "checked_at": checked.strftime("%Y-%m-%d %H:%M"),
        }

    @classmethod
    def risks(cls, brand_ids: Iterable[str]) -> dict[str, str]:
        """查过的公司 → 风险等级；没查过的不在结果里。"""
        from job.models import db_session

        wanted = {b for b in brand_ids if b}
        if not wanted:
            return {}
        stmt = select(cls.brand_id, cls.risk).where(col(cls.brand_id).in_(wanted))
        with db_session() as session:
            return dict(session.exec(stmt).all())
