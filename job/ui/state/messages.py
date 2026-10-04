"""消息页状态：会话列表与聊天记录。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlencode

import reflex as rx
from patchright.async_api import Error as PlaywrightError
from sqlalchemy.exc import SQLAlchemyError

from job.boss.filters import KeywordFilter
from job.models import init_db
from job.models.chat import ChatMessageRow, ChatStatusRow
from job.models.search import SearchConfigRow
from job.ui.state.boss import BossState, _syncer
from job.ui.state.export import BROWSER_DOWNLOAD, save_dialog_script


def _export_name() -> str:
    """导出文件名，带当前时间。"""
    return datetime.now().astimezone().strftime("聊天记录-%Y%m%d-%H%M.json")


class MessagesState(rx.State):
    # 会话列表一次渲染几千项时切换会话要卡一秒多，先显示一批，滚到底部再加载下一批
    PAGE: ClassVar[int] = 100

    # 符合搜索和筛选的全部会话；页面只显示前 limit 个（conversations）
    _all: rx.Field[list[dict]] = rx.field(default_factory=list)
    limit: int = PAGE
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
    # 是否在同步 BOSS 上的历史会话，以及进度文案
    syncing: bool = False
    sync_text: str = ""

    @rx.var
    def active(self) -> dict:
        return next((c for c in self._all if c["boss_id"] == self.active_id), {})

    @rx.var
    def selected_count(self) -> int:
        return len(self.selected)

    @rx.var
    def all_selected(self) -> bool:
        selected = set(self.selected)
        return bool(self._all) and all(c["boss_id"] in selected for c in self._all)

    @rx.var
    def active_status(self) -> str:
        """当前会话的沟通状态文案，没有状态时为「无」。"""
        return self.active.get("status_label") or "无"

    def _load(self, *, reset: bool = False) -> None:
        """重新读会话列表；``reset`` 时（换了搜索或筛选）从第一批开始显示。"""
        self._all = ChatMessageRow.conversations(self.search, self.status_filter)
        if reset:
            self.limit = self.PAGE
        self.conversations = self._all[: self.limit]
        ids = {c["boss_id"] for c in self._all}
        if self.active_id not in ids:
            self.active_id = self._all[0]["boss_id"] if self._all else ""
        self.messages = (
            ChatMessageRow.list_for_boss(self.active_id) if self.active_id else []
        )
        self.selected = [i for i in self.selected if i in ids]

    @rx.event
    def load_more(self, near_bottom: bool) -> None:
        """会话列表滚动停下时，离底部不远就再显示一批。"""
        if near_bottom and self.limit < len(self._all):
            self.limit += self.PAGE
            self.conversations = self._all[: self.limit]

    @rx.event
    def on_load(self) -> None:
        init_db()
        self._load(reset=True)

    @rx.event
    def refresh(self) -> None:
        self._load()

    @rx.event(background=True)
    async def sync(self):
        """把 BOSS 上聊过、库里还没有的会话同步进来；新岗位只按关键词判断。"""
        async with self:
            if self.syncing:
                return
            boss = await self.get_state(BossState)
            if boss.busy or boss.reply_busy:
                task = "自动投递" if boss.busy else "自动回复"
                return rx.toast.warning(f"{task}正在运行，请先在工作台停止{task}再同步")
            self.syncing = True
            self.sync_text = "正在打开聊天页…"
        keywords = KeywordFilter.from_config(SearchConfigRow.load())

        async def on_progress(done: int, total: int, label: str) -> None:
            async with self:
                self.sync_text = f"正在同步 {done}/{total} · {label}"
                # 每同步一批刷新一次列表，能边同步边看
                if done % 20 == 0:
                    self._load()

        try:
            result = await _syncer.run(keywords, on_progress)
        except (RuntimeError, PlaywrightError, SQLAlchemyError) as exc:
            async with self:
                self.syncing, self.sync_text = False, ""
                self._load()
            return rx.toast.error(str(exc))
        async with self:
            self.syncing, self.sync_text = False, ""
            self._load()
        if result.state == "need_login":
            return rx.toast.warning("需要登录 BOSS，请在浏览器里登录后再同步")
        head = "已停止同步" if result.state == "stopped" else "同步完成"
        failed = f"，{result.failed} 个读取失败" if result.failed else ""
        updated = f"，{result.updated} 个会话有新消息" if result.updated else ""
        empty = f"，{result.empty} 个没有可记录的消息" if result.empty else ""
        return rx.toast.success(
            f"{head}：新增 {result.chats} 个会话、{result.jobs} 个岗位"
            f"{updated}{failed}{empty}"
        )

    @rx.event
    def stop_sync(self) -> None:
        _syncer.request_stop()
        self.sync_text = "正在停止，处理完当前会话后结束…"

    @rx.event
    def set_search(self, value: str) -> None:
        self.search = value
        self._load(reset=True)

    @rx.event
    def set_status_filter(self, value: str) -> None:
        self.status_filter = value
        self._load(reset=True)

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
        self.selected = [] if self.all_selected else [c["boss_id"] for c in self._all]

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
