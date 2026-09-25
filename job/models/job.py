"""职位表模型与增删查改。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlmodel import Field, SQLModel, col, select

if TYPE_CHECKING:
    from job.boss.jobs import Job


class JobRow(SQLModel, table=True):
    """投递成功的岗位记录。"""

    __tablename__ = "job"

    # 高匹配分数线
    HIGH_MATCH: ClassVar[int] = 80
    # 分析状态筛选项（第一项为不筛选）
    ANALYSIS_FILTERS: ClassVar[tuple[str, ...]] = (
        "全部分析状态",
        "已分析",
        "未分析",
        f"高匹配（≥{HIGH_MATCH}）",
    )

    uid: str = Field(primary_key=True, description="主键：优先 job_id，否则用 link")
    job_id: str | None = Field(default=None, index=True)
    link: str = Field(default="", index=True)
    title: str = ""
    salary: str = ""
    company: str = ""
    location: str = ""
    experience: str = ""
    education: str = ""
    description: str = ""
    hr_name: str = ""
    hr_title: str = ""
    address: str = ""
    match_score: int | None = Field(
        default=None, index=True, description="匹配度 0–100；未分析为空"
    )
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """转为前端表格字典。"""
        score = self.match_score
        return {
            "uid": self.uid,
            "title": self.title,
            "salary": self.salary,
            "company": self.company,
            "location": self.location,
            "link": self.link,
            "hrName": self.hr_name,
            "hrTitle": self.hr_title,
            "address": self.address,
            "description": self.description,
            "experience": self.experience,
            "education": self.education,
            "matchStatus": "未分析" if score is None else f"{score} 分",
            "matchHigh": score is not None and score >= self.HIGH_MATCH,
        }

    @staticmethod
    def uid_for(job: Job) -> str:
        """根据抓取结果生成稳定主键。"""
        return job.job_id or job.link or f"{job.company}|{job.title}|{job.salary}"

    @classmethod
    def upsert_from(cls, job: Job, score: int | None = None) -> JobRow:
        """按 uid 插入或更新；没给新匹配度 ``score`` 时保留已有的。"""
        from job.models import db_session

        row = cls(
            **job.model_dump(),
            uid=cls.uid_for(job),
            match_score=score,
            scraped_at=datetime.now(UTC),
        )
        with db_session() as session:
            if score is None and (existing := session.get(cls, row.uid)):
                row.match_score = existing.match_score
            merged = session.merge(row)
            session.commit()
            session.refresh(merged)
            return merged

    @classmethod
    def _apply_filters(cls, stmt, search: str, analysis: str):
        """按岗位名 / 公司模糊搜，并按分析状态（``ANALYSIS_FILTERS`` 之一）筛选。"""
        from sqlalchemy import or_

        if q := search.strip():
            like = f"%{q}%"
            stmt = stmt.where(
                or_(col(cls.title).like(like), col(cls.company).like(like))
            )
        _, analyzed, pending, high = cls.ANALYSIS_FILTERS
        score = col(cls.match_score)
        conditions = {
            analyzed: score.is_not(None),
            pending: score.is_(None),
            high: score >= cls.HIGH_MATCH,
        }
        return stmt.where(conditions[analysis]) if analysis in conditions else stmt

    @classmethod
    def count(cls, *, search: str = "", analysis: str = "") -> int:
        """统计岗位数；可按关键字与分析状态筛选。"""
        from sqlalchemy import func

        from job.models import db_session

        with db_session() as session:
            stmt = select(func.count()).select_from(cls)
            return int(session.exec(cls._apply_filters(stmt, search, analysis)).one())

    @classmethod
    def list_dicts(
        cls,
        *,
        search: str = "",
        analysis: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """分页列表（新抓取优先）。"""
        from job.models import db_session

        with db_session() as session:
            stmt = select(cls).order_by(col(cls.scraped_at).desc())
            stmt = cls._apply_filters(stmt, search, analysis)
            rows = session.exec(stmt.offset(offset).limit(limit)).all()
        return [r.to_dict() for r in rows]

    @classmethod
    def get_dict(cls, uid: str) -> dict[str, Any] | None:
        """按主键查询。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, uid)
            return None if row is None else row.to_dict()

    @classmethod
    def count_today(cls) -> int:
        """今天（本地时区）入库的岗位数，即今日投递数。"""
        from sqlalchemy import func

        from job.models import db_session

        midnight = datetime.now().astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        since = midnight.astimezone(UTC)
        stmt = select(func.count()).select_from(cls).where(col(cls.scraped_at) >= since)
        with db_session() as session:
            return int(session.exec(stmt).one())

    @classmethod
    def set_score(cls, uid: str, score: int) -> bool:
        """更新匹配度；岗位不存在返回 False。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, uid)
            if row is None:
                return False
            row.match_score = score
            session.add(row)
            session.commit()
            return True

    @classmethod
    def exists(cls, job: Job) -> bool:
        """这条职位是否已入库。"""
        from job.models import db_session

        with db_session() as session:
            return session.get(cls, cls.uid_for(job)) is not None

    @classmethod
    def delete_by_uid(cls, uid: str) -> bool:
        """删除一条，不存在则 False。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, uid)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    @classmethod
    def delete_many(cls, uids: list[str]) -> int:
        """批量删除，返回实际删除数。"""
        from job.models import db_session

        deleted = 0
        with db_session() as session:
            for uid in uids:
                row = session.get(cls, uid)
                if row is None:
                    continue
                session.delete(row)
                deleted += 1
            session.commit()
        return deleted
