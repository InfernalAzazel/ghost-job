"""BOSS scrape session state."""

from __future__ import annotations

import reflex as rx
from patchright.async_api import Error as PlaywrightError
from sqlalchemy.exc import SQLAlchemyError

from job.boss.filters import PaceProfile, SearchUrl
from job.boss.jobs import JobScraper
from job.boss.session import BossSession
from job.models import DB_PATH, init_db
from job.models.job import JobRow
from job.models.plan import SearchPlanRow

_session = BossSession()
_scraper = JobScraper(_session)


class BossState(rx.State):
    boss_state: str = "—"
    busy: bool = False
    log: list[str] = rx.field(default_factory=list)
    stored_count: int = 0
    session_count: int = 0
    active_plan_name: str = ""

    def _push_log(self, line: str) -> None:
        self.log = [line, *self.log][:40]

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
        self._push_log(f"库就绪 {DB_PATH} · 已入库 {self.stored_count}")

    @rx.event
    async def open_boss(self):
        if self.busy:
            return
        self.busy = True
        self.boss_state = "launching"
        self._push_log("→ open")
        try:
            await _session.open()
            self.boss_state = "ready"
            self._push_log("Chrome ready")
        except RuntimeError as exc:
            self.boss_state = f"error: {exc}"
            self._push_log(str(exc))
        finally:
            self.busy = False

    @rx.event
    def stop_search(self):
        _scraper.request_stop()
        self._push_log("→ stop")
        self.boss_state = "stopping"

    @rx.event
    async def close_boss(self):
        await _session.close()
        self.boss_state = "done"
        self.busy = False
        self._push_log("→ close")

    @rx.event(background=True)
    async def start_search(self):
        async with self:
            if self.busy:
                return
            plan = SearchPlanRow.get_active_dict()
            query = str(plan.get("query") or "").strip()
            if not query:
                self._push_log("请先在配置中心填写岗位关键词")
                self.boss_state = "need query"
                return
            url = SearchUrl.build(plan)
            pace = PaceProfile.from_plan(plan)
            self.busy = True
            self.boss_state = "navigating"
            self.session_count = 0
            self.active_plan_name = str(plan.get("name") or "")
            self._push_log(
                f"→ search plan={self.active_plan_name} url={url}"
            )
            self._push_log(f"速率：{pace.describe()}")

        async def on_job(_job) -> None:
            async with self:
                self.session_count += 1
                self._refresh_stored_count()
                self.boss_state = "scraping"

        try:
            final_url, _jobs, state = await _scraper.search(
                url, pace=pace, on_job=on_job
            )
            async with self:
                self.boss_state = state
                self._refresh_stored_count()
                self._push_log(
                    f"search {state} plan={self.active_plan_name} url={final_url} "
                    f"session={self.session_count} stored={self.stored_count}"
                )
                self.busy = False
        except (RuntimeError, PlaywrightError, SQLAlchemyError) as exc:
            async with self:
                self.boss_state = f"error: {exc}"
                self._push_log(str(exc))
                self.busy = False
