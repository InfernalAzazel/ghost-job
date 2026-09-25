"""职位表模型与增删查改。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, SQLModel, col, select

if TYPE_CHECKING:
    from job.boss.jobs import Job


class JobRow(SQLModel, table=True):
    """抓取入库的岗位记录。"""

    __tablename__ = "job"

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
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
    )

    def to_dict(self) -> dict[str, str]:
        """转为前端表格字典（匹配度/沟通等为占位）。"""
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
            "matchStatus": "未分析",
            "chatStatus": "未回复",
            "latestMessage": "-",
        }

    @staticmethod
    def uid_for(job: Job) -> str:
        """根据抓取结果生成稳定主键。"""
        return job.job_id or job.link or f"{job.company}|{job.title}|{job.salary}"

    @classmethod
    def upsert_from(cls, job: Job) -> JobRow:
        """按 uid 插入或更新。"""
        from job.models import db_session

        row = cls(
            **job.model_dump(),
            uid=cls.uid_for(job),
            scraped_at=datetime.now(UTC),
        )
        with db_session() as session:
            merged = session.merge(row)
            session.commit()
            session.refresh(merged)
            return merged

    @classmethod
    def _apply_search(cls, stmt, search: str):
        from sqlalchemy import or_

        q = search.strip()
        if not q:
            return stmt
        like = f"%{q}%"
        return stmt.where(or_(col(cls.title).like(like), col(cls.company).like(like)))

    @classmethod
    def count(cls, *, search: str = "") -> int:
        """统计岗位数；可按岗位名/公司模糊搜。"""
        from sqlalchemy import func

        from job.models import db_session

        with db_session() as session:
            stmt = cls._apply_search(select(func.count()).select_from(cls), search)
            return int(session.exec(stmt).one())

    @classmethod
    def list_dicts(
        cls,
        *,
        search: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, str]]:
        """分页列表（新抓取优先）。"""
        from job.models import db_session

        with db_session() as session:
            stmt = cls._apply_search(
                select(cls).order_by(col(cls.scraped_at).desc()), search
            )
            rows = session.exec(stmt.offset(offset).limit(limit)).all()
        return [r.to_dict() for r in rows]

    @classmethod
    def get_dict(cls, uid: str) -> dict[str, str] | None:
        """按主键查询。"""
        from job.models import db_session

        with db_session() as session:
            row = session.get(cls, uid)
            return None if row is None else row.to_dict()

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
