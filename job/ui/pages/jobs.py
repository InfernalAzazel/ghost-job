"""岗位管理 page."""

from __future__ import annotations

import reflex as rx

from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state import JobsState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class JobsPage:
    """岗位管理：表格浏览、搜索、详情、删除。"""

    PAGE_SIZE_OPTIONS = ["15 / page", "30 / page", "50 / page"]

    @classmethod
    def create(cls) -> rx.Component:
        return page_root(
            rx.box(site_header(active="jobs"), flex_shrink="0", width="100%"),
            rx.box(
                cls._toolbar(),
                cls._table(),
                cls._pagination(),
                cls._detail_dialog(),
                bg=CARD,
                border=f"1px solid {BORDER}",
                border_radius="16px",
                padding="1.25em 1.35em",
                width="100%",
                box_shadow="0 1px 2px rgba(16,24,40,0.04)",
                margin_top="0.5em",
                flex="1",
                min_height="0",
                display="flex",
                flex_direction="column",
                overflow="hidden",
            ),
            max_width="1200px",
        )

    @classmethod
    def _toolbar(cls) -> rx.Component:
        return rx.hstack(
            rx.text("岗位数据", font_weight="700", font_size="1.05em", color=TEXT),
            rx.spacer(),
            rx.select(
                ["全部沟通状态"],
                value="全部沟通状态",
                size="2",
                width="140px",
            ),
            rx.select(
                ["全部分析状态"],
                value="全部分析状态",
                size="2",
                width="140px",
            ),
            rx.box(
                rx.hstack(
                    rx.icon("search", size=16, color=MUTED),
                    rx.input(
                        value=JobsState.search,
                        on_change=JobsState.set_search_and_reload.debounce(350),
                        placeholder="搜索岗位或公司",
                        variant="soft",
                        width="220px",
                        size="2",
                    ),
                    spacing="2",
                    align="center",
                ),
                bg="#F8FAFC",
                border=f"1px solid {BORDER}",
                border_radius="8px",
                padding_x="0.6em",
            ),
            width="100%",
            align="center",
            spacing="3",
            flex_wrap="wrap",
            flex_shrink="0",
            margin_bottom="1em",
        )

    @classmethod
    def _table(cls) -> rx.Component:
        return rx.box(
            rx.box(
                cls._header_row(),
                border_bottom=f"1px solid {BORDER}",
                width="100%",
                flex_shrink="0",
            ),
            rx.cond(
                JobsState.rows.length() == 0,
                rx.center(
                    rx.text("暂无岗位数据，请先在工作台抓取", color=MUTED),
                    width="100%",
                    padding_y="3em",
                ),
                rx.box(
                    rx.foreach(JobsState.rows, cls._data_row),
                    width="100%",
                    flex="1",
                    min_height="0",
                    overflow_y="auto",
                ),
            ),
            width="100%",
            flex="1",
            min_height="0",
            display="flex",
            flex_direction="column",
            overflow="hidden",
        )

    @classmethod
    def _header_row(cls) -> rx.Component:
        return rx.hstack(
            rx.checkbox(
                on_change=lambda _: JobsState.toggle_select_all(),
                size="1",
            ),
            rx.text("岗位名称", font_size="0.8em", color=MUTED, font_weight="600", flex="1.4"),
            rx.text("公司", font_size="0.8em", color=MUTED, font_weight="600", flex="1"),
            rx.text("匹配度", font_size="0.8em", color=MUTED, font_weight="600", width="90px"),
            rx.text("沟通状态", font_size="0.8em", color=MUTED, font_weight="600", width="90px"),
            rx.text("最新消息", font_size="0.8em", color=MUTED, font_weight="600", flex="0.8"),
            rx.box(
                rx.text("操作", font_size="0.8em", color=MUTED, font_weight="600"),
                width="320px",
                border_left=f"1px solid {BORDER}",
                padding_left="0.75em",
            ),
            width="100%",
            align="center",
            spacing="3",
            padding_y="0.65em",
            padding_x="0.25em",
        )

    @staticmethod
    def _data_row(job: rx.Var, _index: rx.Var) -> rx.Component:
        return rx.hstack(
            rx.checkbox(
                on_change=lambda _: JobsState.toggle_select(job["uid"]),
                size="1",
            ),
            rx.vstack(
                rx.text(job["title"], font_size="0.9em", font_weight="600", color=TEXT),
                rx.text(job["salary"], font_size="0.75em", color=MUTED),
                spacing="0",
                align="start",
                flex="1.4",
                min_width="0",
            ),
            rx.text(job["company"], font_size="0.85em", color=TEXT, flex="1", min_width="0"),
            rx.badge(
                job["matchStatus"],
                color_scheme="gray",
                variant="soft",
                width="90px",
            ),
            rx.badge(
                job["chatStatus"],
                color_scheme="orange",
                variant="soft",
                width="90px",
            ),
            rx.text(
                job["latestMessage"],
                font_size="0.85em",
                color=MUTED,
                flex="0.8",
            ),
            rx.hstack(
                rx.button(
                    rx.hstack(
                        rx.icon("eye", size=14),
                        rx.text("详情", font_size="0.8em"),
                        spacing="1",
                    ),
                    size="1",
                    variant="ghost",
                    color=ACCENT,
                    on_click=JobsState.open_detail(job["uid"]),
                ),
                rx.button(
                    rx.hstack(
                        rx.icon("message-circle", size=14),
                        rx.text("沟通记录", font_size="0.8em"),
                        spacing="1",
                    ),
                    size="1",
                    variant="ghost",
                    color=ACCENT,
                    on_click=JobsState.coming_soon,
                ),
                rx.button(
                    rx.hstack(
                        rx.icon("bot", size=14),
                        rx.text("模拟面试", font_size="0.8em"),
                        spacing="1",
                    ),
                    size="1",
                    variant="ghost",
                    color=ACCENT,
                    on_click=JobsState.coming_soon,
                ),
                rx.button(
                    rx.hstack(
                        rx.icon("trash-2", size=14),
                        rx.text("删除", font_size="0.8em"),
                        spacing="1",
                    ),
                    size="1",
                    variant="ghost",
                    color="red",
                    on_click=JobsState.delete_one(job["uid"]),
                ),
                spacing="1",
                width="320px",
                border_left=f"1px solid {BORDER}",
                padding_left="0.5em",
                flex_wrap="wrap",
            ),
            width="100%",
            align="center",
            spacing="3",
            padding_y="0.85em",
            padding_x="0.25em",
            border_bottom=f"1px solid {BORDER}",
        )

    @classmethod
    def _pagination(cls) -> rx.Component:
        return rx.hstack(
            rx.text(f"共 {JobsState.total} 条", font_size="0.8em", color=MUTED),
            rx.spacer(),
            rx.hstack(
                rx.icon_button(
                    rx.icon("chevron-left", size=16),
                    size="1",
                    variant="soft",
                    disabled=JobsState.has_prev == False,
                    on_click=JobsState.prev_page,
                ),
                rx.center(
                    rx.text(JobsState.page, font_size="0.85em", font_weight="600"),
                    bg=ACCENT_SOFT,
                    color=ACCENT,
                    border_radius="999px",
                    width="28px",
                    height="28px",
                ),
                rx.icon_button(
                    rx.icon("chevron-right", size=16),
                    size="1",
                    variant="soft",
                    disabled=JobsState.has_next == False,
                    on_click=JobsState.next_page,
                ),
                spacing="2",
                align="center",
            ),
            rx.select(
                cls.PAGE_SIZE_OPTIONS,
                value=JobsState.page_label,
                on_change=JobsState.set_page_size,
                size="1",
                width="110px",
            ),
            width="100%",
            align="center",
            margin_top="0.85em",
            flex_shrink="0",
        )

    @classmethod
    def _detail_dialog(cls) -> rx.Component:
        return rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title(JobsState.detail["title"]),
                rx.dialog.description(
                    f"{JobsState.detail['salary']} · {JobsState.detail['company']} · {JobsState.detail['location']}"
                ),
                rx.vstack(
                    rx.cond(
                        JobsState.detail["hrName"] != "",
                        rx.text(
                            f"HR：{JobsState.detail['hrName']} · {JobsState.detail['hrTitle']}",
                            font_size="0.85em",
                            color=MUTED,
                        ),
                    ),
                    rx.cond(
                        JobsState.detail["address"] != "",
                        rx.text(
                            f"地址：{JobsState.detail['address']}",
                            font_size="0.85em",
                            color=MUTED,
                        ),
                    ),
                    rx.box(
                        rx.text(
                            JobsState.detail["description"],
                            font_size="0.85em",
                            color=TEXT,
                            white_space="pre-wrap",
                        ),
                        max_height="320px",
                        overflow_y="auto",
                        width="100%",
                        margin_top="0.75em",
                        padding="0.75em",
                        bg="#F8FAFC",
                        border_radius="8px",
                    ),
                    align="start",
                    spacing="2",
                    width="100%",
                    margin_top="0.5em",
                ),
                rx.flex(
                    rx.dialog.close(
                        rx.button("关闭", variant="soft", on_click=JobsState.close_detail)
                    ),
                    justify="end",
                    margin_top="1em",
                    width="100%",
                ),
                max_width="640px",
                width="90vw",
            ),
            open=JobsState.detail_open,
            on_open_change=JobsState.set_detail_open,
        )
