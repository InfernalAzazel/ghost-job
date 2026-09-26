"""Workbench page."""

from __future__ import annotations

import reflex as rx

from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state.boss import BossState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class WorkbenchPage:
    """工作台：自动投递控制与运行日志。"""

    @classmethod
    def create(cls) -> rx.Component:
        return page_root(
            rx.box(site_header(active="workbench"), flex_shrink="0", width="100%"),
            rx.hstack(
                cls._stat_card(
                    "投递状态", BossState.boss_state, "实时更新", "activity"
                ),
                cls._stat_card(
                    "累计投递", BossState.stored_count, "历史沟通过的岗位", "briefcase"
                ),
                cls._stat_card("本次投递", BossState.session_count, "本轮新增", "send"),
                spacing="3",
                width="100%",
                flex_wrap="wrap",
                flex_shrink="0",
            ),
            rx.hstack(
                cls._platform_panel(),
                cls._log_panel(),
                spacing="4",
                width="100%",
                align="stretch",
                flex="1",
                min_height="0",
                margin_top="1em",
                overflow="hidden",
            ),
        )

    @classmethod
    def _stat_card(
        cls, label: str, value: rx.Var | str, hint: str, icon: str
    ) -> rx.Component:
        return rx.box(
            rx.hstack(
                rx.box(
                    rx.icon(icon, size=18, color=ACCENT),
                    bg=ACCENT_SOFT,
                    border_radius="10px",
                    padding="0.55em",
                ),
                rx.spacer(),
            ),
            rx.text(
                value, font_size="1.6em", font_weight="700", color=TEXT, margin_top="0.5em"
            ),
            rx.text(label, font_size="0.85em", color=TEXT, font_weight="600"),
            rx.text(hint, font_size="0.75em", color=MUTED, margin_top="0.15em"),
            bg=CARD,
            border=f"1px solid {BORDER}",
            border_radius="14px",
            padding="1em 1.1em",
            flex="1",
            min_width="140px",
            box_shadow="0 1px 2px rgba(16,24,40,0.04)",
        )

    @classmethod
    def _platform_panel(cls) -> rx.Component:
        status_hint = rx.cond(
            BossState.busy,
            "正在为你投递，可随时停止",
            "准备好后点击下方按钮开始，浏览器会自动打开",
        )
        return rx.box(
            rx.heading("自动投递", size="5", color=TEXT),
            rx.text(
                "按求职配置智能筛选合适的岗位，自动替你向 HR 打招呼。",
                color=MUTED,
                font_size="0.85em",
                margin_top="0.35em",
            ),
            rx.cond(
                BossState.target_cities != "",
                rx.text(
                    f"目标城市：{BossState.target_cities}",
                    font_size="0.8em",
                    color=ACCENT,
                    margin_top="0.5em",
                ),
            ),
            rx.box(
                rx.vstack(
                    rx.text("当前状态", font_size="0.8em", color=MUTED),
                    rx.text(
                        BossState.boss_state,
                        font_weight="600",
                        font_size="0.95em",
                        color=TEXT,
                    ),
                    rx.text(status_hint, font_size="0.8em", color=MUTED),
                    align="start",
                    spacing="1",
                    width="100%",
                ),
                bg="#F8FAFC",
                border=f"1px solid {BORDER}",
                border_radius="12px",
                padding="1em",
                margin_top="1em",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.button(
                    rx.icon("send", size=16),
                    "开始自动投递",
                    on_click=BossState.start_apply,
                    disabled=BossState.busy,
                    width="100%",
                    size="3",
                    style={
                        "background": ACCENT,
                        "color": "white",
                        "_disabled": {
                            "background": "var(--gray-a3)",
                            "color": "var(--gray-a8)",
                            "cursor": "not-allowed",
                        },
                    },
                ),
                rx.hstack(
                    rx.button(
                        "停止",
                        on_click=BossState.stop_apply,
                        disabled=BossState.busy == False,
                        color_scheme="red",
                        variant="soft",
                        flex="1",
                    ),
                    rx.button(
                        "关闭浏览器",
                        on_click=BossState.close_boss,
                        variant="outline",
                        flex="1",
                    ),
                    width="100%",
                    spacing="2",
                ),
                spacing="2",
                width="100%",
                margin_top="1.1em",
                flex_shrink="0",
            ),
            bg=CARD,
            border=f"1px solid {BORDER}",
            border_radius="16px",
            padding="1.25em",
            flex="1",
            min_width="280px",
            min_height="0",
            height="100%",
            overflow_y="auto",
            box_shadow="0 1px 2px rgba(16,24,40,0.04)",
        )

    @staticmethod
    def _log_row(entry: rx.Var) -> rx.Component:
        """一条日志：时间 · 级别图标 · 内容；投递绿色、重复蓝灰、跳过灰色、异常橙色。"""
        level = entry["level"]
        icon = rx.match(
            level,
            ("ok", rx.icon("circle-check", size=14, color="#12b76a")),
            ("dup", rx.icon("copy", size=14, color="#98a2b3")),
            ("skip", rx.icon("circle-minus", size=14, color="#98a2b3")),
            ("warn", rx.icon("triangle-alert", size=14, color="#f79009")),
            rx.icon("info", size=14, color=ACCENT),
        )
        tag = rx.match(
            level,
            ("ok", rx.badge("投递", color_scheme="green", variant="soft", size="1")),
            ("dup", rx.badge("重复", color_scheme="indigo", variant="soft", size="1")),
            ("skip", rx.badge("跳过", color_scheme="gray", variant="soft", size="1")),
            ("warn", rx.badge("注意", color_scheme="orange", variant="soft", size="1")),
            rx.fragment(),
        )
        return rx.hstack(
            rx.text(
                entry["time"],
                font_size="0.75em",
                color="#98a2b3",
                font_family="monospace",
                flex_shrink="0",
                padding_top="1px",
            ),
            rx.box(icon, display="flex", padding_top="2px", flex_shrink="0"),
            tag,
            rx.text(
                entry["text"],
                font_size="0.85em",
                color=rx.cond((level == "skip") | (level == "dup"), MUTED, TEXT),
                word_break="break-all",
            ),
            align="start",
            spacing="2",
            width="100%",
            padding="0.35em 0",
            border_bottom=f"1px dashed {BORDER}",
        )

    @classmethod
    def _log_panel(cls) -> rx.Component:
        return rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text("运行日志", font_weight="700", color=TEXT),
                    rx.text(
                        f"本次投递 {BossState.session_count} · 重复 {BossState.dup_count}"
                        f" · 跳过 {BossState.skip_count} · 共 {BossState.log.length()} 条",
                        font_size="0.75em",
                        color=MUTED,
                    ),
                    spacing="0",
                    align="start",
                ),
                rx.spacer(),
                rx.button(
                    rx.icon("trash-2", size=14),
                    "清空",
                    variant="ghost",
                    size="1",
                    color_scheme="gray",
                    on_click=BossState.clear_log,
                ),
                width="100%",
                align="center",
                flex_shrink="0",
            ),
            rx.cond(
                BossState.log.length() == 0,
                rx.box(
                    rx.hstack(
                        rx.icon("info", size=16, color=ACCENT),
                        rx.text(
                            "暂无日志，开始投递后会显示在这里",
                            font_size="0.85em",
                            color=ACCENT,
                        ),
                        spacing="2",
                    ),
                    bg=ACCENT_SOFT,
                    border_radius="10px",
                    padding="0.75em 1em",
                    margin_top="1em",
                    width="100%",
                ),
                rx.box(
                    rx.foreach(BossState.log, lambda entry: cls._log_row(entry)),
                    overflow_y="auto",
                    margin_top="0.5em",
                    width="100%",
                    flex="1",
                    min_height="0",
                ),
            ),
            bg=CARD,
            border=f"1px solid {BORDER}",
            border_radius="16px",
            padding="1.25em",
            flex="1.2",
            min_width="320px",
            min_height="0",
            height="100%",
            display="flex",
            flex_direction="column",
            overflow="hidden",
            box_shadow="0 1px 2px rgba(16,24,40,0.04)",
        )
