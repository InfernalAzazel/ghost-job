"""Configuration center page (plan header + filters + manager)."""

from __future__ import annotations

import reflex as rx

from job.boss.filters import Industry
from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state import LlmState, PlansState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class ConfigPage:
    """配置中心：左侧菜单（求职方案 / 大模型）+ 右侧内容。"""

    # 左侧菜单：(分组, [(section, 图标, 名称)])
    MENU = (
        ("求职设置", (("plan", "layout-grid", "求职方案"),)),
        ("系统能力", (("llm", "cpu", "大模型"),)),
    )

    @classmethod
    def create(cls) -> rx.Component:
        return page_root(
            rx.box(site_header(active="config"), flex_shrink="0", width="100%"),
            rx.hstack(
                cls._sidebar(),
                rx.box(
                    rx.cond(
                        PlansState.section == "llm",
                        cls._llm_panel(),
                        cls._plan_panel(),
                    ),
                    bg=CARD,
                    border=f"1px solid {BORDER}",
                    border_radius="16px",
                    padding="1.5em",
                    box_shadow="0 1px 2px rgba(16,24,40,0.04)",
                    flex="1",
                    min_width="0",
                    min_height="0",
                    display="flex",
                    flex_direction="column",
                    overflow="hidden",
                ),
                spacing="4",
                align="stretch",
                width="100%",
                flex="1",
                min_height="0",
                margin_top="0.5em",
            ),
            cls._plan_manager(),
            max_width="1240px",
        )

    # --- sidebar ---

    @classmethod
    def _sidebar(cls) -> rx.Component:
        """左侧：自动保存提示 + 分组菜单。"""
        return rx.vstack(
            rx.hstack(
                rx.icon("circle-check", size=14, color=MUTED),
                rx.text(PlansState.save_hint, font_size="0.8em", color=MUTED),
                spacing="2",
                align="center",
                width="100%",
                padding="0.5em 0.75em",
                border=f"1px solid {BORDER}",
                border_radius="10px",
                bg=CARD,
            ),
            rx.vstack(
                *[
                    rx.fragment(
                        rx.text(
                            group,
                            font_size="0.8em",
                            color=MUTED,
                            padding="0.5em 0.5em 0.25em",
                        ),
                        *[cls._menu_item(*item) for item in items],
                    )
                    for group, items in cls.MENU
                ],
                spacing="1",
                width="100%",
                padding="0.5em",
                border=f"1px solid {BORDER}",
                border_radius="12px",
                bg=CARD,
            ),
            width="200px",
            flex_shrink="0",
            spacing="3",
        )

    @staticmethod
    def _menu_item(section: str, icon: str, label: str) -> rx.Component:
        """菜单项：当前项高亮。"""
        active = PlansState.section == section
        return rx.hstack(
            rx.icon(icon, size=16),
            rx.text(label, font_size="0.9em"),
            spacing="3",
            align="center",
            width="100%",
            padding="0.55em 0.85em",
            border_radius="8px",
            cursor="pointer",
            color=rx.cond(active, ACCENT, TEXT),
            bg=rx.cond(active, ACCENT_SOFT, "transparent"),
            _hover={"bg": ACCENT_SOFT},
            on_click=PlansState.set_section(section),
        )

    # --- plan panel ---

    @classmethod
    def _plan_panel(cls) -> rx.Component:
        """求职方案：方案头 + 筛选卡片。"""
        return rx.fragment(
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
        )

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
                        "这张方案统一管理岗位筛选与 AI 复核，"
                        "工作台抓取将使用当前方案。",
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

    @staticmethod
    def _section(title: str, *children: rx.Component, hint: str = "") -> rx.Component:
        """配置分块卡片：标题（可带一行小字说明）+ 内容。"""
        return rx.box(
            rx.vstack(
                rx.text(title, font_weight="700", color=TEXT),
                rx.text(hint, font_size="0.8em", color=MUTED) if hint else rx.fragment(),
                spacing="1",
                margin_bottom="0.85em",
            ),
            *children,
            width="100%",
            padding="1.1em 1.25em",
            border=f"1px solid {BORDER}",
            border_radius="12px",
            bg="#fcfcfd",
        )

    @classmethod
    def _filters_form(cls) -> rx.Component:
        """四张卡片：基础条件、多选条件、行业与关键词、拟人化。"""
        return rx.vstack(
            cls._section(
                "基础条件",
                cls._basic_fields(),
                hint="搜什么岗位、在哪个城市找，会直接拼进 BOSS 搜索地址",
            ),
            cls._section(
                "经验 / 学历 / 公司",
                cls._multi_fields(),
                hint="可多选，不选表示不限，由 BOSS 按条件筛选",
            ),
            cls._section(
                "行业与关键词",
                cls._keyword_section(),
                hint="行业由 BOSS 筛选；关键词按职位名 / 公司名在本地过滤，不符合的不会点开",
            ),
            cls._section(
                "拟人化",
                cls._pace_section(),
                hint="模拟真人的操作节奏，同一账号每天的表现也会略有差异",
            ),
            width="100%",
            height="100%",
            align="start",
            spacing="4",
            flex="1",
            min_height="0",
            overflow_y="auto",
            padding_right="0.35em",
            padding_bottom="0.5em",
        )

    @classmethod
    def _basic_fields(cls) -> rx.Component:
        """岗位关键词、城市、求职类型、薪资。"""
        return rx.grid(
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
            cls._select_field(
                "目标城市",
                PlansState.city_options,
                PlansState.city_label,
                PlansState.set_city,
            ),
            cls._select_field(
                "求职类型",
                PlansState.job_type_options,
                PlansState.job_type_label,
                PlansState.set_job_type,
            ),
            cls._select_field(
                "薪资范围",
                PlansState.salary_options,
                PlansState.salary_label,
                PlansState.set_salary,
            ),
            columns="2",
            spacing="4",
            width="100%",
        )

    @classmethod
    def _select_field(cls, title: str, options, value, on_change) -> rx.Component:
        """带标题的单选下拉。"""
        return rx.box(
            cls._field_label(title),
            rx.select(options, value=value, on_change=on_change, width="100%"),
            width="100%",
        )

    @classmethod
    def _multi_fields(cls) -> rx.Component:
        """经验、学历、融资阶段、公司规模四个多选。"""
        return rx.grid(
            cls._multi_field(
                "工作经验要求（多选）",
                PlansState.experience,
                PlansState.experience_options,
                PlansState.toggle_experience,
                PlansState.remove_experience,
            ),
            cls._multi_field(
                "最低学历（多选）",
                PlansState.education,
                PlansState.education_options,
                PlansState.toggle_education,
                PlansState.remove_education,
            ),
            cls._multi_field(
                "融资阶段（多选）",
                PlansState.funding,
                PlansState.funding_options,
                PlansState.toggle_funding,
                PlansState.remove_funding,
            ),
            cls._multi_field(
                "企业规模（多选）",
                PlansState.scale,
                PlansState.scale_options,
                PlansState.toggle_scale,
                PlansState.remove_scale,
            ),
            columns="2",
            spacing="4",
            width="100%",
        )

    @classmethod
    def _multi_field(
        cls, title: str, selected, options, toggle_event, remove_event
    ) -> rx.Component:
        """带标题的多选：已选标签 + 选项按钮。"""
        return rx.box(
            cls._field_label(title),
            cls._selected_chips(selected, remove_event),
            cls._option_buttons(options, toggle_event),
            width="100%",
        )

    @classmethod
    def _keyword_section(cls) -> rx.Component:
        """行业多选 + 职位 / 公司的包含、排除关键词。"""
        return rx.box(
            cls._industry_select(),
            rx.grid(
                cls._tag_input("包含关键词", "include_keywords", "输入并回车添加包含词"),
                cls._tag_input("排除关键词", "exclude_keywords", "输入并回车添加排除词"),
                cls._tag_input(
                    "包含公司关键词", "include_companies", "输入并回车添加公司包含词"
                ),
                cls._tag_input(
                    "排除公司关键词", "exclude_companies", "输入并回车添加公司排除词"
                ),
                columns="2",
                spacing="4",
                width="100%",
                margin_top="1em",
            ),
            cls._ai_review(),
            width="100%",
        )

    @classmethod
    def _ai_review(cls) -> rx.Component:
        """AI 岗位意图复核：开关 + 目标岗位要求。"""
        return rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text("AI 岗位意图复核", font_weight="600", color=TEXT),
                    rx.text(
                        "关键词过滤通过后，再由 DeepSeek 根据岗位职责复核一次；"
                        "复核不通过或模型异常时跳过该岗位，不入库。",
                        font_size="0.8em",
                        color=MUTED,
                    ),
                    spacing="1",
                ),
                rx.switch(
                    checked=PlansState.ai_review,
                    on_change=PlansState.set_ai_review,
                ),
                justify="between",
                align="start",
                spacing="4",
                width="100%",
                margin_bottom="0.85em",
            ),
            cls._field_label("目标岗位要求"),
            rx.text_area(
                value=PlansState.ai_requirement,
                on_change=PlansState.set_ai_requirement.debounce(500),
                placeholder=(
                    "例如：只投 AI 应用开发、AI Agent 工程师等岗位，"
                    "以 Python、LLM、Agent、RAG 落地为核心。"
                    "明确排除：销售、运营、纯算法研究、传统 CRUD、外包驻场。"
                ),
                rows="5",
                width="100%",
            ),
            rx.text(
                "建议同时写清希望投递和明确排除的岗位方向。",
                font_size="0.8em",
                color=MUTED,
                margin_top="0.35em",
            ),
            rx.cond(
                LlmState.key_ready,
                rx.fragment(),
                rx.hstack(
                    rx.text("尚未配置 DeepSeek API Key，", color="#d92d20"),
                    rx.link(
                        "前往「大模型」填写",
                        on_click=PlansState.set_section("llm"),
                        cursor="pointer",
                    ),
                    spacing="0",
                    font_size="0.8em",
                    margin_top="0.25em",
                ),
            ),
            width="100%",
            margin_top="1em",
            padding="0.9em 1em",
            border=f"1px solid {BORDER}",
            border_radius="10px",
            bg=CARD,
        )

    @classmethod
    def _industry_select(cls) -> rx.Component:
        """行业多选：已选为标签，右侧下拉按大类分组挑选。"""
        return rx.box(
            cls._field_label("行业选择（可多选）"),
            cls._tag_box(
                "industry",
                rx.select.root(
                    rx.select.trigger(
                        placeholder="选择行业", variant="ghost", margin_left="auto"
                    ),
                    rx.select.content(
                        *[
                            rx.select.group(
                                rx.select.label(group),
                                *[rx.select.item(name, value=name) for name in names],
                            )
                            for group, names in Industry.groups.items()
                        ]
                    ),
                    value="",
                    on_change=lambda value: PlansState.add_item("industry", value),
                ),
            ),
            width="100%",
        )

    @classmethod
    def _tag_input(cls, title: str, field: str, placeholder: str) -> rx.Component:
        """关键词输入：回车添加为标签，点 × 删除。"""
        return rx.box(
            cls._field_label(title),
            rx.form(
                cls._tag_box(
                    field,
                    rx.el.input(
                        name="tag",
                        placeholder=placeholder,
                        auto_complete="off",
                        style={
                            "border": "none",
                            "outline": "none",
                            "background": "transparent",
                            "flex": "1",
                            "min_width": "140px",
                            "font_size": "0.9em",
                        },
                    ),
                ),
                on_submit=lambda form: PlansState.add_item(
                    field, form.to(dict)["tag"]
                ),
                reset_on_submit=True,
                width="100%",
            ),
            width="100%",
        )

    @staticmethod
    def _tag_box(field: str, *tail: rx.Component) -> rx.Component:
        """带边框的标签框：``field`` 已选项为可删除标签，后面接输入框或下拉。"""
        return rx.hstack(
            rx.foreach(
                getattr(PlansState, field),
                lambda label: rx.hstack(
                    rx.text(label, font_size="0.8em", color=TEXT),
                    rx.icon(
                        "x",
                        size=12,
                        color=MUTED,
                        cursor="pointer",
                        on_click=PlansState.remove_item(field, label),
                    ),
                    spacing="1",
                    align="center",
                    bg="#f2f4f7",
                    border_radius="4px",
                    padding="0.15em 0.45em",
                ),
            ),
            *tail,
            spacing="1",
            align="center",
            flex_wrap="wrap",
            width="100%",
            min_height="36px",
            padding="4px 8px",
            border=f"1px solid {BORDER}",
            border_radius="8px",
        )

    @classmethod
    def _pace_section(cls) -> rx.Component:
        """拟人化节奏：预设档位 + 明细参数（仅「自定义」档可改）。"""
        num, unit = cls._pace_input, cls._pace_unit
        return rx.box(
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

    # --- llm panel ---

    @classmethod
    def _llm_panel(cls) -> rx.Component:
        """大模型：DeepSeek API Key、模型与连接测试。"""
        return rx.vstack(
            rx.vstack(
                rx.text("大模型", font_weight="700", font_size="1.1em", color=TEXT),
                rx.text(
                    "AI 岗位意图复核使用的模型，所有求职方案共用",
                    font_size="0.8em",
                    color=MUTED,
                ),
                spacing="1",
            ),
            cls._section(
                "DeepSeek",
                rx.grid(
                    rx.box(
                        cls._field_label("API Key"),
                        rx.input(
                            value=LlmState.api_key,
                            on_change=LlmState.set_api_key.debounce(500),
                            type="password",
                            placeholder="sk-...",
                            width="100%",
                        ),
                        rx.text(
                            LlmState.key_hint,
                            font_size="0.8em",
                            color=MUTED,
                            margin_top="0.35em",
                        ),
                        width="100%",
                    ),
                    cls._select_field(
                        "模型",
                        LlmState.model_options,
                        LlmState.model,
                        LlmState.set_model,
                    ),
                    columns="2",
                    spacing="4",
                    width="100%",
                ),
                rx.hstack(
                    rx.button(
                        rx.hstack(rx.icon("plug", size=16), rx.text("测试连接")),
                        on_click=LlmState.test_connection,
                        loading=LlmState.testing,
                        variant="outline",
                        size="2",
                    ),
                    rx.text(LlmState.test_hint, font_size="0.8em", color=MUTED),
                    spacing="3",
                    align="center",
                    margin_top="1em",
                ),
                hint="API Key 只保存在本机数据库；测试会用一个样例岗位真实调用一次",
            ),
            width="100%",
            spacing="4",
            align="start",
            overflow_y="auto",
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
