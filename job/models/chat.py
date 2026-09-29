"""聊天消息表：与 HR 的消息按岗位关联，自动回复据此判断哪些是新消息。"""

from __future__ import annotations

import json
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


class ChatStatusRow(SQLModel, table=True):
    """会话的沟通状态：面试进展或会话已结束（HR 拒绝 / AI 已婉拒），每个 HR 一个。

    AI 回复时按判断自动更新；已面试、面试通过、面试不通过只能手动标记，AI 不会改动。
    """

    __tablename__ = "chat_status"  # pyright: ignore[reportAssignmentType]

    LABELS: ClassVar[dict[str, str]] = {
        "invited": "有面试",
        "done": "已面试",
        "passed": "面试通过",
        "failed": "面试不通过",
        "hr_rejected": "HR 已拒绝",
        "declined": "AI 已婉拒",
    }
    INTERVIEWS: ClassVar[frozenset[str]] = frozenset(
        {"invited", "done", "passed", "failed"}
    )
    # 会话已结束：HR 没有新消息时不再回复
    ENDED: ClassVar[frozenset[str]] = frozenset({"hr_rejected", "declined", "failed"})
    # 只能手动标记的面试进展
    MANUAL: ClassVar[frozenset[str]] = frozenset({"done", "passed", "failed"})
    # 会话列表筛选；「无状态」是未标记任何状态，「所有面试」是任意面试状态
    FILTERS: ClassVar[tuple[str, ...]] = (
        "全部",
        "无状态",
        "所有面试",
        *LABELS.values(),
    )
    # 手动标记的选项；「无」是清除
    CHOICES: ClassVar[tuple[str, ...]] = ("无", *LABELS.values())

    boss_id: str = Field(primary_key=True, description="HR 的加密 ID")
    status: str = Field(description="状态值，见 LABELS")
    source: str = Field(default="manual", description="auto AI 标记 / manual 手动标记")
    text: str = Field(default="", description="触发标记的那句话（拒绝或婉拒时）")
    updated_at: datetime = Field(
        default_factory=_now, description="最后更新时间（UTC）"
    )

    @classmethod
    def mark(
        cls, boss_id: str, status: str, *, source: str = "manual", text: str = ""
    ) -> None:
        from job.models import db_session

        with db_session() as session:
            session.merge(cls(boss_id=boss_id, status=status, source=source, text=text))
            session.commit()

    @classmethod
    def clear(cls, boss_id: str) -> None:
        from job.models import db_session

        with db_session() as session:
            if row := session.get(cls, boss_id):
                session.delete(row)
                session.commit()

    @classmethod
    def statuses(cls) -> dict[str, str]:
        """HR → 状态值。"""
        from job.models import db_session

        with db_session() as session:
            return {r.boss_id: r.status for r in session.exec(select(cls)).all()}

    @classmethod
    def ended(cls, boss_id: str) -> bool:
        return cls.statuses().get(boss_id, "") in cls.ENDED

    @classmethod
    def follow_ai(
        cls, boss_id: str, *, outcome: str, interview: bool, text: str
    ) -> str | None:
        """按 AI 对会话的判断更新状态，返回变化后的状态值（清除为空串），没变返回 None。

        HR 拒绝 / AI 已婉拒直接标记；继续沟通时识别到面试邀请标「有面试」，
        否则清掉之前的拒绝或婉拒；手动标记的面试进展不动。
        """
        before = cls.statuses().get(boss_id, "")
        if before in cls.MANUAL:
            return None
        if outcome in ("hr_rejected", "declined"):
            after = outcome
        elif interview:
            after = "invited"
        else:
            after = "" if before in cls.ENDED else before
        if after == before:
            return None
        if after:
            cls.mark(boss_id, after, source="auto", text=text)
        else:
            cls.clear(boss_id)
        return after

    @classmethod
    def matches(cls, status: str, wanted: str) -> bool:
        """状态值 ``status`` 是否符合筛选文案 ``wanted``（空串或「全部」不筛选）。"""
        if wanted in ("", "全部"):
            return True
        if wanted == "无状态":
            return status == ""
        if wanted == "所有面试":
            return status in cls.INTERVIEWS
        return cls.LABELS.get(status) == wanted


class ChatMessageRow(SQLModel, table=True):
    """与 HR 的一条聊天消息。"""

    __tablename__ = "chat_message"  # pyright: ignore[reportAssignmentType]

    mid: str = Field(primary_key=True, description="BOSS 消息 ID")
    job_uid: str = Field(
        default="", index=True, description="关联岗位主键（job.uid），无岗位时为空"
    )
    boss_id: str = Field(default="", index=True, description="HR 的加密 ID")
    hr_name: str = Field(default="", description="HR 称呼")
    from_hr: bool = Field(default=True, description="是否 HR 发来的")
    text: str = ""
    auto: bool = Field(default=False, description="是否由自动回复发出")
    created_at: datetime = Field(
        default_factory=_now, index=True, description="入库时间（UTC）"
    )

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
            stale = (
                {
                    row.text: row
                    for row in session.exec(
                        select(cls).where(
                            cls.boss_id == boss_id,
                            col(cls.auto).is_(True),
                            col(cls.mid).not_in([m.mid for m in messages]),
                        )
                    ).all()
                }
                if any(not m.from_hr for m in fresh)
                else {}
            )
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

    @classmethod
    def boss_ids(cls) -> set[str]:
        """库里有聊天记录的 HR。"""
        from job.models import db_session

        with db_session() as session:
            return set(session.exec(select(cls.boss_id).distinct()).all())

    @property
    def local_time(self) -> datetime:
        return self.created_at.replace(
            tzinfo=self.created_at.tzinfo or UTC
        ).astimezone()

    @classmethod
    def conversations(cls, search: str = "", status: str = "") -> list[dict[str, Any]]:
        """会话列表：每个 HR 一条，带关联岗位、最后一条消息与沟通状态，最近的在前。

        ``search`` 模糊匹配 HR、公司或岗位名；``status`` 按沟通状态筛选，
        取 ``ChatStatusRow.FILTERS`` 里的文案。
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
        from job.models.company import CompanyRow

        statuses = ChatStatusRow.statuses()
        risks = CompanyRow.risks(j.brand_id for j in jobs.values())
        today = datetime.now().astimezone().date()
        items = []
        for boss_id, last in sorted(
            latest.items(), key=lambda kv: kv[1].created_at, reverse=True
        ):
            current = statuses.get(boss_id, "")
            if not ChatStatusRow.matches(current, status):
                continue
            job = jobs.get(job_uids.get(boss_id, ""))
            risk = risks.get(job.brand_id, "") if job else ""
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
                "last_time": when.strftime(
                    "%H:%M" if when.date() == today else "%m-%d"
                ),
                "status": current,
                "status_label": ChatStatusRow.LABELS.get(current, ""),
                "risk": risk,
                "risk_label": CompanyRow.RISK_LABELS.get(risk, ""),
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

    # 导出时会话里保留的字段（去掉列表展示用的最后一条消息）
    EXPORT_FIELDS: ClassVar[tuple[str, ...]] = (
        "boss_id",
        "hr_name",
        "hr_title",
        "company",
        "title",
        "salary",
        "location",
        "link",
        "job_uid",
        "status",
        "status_label",
    )

    @classmethod
    def to_json(cls, boss_ids: list[str] | None = None) -> tuple[str, int]:
        """导出 JSON 文本与会话数：``boss_ids`` 为空导出全部，否则只导出这些会话。

        每个会话带岗位、沟通状态与完整聊天记录（从早到晚），最近的会话在前。
        """
        from job.models import db_session

        chats = [
            {k: c[k] for k in cls.EXPORT_FIELDS}
            for c in cls.conversations()
            if not boss_ids or c["boss_id"] in boss_ids
        ]
        stmt = select(cls).where(col(cls.boss_id).in_([c["boss_id"] for c in chats]))
        with db_session() as session:
            rows = session.exec(stmt.order_by(col(cls.created_at), col(cls.mid))).all()
        messages: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            messages.setdefault(r.boss_id, []).append(
                {
                    "mid": r.mid,
                    "sender": "HR" if r.from_hr else "我",
                    "from_hr": r.from_hr,
                    "text": r.text,
                    "auto": r.auto,
                    "time": r.local_time.isoformat(timespec="seconds"),
                }
            )
        for chat in chats:
            chat["messages"] = messages.get(chat["boss_id"], [])
        return json.dumps(chats, ensure_ascii=False, indent=2), len(chats)
