from __future__ import annotations

import reflex as rx

from job.lib.boss.jobs import DEFAULT_SEARCH_URL, job_to_dict
from job.lib.boss.session import BossSession

_session = BossSession()


class BossState(rx.State):
    boss_state: str = "—"
    busy: bool = False
    log: list[str] = []
    jobs: list[dict] = []

    def _push_log(self, line: str) -> None:
        self.log = [line, *self.log][:20]

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
        except Exception as exc:  # noqa: BLE001
            self.boss_state = f"error: {exc}"
            self._push_log(str(exc))
        finally:
            self.busy = False

    @rx.event
    def stop_search(self):
        _session.request_stop()
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
            self.busy = True
            self.boss_state = "navigating"
            self.jobs = []
            self._push_log("→ search")

        async def on_job(job) -> None:
            async with self:
                self.jobs = [*self.jobs, job_to_dict(job)]
                self.boss_state = "scraping"

        try:
            if not _session.is_open:
                await _session.open()
            final_url, _jobs, state = await _session.search(
                DEFAULT_SEARCH_URL, on_job=on_job
            )
            async with self:
                self.boss_state = state
                self._push_log(f"search {state} url={final_url} n={len(self.jobs)}")
                self.busy = False
        except Exception as exc:  # noqa: BLE001
            async with self:
                self.boss_state = f"error: {exc}"
                self._push_log(str(exc))
                self.busy = False
