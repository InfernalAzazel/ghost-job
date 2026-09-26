"""消息页：左侧会话列表，右侧聊天记录。"""

from __future__ import annotations

import reflex as rx

from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state.messages import MessagesState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class MessagesPage:
    """与 HR 的聊天记录，布局参照 BOSS 直聘消息页。"""

    LIST_WIDTH = "300px"
    SALARY = "#F26D5F"

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
                ),
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
            spacing="0",
            width=cls.LIST_WIDTH,
            min_width=cls.LIST_WIDTH,
            border_right=f"1px solid {BORDER}",
            height="100%",
        )

    @classmethod
    def _conversation(cls, item: rx.Var) -> rx.Component:
        is_active = item["boss_id"] == MessagesState.active_id
        return rx.hstack(
            cls._avatar(item["hr_name"], "40px"),
            rx.vstack(
                rx.hstack(
                    rx.text(item["hr_name"], font_weight="600", color=TEXT, font_size="0.9em"),
                    rx.text(
                        item["company"],
                        font_size="0.78em",
                        color=MUTED,
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap",
                    ),
                    rx.spacer(),
                    rx.text(item["last_time"], font_size="0.75em", color=MUTED, white_space="nowrap"),
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
                align="center",
                spacing="2",
            ),
            rx.cond(
                chat["title"] != "",
                rx.hstack(
                    rx.text("沟通职位", font_size="0.8em", color=MUTED),
                    rx.text(chat["title"], font_size="0.85em", font_weight="600", color=TEXT),
                    rx.text(chat["salary"], font_size="0.85em", font_weight="600", color=cls.SALARY),
                    rx.text(chat["location"], font_size="0.8em", color=MUTED),
                    rx.spacer(),
                    rx.link(
                        rx.hstack(
                            rx.text("查看岗位", font_size="0.8em"),
                            rx.icon("external-link", size=13),
                            spacing="1",
                            align="center",
                        ),
                        href=chat["link"],
                        is_external=True,
                        color=ACCENT,
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
    def _bubble(cls, message: rx.Var) -> rx.Component:
        mine = ~message["from_hr"].to(bool)
        body = rx.vstack(
            rx.box(
                rx.text(message["text"], font_size="0.9em", color=TEXT, white_space="pre-wrap"),
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
