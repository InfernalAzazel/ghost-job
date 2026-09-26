"""聊天消息表：与 HR 的消息按岗位关联，自动回复据此判断哪些是新消息。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlmodel import Field, SQLModel, col, select


def _now() -> datetime:
    return datetime.now(UTC)


class ChatMessage(BaseModel):
    """聊天页里的一条消息。"""

    # BOSS 消息 ID
    mid: str
    # 是否 HR 发来的（否则是我发的）
    from_hr: bool
    text: str = ""


class ChatMessageRow(SQLModel, table=True):
    """与 HR 的一条聊天消息。"""

    __tablename__ = "chat_message"

    mid: str = Field(primary_key=True, description="BOSS 消息 ID")
    job_uid: str = Field(default="", index=True, description="关联岗位主键（job.uid），无岗位时为空")
    boss_id: str = Field(default="", index=True, description="HR 的加密 ID")
    hr_name: str = Field(default="", description="HR 称呼")
    from_hr: bool = Field(default=True, description="是否 HR 发来的")
    text: str = ""
    auto: bool = Field(default=False, description="是否由自动回复发出")
    created_at: datetime = Field(default_factory=_now, index=True, description="入库时间（UTC）")

    @classmethod
    def record_new(
        cls,
        messages: Iterable[ChatMessage],
        *,
        job_uid: str,
        boss_id: str,
        hr_name: str,
        auto: bool = False,
    ) -> list[ChatMessage]:
        """把库里还没有的消息入库，返回这些新消息（保持原顺序）。"""
        from job.models import db_session

        messages = [m for m in messages if m.mid]
        with db_session() as session:
            known = set(
                session.exec(
                    select(cls.mid).where(col(cls.mid).in_([m.mid for m in messages]))
                ).all()
            )
            fresh = [m for m in messages if m.mid not in known]
            for m in fresh:
                session.add(
                    cls(
                        mid=m.mid,
                        job_uid=job_uid,
                        boss_id=boss_id,
                        hr_name=hr_name,
                        from_hr=m.from_hr,
                        text=m.text,
                        auto=auto and not m.from_hr,
                    )
                )
            session.commit()
        return fresh

    @property
    def local_time(self) -> datetime:
        return self.created_at.replace(tzinfo=self.created_at.tzinfo or UTC).astimezone()

    @classmethod
    def conversations(cls, search: str = "") -> list[dict[str, Any]]:
        """会话列表：每个 HR 一条，带关联岗位与最后一条消息，最近的在前。

        ``search`` 模糊匹配 HR、公司或岗位名。
        """
        from job.models import db_session
        from job.models.job import JobRow

        stmt = select(cls).order_by(col(cls.created_at), col(cls.mid))
        with db_session() as session:
            rows = session.exec(stmt).all()
            latest: dict[str, ChatMessageRow] = {}
            job_uids: dict[str, str] = {}
            for row in rows:
                latest[row.boss_id] = row
                if row.job_uid:
                    job_uids[row.boss_id] = row.job_uid
            jobs = {
                j.uid: j
                for j in session.exec(
                    select(JobRow).where(col(JobRow.uid).in_(set(job_uids.values())))
                ).all()
            }
        today = datetime.now().astimezone().date()
        items = []
        for boss_id, last in sorted(latest.items(), key=lambda kv: kv[1].created_at, reverse=True):
            job = jobs.get(job_uids.get(boss_id, ""))
            when = last.local_time
            item = {
                "boss_id": boss_id,
                "hr_name": last.hr_name,
                "hr_title": job.hr_title if job else "",
                "company": job.company if job else "",
                "title": job.title if job else "",
                "salary": job.salary if job else "",
                "location": job.location if job else "",
                "link": job.link if job else "",
                "last_text": last.text,
                "last_from_hr": last.from_hr,
                "last_time": when.strftime("%H:%M" if when.date() == today else "%m-%d"),
            }
            q = search.strip()
            if q and not any(q in item[k] for k in ("hr_name", "company", "title")):
                continue
            items.append(item)
        return items

    @classmethod
    def list_for_boss(cls, boss_id: str) -> list[dict[str, Any]]:
        """与某个 HR 的聊天记录（从早到晚）。"""
        from job.models import db_session

        stmt = (
            select(cls)
            .where(col(cls.boss_id) == boss_id)
            .order_by(col(cls.created_at), col(cls.mid))
        )
        with db_session() as session:
            rows = session.exec(stmt).all()
        return [
            {
                "mid": r.mid,
                "from_hr": r.from_hr,
                "text": r.text,
                "auto": r.auto,
                "time": r.local_time.strftime("%m-%d %H:%M"),
            }
            for r in rows
        ]
