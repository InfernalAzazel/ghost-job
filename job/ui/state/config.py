"""求职配置页状态。"""

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
from job.models.search import DEFAULT_MIN_SCORE, LIST_FIELDS, SearchConfigRow
from job.utils.resume import ResumePdf


class ConfigState(rx.State):
    query: str = ""
    # 目标城市，按顺序依次投递
    cities: list[str] = rx.field(default_factory=list)
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
    # 配置中心左侧当前菜单：search / llm
    section: str = "search"
    # 求职配置下的标签页：filters / resume
    search_tab: str = "filters"
    # 当前展开的下拉多选字段与搜索词
    combo_open: str = ""
    combo_query: str = ""
    # 行业级联：左栏当前大类
    industry_group: str = next(iter(Industry.groups))
    save_hint: str = "配置已自动保存"

    cities_options: list[str] = City.labels()
    job_type_options: list[str] = JobType.labels()
    salary_options: list[str] = Salary.labels()
    experience_options: list[str] = Experience.labels(skip_unlimited=True)
    education_options: list[str] = Education.labels(skip_unlimited=True)
    funding_options: list[str] = Funding.labels(skip_unlimited=True)
    scale_options: list[str] = Scale.labels(skip_unlimited=True)
    pace_options: list[str] = Pace.labels()
    industry_groups: list[str] = rx.field(default_factory=lambda: list(Industry.groups))

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

    def _load(self, config: dict) -> None:
        self.query = str(config.get("query") or "")
        self.job_type_label = JobType.label(str(config.get("job_type") or ""))
        self.salary_label = Salary.label(str(config.get("salary") or ""))
        for field in LIST_FIELDS:
            setattr(self, field, list(config.get(field) or []))
        self.pace_label = Pace.label(str(config.get("pace") or ""))
        self.pace_params = PaceProfile.from_config(config).model_dump()
        self.ai_review = bool(config.get("ai_review"))
        self.ai_requirement = str(config.get("ai_requirement") or "")
        self.resume_match = bool(config.get("resume_match"))
        self.score_filter = bool(config.get("score_filter"))
        self.min_score = int(config.get("min_score", DEFAULT_MIN_SCORE))
        self.resume_path = str(config.get("resume_path") or "")
        self.resume_text = str(config.get("resume_text") or "")
        self.resume_hint = ""

    def _save(self) -> None:
        SearchConfigRow.save(
            query=self.query,
            job_type=JobType.code(self.job_type_label),
            salary=Salary.code(self.salary_label),
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

    @rx.event
    def on_load(self):
        init_db()
        self._load(SearchConfigRow.load())
        self.save_hint = "配置已自动保存"

    @rx.event
    def set_query(self, value: str):
        self.query = value
        self._save()

    @rx.event
    def set_job_type(self, value: str):
        self.job_type_label = value
        self._save()

    @rx.event
    def set_salary(self, value: str):
        self.salary_label = value
        self._save()

    @rx.event
    def set_pace(self, value: str | list[str]):
        """切档位：预设档把明细参数刷成预设值，「自定义」保留当前参数。"""
        self.pace_label = value if isinstance(value, str) else value[0]
        code = Pace.code(self.pace_label)
        if code != PaceProfile.CUSTOM:
            self.pace_params = PaceProfile.preset(code).model_dump()
        self._save()

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
        self._save()

    @rx.event
    def set_section(self, value: str):
        self.section = value

    @rx.event
    def set_search_tab(self, value: str):
        self.search_tab = value

    @rx.event
    def set_resume_match(self, value: bool):
        self.resume_match = value
        self._save()

    @rx.event
    def set_score_filter(self, value: bool):
        self.score_filter = value
        self._save()

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
        self._save()

    @rx.event
    def set_resume_text(self, value: str):
        self.resume_text = value
        self._save()

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
        self._save()

    @rx.event
    def set_ai_review(self, value: bool):
        self.ai_review = value
        self._save()

    @rx.event
    def set_ai_requirement(self, value: str):
        self.ai_requirement = value
        self._save()

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
        self._save()

    @rx.event
    def toggle_item(self, field: str, value: str):
        """下拉多选点一项：未选则加上，已选则去掉；选完清空搜索词。"""
        if field not in LIST_FIELDS:
            return
        items = getattr(self, field)
        if value in items:
            setattr(self, field, [x for x in items if x != value])
        else:
            setattr(self, field, [*items, value])
        self.combo_query = ""
        self._save()

    @rx.event
    def add_item(self, field: str, value: str):
        """多选字段加一项（去空白、去重），如行业、关键词。"""
        value = str(value or "").strip()
        items = getattr(self, field) if field in LIST_FIELDS else None
        if items is None or not value or value in items:
            return
        setattr(self, field, [*items, value])
        self._save()

    @rx.event
    def remove_item(self, field: str, value: str):
        """多选字段删一项。"""
        if field not in LIST_FIELDS:
            return
        setattr(self, field, [x for x in getattr(self, field) if x != value])
        self._save()
