"""Search plan configuration state."""

from __future__ import annotations

import reflex as rx
from pydantic import ValidationError

from job.boss.filters import (
    City,
    Education,
    Experience,
    Funding,
    Industry,
    JobType,
    Pace,
    PaceProfile,
    Salary,
    Scale,
)
from job.models import init_db
from job.models.plan import DEFAULT_MIN_SCORE, LIST_FIELDS, SearchPlanRow
from job.utils.resume import ResumePdf


class PlansState(rx.State):
    plans: list[dict] = rx.field(default_factory=list)
    plan_names: list[str] = rx.field(default_factory=list)
    plan_id: str = ""
    plan_name: str = ""
    is_default: bool = False
    query: str = ""
    city_label: str = "广州"
    job_type_label: str = "全职"
    salary_label: str = "不限"
    experience: list[str] = rx.field(default_factory=list)
    education: list[str] = rx.field(default_factory=list)
    funding: list[str] = rx.field(default_factory=list)
    scale: list[str] = rx.field(default_factory=list)
    industry: list[str] = rx.field(default_factory=list)
    include_keywords: list[str] = rx.field(default_factory=list)
    exclude_keywords: list[str] = rx.field(default_factory=list)
    include_companies: list[str] = rx.field(default_factory=list)
    exclude_companies: list[str] = rx.field(default_factory=list)
    pace_label: str = Pace.default_label
    pace_params: dict[str, float] = rx.field(
        default_factory=lambda: PaceProfile().model_dump()
    )
    ai_review: bool = False
    ai_requirement: str = ""
    resume_match: bool = False
    score_filter: bool = False
    min_score: int = DEFAULT_MIN_SCORE
    resume_path: str = ""
    resume_text: str = ""
    resume_hint: str = ""
    # 配置中心左侧当前菜单：plan / llm
    section: str = "plan"
    # 求职方案下的标签页：filters / resume
    plan_tab: str = "filters"
    # 当前展开的下拉多选字段与搜索词
    combo_open: str = ""
    combo_query: str = ""
    # 行业级联：左栏当前大类
    industry_group: str = next(iter(Industry.groups))
    save_hint: str = "配置已自动保存"
    manager_open: bool = False
    rename_draft: str = ""
    error: str = ""

    city_options: list[str] = City.labels()
    job_type_options: list[str] = JobType.labels()
    salary_options: list[str] = Salary.labels()
    experience_options: list[str] = Experience.labels(skip_unlimited=True)
    education_options: list[str] = Education.labels(skip_unlimited=True)
    funding_options: list[str] = Funding.labels(skip_unlimited=True)
    scale_options: list[str] = Scale.labels(skip_unlimited=True)
    pace_options: list[str] = Pace.labels()
    industry_groups: list[str] = list(Industry.groups)

    @rx.var
    def industry_group_items(self) -> list[str]:
        """行业级联右栏：当前大类下的行业。"""
        return list(Industry.groups.get(self.industry_group, {}))

    @rx.var
    def industry_group_marks(self) -> dict[str, str]:
        """各大类勾选状态：all 全选 / some 部分 / none 未选。"""
        chosen = set(self.industry)
        marks = {}
        for group, names in Industry.groups.items():
            hit = len(chosen & names.keys())
            marks[group] = "all" if hit == len(names) else "some" if hit else "none"
        return marks

    @rx.var
    def industry_matches(self) -> list[str]:
        """行业搜索结果（输入搜索词时替代级联面板）。"""
        query = self.combo_query.strip().lower()
        if not query:
            return []
        return [name for name in Industry.options if query in name.lower()]

    @rx.var
    def pace_custom(self) -> bool:
        """当前是否「自定义」档（只有此时明细参数可改）。"""
        return Pace.code(self.pace_label) == PaceProfile.CUSTOM

    @rx.var
    def pace_hint(self) -> str:
        """当前速率的节奏说明；预设档附带「切到自定义才能改」的提示。"""
        text = PaceProfile.model_validate(self.pace_params).describe()
        return text if self.pace_custom else f"{text}；选择「自定义」可自行调整"

    def _load_from_plan(self, plan: dict) -> None:
        self.plan_id = str(plan.get("id") or "")
        self.plan_name = str(plan.get("name") or "")
        self.is_default = bool(plan.get("is_default"))
        self.query = str(plan.get("query") or "")
        self.city_label = City.label(str(plan.get("city_code") or ""))
        self.job_type_label = JobType.label(str(plan.get("job_type") or ""))
        self.salary_label = Salary.label(str(plan.get("salary") or ""))
        for field in LIST_FIELDS:
            setattr(self, field, list(plan.get(field) or []))
        self.pace_label = Pace.label(str(plan.get("pace") or ""))
        self.pace_params = PaceProfile.from_plan(plan).model_dump()
        self.ai_review = bool(plan.get("ai_review"))
        self.ai_requirement = str(plan.get("ai_requirement") or "")
        self.resume_match = bool(plan.get("resume_match"))
        self.score_filter = bool(plan.get("score_filter"))
        self.min_score = int(plan.get("min_score", DEFAULT_MIN_SCORE))
        self.resume_path = str(plan.get("resume_path") or "")
        self.resume_text = str(plan.get("resume_text") or "")
        self.resume_hint = ""
        self.rename_draft = self.plan_name
        self.error = ""

    def _refresh_plans(self) -> None:
        self.plans = SearchPlanRow.list_dicts()
        self.plan_names = [str(p.get("name") or "") for p in self.plans]

    def _persist_filters(self) -> None:
        if not self.plan_id:
            return
        city_code = City.code(self.city_label)
        job_type = JobType.code(self.job_type_label)
        salary = Salary.code(self.salary_label)
        SearchPlanRow.update_filters(
            self.plan_id,
            query=self.query,
            city_code=city_code,
            job_type=job_type,
            salary=salary,
            pace=Pace.code(self.pace_label),
            pace_params=self.pace_params,
            ai_review=self.ai_review,
            ai_requirement=self.ai_requirement,
            resume_match=self.resume_match,
            score_filter=self.score_filter,
            min_score=self.min_score,
            resume_path=self.resume_path,
            resume_text=self.resume_text,
            **{field: getattr(self, field) for field in LIST_FIELDS},
        )
        self.save_hint = "配置已自动保存"
        self._refresh_plans()

    @rx.event
    def on_load(self):
        init_db()
        plan = SearchPlanRow.get_active_dict()
        self._load_from_plan(plan)
        self._refresh_plans()
        self.save_hint = "配置已自动保存"

    @rx.event
    def select_plan(self, plan_id: str):
        if not plan_id or plan_id == self.plan_id:
            return
        plan = SearchPlanRow.set_active(plan_id)
        self._load_from_plan(plan)
        self._refresh_plans()

    @rx.event
    def select_plan_by_name(self, name: str):
        match = next((p for p in self.plans if p.get("name") == name), None)
        if match is None:
            return
        plan_id = str(match["id"])
        if plan_id == self.plan_id:
            return
        plan = SearchPlanRow.set_active(plan_id)
        self._load_from_plan(plan)
        self._refresh_plans()

    @rx.event
    def create_plan(self):
        plan = SearchPlanRow.create("新方案", copy_from_id=self.plan_id or None)
        self._load_from_plan(plan)
        self._refresh_plans()
        self.save_hint = "已新建方案"

    @rx.event
    def open_manager(self):
        self.manager_open = True
        self.rename_draft = self.plan_name
        self._refresh_plans()

    @rx.event
    def close_manager(self):
        self.manager_open = False
        self.error = ""

    @rx.event
    def set_manager_open(self, is_open: bool):
        self.manager_open = is_open
        if not is_open:
            self.error = ""
        else:
            self.rename_draft = self.plan_name
            self._refresh_plans()

    @rx.event
    def set_rename_draft(self, value: str):
        self.rename_draft = value

    @rx.event
    def rename_active(self):
        if not self.plan_id:
            return
        plan = SearchPlanRow.rename(self.plan_id, self.rename_draft)
        self._load_from_plan(plan)
        self._refresh_plans()
        self.save_hint = "已重命名"

    @rx.event
    def rename_plan(self, plan_id: str):
        name = self.rename_draft.strip()
        if not name:
            self.error = "名称不能为空"
            return
        plan = SearchPlanRow.rename(plan_id, name)
        if plan_id == self.plan_id:
            self._load_from_plan(plan)
        self._refresh_plans()
        self.save_hint = "已重命名"
        self.error = ""

    @rx.event
    def set_default(self, plan_id: str):
        plan = SearchPlanRow.set_default(plan_id)
        if plan_id == self.plan_id:
            self.is_default = True
        self._refresh_plans()
        if plan_id == self.plan_id:
            self._load_from_plan(SearchPlanRow.get_dict(plan_id) or plan)
        self.save_hint = "已设为默认"

    @rx.event
    def duplicate(self, plan_id: str):
        plan = SearchPlanRow.duplicate(plan_id)
        self._load_from_plan(plan)
        self._refresh_plans()
        self.save_hint = "已复制方案"

    @rx.event
    def delete(self, plan_id: str):
        try:
            plan = SearchPlanRow.delete(plan_id)
            self._load_from_plan(plan)
            self._refresh_plans()
            self.save_hint = "已删除方案"
            self.error = ""
        except ValueError as exc:
            self.error = str(exc)

    @rx.event
    def set_query(self, value: str):
        self.query = value
        self._persist_filters()

    @rx.event
    def set_city(self, value: str):
        self.city_label = value
        self._persist_filters()

    @rx.event
    def set_job_type(self, value: str):
        self.job_type_label = value
        self._persist_filters()

    @rx.event
    def set_salary(self, value: str):
        self.salary_label = value
        self._persist_filters()

    @rx.event
    def set_pace(self, value: str | list[str]):
        """切档位：预设档把明细参数刷成预设值，「自定义」保留当前参数。"""
        self.pace_label = value if isinstance(value, str) else value[0]
        code = Pace.code(self.pace_label)
        if code != PaceProfile.CUSTOM:
            self.pace_params = PaceProfile.preset(code).model_dump()
        self._persist_filters()

    @rx.event
    def set_pace_param(self, key: str, value: str):
        """改某个明细参数（仅「自定义」档）：校验通过就保存。"""
        if Pace.code(self.pace_label) != PaceProfile.CUSTOM:
            return
        try:
            profile = PaceProfile.model_validate({**self.pace_params, key: value})
        except ValidationError:
            self.save_hint = "请输入 0–600 之间的数字"
            return
        self.pace_params = profile.model_dump()
        self._persist_filters()

    @rx.event
    def set_section(self, value: str):
        self.section = value

    @rx.event
    def set_plan_tab(self, value: str):
        self.plan_tab = value

    @rx.event
    def set_resume_match(self, value: bool):
        self.resume_match = value
        self._persist_filters()

    @rx.event
    def set_score_filter(self, value: bool):
        self.score_filter = value
        self._persist_filters()

    @rx.event
    def set_min_score(self, value: str):
        """改最低匹配度：需为 0–100 的整数。"""
        try:
            score = int(value)
        except ValueError:
            score = -1
        if not 0 <= score <= 100:
            self.save_hint = "请输入 0–100 之间的整数"
            return
        self.min_score = score
        self._persist_filters()

    @rx.event
    def set_resume_text(self, value: str):
        self.resume_text = value
        self._persist_filters()

    @rx.event
    async def upload_resume(self, files: list[rx.UploadFile]):
        """选择 PDF：存到本地数据目录并解析成文本，覆盖当前简历内容。"""
        if not files:
            return
        file = files[0]
        data = await file.read()
        try:
            text = ResumePdf.extract_text(data)
        except ValueError as exc:
            self.resume_hint = str(exc)
            return
        self.resume_path = str(ResumePdf.save(file.name or "resume.pdf", data))
        self.resume_text = text
        self.resume_hint = (
            f"已识别简历内容，共 {len(text)} 字"
            if text
            else "未能识别简历文字，请直接粘贴简历内容"
        )
        self._persist_filters()

    @rx.event
    def set_ai_review(self, value: bool):
        self.ai_review = value
        self._persist_filters()

    @rx.event
    def set_ai_requirement(self, value: str):
        self.ai_requirement = value
        self._persist_filters()

    @rx.event
    def open_combo(self, field: str):
        """展开某个下拉多选，清空搜索词。"""
        self.combo_open = field
        self.combo_query = ""

    @rx.event
    def close_combo(self):
        self.combo_open = ""
        self.combo_query = ""

    @rx.event
    def set_combo_query(self, value: str):
        self.combo_query = value

    @rx.event
    def set_industry_group(self, group: str):
        self.industry_group = group

    @rx.event
    def toggle_industry_group(self, group: str):
        """勾大类：已全选则全部取消，否则补齐该大类下所有行业。"""
        names = list(Industry.groups.get(group, {}))
        missing = [n for n in names if n not in self.industry]
        if missing:
            self.industry = [*self.industry, *missing]
        else:
            self.industry = [x for x in self.industry if x not in names]
        self.industry_group = group
        self._persist_filters()

    @rx.event
    def toggle_item(self, field: str, value: str):
        """下拉多选点一项：未选则加上，已选则去掉。"""
        if field not in LIST_FIELDS:
            return
        items = getattr(self, field)
        if value in items:
            setattr(self, field, [x for x in items if x != value])
        else:
            setattr(self, field, [*items, value])
        self._persist_filters()

    @rx.event
    def add_item(self, field: str, value: str):
        """多选字段加一项（去空白、去重），如行业、关键词。"""
        value = str(value or "").strip()
        items = getattr(self, field) if field in LIST_FIELDS else None
        if items is None or not value or value in items:
            return
        setattr(self, field, [*items, value])
        self._persist_filters()

    @rx.event
    def remove_item(self, field: str, value: str):
        """多选字段删一项。"""
        if field not in LIST_FIELDS:
            return
        setattr(self, field, [x for x in getattr(self, field) if x != value])
        self._persist_filters()
