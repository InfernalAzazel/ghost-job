import reflex as rx

from ghostjob.state import BossState


def index() -> rx.Component:
    return rx.container(
        rx.heading("Ghostjob", size="8"),
        rx.text(BossState.boss_state),
        rx.text("Reflex 壳就绪"),
        padding="2em",
        max_width="720px",
    )


app = rx.App()
app.add_page(index, route="/", title="Ghostjob")
