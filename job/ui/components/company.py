"""查企业：风险标签与结果弹窗，岗位管理和消息页共用。"""

from __future__ import annotations

import reflex as rx
from reflex.vars import ObjectVar

from job.ui.state.company import CompanyState
from job.ui.theme import ACCENT, BORDER, MUTED, TEXT

# 风险等级 → 标签颜色
RISK_COLORS = {"low": "green", "medium": "orange", "high": "red"}


def risk_badge(risk: rx.Var, label: rx.Var) -> rx.Component:
    """公司风险标签；没查过（label 为空）不显示。"""
    return rx.cond(
        label != "",
        rx.badge(
            label,
            color_scheme=rx.match(risk, *RISK_COLORS.items(), "gray"),
            variant="soft",
            size="1",
            flex_shrink="0",
        ),
    )


def _section(title: str, *children: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.text(title, font_size="0.8em", font_weight="600", color=MUTED),
        *children,
        spacing="2",
        width="100%",
    )


def _link(text: rx.Var, href: rx.Var, **props) -> rx.Component:
    return rx.text(
        text,
        color=ACCENT,
        cursor="pointer",
        _hover={"text_decoration": "underline"},
        on_click=CompanyState.open_link(href),
        **props,
    )


def _point(point: ObjectVar[dict]) -> rx.Component:
    return rx.hstack(
        rx.text("·", color=MUTED),
        rx.text(point["text"], font_size="0.85em", color=TEXT),
        rx.cond(
            point["href"] != "",
            rx.icon(
                "external-link",
                size=13,
                color=ACCENT,
                cursor="pointer",
                flex_shrink="0",
                on_click=CompanyState.open_link(point["href"]),
            ),
        ),
        spacing="2",
        align="center",
    )


def _info_item(item: ObjectVar[dict]) -> rx.Component:
    return rx.hstack(
        rx.text(item["label"], font_size="0.8em", color=MUTED, width="110px", flex_shrink="0"),
        rx.text(item["value"], font_size="0.8em", color=TEXT, word_break="break-all"),
        spacing="2",
        align="start",
        width="100%",
    )


def _hit(hit: ObjectVar[dict]) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            _link(hit["title"], hit["href"], font_size="0.85em", font_weight="500"),
            rx.spacer(),
            rx.badge(hit["query"], variant="soft", color_scheme="gray", size="1", flex_shrink="0"),
            width="100%",
            align="center",
        ),
        rx.text(hit["body"], font_size="0.75em", color=MUTED, line_clamp=2),
        spacing="1",
        width="100%",
        padding_y="0.5em",
        border_bottom=f"1px solid {BORDER}",
    )


def _report() -> rx.Component:
    report = CompanyState.report
    return rx.vstack(
        _section(
            "AI 评估",
            rx.hstack(
                risk_badge(report["risk"], report["risk_label"]),
                rx.text(report["summary"], font_size="0.9em", color=TEXT, font_weight="500"),
                spacing="2",
                align="center",
            ),
            rx.foreach(report["points"].to(list[dict]), _point),
        ),
        _section(
            "工商信息",
            rx.cond(
                report["info"].to(list).length() > 0,
                rx.vstack(rx.foreach(report["info"].to(list[dict]), _info_item), spacing="1", width="100%"),
                rx.text("BOSS 公司主页上没有工商信息", font_size="0.8em", color=MUTED),
            ),
        ),
        _section(
            f"网上搜索（{report['hits'].to(list).length()} 条）",
            rx.foreach(report["hits"].to(list[dict]), _hit),
        ),
        spacing="5",
        width="100%",
    )


def company_dialog() -> rx.Component:
    report = CompanyState.report
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.cond(CompanyState.has_report, rx.cond(report["full_name"] != "", report["full_name"], report["name"]), CompanyState.company),
            ),
            rx.dialog.description(
                rx.cond(
                    CompanyState.has_report,
                    f"{report['name']} · 查询于 {report['checked_at']}",
                    "工商信息来自 BOSS 公司主页，负面信息来自网上搜索，由 AI 综合评估",
                ),
                font_size="0.8em",
                color=MUTED,
                margin_bottom="0.75em",
            ),
            rx.cond(
                CompanyState.busy,
                rx.hstack(
                    rx.spinner(size="2"),
                    rx.text(CompanyState.step, font_size="0.85em", color=TEXT),
                    spacing="2",
                    align="center",
                    padding="0.75em",
                    bg="#F8FAFC",
                    border_radius="8px",
                    width="100%",
                    margin_bottom="0.75em",
                ),
            ),
            rx.cond(
                CompanyState.error != "",
                rx.callout(CompanyState.error, icon="triangle-alert", color_scheme="red", size="1", margin_bottom="0.75em"),
            ),
            rx.cond(CompanyState.has_report, rx.scroll_area(_report(), max_height="60vh", type="auto", scrollbars="vertical")),
            rx.hstack(
                rx.spacer(),
                rx.button(
                    rx.icon("refresh-cw", size=14),
                    "重新查询",
                    variant="soft",
                    loading=CompanyState.busy,
                    on_click=CompanyState.check,
                ),
                rx.dialog.close(rx.button("关闭", variant="soft", color_scheme="gray")),
                spacing="3",
                margin_top="1em",
            ),
            max_width="640px",
            # 打开时不把焦点放到「重新查询」上，否则按钮上会有一圈蓝色焦点框
            on_open_auto_focus=rx.prevent_default,
        ),
        open=CompanyState.open,
        on_open_change=CompanyState.set_open,
    )
