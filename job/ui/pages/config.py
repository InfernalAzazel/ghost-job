"""Configuration center page (plan header + filters + manager)."""

from __future__ import annotations

from typing import Any

import reflex as rx

from job.ui.components.header import site_header
from job.ui.components.layout import page_root
from job.ui.state import LlmState, PlansState
from job.ui.theme import ACCENT, ACCENT_SOFT, BORDER, CARD, MUTED, TEXT


class ConfigPage:
    """配置中心：左侧菜单（求职方案 / 大模型）+ 右侧内容。"""

    # 左侧菜单：(分组, [(section, 图标, 名称)])
    # 标签框里的无边框输入框样式
    BARE_INPUT = {
        "border": "none",
        "outline": "none",
        "background": "transparent",
        "flex": "1",
        "min_width": "120px",
        "font_size": "0.9em",
    }

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
        """经验、学历、融资阶段、公司规模四个下拉多选。"""
        return rx.grid(
            cls._combo_field("工作经验要求（多选）", "experience", "选择经验要求"),
            cls._combo_field("最低学历（多选）", "education", "选择学历"),
            cls._combo_field("融资阶段（多选）", "funding", "选择融资阶段"),
            cls._combo_field("企业规模（多选）", "scale", "选择企业规模"),
            columns="2",
            spacing="4",
            width="100%",
        )

    @classmethod
    def _combo_field(
        cls, title: str, field: str, placeholder: str, menu: rx.Component | None = None
    ) -> rx.Component:
        """下拉多选：框内是已选标签和搜索框，聚焦后弹出 ``menu``（默认为选项列表）。"""
        is_open = PlansState.combo_open == field
        selected = getattr(PlansState, field)
        return rx.box(
            cls._field_label(title),
            rx.box(
                cls._tag_box(
                    field,
                    rx.el.input(
                        value=rx.cond(is_open, PlansState.combo_query, ""),
                        placeholder=rx.cond(selected.length() > 0, "", placeholder),
                        on_focus=lambda _: PlansState.open_combo(field),
                        on_blur=lambda _: PlansState.close_combo(),
                        on_change=PlansState.set_combo_query,
                        auto_complete="off",
                        style=cls.BARE_INPUT,
                    ),
                    rx.icon(
                        rx.cond(is_open, "search", "chevron-down"),
                        size=16,
                        color=MUTED,
                        margin_left="auto",
                    ),
                    border_color=rx.cond(is_open, ACCENT, BORDER),
                ),
                rx.cond(is_open, menu if menu is not None else cls._combo_menu(field)),
                position="relative",
                width="100%",
            ),
            width="100%",
        )

    @classmethod
    def _combo_menu(cls, field: str) -> rx.Component:
        """下拉选项列表：按搜索词过滤，已选项打勾；按下即切换。"""
        selected = getattr(PlansState, field)
        return cls._popup(
            rx.foreach(
                getattr(PlansState, f"{field}_options"),
                lambda label: rx.cond(
                    label.contains(PlansState.combo_query),
                    rx.hstack(
                        rx.text(label, font_size="0.9em"),
                        rx.cond(
                            selected.contains(label),
                            rx.icon("check", size=14, color=ACCENT, margin_left="auto"),
                        ),
                        align="center",
                        width="100%",
                        padding="0.5em 0.75em",
                        border_radius="8px",
                        cursor="pointer",
                        color=rx.cond(selected.contains(label), ACCENT, TEXT),
                        _hover={"bg": "#f2f4f7"},
                        on_mouse_down=PlansState.toggle_item(field, label),
                    ),
                ),
            ),
            max_height="260px",
            overflow_y="auto",
        )

    @staticmethod
    def _popup(*children: rx.Component, **style: Any) -> rx.Component:
        """输入框下方的浮层；按下时阻止默认行为，输入框不失焦、下拉不收起。"""
        return rx.box(
            *children,
            on_mouse_down=rx.prevent_default,
            **{
                "position": "absolute",
                "top": "calc(100% + 4px)",
                "left": "0",
                "right": "0",
                "z_index": "20",
                "padding": "4px",
                "bg": CARD,
                "border": f"1px solid {BORDER}",
                "border_radius": "12px",
                "box_shadow": "0 8px 24px rgba(16,24,40,0.12)",
                **style,
            },
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
                    rx.text("尚未配置大模型 Key 与模型，", color="#d92d20"),
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
        """行业多选：左栏大类（可整类勾选）、右栏行业；输入文字时改为搜索结果。"""
        return cls._combo_field(
            "行业选择（可多选）",
            "industry",
            "选择行业，或输入关键字搜索",
            menu=cls._popup(
                rx.cond(
                    PlansState.combo_query != "",
                    cls._industry_matches(),
                    rx.hstack(
                        cls._industry_groups(),
                        cls._industry_leaves(),
                        spacing="0",
                        align="stretch",
                    ),
                ),
                right="auto",
                width="460px",
                padding="0",
            ),
        )

    @classmethod
    def _industry_groups(cls) -> rx.Component:
        """左栏：大类；悬停切换右栏，勾选框整类全选 / 取消。"""
        return rx.box(
            rx.foreach(
                PlansState.industry_groups,
                lambda group: cls._check_row(
                    group,
                    PlansState.industry_group_marks[group],
                    on_check=PlansState.toggle_industry_group(group),
                    active=PlansState.industry_group == group,
                    on_mouse_enter=PlansState.set_industry_group(group),
                    trailing=rx.icon("chevron-right", size=14, color=MUTED),
                ),
            ),
            width="210px",
            padding="4px",
            border_right=f"1px solid {BORDER}",
            max_height="280px",
            overflow_y="auto",
        )

    @classmethod
    def _industry_leaves(cls) -> rx.Component:
        """右栏：当前大类下的行业。"""
        return rx.box(
            rx.foreach(
                PlansState.industry_group_items, lambda n: cls._industry_leaf(n)
            ),
            flex="1",
            padding="4px",
            max_height="280px",
            overflow_y="auto",
        )

    @classmethod
    def _industry_matches(cls) -> rx.Component:
        """搜索结果：所有大类里名字含关键字的行业。"""
        return rx.box(
            rx.foreach(PlansState.industry_matches, lambda n: cls._industry_leaf(n)),
            rx.cond(
                PlansState.industry_matches.length() == 0,
                rx.text(
                    "没有匹配的行业", font_size="0.85em", color=MUTED, padding="0.75em"
                ),
            ),
            padding="4px",
            max_height="280px",
            overflow_y="auto",
        )

    @classmethod
    def _industry_leaf(cls, name: rx.Var) -> rx.Component:
        mark = rx.cond(PlansState.industry.contains(name), "all", "none")
        return cls._check_row(
            name, mark, on_check=PlansState.toggle_item("industry", name)
        )

    @staticmethod
    def _check_row(
        label: rx.Var,
        mark: rx.Var,
        *,
        on_check,
        active: rx.Var | bool = False,
        on_mouse_enter=None,
        trailing: rx.Component | None = None,
    ) -> rx.Component:
        """带勾选框的一行；``mark`` 为 all / some / none（全选 / 部分 / 未选）。"""
        box = rx.match(
            mark,
            ("all", rx.icon("square-check", size=16, color=ACCENT)),
            ("some", rx.icon("square-minus", size=16, color=ACCENT)),
            rx.icon("square", size=16, color="#98a2b3"),
        )
        # 有悬停切换的行（大类）只在勾选框上勾选，其余整行可点
        split = on_mouse_enter is not None
        check = {"on_mouse_down": on_check}
        events = {"on_mouse_enter": on_mouse_enter} if split else check
        return rx.hstack(
            rx.box(box, display="flex", **(check if split else {})),
            rx.text(label, font_size="0.9em", flex="1"),
            trailing or rx.fragment(),
            align="center",
            spacing="2",
            width="100%",
            padding="0.45em 0.6em",
            border_radius="8px",
            cursor="pointer",
            color=rx.cond(active, ACCENT, TEXT),
            bg=rx.cond(active, ACCENT_SOFT, "transparent"),
            _hover={"bg": rx.cond(active, ACCENT_SOFT, "#f2f4f7")},
            **events,
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
                        style=cls.BARE_INPUT,
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
    def _tag_box(field: str, *tail: rx.Component, **style: Any) -> rx.Component:
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
            **style,
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
                rx.vstack(
                    rx.box(
                        cls._field_label("1. API Key"),
                        rx.input(
                            value=LlmState.api_key,
                            on_change=LlmState.set_api_key.debounce(500),
                            type="password",
                            placeholder="在 DeepSeek 开放平台创建后粘贴到这里，sk-...",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.box(
                        cls._field_label("2. 模型"),
                        rx.hstack(
                            rx.select(
                                LlmState.model_options,
                                value=LlmState.model,
                                on_change=LlmState.set_model,
                                placeholder="先拉取最新模型",
                                disabled=LlmState.model_options.length() == 0,
                                width="100%",
                            ),
                            cls._llm_button(
                                "refresh-cw", "拉取最新模型", LlmState.fetch_models
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    rx.hstack(
                        cls._llm_button("plug", "测试连接", LlmState.test_connection),
                        rx.text(LlmState.hint, font_size="0.8em", color=MUTED),
                        spacing="3",
                        align="center",
                    ),
                    spacing="4",
                    width="100%",
                    max_width="560px",
                ),
                hint="API Key 只保存在本机数据库；测试会用一个样例岗位真实调用一次",
            ),
            width="100%",
            spacing="4",
            align="start",
            overflow_y="auto",
        )

    @staticmethod
    def _llm_button(icon: str, label: str, on_click) -> rx.Component:
        """大模型页的操作按钮；请求进行中时统一禁用。"""
        return rx.button(
            rx.hstack(rx.icon(icon, size=16), rx.text(label), spacing="2"),
            on_click=on_click,
            disabled=LlmState.busy,
            variant="outline",
            size="2",
            flex_shrink="0",
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
