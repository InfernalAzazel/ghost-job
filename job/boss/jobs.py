"""BOSS 职位抓取：逐个点击卡片，从接口响应提取信息与详情，存入数据库。"""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from patchright.async_api import Error as PlaywrightError
from patchright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

from job.boss.filters import BASE_URL, KeywordFilter, PaceProfile
from job.models.job import JobRow
from job.utils import as_dict

# 日志回调：(级别 info / ok / skip / warn, 内容)
LogSink = Callable[[str, str], Awaitable[None]]

if TYPE_CHECKING:
    from patchright.async_api import Locator, Page, Response

    from job.boss.review import JobReviewer
    from job.boss.session import BossSession

DEFAULT_SEARCH_URL = (
    f"{BASE_URL}/web/geek/jobs?city=101280100&jobType=1901&query=ai应用开发"
)

# 字体加密字符（Unicode 私用区）
_ENCRYPTED = re.compile(r"[\ue000-\uf8ff]")


def _detail_path(*keys: str) -> AliasPath:
    """详情接口 zpData 下的字段路径。"""
    return AliasPath("zpData", *keys)


class Job(BaseModel):
    """一条职位：列表接口 joblist.json 与详情接口 job/detail.json 都能直接解析。"""

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        str_strip_whitespace=True,
        coerce_numbers_to_str=True,
    )

    job_id: str = Field("", validation_alias="encryptJobId")
    title: str = Field("", validation_alias="jobName")
    salary: str = Field("", validation_alias="salaryDesc")
    company: str = Field("", validation_alias="brandName")
    location: str = ""
    experience: str = Field("", validation_alias="jobExperience")
    education: str = Field("", validation_alias="jobDegree")
    description: str = Field(
        "",
        validation_alias=AliasChoices(
            _detail_path("jobInfo", "postDescription"),
            _detail_path("jobCard", "postDescription"),
        ),
    )
    address: str = Field(
        "",
        validation_alias=AliasChoices(
            _detail_path("jobInfo", "address"),
            _detail_path("jobCard", "address"),
        ),
    )
    hr_name: str = Field(
        "",
        validation_alias=AliasChoices("bossName", _detail_path("bossInfo", "name")),
    )
    hr_title: str = Field(
        "",
        validation_alias=AliasChoices("bossTitle", _detail_path("bossInfo", "title")),
    )

    @computed_field
    @property
    def link(self) -> str:
        """职位详情页地址。"""
        return f"{BASE_URL}/job_detail/{self.job_id}.html" if self.job_id else ""

    @model_validator(mode="before")
    @classmethod
    def _join_location(cls, data: Any) -> Any:
        """列表接口的城市 / 区 / 商圈拼成「广州·黄埔区·科学城」。"""
        if not isinstance(data, dict) or "location" in data:
            return data
        parts = (data.get(k) for k in ("cityName", "areaDistrict", "businessDistrict"))
        location = "·".join(str(p).strip() for p in parts if p)
        return {**data, "location": location} if location else data

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_empty(cls, value: Any) -> Any:
        """接口里的 null 按空字符串处理。"""
        return "" if value is None else value

    @field_validator("salary")
    @classmethod
    def _drop_encrypted_salary(cls, value: str) -> str:
        """字体加密的薪资无法还原，直接留空。"""
        return "" if _ENCRYPTED.search(value) else value

    def with_detail(self, payload: dict[str, Any]) -> Job:
        """用详情接口的非空字段（描述、地址、HR）补全当前职位。"""
        detail = Job.model_validate(payload)
        fields = ("description", "address", "hr_name", "hr_title")
        return self.model_copy(
            update={k: v for k in fields if (v := getattr(detail, k))}
        )


class JobScraper:
    """在 BossSession 的页面上抓取：点击卡片 → 取详情 → 入库。"""

    # 列表卡片
    CARD = "li.job-card-box, .job-card-wrapper"
    # 登录弹层
    LOGIN = ".login-dialog-wrap"
    # 列表接口 URL 特征
    LIST_API = "joblist.json"
    # 详情接口 URL 特征
    DETAIL_APIS = ("job/detail.json", "job/card.json")
    # 最多下滑加载次数
    MAX_SCROLLS = 20

    def __init__(self, session: BossSession) -> None:
        self.session = session
        self._stop = asyncio.Event()
        self._listed: dict[str, Job] = {}
        self._pace = PaceProfile()
        self._keywords = KeywordFilter()
        self._reviewer: JobReviewer | None = None
        self._saved = 0
        self._day_factor = 1.0
        self._on_log: LogSink | None = None

    def request_stop(self) -> None:
        """请求停止当前抓取。"""
        self._stop.set()

    async def search(
        self,
        url: str | None = None,
        *,
        pace: PaceProfile | None = None,
        keywords: KeywordFilter | None = None,
        reviewer: JobReviewer | None = None,
        on_job: Callable[[Job], Awaitable[None]] | None = None,
        on_log: LogSink | None = None,
    ) -> tuple[str, list[Job], str]:
        """按节奏 ``pace`` 抓取搜索页，``keywords`` 不符合的卡片跳过不点开。

        传了 ``reviewer`` 时，点开详情后再做一次 AI 复核，不通过的不入库。
        过程日志交给 ``on_log``（不打印到终端）。
        返回 (最终 URL, 职位列表, 状态)；状态为 done / stopped / need_login。
        """
        self._stop.clear()
        self._listed.clear()
        self._pace = pace or PaceProfile()
        self._keywords = keywords or KeywordFilter()
        self._reviewer = reviewer
        self._on_log = on_log
        self._saved = 0
        self._day_factor = PaceProfile.daily_factor(str(self.session.user_data_dir))
        await self._log(f"今日节奏系数 ×{self._day_factor:.2f}")
        page = await self.session.page()

        page.on("response", self._on_list_response)
        try:
            await page.goto(url or DEFAULT_SEARCH_URL, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector(self.CARD, timeout=20_000)
            except PlaywrightTimeoutError:
                need_login = await page.locator(self.LOGIN).is_visible()
                return page.url, [], "need_login" if need_login else "done"

            jobs: list[Job] = []
            done: set[str] = set()
            idle = 0
            for _ in range(self.MAX_SCROLLS):
                seen = len(done)
                jobs += await self._scrape_cards(page, done, on_job)
                idle = 0 if len(done) > seen else idle + 1
                if self._stop.is_set() or idle >= 2:
                    break
                await self._load_more(page)
                await self._pause(self._pace.scroll)
            return page.url, jobs, "stopped" if self._stop.is_set() else "done"
        finally:
            page.remove_listener("response", self._on_list_response)

    async def _scrape_cards(
        self,
        page: Page,
        done: set[str],
        on_job: Callable[[Job], Awaitable[None]] | None,
    ) -> list[Job]:
        """逐个处理当前可见、未看过的卡片：不符合关键词就跳过，否则点开取详情并入库。"""
        cards = page.locator(self.CARD)
        batch: list[Job] = []
        for i in range(await cards.count()):
            if self._stop.is_set():
                break
            card = cards.nth(i)
            job = await self._listed_job_for(card, i)
            if job is None or job.job_id in done:
                continue
            done.add(job.job_id)
            if reason := self._keywords.reject_reason(job.title, job.company):
                await self._log(f"{job.title} · {job.company}（{reason}）", "skip")
                continue

            job = await self._open_detail(page, card, job)
            if self._reviewer and (reason := await self._reviewer.reject_reason(job)):
                await self._log(f"{job.title} · {job.company}（{reason}）", "skip")
                await self._pause(self._pace.read)
                continue
            JobRow.upsert_from(job)
            batch.append(job)
            self._saved += 1
            salary = job.salary or "薪资未知"
            await self._log(f"{job.title} · {job.company} · {salary}", "ok")
            if on_job is not None:
                await on_job(job)
            await self._rest_after(self._saved)
        return batch

    async def _rest_after(self, count: int) -> None:
        """看完一条后停顿；每满 ``rest_every`` 条再多歇一会。"""
        await self._pause(self._pace.read)
        every = self._pace.rest_every
        if every and count % every == 0:
            await self._log(f"已入库 {count} 条，休息一会")
            await self._pause(self._pace.rest)

    async def _log(self, text: str, level: str = "info") -> None:
        """把一条过程日志交给 ``on_log``；没传回调就丢弃。"""
        if self._on_log is not None:
            await self._on_log(level, text)

    async def _pause(self, span: tuple[float, float]) -> None:
        """随机停顿（乘以今日节奏系数）；期间请求停止会立即返回。"""
        seconds = random.uniform(*span) * self._day_factor
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), seconds)

    async def _listed_job_for(self, card: Locator, index: int) -> Job | None:
        """找卡片对应的列表职位：先按 data-jobid，找不到就按顺序对应。"""
        job_id = await card.get_attribute("data-jobid")
        if job_id and job_id in self._listed:
            return self._listed[job_id]
        jobs = list(self._listed.values())
        return jobs[index] if index < len(jobs) else None

    async def _open_detail(self, page: Page, card: Locator, job: Job) -> Job:
        """点击卡片，等详情接口返回并合并进 Job。"""
        try:
            async with page.expect_response(self._is_detail, timeout=8_000) as resp:
                await card.click(timeout=5_000)
            payload = await (await resp.value).json()
        except (PlaywrightError, ValueError) as exc:
            await self._log(f"{job.title} 详情获取失败：{exc}", "warn")
            return job
        return job.with_detail(as_dict(payload))

    async def _load_more(self, page: Page) -> None:
        """滚到底部触发下一页；等不到列表接口就短暂等待。"""
        try:
            async with page.expect_response(self._is_list, timeout=8_000):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except PlaywrightError:
            await page.wait_for_timeout(1_500)

    async def _on_list_response(self, response: Response) -> None:
        """监听列表接口，把每条职位解析成 Job 按 job_id 收下。"""
        if not self._is_list(response):
            return
        try:
            payload = as_dict(await response.json())
        except (PlaywrightError, ValueError):
            return
        for item in as_dict(payload.get("zpData")).get("jobList") or []:
            try:
                job = Job.model_validate(item)
            except ValidationError as exc:
                await self._log(f"列表数据解析失败：{exc}", "warn")
                continue
            if job.job_id:
                self._listed.setdefault(job.job_id, job)

    def _is_list(self, response: Response) -> bool:
        return response.status == 200 and self.LIST_API in response.url

    def _is_detail(self, response: Response) -> bool:
        if response.status != 200:
            return False
        return any(marker in response.url for marker in self.DETAIL_APIS)
