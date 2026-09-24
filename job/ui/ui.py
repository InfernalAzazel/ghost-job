import reflex as rx

from job.ui.state import BossState


def index() -> rx.Component:
    return rx.container(
        rx.heading("Ghostjob", size="8"),
        rx.hstack(
            rx.button("打开 BOSS", on_click=BossState.open_boss, disabled=BossState.busy),
            rx.button(
                "抓列表+详情",
                on_click=BossState.start_search,
                disabled=BossState.busy,
                color_scheme="green",
            ),
            rx.button(
                "停止",
                on_click=BossState.stop_search,
                disabled=~BossState.busy,
                color_scheme="red",
            ),
            rx.button("关闭", on_click=BossState.close_boss),
            spacing="3",
        ),
        rx.text(BossState.boss_state),
        rx.foreach(
            BossState.jobs,
            lambda job: rx.box(
                rx.link(job["title"], href=job["link"], is_external=True),
                rx.text(f"{job['salary']} · {job['company']} · {job['location']}"),
                rx.cond(
                    job["hrName"] != "",
                    rx.text(f"HR：{job['hrName']} · {job['hrTitle']}"),
                ),
                rx.cond(job["address"] != "", rx.text(f"地址：{job['address']}")),
                rx.cond(
                    job["description"] != "",
                    rx.text(job["description"], white_space="pre-wrap"),
                ),
                border_bottom="1px solid #333",
                padding_y="0.75em",
                width="100%",
            ),
        ),
        rx.heading("日志", size="4", margin_top="1.5em"),
        rx.foreach(BossState.log, lambda line: rx.text(line, font_size="0.85em")),
        padding="2em",
        max_width="720px",
    )


app = rx.App()
app.add_page(index, route="/", title="Ghostjob")
