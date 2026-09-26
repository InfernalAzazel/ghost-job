"""BOSS 直聘筛选选项与搜索 URL 拼装。"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from job.boss.city_codes import CITY_OPTIONS
from job.boss.industry_codes import INDUSTRY_GROUPS, INDUSTRY_OPTIONS

BASE_URL = "https://www.zhipin.com"


class FilterField:
    """单项筛选：展示文案 → BOSS 参数码。"""

    options: ClassVar[dict[str, str]] = {}
    default_label: ClassVar[str] = "不限"

    @classmethod
    def code(cls, label: str) -> str:
        """文案 → 参数码；未知文案返回空串。"""
        return cls.options.get(label, "")

    @classmethod
    def label(cls, code: str) -> str:
        """参数码 → 文案；未知码返回默认文案。"""
        for text, value in cls.options.items():
            if value == code:
                return text
        return cls.default_label

    @classmethod
    def codes(cls, labels: Sequence[str] | None) -> list[str]:
        """多选文案 → 非空参数码列表（跳过「不限」等空码）。"""
        if not labels:
            return []
        out: list[str] = []
        for text in labels:
            value = cls.code(text)
            if value:
                out.append(value)
        return out

    @classmethod
    def labels(cls, *, skip_unlimited: bool = False) -> list[str]:
        """全部展示文案；``skip_unlimited`` 时去掉「不限」。"""
        if not skip_unlimited:
            return list(cls.options)
        return [k for k in cls.options if k != "不限"]


class City(FilterField):
    """工作城市（``city``）；选项见 ``city_codes.CITY_OPTIONS``。"""

    default_label: ClassVar[str] = "广州"
    options: ClassVar[dict[str, str]] = CITY_OPTIONS


class JobType(FilterField):
    """求职类型（``jobType``）。"""

    options: ClassVar[dict[str, str]] = {
        "不限": "",
        "全职": "1901",
        "兼职": "1903",
    }


class Salary(FilterField):
    """薪资范围（``salary``）。"""

    options: ClassVar[dict[str, str]] = {
        "不限": "",
        "3K以下": "402",
        "3-5K": "403",
        "5-10K": "404",
        "10-20K": "405",
        "20-50K": "406",
        "50K以上": "407",
    }


class Experience(FilterField):
    """工作经验（``experience``，可多选）。"""

    options: ClassVar[dict[str, str]] = {
        "不限": "",
        "在校生": "108",
        "应届生": "102",
        "经验不限": "101",
        "1年以内": "103",
        "1-3年": "104",
        "3-5年": "105",
        "5-10年": "106",
        "10年以上": "107",
    }


class Education(FilterField):
    """学历要求（``degree``，可多选）。"""

    options: ClassVar[dict[str, str]] = {
        "不限": "",
        "初中及以下": "209",
        "中专/中技": "208",
        "高中": "206",
        "大专": "202",
        "本科": "203",
        "硕士": "204",
        "博士": "205",
    }


class Funding(FilterField):
    """融资阶段（``stage``，可多选）。"""

    options: ClassVar[dict[str, str]] = {
        "不限": "",
        "未融资": "801",
        "天使轮": "802",
        "A轮": "803",
        "B轮": "804",
        "C轮": "805",
        "D轮及以上": "806",
        "已上市": "807",
        "不需要融资": "808",
    }


class Scale(FilterField):
    """公司规模（``scale``，可多选）。"""

    options: ClassVar[dict[str, str]] = {
        "不限": "",
        "0-20人": "301",
        "20-99人": "302",
        "100-499人": "303",
        "500-999人": "304",
        "1000-9999人": "305",
        "10000人以上": "306",
    }


class Industry(FilterField):
    """行业（``industry``，可多选）；选项见 ``industry_codes``。"""

    # 大类 → {行业名: 行业编码}，给下拉分组用
    groups: ClassVar[dict[str, dict[str, str]]] = INDUSTRY_GROUPS
    options: ClassVar[dict[str, str]] = INDUSTRY_OPTIONS


class KeywordFilter(BaseModel):
    """本地关键词过滤（BOSS URL 不支持）：按列表数据判断，不符合的卡片不点开。"""

    # 职位名需包含其中任一词（空表示不限）
    include: list[str] = []
    # 职位名包含其中任一词就跳过
    exclude: list[str] = []
    # 公司名需包含其中任一词（空表示不限）
    include_companies: list[str] = []
    # 公司名包含其中任一词就跳过
    exclude_companies: list[str] = []

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> KeywordFilter:
        """从求职配置取四组关键词。"""
        return cls(
            include=config.get("include_keywords") or [],
            exclude=config.get("exclude_keywords") or [],
            include_companies=config.get("include_companies") or [],
            exclude_companies=config.get("exclude_companies") or [],
        )

    def reject_reason(self, title: str, company: str) -> str:
        """不符合时返回原因，符合返回空串（不区分大小写）。"""
        checks = (
            (title, self.include, True, "职位名不含包含词"),
            (title, self.exclude, False, "职位名含排除词"),
            (company, self.include_companies, True, "公司名不含包含词"),
            (company, self.exclude_companies, False, "公司名含排除词"),
        )
        for text, words, must_hit, reason in checks:
            if words and self._hit(text, words) != must_hit:
                return reason
        return ""

    @staticmethod
    def _hit(text: str, words: list[str]) -> bool:
        """text 是否包含任一关键词。"""
        lowered = text.lower()
        return any(w.lower() in lowered for w in words)


class Pace(FilterField):
    """投递速率（不进 URL）：文案 → 节奏码，节奏细节见 ``PaceProfile``。"""

    default_label: ClassVar[str] = "正常"
    options: ClassVar[dict[str, str]] = {
        "慢速": "slow",
        "正常": "normal",
        "快速": "fast",
        "自定义": "custom",
    }


class PaceProfile(BaseModel):
    """投递节奏明细：各步骤之后的随机停顿（秒），默认值即「正常」。"""

    model_config = ConfigDict(frozen=True)

    # 自定义速率码：此时读配置里保存的明细参数
    CUSTOM: ClassVar[str] = "custom"
    # 预设速率码 → 与默认值不同的参数
    PRESETS: ClassVar[dict[str, dict[str, float]]] = {
        "slow": {
            "read_min": 6,
            "read_max": 15,
            "scroll_min": 4,
            "scroll_max": 8,
            "rest_every": 10,
            "rest_min": 60,
            "rest_max": 120,
        },
        "normal": {},
        "fast": {
            "read_min": 1,
            "read_max": 2.5,
            "scroll_min": 1,
            "scroll_max": 2,
            "rest_every": 0,
        },
    }

    # 看完一条详情后最少停顿
    read_min: float = Field(3, ge=0, le=600)
    # 看完一条详情后最多停顿
    read_max: float = Field(8, ge=0, le=600)
    # 下滑翻页后最少停顿
    scroll_min: float = Field(2, ge=0, le=600)
    # 下滑翻页后最多停顿
    scroll_max: float = Field(5, ge=0, le=600)
    # 每投递多少条歇一次（0 表示不歇）
    rest_every: int = Field(15, ge=0, le=1000)
    # 歇一次最少多久
    rest_min: float = Field(30, ge=0, le=600)
    # 歇一次最多多久
    rest_max: float = Field(60, ge=0, le=600)

    @staticmethod
    def daily_factor(account: str, day: date | None = None) -> float:
        """按「账号 + 日期」算当天的节奏系数（0.85–1.2），同一天多次调用结果相同。"""
        today = datetime.now().astimezone().date()
        seed = f"{account}|{(day or today).isoformat()}"
        return random.Random(seed).uniform(0.85, 1.2)

    @classmethod
    def preset(cls, code: str) -> PaceProfile:
        """预设速率码 → 节奏；未知码按「正常」。"""
        return cls(**cls.PRESETS.get(code, {}))

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> PaceProfile:
        """求职配置 → 节奏：自定义读明细参数，否则按预设；参数不合法退回「正常」。"""
        code = str(config.get("pace") or "")
        if code != cls.CUSTOM:
            return cls.preset(code)
        try:
            return cls.model_validate(config.get("pace_params") or {})
        except ValidationError:
            return cls()

    @property
    def read(self) -> tuple[float, float]:
        """看完一条后的停顿区间。"""
        return self._sorted(self.read_min, self.read_max)

    @property
    def scroll(self) -> tuple[float, float]:
        """翻页后的停顿区间。"""
        return self._sorted(self.scroll_min, self.scroll_max)

    @property
    def rest(self) -> tuple[float, float]:
        """歇一次的时长区间。"""
        return self._sorted(self.rest_min, self.rest_max)

    def describe(self) -> str:
        """给配置页看的一句话说明。"""
        read, scroll = self._span(self.read), self._span(self.scroll)
        text = f"每条停 {read} 秒，翻页停 {scroll} 秒"
        if self.rest_every:
            text += f"，每 {self.rest_every} 条歇 {self._span(self.rest)} 秒"
        return text

    @staticmethod
    def _sorted(low: float, high: float) -> tuple[float, float]:
        """最小 / 最大填反了也照样成区间。"""
        return (low, high) if low <= high else (high, low)

    @staticmethod
    def _span(span: tuple[float, float]) -> str:
        """(3, 8) → "3–8"。"""
        return f"{span[0]:g}–{span[1]:g}"


class ReplyPaceProfile(BaseModel):
    """自动回复节奏：只在回复时段内回复，收到消息后随机等一会儿，回复几条歇一次；默认值即「正常」。"""

    model_config = ConfigDict(frozen=True)

    CUSTOM: ClassVar[str] = PaceProfile.CUSTOM
    # 预设速率码（与投递节奏同一套档位）→ 与默认值不同的参数
    PRESETS: ClassVar[dict[str, dict[str, float]]] = {
        "slow": {
            "start_hour": 9,
            "end_hour": 21,
            "delay_min": 120,
            "delay_max": 600,
            "rest_every": 5,
            "rest_min": 10,
            "rest_max": 30,
        },
        "normal": {},
        "fast": {
            "start_hour": 8,
            "end_hour": 23,
            "delay_min": 10,
            "delay_max": 60,
            "rest_every": 0,
        },
    }

    # 每天几点开始回复
    start_hour: int = Field(9, ge=0, le=23)
    # 每天几点停止回复（不含该整点）
    end_hour: int = Field(22, ge=1, le=24)
    # 收到消息后最少等多久再回（秒）
    delay_min: float = Field(30, ge=0, le=3600)
    # 收到消息后最多等多久再回（秒）
    delay_max: float = Field(180, ge=0, le=3600)
    # 每回复多少条歇一次（0 表示不歇）
    rest_every: int = Field(10, ge=0, le=1000)
    # 歇一次最少多久（分钟）
    rest_min: float = Field(5, ge=0, le=600)
    # 歇一次最多多久（分钟）
    rest_max: float = Field(15, ge=0, le=600)

    @model_validator(mode="after")
    def _check_hours(self) -> ReplyPaceProfile:
        if self.end_hour <= self.start_hour:
            raise ValueError("停止回复的时间需晚于开始时间")
        return self

    @classmethod
    def preset(cls, code: str) -> ReplyPaceProfile:
        """预设速率码 → 节奏；未知码按「正常」。"""
        return cls(**cls.PRESETS.get(code, {}))

    @classmethod
    def from_saved(cls, code: str, params: Mapping[str, Any]) -> ReplyPaceProfile:
        """保存的档位与明细 → 节奏：自定义读明细，否则按预设；明细不合法退回「正常」。"""
        if code != cls.CUSTOM:
            return cls.preset(code)
        try:
            return cls.model_validate(params)
        except ValidationError:
            return cls()

    def is_active(self, now: datetime) -> bool:
        """``now`` 是否在回复时段内。"""
        return self.start_hour <= now.hour < self.end_hour

    def next_active(self, now: datetime) -> datetime:
        """下一次可以回复的时间：时段内就是 ``now``，否则是下一个开始整点。"""
        if self.is_active(now):
            return now
        start = now.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        return start if now < start else start + timedelta(days=1)

    @property
    def delay(self) -> tuple[float, float]:
        """收到消息后的等待区间（秒）。"""
        return PaceProfile._sorted(self.delay_min, self.delay_max)

    @property
    def rest(self) -> tuple[float, float]:
        """歇一次的时长区间（分钟）。"""
        return PaceProfile._sorted(self.rest_min, self.rest_max)

    def describe(self) -> str:
        """给配置页看的一句话说明。"""
        span = PaceProfile._span
        text = (
            f"每天 {self.start_hour}:00–{self.end_hour}:00 回复，"
            f"收到消息后等 {span(self.delay)} 秒再回"
        )
        if self.rest_every:
            text += f"，每回 {self.rest_every} 条歇 {span(self.rest)} 分钟"
        return text + "；其他时间收到的消息顺延到下一个回复时段"


class Defaults:
    """首次使用时的默认筛选值。"""

    QUERY = "ai应用开发"
    CITIES = (City.default_label,)
    JOB_TYPE = JobType.code("全职")
    SALARY = ""
    PACE = Pace.code(Pace.default_label)


class SearchUrl:
    """根据求职配置拼装 BOSS geek jobs 搜索 URL。"""

    PATH = f"{BASE_URL}/web/geek/jobs"

    @classmethod
    def by_city(cls, config: Mapping[str, Any]) -> list[tuple[str, str]]:
        """按所选城市顺序生成 [(城市名, 搜索 URL)]；未选城市时用默认城市。"""
        cities = [c for c in config.get("cities") or [] if City.code(c)] or list(Defaults.CITIES)
        return [(city, cls.build(config, city)) for city in cities]

    @classmethod
    def build(cls, config: Mapping[str, Any], city: str) -> str:
        """拼装某个城市的搜索 URL。"""

        def _get(key: str) -> str:
            return str(config.get(key) or "").strip()

        def _list(key: str) -> list[str]:
            raw = config.get(key) or []
            return [] if isinstance(raw, str) else list(raw)

        params: dict[str, str] = {}
        query = _get("query")
        city_code = City.code(city)
        job_type = _get("job_type")
        salary = _get("salary")

        if query:
            params["query"] = query
        if city_code:
            params["city"] = city_code
        if job_type:
            params["jobType"] = job_type
        if salary:
            params["salary"] = salary

        for param, field, values in (
            ("experience", Experience, _list("experience")),
            ("degree", Education, _list("education")),
            ("stage", Funding, _list("funding")),
            ("scale", Scale, _list("scale")),
            ("industry", Industry, _list("industry")),
        ):
            codes = field.codes(values)
            if codes:
                params[param] = ",".join(codes)

        return f"{cls.PATH}?{urlencode(params)}"
