"""消息页：左侧会话列表，右侧聊天记录。"""

from __future__ import annotations

from typing import Any, ClassVar

import reflex as rx
from reflex.vars import ObjectVar

from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state.messages import MessagesState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class MessagesPage:
    """与 HR 的聊天记录，布局参照 BOSS 直聘消息页。"""

    LIST_WIDTH = "300px"
    SALARY = "#F26D5F"
    # 同一行里不被挤压换行的短文本
    NO_SHRINK: ClassVar[dict[str, Any]] = {"white_space": "nowrap", "flex_shrink": "0"}
    # 沟通状态标签的颜色，未列出的为灰色
    STATUS_COLORS: ClassVar[dict[str, str]] = {
        "invited": "green",
        "done": "blue",
        "passed": "green",
        "failed": "red",
        "hr_rejected": "red",
    }

    @classmethod
    def create(cls) -> rx.Component:
        return page_root(
            rx.box(site_header(active="messages"), flex_shrink="0", width="100%"),
            rx.hstack(
                cls._sidebar(),
                cls._chat(),
                spacing="0",
                bg=CARD,
                border=f"1px solid {BORDER}",
                border_radius="16px",
                width="100%",
                box_shadow="0 1px 2px rgba(16,24,40,0.04)",
                margin_top="0.5em",
                flex="1",
                min_height="0",
                overflow="hidden",
                align="stretch",
            ),
        )

    @staticmethod
    def _avatar(name: rx.Var, size: str) -> rx.Component:
        return rx.center(
            rx.text(name.to(str)[:1], font_weight="600", color=ACCENT),
            width=size,
            height=size,
            min_width=size,
            border_radius="50%",
            bg=ACCENT_SOFT,
        )

    @classmethod
    def _sidebar(cls) -> rx.Component:
        return rx.vstack(
            rx.hstack(
                rx.box(
                    rx.hstack(
                        rx.icon("search", size=15, color=MUTED),
                        rx.input(
                            value=MessagesState.search,
                            on_change=MessagesState.set_search.debounce(350),
                            placeholder="搜索 HR、公司或岗位",
                            variant="soft",
                            color_scheme="gray",
                            size="2",
                            width="100%",
                            style={"background": "transparent", "box_shadow": "none", "outline": "none"},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    bg="#F8FAFC",
                    border=f"1px solid {BORDER}",
                    border_radius="8px",
                    padding_x="0.6em",
                    flex="1",
                    min_width="0",
                ),
                cls._status_filter(),
                rx.tooltip(
                    rx.icon_button(
                        rx.icon("refresh-cw", size=15),
                        on_click=MessagesState.refresh,
                        variant="ghost",
                        color_scheme="gray",
                        size="2",
                    ),
                    content="刷新",
                ),
                width="100%",
                align="center",
                padding="1em",
                border_bottom=f"1px solid {BORDER}",
            ),
            rx.cond(
                MessagesState.conversations.length() > 0,
                rx.box(
                    rx.foreach(MessagesState.conversations, lambda c: cls._conversation(c)),
                    width="100%",
                    flex="1",
                    min_height="0",
                    overflow_y="auto",
                ),
                rx.center(
                    rx.text("暂无会话", font_size="0.85em", color=MUTED),
                    width="100%",
                    flex="1",
                ),
            ),
            cls._export_bar(),
            spacing="0",
            width=cls.LIST_WIDTH,
            min_width=cls.LIST_WIDTH,
            border_right=f"1px solid {BORDER}",
            height="100%",
        )

    @staticmethod
    def _status_filter() -> rx.Component:
        """按沟通状态筛选会话的图标菜单；筛选生效时图标高亮。"""
        filtering = MessagesState.status_filter != "全部"
        return rx.menu.root(
            rx.menu.trigger(
                rx.icon_button(
                    rx.icon("list-filter", size=15),
                    variant=rx.cond(filtering, "soft", "ghost"),
                    color_scheme=rx.cond(filtering, "teal", "gray"),
                    size="2",
                    title="按沟通状态筛选",
                ),
            ),
            rx.menu.content(
                rx.text("按沟通状态筛选", font_size="0.75em", color=MUTED, padding="0.3em 0.75em"),
                rx.foreach(
                    MessagesState.status_filters,
                    lambda label: rx.menu.item(
                        rx.hstack(
                            rx.text(label),
                            rx.spacer(),
                            rx.cond(
                                label == MessagesState.status_filter,
                                rx.icon("check", size=14),
                            ),
                            width="100%",
                            align="center",
                            spacing="3",
                        ),
                        on_select=MessagesState.set_status_filter(label),
                    ),
                ),
                min_width="140px",
                # 关闭后不把焦点还给按钮，否则按钮上会留一圈蓝色焦点框
                on_close_auto_focus=rx.prevent_default,
            ),
        )

    @staticmethod
    def _export_bar() -> rx.Component:
        """会话列表底部：全选、已选数量（点 × 取消选择）与导出 JSON；没勾选时导出全部。"""
        selecting = MessagesState.selected_count > 0
        return rx.hstack(
            rx.checkbox(
                checked=MessagesState.all_selected,
                on_change=MessagesState.toggle_select_all,
                disabled=MessagesState.conversations.length() == 0,
            ),
            rx.cond(
                selecting,
                rx.button(
                    f"已选 {MessagesState.selected_count} 项",
                    rx.icon("x", size=13),
                    on_click=MessagesState.clear_selection,
                    variant="ghost",
                    color_scheme="gray",
                    size="1",
                    title="取消选择",
                ),
                rx.text("全选", font_size="0.8em", color=MUTED),
            ),
            rx.spacer(),
            rx.button(
                rx.icon("download", size=14),
                rx.cond(selecting, "导出", "导出全部"),
                on_click=MessagesState.export_json,
                disabled=MessagesState.conversations.length() == 0,
                variant="outline",
                size="1",
            ),
            width="100%",
            align="center",
            spacing="2",
            padding="0.6em 1em",
            border_top=f"1px solid {BORDER}",
            flex_shrink="0",
        )

    @classmethod
    def _conversation(cls, item: ObjectVar[dict]) -> rx.Component:
        is_active = item["boss_id"] == MessagesState.active_id
        return rx.hstack(
            # 点勾选框只勾选，不打开会话
            rx.box(
                rx.checkbox(
                    checked=MessagesState.selected.contains(item["boss_id"]),
                    on_change=MessagesState.toggle_select(item["boss_id"]),
                ),
                on_click=rx.stop_propagation,
                display="flex",
            ),
            cls._avatar(item["hr_name"], "40px"),
            rx.vstack(
                rx.hstack(
                    rx.text(
                        item["hr_name"],
                        font_weight="600",
                        color=TEXT,
                        font_size="0.9em",
                        white_space="nowrap",
                        flex_shrink="0",
                    ),
                    rx.text(
                        item["company"],
                        font_size="0.78em",
                        color=MUTED,
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap",
                        min_width="0",
                    ),
                    rx.spacer(),
                    rx.cond(
                        item["status"] != "",
                        rx.badge(
                            item["status_label"],
                            color_scheme=rx.match(
                                item["status"],
                                *cls.STATUS_COLORS.items(),
                                "gray",
                            ),
                            variant="soft",
                            size="1",
                            flex_shrink="0",
                        ),
                    ),
                    rx.text(
                        item["last_time"],
                        font_size="0.75em",
                        color=MUTED,
                        white_space="nowrap",
                        flex_shrink="0",
                        font_variant_numeric="tabular-nums",
                    ),
                    width="100%",
                    align="center",
                    spacing="2",
                ),
                rx.text(
                    rx.cond(item["last_from_hr"], "", "我："),
                    item["last_text"],
                    font_size="0.8em",
                    color=MUTED,
                    overflow="hidden",
                    text_overflow="ellipsis",
                    white_space="nowrap",
                    width="100%",
                ),
                spacing="1",
                min_width="0",
                flex="1",
            ),
            on_click=MessagesState.open_chat(item["boss_id"]),
            bg=rx.cond(is_active, ACCENT_SOFT, "transparent"),
            _hover={"bg": rx.cond(is_active, ACCENT_SOFT, "#F8FAFC")},
            cursor="pointer",
            padding="0.8em 1em",
            width="100%",
            align="center",
            spacing="3",
        )

    @classmethod
    def _chat(cls) -> rx.Component:
        return rx.cond(
            MessagesState.active_id != "",
            rx.vstack(
                cls._chat_header(),
                rx.auto_scroll(
                    rx.foreach(MessagesState.messages, lambda m: cls._bubble(m)),
                    width="100%",
                    flex="1",
                    min_height="0",
                    padding="1.25em 1.5em",
                    bg="#F8FAFC",
                    display="flex",
                    flex_direction="column",
                    gap="1em",
                ),
                rx.hstack(
                    rx.icon("info", size=14, color=MUTED),
                    rx.text(
                        "消息由自动回复记录，需要亲自回复请到 BOSS 直聘 App 或网页",
                        font_size="0.8em",
                        color=MUTED,
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                    padding="0.75em 1.5em",
                    border_top=f"1px solid {BORDER}",
                ),
                spacing="0",
                flex="1",
                min_width="0",
                height="100%",
            ),
            rx.center(
                rx.vstack(
                    rx.icon("message-circle", size=40, color=BORDER),
                    rx.text("还没有聊天记录", font_weight="600", color=TEXT),
                    rx.text(
                        "在工作台开启自动回复后，与 HR 的消息会出现在这里",
                        font_size="0.85em",
                        color=MUTED,
                    ),
                    align="center",
                    spacing="2",
                ),
                flex="1",
                height="100%",
            ),
        )

    @classmethod
    def _chat_header(cls) -> rx.Component:
        chat = MessagesState.active
        return rx.vstack(
            rx.hstack(
                rx.text(chat["hr_name"], font_weight="700", color=TEXT),
                rx.text(chat["company"], font_size="0.85em", color=MUTED),
                rx.cond(chat["hr_title"] != "", rx.text("·", color=MUTED)),
                rx.text(chat["hr_title"], font_size="0.85em", color=MUTED),
                rx.spacer(),
                rx.text("沟通状态", font_size="0.8em", color=MUTED, **cls.NO_SHRINK),
                rx.select.root(
                    rx.select.trigger(width="116px"),
                    rx.select.content(
                        rx.foreach(
                            MessagesState.status_choices,
                            lambda label: rx.select.item(label, value=label),
                        ),
                        # 关闭后不把焦点还给下拉框，否则会留一圈蓝色焦点框
                        on_close_auto_focus=rx.prevent_default,
                    ),
                    value=MessagesState.active_status,
                    on_change=MessagesState.set_status,
                    size="1",
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.cond(
                chat["title"] != "",
                rx.hstack(
                    rx.text("沟通职位", font_size="0.8em", color=MUTED, **cls.NO_SHRINK),
                    rx.text(
                        chat["title"],
                        font_size="0.85em",
                        font_weight="600",
                        color=TEXT,
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap",
                        min_width="0",
                    ),
                    rx.text(
                        chat["salary"],
                        font_size="0.85em",
                        font_weight="600",
                        color=cls.SALARY,
                        **cls.NO_SHRINK,
                    ),
                    rx.text(chat["location"], font_size="0.8em", color=MUTED, **cls.NO_SHRINK),
                    rx.spacer(),
                    rx.cond(
                        chat["job_uid"] != "",
                        rx.link(
                            rx.hstack(
                                rx.text("查看岗位", font_size="0.8em"),
                                rx.icon("arrow-right", size=13),
                                spacing="1",
                                align="center",
                            ),
                            on_click=MessagesState.open_job,
                            cursor="pointer",
                            color=ACCENT,
                            **cls.NO_SHRINK,
                        ),
                    ),
                    width="100%",
                    align="center",
                    spacing="3",
                ),
            ),
            width="100%",
            spacing="2",
            padding="1em 1.5em",
            border_bottom=f"1px solid {BORDER}",
        )

    @classmethod
    def _bubble(cls, message: ObjectVar[dict]) -> rx.Component:
        mine = ~message["from_hr"].to(bool)
        body = rx.vstack(
            rx.box(
                rx.cond(
                    message["text"].to(str) != "",
                    rx.text(message["text"], font_size="0.9em", color=TEXT, white_space="pre-wrap"),
                    rx.text("[卡片消息，请在 BOSS 直聘查看]", font_size="0.9em", color=MUTED),
                ),
                bg=rx.cond(mine, ACCENT_SOFT, CARD),
                border=rx.cond(mine, "1px solid transparent", f"1px solid {BORDER}"),
                border_radius="10px",
                padding="0.55em 0.85em",
                max_width="100%",
            ),
            rx.hstack(
                rx.text(message["time"], font_size="0.72em", color=MUTED),
                rx.cond(
                    message["auto"],
                    rx.badge("AI 自动回复", color_scheme="teal", variant="soft", size="1"),
                ),
                spacing="2",
                align="center",
            ),
            spacing="1",
            align=rx.cond(mine, "end", "start"),
            max_width="65%",
        )
        return rx.hstack(
            rx.cond(mine, rx.fragment(), cls._avatar(MessagesState.active["hr_name"], "34px")),
            body,
            width="100%",
            justify=rx.cond(mine, "end", "start"),
            align="start",
            spacing="2",
        )
