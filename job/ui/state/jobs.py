"""Job list management state (岗位管理)."""

from __future__ import annotations

import math

import reflex as rx

from job.models import init_db
from job.models.job import JobRow


class JobsState(rx.State):
    rows: list[dict] = rx.field(default_factory=list)
    total: int = 0
    search: str = ""
    page: int = 1
    page_size: int = 15
    selected: list[str] = rx.field(default_factory=list)
    detail_open: bool = False
    detail: dict = rx.field(default_factory=dict)

    @rx.var
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 1
        return max(1, math.ceil(self.total / self.page_size))

    @rx.var
    def page_label(self) -> str:
        return f"{self.page_size} / page"

    @rx.var
    def has_prev(self) -> bool:
        return self.page > 1

    @rx.var
    def has_next(self) -> bool:
        return self.page < self.total_pages

    def _reload(self) -> None:
        self.total = JobRow.count(search=self.search)
        max_page = max(1, math.ceil(self.total / self.page_size)) if self.page_size else 1
        if self.page > max_page:
            self.page = max_page
        offset = (self.page - 1) * self.page_size
        self.rows = JobRow.list_dicts(
            search=self.search, limit=self.page_size, offset=offset
        )
        # Drop selections that are no longer on this page
        visible = {str(r.get("uid") or "") for r in self.rows}
        self.selected = [u for u in self.selected if u in visible]

    @rx.event
    def on_load(self):
        init_db()
        self.page = 1
        self.selected = []
        self._reload()

    @rx.event
    def set_search(self, value: str):
        self.search = value

    @rx.event
    def apply_search(self):
        self.page = 1
        self._reload()

    @rx.event
    def set_search_and_reload(self, value: str):
        self.search = value
        self.page = 1
        self._reload()

    @rx.event
    def prev_page(self):
        if self.page > 1:
            self.page -= 1
            self._reload()

    @rx.event
    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1
            self._reload()

    @rx.event
    def set_page_size(self, label: str):
        # labels like "15 / page"
        try:
            size = int(str(label).split("/")[0].strip())
        except ValueError:
            size = 15
        self.page_size = size
        self.page = 1
        self._reload()

    @rx.event
    def toggle_select(self, uid: str):
        if uid in self.selected:
            self.selected = [u for u in self.selected if u != uid]
        else:
            self.selected = [*self.selected, uid]

    @rx.event
    def toggle_select_all(self):
        visible = [str(r.get("uid") or "") for r in self.rows if r.get("uid")]
        if visible and all(u in self.selected for u in visible):
            self.selected = [u for u in self.selected if u not in visible]
        else:
            merged = set(self.selected) | set(visible)
            self.selected = list(merged)

    @rx.event
    def open_detail(self, uid: str):
        job = JobRow.get_dict(uid)
        if job is None:
            return
        self.detail = job
        self.detail_open = True

    @rx.event
    def close_detail(self):
        self.detail_open = False

    @rx.event
    def set_detail_open(self, is_open: bool):
        self.detail_open = is_open

    @rx.event
    def delete_one(self, uid: str):
        JobRow.delete_by_uid(uid)
        self.selected = [u for u in self.selected if u != uid]
        if self.detail.get("uid") == uid:
            self.detail_open = False
        self._reload()

    @rx.event
    def delete_selected(self):
        if not self.selected:
            return
        JobRow.delete_by_uids(list(self.selected))
        self.selected = []
        self._reload()

    @rx.event
    def coming_soon(self):
        return rx.toast.info("功能开发中，敬请期待")
