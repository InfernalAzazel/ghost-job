import reflex as rx


class BossState(rx.State):
    boss_state: str = "—"
    busy: bool = False
    log: list[str] = []
    jobs: list[dict] = []

    def _push_log(self, line: str) -> None:
        self.log = [line, *self.log][:20]
