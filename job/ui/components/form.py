"""配置页通用表单小件：字段标题、开关卡片、表单页标题。"""

from __future__ import annotations

import reflex as rx

from job.ui.theme import BORDER, MUTED, TEXT


def field_label(text: str) -> rx.Component:
    """输入框上方的字段标题。"""
    return rx.text(
        text, font_size="0.85em", font_weight="600", color=TEXT, margin_bottom="0.35em"
    )


def form_title(icon: str, title: str, subtitle: str) -> rx.Component:
    """标签页顶部：图标 + 大标题 + 一行说明。"""
    return rx.vstack(
        rx.hstack(
            rx.icon(icon, size=20, color=TEXT),
            rx.text(title, font_size="1.15em", font_weight="700"),
            spacing="2",
            align="center",
        ),
        rx.text(subtitle, font_size="0.85em", color=MUTED),
        spacing="1",
    )


def card(*children: rx.Component, **style) -> rx.Component:
    """浅底圆角卡片。"""
    return rx.vstack(
        *children,
        **{
            "spacing": "3",
            "width": "100%",
            "padding": "1.1em 1.25em",
            "border": f"1px solid {BORDER}",
            "border_radius": "12px",
            "bg": "#fcfcfd",
            **style,
        },
    )


def switch_card(
    title: str, desc: str, checked: rx.Var, on_change, *extra: rx.Component
) -> rx.Component:
    """带说明的开关卡片；``extra`` 为开关下方的内容。"""
    return card(
        rx.hstack(
            rx.vstack(
                rx.text(title, font_weight="600", color=TEXT),
                rx.text(desc, font_size="0.85em", color=MUTED),
                spacing="1",
            ),
            rx.spacer(),
            rx.switch(checked=checked, on_change=on_change, size="3"),
            align="center",
            width="100%",
        ),
        *extra,
        spacing="2",
    )
