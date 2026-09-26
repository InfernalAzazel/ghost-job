"""Top navigation header."""

from __future__ import annotations

import reflex as rx

from job.ui.theme import ACCENT, MUTED, TEXT


def site_header(*, active: str) -> rx.Component:
    """active: 'workbench' | 'jobs' | 'messages' | 'config'."""

    def nav_item(label: str, href: str, key: str) -> rx.Component:
        is_active = active == key
        return rx.link(
            rx.box(
                rx.text(
                    label,
                    font_weight="600",
                    color=ACCENT if is_active else MUTED,
                    font_size="0.9em",
                ),
                border_bottom=f"2px solid {ACCENT}" if is_active else "2px solid transparent",
                padding_bottom="0.35em",
            ),
            href=href,
            text_decoration="none",
        )

    return rx.hstack(
        rx.hstack(
            rx.box(
                rx.icon("ghost", size=20, color="white"),
                bg=ACCENT,
                border_radius="12px",
                padding="0.55em",
            ),
            rx.vstack(
                rx.text("Ghost Job", font_weight="700", font_size="1.05em", color=TEXT),
                rx.text("智聘助手 · BOSS", font_size="0.75em", color=MUTED),
                spacing="0",
                align="start",
            ),
            spacing="3",
            align="center",
        ),
        rx.spacer(),
        rx.hstack(
            nav_item("工作台", "/", "workbench"),
            nav_item("岗位管理", "/jobs", "jobs"),
            nav_item("消息", "/messages", "messages"),
            nav_item("配置中心", "/config", "config"),
            spacing="5",
            align="center",
        ),
        width="100%",
        align="center",
        padding_y="0.75em",
    )
