"""Search plan configuration state."""

from __future__ import annotations

import reflex as rx
from pydantic import ValidationError

from job.boss.filters import (
    City,
    Education,
    Experience,
    Funding,
    JobType,
    Pace,
    PaceProfile,
    Salary,
    Scale,
)
from job.models import init_db
from job.models.plan import SearchPlanRow


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
    pace_label: str = Pace.default_label
    pace_params: dict[str, float] = rx.field(
        default_factory=lambda: PaceProfile().model_dump()
    )
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

    @rx.var
    def pace_custom(self) -> bool:
        """当前是否「自定义」档（只有此时明细参数可改）。"""
        return Pace.code(self.pace_label) == PaceProfile.CUSTOM

    @rx.var
    def pace_hint(self) -> str:
        """当前速率的节奏说明；预设档附带「切到自定义才能改」的提示。"""
        text = PaceProfile.model_validate(self.pace_params).describe()
        return text if self.pace_custom else f"{text}；切到「自定义」后可修改明细参数"

    def _load_from_plan(self, plan: dict) -> None:
        self.plan_id = str(plan.get("id") or "")
        self.plan_name = str(plan.get("name") or "")
        self.is_default = bool(plan.get("is_default"))
        self.query = str(plan.get("query") or "")
        self.city_label = City.label(str(plan.get("city_code") or ""))
        self.job_type_label = JobType.label(str(plan.get("job_type") or ""))
        self.salary_label = Salary.label(str(plan.get("salary") or ""))
        self.experience = list(plan.get("experience") or [])
        self.education = list(plan.get("education") or [])
        self.funding = list(plan.get("funding") or [])
        self.scale = list(plan.get("scale") or [])
        self.pace_label = Pace.label(str(plan.get("pace") or ""))
        self.pace_params = PaceProfile.from_plan(plan).model_dump()
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
            experience=self.experience,
            education=self.education,
            funding=self.funding,
            scale=self.scale,
            pace=Pace.code(self.pace_label),
            pace_params=self.pace_params,
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
            self.save_hint = "速率参数需为 0–600 之间的数字"
            return
        self.pace_params = profile.model_dump()
        self._persist_filters()

    @rx.event
    def toggle_experience(self, label: str):
        if label in self.experience:
            self.experience = [x for x in self.experience if x != label]
        else:
            self.experience = [*self.experience, label]
        self._persist_filters()

    @rx.event
    def toggle_education(self, label: str):
        if label in self.education:
            self.education = [x for x in self.education if x != label]
        else:
            self.education = [*self.education, label]
        self._persist_filters()

    @rx.event
    def toggle_funding(self, label: str):
        if label in self.funding:
            self.funding = [x for x in self.funding if x != label]
        else:
            self.funding = [*self.funding, label]
        self._persist_filters()

    @rx.event
    def toggle_scale(self, label: str):
        if label in self.scale:
            self.scale = [x for x in self.scale if x != label]
        else:
            self.scale = [*self.scale, label]
        self._persist_filters()

    @rx.event
    def remove_experience(self, label: str):
        self.experience = [x for x in self.experience if x != label]
        self._persist_filters()

    @rx.event
    def remove_education(self, label: str):
        self.education = [x for x in self.education if x != label]
        self._persist_filters()

    @rx.event
    def remove_funding(self, label: str):
        self.funding = [x for x in self.funding if x != label]
        self._persist_filters()

    @rx.event
    def remove_scale(self, label: str):
        self.scale = [x for x in self.scale if x != label]
        self._persist_filters()
