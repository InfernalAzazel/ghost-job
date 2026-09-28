"""消息页状态：会话列表与聊天记录。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import reflex as rx

from job.models import init_db
from job.models.chat import ChatMessageRow, ChatStatusRow
from job.ui.state.export import BROWSER_DOWNLOAD, save_dialog_script


def _export_name() -> str:
    """导出文件名，带当前时间。"""
    return datetime.now().astimezone().strftime("聊天记录-%Y%m%d-%H%M.json")


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
    # 勾选的会话（HR 的加密 ID）
    selected: rx.Field[list[str]] = rx.field(default_factory=list)
    # 点导出时勾选的会话；空表示导出全部
    _export_ids: rx.Field[list[str]] = rx.field(default_factory=list)

    @rx.var
    def active(self) -> dict:
        return next((c for c in self.conversations if c["boss_id"] == self.active_id), {})

    @rx.var
    def selected_count(self) -> int:
        return len(self.selected)

    @rx.var
    def all_selected(self) -> bool:
        ids = [c["boss_id"] for c in self.conversations]
        return bool(ids) and all(i in self.selected for i in ids)

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
        self.selected = [i for i in self.selected if i in ids]

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
    def toggle_select(self, boss_id: str) -> None:
        if boss_id in self.selected:
            self.selected = [i for i in self.selected if i != boss_id]
        else:
            self.selected = [*self.selected, boss_id]

    @rx.event
    def toggle_select_all(self) -> None:
        self.selected = [] if self.all_selected else [c["boss_id"] for c in self.conversations]

    @rx.event
    def clear_selection(self) -> None:
        self.selected = []

    @rx.event
    def export_json(self):
        """导出 JSON：有勾选导出选中的会话，否则导出全部；桌面端弹系统保存框选位置。"""
        self._export_ids = list(self.selected)
        script = save_dialog_script(_export_name(), "JSON", "json")
        return rx.call_script(script, callback=MessagesState.save_json)

    @rx.event
    def save_json(self, path: str | None):
        """把 JSON 写到保存框选中的路径；取消时 ``path`` 为空。"""
        if not path:
            return
        text, count = ChatMessageRow.to_json(self._export_ids or None)
        if path == BROWSER_DOWNLOAD:
            return rx.download(data=text, filename=_export_name())
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            return rx.toast.error(f"导出失败：{exc.strerror or exc}")
        return rx.toast.success(f"已导出 {count} 个会话到 {path}")

    @rx.event
    def open_chat(self, boss_id: str) -> None:
        self.active_id = boss_id
        self.messages = ChatMessageRow.list_for_boss(boss_id)

    @rx.event
    def open_job(self):
        """跳到岗位管理，只显示当前会话沟通的岗位。"""
        if uid := self.active.get("job_uid"):
            return rx.redirect(f"/jobs?{urlencode({'job': uid})}")
