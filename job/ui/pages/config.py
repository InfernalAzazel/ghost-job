"""Configuration center page (plan header + filters + manager)."""

from __future__ import annotations

import reflex as rx

from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state import PlansState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class ConfigPage:
    """配置中心：求职方案 + 岗位筛选。"""

    @classmethod
    def create(cls) -> rx.Component:
        return page_root(
            rx.box(site_header(active="config"), flex_shrink="0", width="100%"),
            rx.box(
                rx.box(cls._plan_header(), flex_shrink="0", width="100%"),
                rx.box(
                    cls._filters_form(),
                    margin_top="1.25em",
                    padding_top="1.25em",
                    border_top=f"1px solid {BORDER}",
                    width="100%",
                    flex="1",
                    min_height="0",
                    display="flex",
                    flex_direction="column",
                    overflow="hidden",
                ),
                bg=CARD,
                border=f"1px solid {BORDER}",
                border_radius="16px",
                padding="1.5em",
                width="100%",
                box_shadow="0 1px 2px rgba(16,24,40,0.04)",
                margin_top="0.5em",
                flex="1",
                min_height="0",
                display="flex",
                flex_direction="column",
                overflow="hidden",
            ),
            cls._plan_manager(),
            max_width="1100px",
        )

    # --- plan header ---

    @classmethod
    def _plan_header(cls) -> rx.Component:
        return rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text("当前求职方案", font_weight="700", color=TEXT),
                    rx.hstack(
                        rx.select(
                            PlansState.plan_names,
                            value=PlansState.plan_name,
                            on_change=PlansState.select_plan_by_name,
                            placeholder="选择方案",
                            size="3",
                            width="280px",
                        ),
                        rx.cond(
                            PlansState.is_default,
                            rx.badge("默认使用", color_scheme="blue", variant="soft"),
                        ),
                        spacing="3",
                        align="center",
                    ),
                    rx.text(
                        "管理筛选条件；工作台抓取将使用当前方案。",
                        font_size="0.8em",
                        color=MUTED,
                        margin_top="0.35em",
                    ),
                    align="start",
                    spacing="2",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.button(
                        rx.hstack(
                            rx.icon("plus", size=16), rx.text("新建方案"), spacing="2"
                        ),
                        on_click=PlansState.create_plan,
                        style={"background": ACCENT, "color": "white"},
                        size="2",
                    ),
                    rx.button(
                        rx.hstack(
                            rx.icon("settings", size=16),
                            rx.text("方案管理"),
                            spacing="2",
                        ),
                        on_click=PlansState.open_manager,
                        variant="outline",
                        size="2",
                    ),
                    spacing="2",
                ),
                width="100%",
                align="start",
            ),
            rx.hstack(
                rx.icon("circle-check", size=14, color=ACCENT),
                rx.text(PlansState.save_hint, font_size="0.8em", color=ACCENT),
                spacing="2",
                bg=ACCENT_SOFT,
                border_radius="8px",
                padding="0.45em 0.75em",
                margin_top="0.75em",
                width="fit-content",
            ),
            width="100%",
            align="start",
            spacing="1",
        )

    # --- filters ---

    @classmethod
    def _field_label(cls, text: str) -> rx.Component:
        return rx.text(
            text,
            font_size="0.85em",
            font_weight="600",
            color=TEXT,
            margin_bottom="0.35em",
        )

    @classmethod
    def _selected_chips(cls, selected: rx.Var, remove_event) -> rx.Component:
        return rx.cond(
            selected.length() > 0,
            rx.hstack(
                rx.foreach(
                    selected,
                    lambda label: rx.hstack(
                        rx.text(label, font_size="0.75em", color=ACCENT),
                        rx.box(
                            rx.icon("x", size=12, color=ACCENT),
                            on_click=remove_event(label),
                            cursor="pointer",
                        ),
                        spacing="1",
                        align="center",
                        bg=ACCENT_SOFT,
                        border_radius="6px",
                        padding="0.25em 0.5em",
                    ),
                ),
                spacing="2",
                flex_wrap="wrap",
                margin_bottom="0.5em",
            ),
        )

    @classmethod
    def _option_buttons(cls, options: rx.Var, toggle_event) -> rx.Component:
        return rx.hstack(
            rx.foreach(
                options,
                lambda label: rx.button(
                    label,
                    size="1",
                    variant="soft",
                    on_click=toggle_event(label),
                ),
            ),
            spacing="2",
            flex_wrap="wrap",
        )

    @classmethod
    def _filters_form(cls) -> rx.Component:
        return rx.vstack(
            rx.text(
                "岗位筛选",
                font_weight="700",
                font_size="1em",
                color=TEXT,
                flex_shrink="0",
            ),
            rx.box(
                rx.box(
                    rx.grid(
                        rx.box(
                            cls._field_label("岗位关键词"),
                            rx.input(
                                value=PlansState.query,
                                on_change=PlansState.set_query.debounce(400),
                                placeholder="例如：Agent 工程师",
                                width="100%",
                            ),
                            width="100%",
                        ),
                        rx.box(
                            cls._field_label("目标城市"),
                            rx.select(
                                PlansState.city_options,
                                value=PlansState.city_label,
                                on_change=PlansState.set_city,
                                width="100%",
                            ),
                            width="100%",
                        ),
                        rx.box(
                            cls._field_label("求职类型"),
                            rx.select(
                                PlansState.job_type_options,
                                value=PlansState.job_type_label,
                                on_change=PlansState.set_job_type,
                                width="100%",
                            ),
                            width="100%",
                        ),
                        rx.box(
                            cls._field_label("薪资范围"),
                            rx.select(
                                PlansState.salary_options,
                                value=PlansState.salary_label,
                                on_change=PlansState.set_salary,
                                width="100%",
                            ),
                            width="100%",
                        ),
                        columns="2",
                        spacing="4",
                        width="100%",
                    ),
                    width="100%",
                    margin_top="0.75em",
                ),
                rx.box(
                    rx.grid(
                        rx.box(
                            cls._field_label("工作经验要求（多选）"),
                            cls._selected_chips(
                                PlansState.experience, PlansState.remove_experience
                            ),
                            cls._option_buttons(
                                PlansState.experience_options,
                                PlansState.toggle_experience,
                            ),
                            width="100%",
                        ),
                        rx.box(
                            cls._field_label("最低学历（多选）"),
                            cls._selected_chips(
                                PlansState.education, PlansState.remove_education
                            ),
                            cls._option_buttons(
                                PlansState.education_options,
                                PlansState.toggle_education,
                            ),
                            width="100%",
                        ),
                        rx.box(
                            cls._field_label("融资阶段（多选）"),
                            cls._selected_chips(
                                PlansState.funding, PlansState.remove_funding
                            ),
                            cls._option_buttons(
                                PlansState.funding_options, PlansState.toggle_funding
                            ),
                            width="100%",
                        ),
                        rx.box(
                            cls._field_label("企业规模（多选）"),
                            cls._selected_chips(
                                PlansState.scale, PlansState.remove_scale
                            ),
                            cls._option_buttons(
                                PlansState.scale_options, PlansState.toggle_scale
                            ),
                            width="100%",
                        ),
                        columns="2",
                        spacing="4",
                        width="100%",
                    ),
                    width="100%",
                    margin_top="1.25em",
                    padding_top="1.25em",
                    padding_bottom="1em",
                    border_top=f"1px solid {BORDER}",
                ),
                cls._pace_section(),
                width="100%",
                flex="1",
                min_height="0",
                overflow_y="auto",
                padding_right="0.35em",
            ),
            width="100%",
            height="100%",
            align="start",
            spacing="2",
            flex="1",
            min_height="0",
        )

    @classmethod
    def _pace_section(cls) -> rx.Component:
        """抓取速率：预设档位 + 明细参数（仅「自定义」档可改）。"""
        num, unit = cls._pace_input, cls._pace_unit
        return rx.box(
            cls._field_label("抓取速率"),
            rx.segmented_control.root(
                rx.foreach(
                    PlansState.pace_options,
                    lambda label: rx.segmented_control.item(label, value=label),
                ),
                value=PlansState.pace_label,
                on_change=PlansState.set_pace,
            ),
            rx.vstack(
                cls._pace_row(
                    unit("看完一条停"), num("read_min"), unit("–"), num("read_max"),
                    unit("秒"),
                ),
                cls._pace_row(
                    unit("每次翻页停"), num("scroll_min"), unit("–"),
                    num("scroll_max"), unit("秒"),
                ),
                cls._pace_row(
                    unit("每抓"), num("rest_every", step="1"), unit("条歇"),
                    num("rest_min"), unit("–"), num("rest_max"),
                    unit("秒（0 条表示不歇）"),
                ),
                spacing="2",
                margin_top="0.75em",
            ),
            rx.text(
                PlansState.pace_hint,
                font_size="0.8em",
                color=MUTED,
                margin_top="0.5em",
            ),
            width="100%",
            padding_top="1.25em",
            padding_bottom="1em",
            border_top=f"1px solid {BORDER}",
        )

    @staticmethod
    def _pace_row(*children: rx.Component) -> rx.Component:
        """一行明细参数：文字与输入框横排。"""
        return rx.hstack(*children, spacing="2", align="center")

    @staticmethod
    def _pace_unit(text: str) -> rx.Component:
        """参数行里的说明文字。"""
        return rx.text(text, font_size="0.85em", color=TEXT)

    @staticmethod
    def _pace_input(key: str, step: str = "0.5") -> rx.Component:
        """单个明细参数的数字输入框；非「自定义」档只读，停止输入 0.5 秒后保存。"""
        return rx.input(
            disabled=~PlansState.pace_custom,
            value=PlansState.pace_params[key].to_string(),
            on_change=lambda value: PlansState.set_pace_param(key, value).debounce(
                500
            ),
            type="number",
            min="0",
            step=step,
            size="1",
            width="72px",
        )

    # --- plan manager dialog ---

    @staticmethod
    def _plan_row(plan: rx.Var, _index: rx.Var) -> rx.Component:
        return rx.box(
            rx.hstack(
                rx.vstack(
                    rx.hstack(
                        rx.text(plan["name"], font_weight="600", color=TEXT),
                        rx.cond(
                            plan["is_default"],
                            rx.badge("默认", color_scheme="blue", variant="soft", size="1"),
                        ),
                        rx.cond(
                            plan["is_active"],
                            rx.badge(
                                "当前", color_scheme="green", variant="soft", size="1"
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.text(
                        f"关键词：{plan['query']}",
                        font_size="0.75em",
                        color=MUTED,
                    ),
                    align="start",
                    spacing="1",
                    flex="1",
                ),
                rx.hstack(
                    rx.button(
                        "切换",
                        size="1",
                        variant="soft",
                        on_click=PlansState.select_plan(plan["id"]),
                    ),
                    rx.button(
                        "设默认",
                        size="1",
                        variant="outline",
                        on_click=PlansState.set_default(plan["id"]),
                    ),
                    rx.button(
                        "复制",
                        size="1",
                        variant="outline",
                        on_click=PlansState.duplicate(plan["id"]),
                    ),
                    rx.button(
                        "删除",
                        size="1",
                        color_scheme="red",
                        variant="soft",
                        on_click=PlansState.delete(plan["id"]),
                    ),
                    spacing="2",
                ),
                width="100%",
                align="center",
            ),
            border_bottom=f"1px solid {BORDER}",
            padding_y="0.85em",
            width="100%",
        )

    @classmethod
    def _plan_manager(cls) -> rx.Component:
        return rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title("方案管理"),
                rx.dialog.description("复制、删除或设为默认；下方可重命名当前方案。"),
                rx.hstack(
                    rx.input(
                        value=PlansState.rename_draft,
                        on_change=PlansState.set_rename_draft,
                        placeholder="当前方案新名称",
                        width="100%",
                    ),
                    rx.button(
                        "重命名当前", on_click=PlansState.rename_active, size="2"
                    ),
                    width="100%",
                    spacing="2",
                    margin_y="0.75em",
                ),
                rx.cond(
                    PlansState.error != "",
                    rx.text(
                        PlansState.error,
                        color="red",
                        font_size="0.8em",
                        margin_bottom="0.5em",
                    ),
                ),
                rx.box(
                    rx.foreach(PlansState.plans, cls._plan_row),
                    max_height="360px",
                    overflow_y="auto",
                    width="100%",
                ),
                rx.flex(
                    rx.dialog.close(
                        rx.button(
                            "关闭", variant="soft", on_click=PlansState.close_manager
                        ),
                    ),
                    justify="end",
                    margin_top="1em",
                    width="100%",
                ),
                max_width="640px",
                width="90vw",
            ),
            open=PlansState.manager_open,
            on_open_change=PlansState.set_manager_open,
        )
