"""岗位管理状态：列表、筛选、勾选、删除与 AI 匹配度分析。"""

from __future__ import annotations

import asyncio
import math

import reflex as rx
from pydantic_ai.exceptions import AgentRunError

from job.boss.jobs import Job
from job.boss.review import JobReviewer
from job.models import init_db
from job.models.job import JobRow
from job.models.search import SearchConfigRow
from job.models.setting import LlmSettings

# AI 分析并发数
_ANALYZE_CONCURRENCY = 4


class JobsState(rx.State):
    rows: list[dict] = rx.field(default_factory=list)
    total: int = 0
    search: str = ""
    analysis: str = JobRow.ANALYSIS_FILTERS[0]
    analysis_options: list[str] = rx.field(
        default_factory=lambda: list(JobRow.ANALYSIS_FILTERS)
    )
    suitable: str = JobRow.SUITABLE_FILTERS[1]
    suitable_options: list[str] = rx.field(
        default_factory=lambda: list(JobRow.SUITABLE_FILTERS)
    )
    page: int = 1
    page_size: int = 15
    selected: list[str] = rx.field(default_factory=list)
    detail_open: bool = False
    detail: dict = rx.field(default_factory=dict)
    # 待确认删除的岗位：{uid, title}；空表示确认框关闭
    pending_delete: dict[str, str] = rx.field(default_factory=dict)
    batch_delete_open: bool = False
    analyzing: bool = False
    # AI 分析进度：已完成数
    analyzed: int = 0

    @rx.var
    def selected_count(self) -> int:
        return len(self.selected)

    @rx.var
    def all_selected(self) -> bool:
        visible = [str(r.get("uid") or "") for r in self.rows]
        return bool(visible) and all(u in self.selected for u in visible)

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
        self.total = JobRow.count(
            search=self.search, analysis=self.analysis, suitable=self.suitable
        )
        max_page = max(1, math.ceil(self.total / self.page_size)) if self.page_size else 1
        self.page = min(self.page, max_page)
        offset = (self.page - 1) * self.page_size
        self.rows = JobRow.list_dicts(
            search=self.search,
            analysis=self.analysis,
            suitable=self.suitable,
            limit=self.page_size,
            offset=offset,
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
    def set_search_and_reload(self, value: str):
        self.search = value
        self.page = 1
        self._reload()

    @rx.event
    def set_analysis(self, value: str):
        """切换分析状态筛选，回到第一页。"""
        self.analysis = value
        self.page = 1
        self._reload()

    @rx.event
    def set_suitable(self, value: str):
        """切换是否合适筛选，回到第一页。"""
        self.suitable = value
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
    def clear_selection(self):
        self.selected = []

    @rx.event(background=True)
    async def analyze_selected(self):
        """按求职配置里的 AI 筛选要求与简历，重新判断选中岗位是否合适并写回原因与匹配度。"""
        async with self:
            if self.analyzing or not self.selected:
                return
            llm = LlmSettings.load()
            if not llm.ready:
                return rx.toast.warning("请先在配置中心开通「AI 服务」")
            reviewer = JobReviewer.from_config(SearchConfigRow.load(), llm)
            if reviewer is None:
                return rx.toast.warning(
                    "请先在配置中心开启「AI 岗位筛选」或「简历技术匹配」"
                )
            uids = list(self.selected)
            self.analyzing = True
            self.analyzed = 0

        limit = asyncio.Semaphore(_ANALYZE_CONCURRENCY)

        async def analyze(uid: str) -> bool:
            row = JobRow.get_dict(uid)
            if row is None:
                return False
            job = Job(
                title=row["title"],
                company=row["company"],
                salary=row["salary"],
                description=row["description"],
            )
            try:
                async with limit:
                    verdict = await reviewer.check(job)
            except AgentRunError:
                ok = False
            else:
                ok = JobRow.set_verdict(
                    uid,
                    suitable=verdict.match,
                    reason=verdict.reason,
                    score=verdict.score,
                )
            async with self:
                self.analyzed += 1
            return ok

        results = await asyncio.gather(*(analyze(uid) for uid in uids))
        done = sum(results)
        async with self:
            self.analyzing = False
            self.selected = []
            self._reload()
        if done == len(uids):
            return rx.toast.success(f"已完成 {done} 个岗位的 AI 分析")
        return rx.toast.warning(f"分析完成 {done} 个，失败 {len(uids) - done} 个")

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
    def ask_delete(self, uid: str, title: str):
        """点删除：先弹确认框。"""
        self.pending_delete = {"uid": uid, "title": title}

    @rx.event
    def set_delete_open(self, is_open: bool):
        if not is_open:
            self.pending_delete = {}

    @rx.event
    def confirm_delete(self):
        """确认框里点「删除」：真正删除并关闭确认框。"""
        uid = self.pending_delete.get("uid", "")
        self.pending_delete = {}
        if not uid:
            return
        JobRow.delete_by_uid(uid)
        self.selected = [u for u in self.selected if u != uid]
        if self.detail.get("uid") == uid:
            self.detail_open = False
        self._reload()

    @rx.event
    def set_batch_delete_open(self, is_open: bool):
        self.batch_delete_open = is_open and bool(self.selected)

    @rx.event
    def delete_selected(self):
        """批量删除确认框里点「删除」：删除全部选中岗位。"""
        self.batch_delete_open = False
        if not self.selected:
            return
        count = JobRow.delete_many(list(self.selected))
        if self.detail.get("uid") in self.selected:
            self.detail_open = False
        self.selected = []
        self._reload()
        return rx.toast.success(f"已删除 {count} 个岗位")
