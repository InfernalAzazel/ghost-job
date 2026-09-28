"""聊天消息表：与 HR 的消息按岗位关联，自动回复据此判断哪些是新消息。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, ClassVar

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


class ChatRejectionRow(SQLModel, table=True):
    """已结束的会话：HR 说了不合适，或我方已婉拒；HR 再发新消息时由 AI 重新判断。"""

    __tablename__ = "chat_rejection"  # pyright: ignore[reportAssignmentType]

    LABELS: ClassVar[dict[str, str]] = {"hr": "HR 已拒绝", "me": "已婉拒"}

    boss_id: str = Field(primary_key=True, description="HR 的加密 ID")
    by: str = Field(description="谁拒绝的：hr / me")
    text: str = Field(default="", description="拒绝的那句话")
    created_at: datetime = Field(default_factory=_now, description="标记时间（UTC）")

    @classmethod
    def mark(cls, boss_id: str, *, by: str, text: str) -> None:
        from job.models import db_session

        with db_session() as session:
            session.merge(cls(boss_id=boss_id, by=by, text=text))
            session.commit()

    @classmethod
    def clear(cls, boss_id: str) -> None:
        from job.models import db_session

        with db_session() as session:
            if row := session.get(cls, boss_id):
                session.delete(row)
                session.commit()

    @classmethod
    def labels(cls) -> dict[str, str]:
        """HR → 标记文案（「HR 已拒绝」/「已婉拒」）。"""
        from job.models import db_session

        with db_session() as session:
            return {r.boss_id: cls.LABELS.get(r.by, "") for r in session.exec(select(cls)).all()}


class ChatMessageRow(SQLModel, table=True):
    """与 HR 的一条聊天消息。"""

    __tablename__ = "chat_message"  # pyright: ignore[reportAssignmentType]

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
            rows = {
                row.mid: row
                for row in session.exec(
                    select(cls).where(col(cls.mid).in_([m.mid for m in messages]))
                ).all()
            }
            # 之前没读到文字的卡片消息（如 HR 索要简历），这次读到了就补上
            for m in messages:
                if (row := rows.get(m.mid)) is not None and not row.text and m.text:
                    row.text = m.text
                    session.add(row)
            fresh = [m for m in messages if m.mid not in rows]
            # 自动回复刚发出就入库，那时页面给的是临时 ID，之后换成正式 ID；按文字认出来换成正式 ID
            stale = {
                row.text: row
                for row in session.exec(
                    select(cls).where(
                        cls.boss_id == boss_id,
                        col(cls.auto).is_(True),
                        col(cls.mid).not_in([m.mid for m in messages]),
                    )
                ).all()
            } if any(not m.from_hr for m in fresh) else {}
            for m in fresh:
                old = None if m.from_hr else stale.pop(m.text, None)
                if old is not None:
                    session.delete(old)
                    session.flush()
                session.add(
                    cls(
                        mid=m.mid,
                        job_uid=old.job_uid if old else job_uid,
                        boss_id=boss_id,
                        hr_name=hr_name,
                        from_hr=m.from_hr,
                        text=m.text,
                        auto=old.auto if old else auto and not m.from_hr,
                        created_at=old.created_at if old else _now(),
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
        rejected = ChatRejectionRow.labels()
        today = datetime.now().astimezone().date()
        items = []
        for boss_id, last in sorted(latest.items(), key=lambda kv: kv[1].created_at, reverse=True):
            job = jobs.get(job_uids.get(boss_id, ""))
            when = last.local_time
            item = {
                "boss_id": boss_id,
                "job_uid": job.uid if job else "",
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
                "rejected": rejected.get(boss_id, ""),
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
