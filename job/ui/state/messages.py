"""消息页状态：会话列表与聊天记录。"""

from __future__ import annotations

import reflex as rx

from job.models import init_db
from job.models.chat import ChatMessageRow


class MessagesState(rx.State):
    conversations: list[dict] = rx.field(default_factory=list)
    search: str = ""
    # 当前打开的会话（HR 的加密 ID）
    active_id: str = ""
    messages: list[dict] = rx.field(default_factory=list)

    @rx.var
    def active(self) -> dict:
        return next((c for c in self.conversations if c["boss_id"] == self.active_id), {})

    def _load(self) -> None:
        self.conversations = ChatMessageRow.conversations(self.search)
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
    def open_chat(self, boss_id: str) -> None:
        self.active_id = boss_id
        self.messages = ChatMessageRow.list_for_boss(boss_id)
