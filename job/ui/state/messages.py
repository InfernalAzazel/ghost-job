"""消息页状态：会话列表与聊天记录。"""

from __future__ import annotations

from urllib.parse import urlencode

import reflex as rx

from job.models import init_db
from job.models.chat import ChatMessageRow, ChatStatusRow


class MessagesState(rx.State):
    conversations: rx.Field[list[dict]] = rx.field(default_factory=list)
    search: str = ""
    # 会话列表按沟通状态筛选，取 ChatStatusRow.FILTERS 里的文案
    status_filter: str = "全部"
    status_filters: rx.Field[list[str]] = rx.field(
        default_factory=lambda: list(ChatStatusRow.FILTERS)
    )
    status_choices: rx.Field[list[str]] = rx.field(
        default_factory=lambda: list(ChatStatusRow.CHOICES)
    )
    # 当前打开的会话（HR 的加密 ID）
    active_id: str = ""
    messages: rx.Field[list[dict]] = rx.field(default_factory=list)

    @rx.var
    def active(self) -> dict:
        return next((c for c in self.conversations if c["boss_id"] == self.active_id), {})

    @rx.var
    def active_status(self) -> str:
        """当前会话的沟通状态文案，没有状态时为「无」。"""
        return self.active.get("status_label") or "无"

    def _load(self) -> None:
        self.conversations = ChatMessageRow.conversations(self.search, self.status_filter)
        ids = [c["boss_id"] for c in self.conversations]
        if self.active_id not in ids:
            self.active_id = ids[0] if ids else ""
        self.messages = ChatMessageRow.list_for_boss(self.active_id) if self.active_id else []

    @rx.event
    def on_load(self) -> None:
        init_db()
        self._load()

    @rx.event
    def refresh(self) -> None:
        self._load()

    @rx.event
    def set_search(self, value: str) -> None:
        self.search = value
        self._load()

    @rx.event
    def set_status_filter(self, value: str) -> None:
        self.status_filter = value
        self._load()

    @rx.event
    def set_status(self, label: str) -> None:
        """手动标记当前会话的沟通状态；「无」是清除。"""
        if not self.active_id:
            return
        status = next((k for k, v in ChatStatusRow.LABELS.items() if v == label), "")
        if status:
            ChatStatusRow.mark(self.active_id, status)
        else:
            ChatStatusRow.clear(self.active_id)
        self._load()

    @rx.event
    def open_chat(self, boss_id: str) -> None:
        self.active_id = boss_id
        self.messages = ChatMessageRow.list_for_boss(boss_id)

    @rx.event
    def open_job(self):
        """跳到岗位管理，只显示当前会话沟通的岗位。"""
        if uid := self.active.get("job_uid"):
            return rx.redirect(f"/jobs?{urlencode({'job': uid})}")
