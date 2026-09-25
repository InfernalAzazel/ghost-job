"""BOSS scrape session state."""

from __future__ import annotations

from datetime import datetime

import reflex as rx
from patchright.async_api import Error as PlaywrightError
from sqlalchemy.exc import SQLAlchemyError

from job.boss.filters import City, KeywordFilter, PaceProfile, SearchUrl
from job.boss.jobs import JobScraper
from job.boss.review import JobReviewer
from job.boss.session import BossSession
from job.models import init_db
from job.models.job import JobRow
from job.models.plan import SearchPlanRow
from job.models.setting import LlmSettings

_session = BossSession()
_scraper = JobScraper(_session)

# 抓取结束状态 → 日志文案
_FINISHED = {
    "done": "抓取完成",
    "stopped": "已停止抓取",
    "need_login": "需要登录 BOSS，请在浏览器里登录后重新开始",
}
# 日志最多保留条数
_MAX_LOG = 200


class BossState(rx.State):
    boss_state: str = "—"
    busy: bool = False
    # 运行日志（新的在前）：{time, level, text}，level 为 info / ok / skip / warn
    log: list[dict[str, str]] = rx.field(default_factory=list)
    stored_count: int = 0
    session_count: int = 0
    active_plan_name: str = ""

    def _push_log(self, text: str, level: str = "info") -> None:
        """追加一条运行日志。"""
        now = datetime.now().strftime("%H:%M:%S")
        self.log = [{"time": now, "level": level, "text": text}, *self.log][:_MAX_LOG]

    def _refresh_stored_count(self) -> None:
        self.stored_count = JobRow.count()

    def _refresh_active_plan_name(self) -> None:
        plan = SearchPlanRow.get_active_dict()
        self.active_plan_name = str(plan.get("name") or "")

    @rx.event
    def on_load(self):
        init_db()
        self._refresh_stored_count()
        self._refresh_active_plan_name()
        if not self.log:
            self._push_log(f"数据库已就绪，已入库 {self.stored_count} 条")

    @rx.event
    def clear_log(self):
        self.log = []

    @rx.event
    async def open_boss(self):
        if self.busy:
            return
        self.busy = True
        self.boss_state = "launching"
        self._push_log("正在启动 Chrome…")
        try:
            await _session.open()
            self.boss_state = "ready"
            self._push_log("Chrome 已就绪", "ok")
        except RuntimeError as exc:
            self.boss_state = f"error: {exc}"
            self._push_log(str(exc), "warn")
        finally:
            self.busy = False

    @rx.event
    def stop_search(self):
        _scraper.request_stop()
        self._push_log("正在停止，处理完当前岗位后结束")
        self.boss_state = "stopping"

    @rx.event
    async def close_boss(self):
        await _session.close()
        self.boss_state = "done"
        self.busy = False
        self._push_log("浏览器已关闭")

    @rx.event(background=True)
    async def start_search(self):
        async with self:
            if self.busy:
                return
            plan = SearchPlanRow.get_active_dict()
            query = str(plan.get("query") or "").strip()
            if not query:
                self._push_log("请先在配置中心填写岗位关键词", "warn")
                self.boss_state = "need query"
                return
            url = SearchUrl.build(plan)
            pace = PaceProfile.from_plan(plan)
            keywords = KeywordFilter.from_plan(plan)
            reviewer = JobReviewer.from_plan(plan, LlmSettings.load())
            if reviewer and not reviewer.llm.ready:
                self._push_log(
                    "已开启 AI 复核，请先在「大模型」配置 Key 与模型", "warn"
                )
                self.boss_state = "need api key"
                return
            self.busy = True
            self.boss_state = "navigating"
            self.session_count = 0
            self.active_plan_name = str(plan.get("name") or "")
            city = City.label(str(plan.get("city_code") or ""))
            self._push_log(f"开始抓取「{self.active_plan_name}」：{query} · {city}")
            self._push_log(f"抓取节奏：{pace.describe()}")
            if reviewer:
                self._push_log("AI 岗位意图复核已开启")

        async def on_job(_job) -> None:
            async with self:
                self.session_count += 1
                self._refresh_stored_count()
                self.boss_state = "scraping"

        async def on_log(level: str, text: str) -> None:
            async with self:
                self._push_log(text, level)

        try:
            _url, _jobs, state = await _scraper.search(
                url,
                pace=pace,
                keywords=keywords,
                reviewer=reviewer,
                on_job=on_job,
                on_log=on_log,
            )
            async with self:
                self.boss_state = state
                self._refresh_stored_count()
                self._push_log(
                    f"{_FINISHED.get(state, state)}：本次入库 {self.session_count} 条，"
                    f"累计 {self.stored_count} 条",
                    "warn" if state == "need_login" else "info",
                )
                self.busy = False
        except (RuntimeError, PlaywrightError, SQLAlchemyError) as exc:
            async with self:
                self.boss_state = f"error: {exc}"
                self._push_log(str(exc), "warn")
                self.busy = False
