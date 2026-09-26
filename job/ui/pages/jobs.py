"""岗位管理 page."""

from __future__ import annotations

import reflex as rx

from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state.jobs import JobsState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class JobsPage:
    """岗位管理：表格浏览、搜索、详情、删除、勾选后 AI 分析匹配度。"""

    PAGE_SIZE_OPTIONS = ("15 / page", "30 / page", "50 / page")
    # 操作列宽度（表头与数据行对齐）
    ACTION_WIDTH = "170px"

    @classmethod
    def create(cls) -> rx.Component:
        return page_root(
            rx.box(site_header(active="jobs"), flex_shrink="0", width="100%"),
            rx.box(
                cls._toolbar(),
                cls._table(),
                cls._pagination(),
                cls._detail_dialog(),
                cls._delete_dialog(),
                cls._batch_delete_dialog(),
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
        )

    @classmethod
    def _toolbar(cls) -> rx.Component:
        return rx.hstack(
            rx.text("岗位数据", font_weight="700", font_size="1.05em", color=TEXT),
            rx.cond(JobsState.selected_count > 0, cls._selection_bar()),
            rx.spacer(),
            rx.select(
                JobsState.suitable_options,
                value=JobsState.suitable,
                on_change=JobsState.set_suitable,
                size="2",
                width="96px",
            ),
            rx.select(
                JobsState.analysis_options,
                value=JobsState.analysis,
                on_change=JobsState.set_analysis,
                size="2",
                width="136px",
            ),
            rx.box(
                rx.hstack(
                    rx.icon("search", size=16, color=MUTED),
                    rx.input(
                        value=JobsState.search,
                        on_change=JobsState.set_search_and_reload.debounce(350),
                        placeholder="搜索岗位或公司",
                        variant="soft",
                        color_scheme="gray",
                        width="180px",
                        size="2",
                        style={
                            "background": "transparent",
                            "box_shadow": "none",
                            "outline": "none",
                        },
                    ),
                    spacing="2",
                    align="center",
                ),
                bg="#F8FAFC",
                border=f"1px solid {BORDER}",
                border_radius="8px",
                padding_x="0.6em",
            ),
            rx.cond(JobsState.selected_count == 0, cls._export_button("导出全部")),
            width="100%",
            align="center",
            spacing="3",
            flex_wrap="wrap",
            flex_shrink="0",
            margin_bottom="1em",
        )

    @staticmethod
    def _export_button(label: str) -> rx.Component:
        """导出 CSV：没勾选时导出全部，勾选后只导出选中的。"""
        return rx.button(
            rx.icon("download", size=14),
            label,
            on_click=JobsState.export_csv,
            variant="outline",
            size="2",
        )

    @classmethod
    def _selection_bar(cls) -> rx.Component:
        """勾选后出现：已选数量（点 × 取消选择）、AI 分析、导出、批量删除。"""
        return rx.hstack(
            rx.tooltip(
                rx.button(
                    f"已选 {JobsState.selected_count} 项",
                    rx.icon("x", size=14),
                    on_click=JobsState.clear_selection,
                    disabled=JobsState.analyzing,
                    variant="soft",
                    size="2",
                ),
                content="取消选择",
            ),
            rx.button(
                rx.icon("sparkles", size=14),
                rx.cond(
                    JobsState.analyzing,
                    f"分析中 {JobsState.analyzed}/{JobsState.selected_count}",
                    "AI 分析",
                ),
                on_click=JobsState.analyze_selected,
                loading=JobsState.analyzing,
                size="2",
                style={"background": ACCENT, "color": "white"},
            ),
            cls._export_button("导出"),
            rx.button(
                rx.icon("trash-2", size=14),
                "批量删除",
                on_click=JobsState.set_batch_delete_open(True),
                disabled=JobsState.analyzing,
                color_scheme="red",
                variant="soft",
                size="2",
            ),
            spacing="3",
            align="center",
            margin_left="0.75em",
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
                    rx.text("暂无岗位数据，请先在工作台开始自动投递", color=MUTED),
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
                checked=JobsState.all_selected,
                on_change=lambda _: JobsState.toggle_select_all(),
                disabled=JobsState.analyzing,
                size="1",
            ),
            rx.text("岗位名称", font_size="0.8em", color=MUTED, font_weight="600", flex="1.4"),
            rx.text("公司", font_size="0.8em", color=MUTED, font_weight="600", flex="1"),
            rx.text("是否合适", font_size="0.8em", color=MUTED, font_weight="600", width="72px"),
            rx.text("判断描述", font_size="0.8em", color=MUTED, font_weight="600", flex="1.4"),
            rx.text("匹配度", font_size="0.8em", color=MUTED, font_weight="600", width="90px"),
            rx.box(
                rx.text("操作", font_size="0.8em", color=MUTED, font_weight="600"),
                width=cls.ACTION_WIDTH,
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
    def _action(icon: str, label: str, on_click, color: str = ACCENT) -> rx.Component:
        """操作列里的文字按钮：图标 + 文字，悬停变淡。"""
        return rx.hstack(
            rx.icon(icon, size=16),
            rx.text(label, font_size="0.9em"),
            spacing="1",
            align="center",
            color=color,
            cursor="pointer",
            white_space="nowrap",
            _hover={"opacity": "0.7"},
            on_click=on_click,
        )

    @staticmethod
    def _suitable_badge(suitable: rx.Var) -> rx.Component:
        """是否合适标签：合适绿色、不合适红色。"""
        return rx.badge(
            rx.cond(suitable, "合适", "不合适"),
            color_scheme=rx.cond(suitable, "green", "red"),
            variant="soft",
        )

    @staticmethod
    def _data_row(job: rx.Var, _index: rx.Var) -> rx.Component:
        return rx.hstack(
            rx.checkbox(
                checked=JobsState.selected.contains(job["uid"]),
                on_change=lambda _: JobsState.toggle_select(job["uid"]),
                disabled=JobsState.analyzing,
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
            rx.box(JobsPage._suitable_badge(job["suitable"]), width="72px"),
            rx.box(
                rx.cond(
                    job["reason"] != "",
                    rx.tooltip(
                        rx.text(
                            job["reason"],
                            font_size="0.8em",
                            color=MUTED,
                            overflow="hidden",
                            text_overflow="ellipsis",
                            white_space="nowrap",
                        ),
                        content=job["reason"],
                        max_width="360px",
                    ),
                    rx.text("—", font_size="0.8em", color=MUTED),
                ),
                flex="1.4",
                min_width="0",
            ),
            rx.badge(
                job["matchStatus"],
                color_scheme=rx.cond(job["matchHigh"], "green", "gray"),
                variant="soft",
                width="90px",
            ),
            rx.hstack(
                JobsPage._action("eye", "详情", JobsState.open_detail(job["uid"])),
                JobsPage._action(
                    "trash-2",
                    "删除",
                    JobsState.ask_delete(job["uid"], job["title"]),
                    color="#f04438",
                ),
                spacing="5",
                align="center",
                width=JobsPage.ACTION_WIDTH,
                border_left=f"1px solid {BORDER}",
                padding_left="0.75em",
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
                list(cls.PAGE_SIZE_OPTIONS),
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

    @staticmethod
    def _delete_dialog() -> rx.Component:
        """删除确认框。"""
        return rx.alert_dialog.root(
            rx.alert_dialog.content(
                rx.alert_dialog.title("删除岗位"),
                rx.alert_dialog.description(
                    f"确定删除「{JobsState.pending_delete['title']}」吗？删除后无法恢复。"
                ),
                rx.flex(
                    rx.alert_dialog.cancel(
                        rx.button("取消", variant="soft", color_scheme="gray")
                    ),
                    rx.alert_dialog.action(
                        rx.button(
                            "删除", color_scheme="red", on_click=JobsState.confirm_delete
                        )
                    ),
                    spacing="3",
                    justify="end",
                    margin_top="1em",
                ),
                max_width="420px",
            ),
            open=JobsState.pending_delete.length() > 0,
            on_open_change=JobsState.set_delete_open,
        )

    @staticmethod
    def _batch_delete_dialog() -> rx.Component:
        """批量删除确认框。"""
        return rx.alert_dialog.root(
            rx.alert_dialog.content(
                rx.alert_dialog.title("批量删除"),
                rx.alert_dialog.description(
                    f"确定删除选中的 {JobsState.selected_count} 个岗位吗？"
                    "删除后无法恢复。"
                ),
                rx.flex(
                    rx.alert_dialog.cancel(
                        rx.button("取消", variant="soft", color_scheme="gray")
                    ),
                    rx.alert_dialog.action(
                        rx.button(
                            "删除",
                            color_scheme="red",
                            on_click=JobsState.delete_selected,
                        )
                    ),
                    spacing="3",
                    justify="end",
                    margin_top="1em",
                ),
                max_width="420px",
            ),
            open=JobsState.batch_delete_open,
            on_open_change=JobsState.set_batch_delete_open,
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
                    rx.hstack(
                        JobsPage._suitable_badge(JobsState.detail["suitable"]),
                        rx.text(JobsState.detail["reason"], font_size="0.85em", color=TEXT),
                        spacing="2",
                        align="center",
                    ),
                    rx.cond(
                        JobsState.detail["suitable"],
                        rx.text(
                            f"投递状态：{JobsState.detail['result']}",
                            font_size="0.85em",
                            color=MUTED,
                        ),
                    ),
                    rx.text(
                        f"入库时间：{JobsState.detail['createdAt']}",
                        font_size="0.85em",
                        color=MUTED,
                    ),
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
