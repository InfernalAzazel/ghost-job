"""Configuration center page (plan header + filters + manager)."""

from __future__ import annotations

from typing import Any

import reflex as rx

from job.ui.components.form import field_label, form_title, switch_card
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
        ("高级设置", (("llm", "sparkles", "AI 服务"),)),
    )

    # 求职方案下的标签页：(tab, 图标, 名称)
    PLAN_TABS = (
        ("filters", "layout-grid", "岗位筛选"),
        ("resume", "file-text", "简历配置"),
    )

    # 简历 PDF 上传控件 id
    RESUME_UPLOAD = "resume_pdf"

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
        """求职方案：方案头 + 标签页（岗位筛选 / 简历配置）。"""
        return rx.fragment(
            rx.box(cls._plan_header(), flex_shrink="0", width="100%"),
            rx.hstack(
                *[cls._tab_item(*tab) for tab in cls.PLAN_TABS],
                spacing="5",
                width="100%",
                flex_shrink="0",
                margin_top="1em",
                border_bottom=f"1px solid {BORDER}",
            ),
            rx.box(
                rx.cond(
                    PlansState.plan_tab == "resume",
                    cls._resume_form(),
                    cls._filters_form(),
                ),
                padding_top="1.25em",
                width="100%",
                flex="1",
                min_height="0",
                display="flex",
                flex_direction="column",
                overflow="hidden",
            ),
        )

    @staticmethod
    def _tab_item(tab: str, icon: str, label: str) -> rx.Component:
        """方案标签页：当前页蓝字加下划线。"""
        active = PlansState.plan_tab == tab
        return rx.hstack(
            rx.icon(icon, size=15),
            rx.text(label, font_size="0.9em"),
            spacing="2",
            align="center",
            padding="0.6em 0.1em",
            margin_bottom="-1px",
            cursor="pointer",
            color=rx.cond(active, ACCENT, TEXT),
            border_bottom=rx.cond(
                active, f"2px solid {ACCENT}", "2px solid transparent"
            ),
            on_click=PlansState.set_plan_tab(tab),
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
                        "可为不同求职方向准备多套方案，自动投递时使用当前方案。",
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
                        rx.icon("plus", size=16),
                        "新建方案",
                        on_click=PlansState.create_plan,
                        style={"background": ACCENT, "color": "white"},
                        size="2",
                    ),
                    rx.button(
                        rx.icon("settings", size=16),
                        "方案管理",
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

    _field_label = staticmethod(field_label)

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
                hint="你想找什么工作、在哪座城市",
            ),
            cls._section(
                "经验 / 学历 / 公司",
                cls._multi_fields(),
                hint="可多选，不选即不限",
            ),
            cls._section(
                "行业与关键词",
                cls._keyword_section(),
                hint="只看感兴趣的行业，并用关键词避开不想要的职位和公司",
            ),
            cls._section(
                "投递节奏",
                cls._pace_section(),
                hint="像真人一样浏览和投递，降低账号风险",
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

    # --- resume ---

    _switch_card = staticmethod(switch_card)

    @classmethod
    def _resume_form(cls) -> rx.Component:
        """简历配置：技术匹配开关、PDF 附件、解析出的简历文本（可修改）。"""
        return rx.vstack(
            form_title(
                "file-text",
                "简历配置",
                "上传你的简历，用于智能匹配岗位",
            ),
            cls._switch_card(
                "简历技术匹配",
                "投递前由 AI 对比岗位要求与你的技能，只投技术对口的岗位，"
                "并在岗位列表显示匹配度",
                PlansState.resume_match,
                PlansState.set_resume_match,
                rx.cond(
                    PlansState.resume_match & (PlansState.resume_text == ""),
                    rx.text(
                        "请先上传简历或填写简历内容",
                        font_size="0.8em",
                        color="#f79009",
                    ),
                ),
                rx.cond(
                    PlansState.resume_match & ~LlmState.key_ready,
                    rx.hstack(
                        rx.text("AI 服务尚未开通，", font_size="0.8em"),
                        rx.link(
                            "去开通",
                            font_size="0.8em",
                            on_click=PlansState.set_section("llm"),
                        ),
                        spacing="0",
                        color="#f79009",
                    ),
                ),
            ),
            cls._switch_card(
                "匹配度过滤",
                "只投递匹配度达到设定分数的岗位",
                PlansState.score_filter,
                PlansState.set_score_filter,
                rx.hstack(
                    rx.text("最低匹配度", font_size="0.85em", color=TEXT),
                    rx.input(
                        disabled=~PlansState.score_filter,
                        value=PlansState.min_score.to_string(),
                        on_change=PlansState.set_min_score.debounce(500),
                        type="number",
                        min="0",
                        max="100",
                        step="5",
                        size="1",
                        width="72px",
                    ),
                    rx.text("分", font_size="0.85em", color=TEXT),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    PlansState.score_filter & ~PlansState.resume_match,
                    rx.text(
                        "请先开启上方的简历技术匹配",
                        font_size="0.8em",
                        color="#f79009",
                    ),
                ),
            ),
            rx.box(
                cls._field_label("简历附件"),
                rx.hstack(
                    rx.input(
                        value=PlansState.resume_path,
                        placeholder="尚未上传简历",
                        read_only=True,
                        flex="1",
                        size="3",
                    ),
                    rx.upload.root(
                        rx.button(
                            rx.icon("upload", size=14),
                            "上传简历",
                            variant="outline",
                            size="3",
                        ),
                        id=cls.RESUME_UPLOAD,
                        accept={"application/pdf": [".pdf"]},
                        max_files=1,
                        no_drag=True,
                        on_drop=PlansState.upload_resume(
                            rx.upload_files(upload_id=cls.RESUME_UPLOAD)
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.cond(
                    PlansState.resume_hint != "",
                    rx.text(
                        PlansState.resume_hint,
                        font_size="0.8em",
                        color=MUTED,
                        margin_top="0.35em",
                    ),
                ),
                width="100%",
            ),
            rx.box(
                cls._field_label("简历内容"),
                rx.text_area(
                    value=PlansState.resume_text,
                    on_change=PlansState.set_resume_text.debounce(500),
                    placeholder="上传后自动识别简历内容，也可以直接粘贴或修改",
                    width="100%",
                    min_height="360px",
                    resize="vertical",
                ),
                width="100%",
            ),
            width="100%",
            height="100%",
            align="start",
            spacing="5",
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
                cls._tag_input("职位名包含", "include_keywords", "如：Agent，回车添加"),
                cls._tag_input("职位名排除", "exclude_keywords", "如：实习，回车添加"),
                cls._tag_input(
                    "只看这些公司", "include_companies", "如：腾讯，回车添加"
                ),
                cls._tag_input(
                    "屏蔽这些公司", "exclude_companies", "如：外包，回车添加"
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
                    rx.text("AI 岗位筛选", font_weight="600", color=TEXT),
                    rx.text(
                        "AI 阅读岗位职责，只投递符合你求职方向的岗位",
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
            cls._field_label("求职方向"),
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
                "写清想投的方向和不想投的方向，筛选会更准确",
                font_size="0.8em",
                color=MUTED,
                margin_top="0.35em",
            ),
            rx.cond(
                LlmState.key_ready,
                rx.fragment(),
                rx.hstack(
                    rx.text("AI 服务尚未开通，", color="#d92d20"),
                    rx.link(
                        "去开通",
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
                    unit("每投"), num("rest_every", step="1"), unit("条歇"),
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
                rx.text("AI 服务", font_weight="700", font_size="1.1em", color=TEXT),
                rx.text(
                    "开通后即可使用 AI 岗位筛选、简历匹配与匹配度分析，所有方案共用",
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
                            placeholder="粘贴你的 DeepSeek API Key，以 sk- 开头",
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
                                placeholder="请先获取模型列表",
                                disabled=LlmState.model_options.length() == 0,
                                width="100%",
                            ),
                            cls._llm_button(
                                "refresh-cw",
                                "获取模型列表",
                                LlmState.fetch_models,
                                "fetch",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    cls._llm_button(
                        "plug", "测试连接", LlmState.test_connection, "test"
                    ),
                    spacing="4",
                    width="100%",
                    max_width="560px",
                ),
                hint="API Key 仅保存在本机，不会上传到任何服务器",
            ),
            width="100%",
            spacing="4",
            align="start",
            overflow_y="auto",
        )

    @staticmethod
    def _llm_button(icon: str, label: str, on_click, action: str) -> rx.Component:
        """大模型页的操作按钮；自己的请求进行中显示加载，其它请求进行中禁用。"""
        return rx.button(
            rx.icon(icon, size=16),
            label,
            on_click=on_click,
            loading=LlmState.action == action,
            disabled=LlmState.action != "",
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
                rx.dialog.description("切换、复制、删除方案，或给当前方案改个名字"),
                rx.hstack(
                    rx.input(
                        value=PlansState.rename_draft,
                        on_change=PlansState.set_rename_draft,
                        placeholder="输入新名称",
                        width="100%",
                    ),
                    rx.button(
                        "重命名", on_click=PlansState.rename_active, size="2"
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
