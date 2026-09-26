"""BOSS 自动投递：逐个点击卡片取详情，筛选复核通过后点「立即沟通」投递并入库。"""

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
from pydantic_ai.exceptions import AgentRunError

from job.boss.filters import BASE_URL, KeywordFilter, PaceProfile
from job.models.job import JobRow
from job.utils import as_dict

# 日志回调：(级别 info / ok / dup 重复 / skip 跳过 / warn, 内容)
LogSink = Callable[[str, str], Awaitable[None]]

if TYPE_CHECKING:
    from patchright.async_api import Locator, Page, Response

    from job.boss.review import JobReviewer
    from job.boss.session import BossSession

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
    """在 BossSession 的页面上自动投递：点击卡片 → 取详情 → 复核 → 立即沟通 → 入库。"""

    # 列表卡片
    CARD = "li.job-card-box, .job-card-wrapper"
    # 登录弹层
    LOGIN = ".login-dialog-wrap"
    # 右侧详情里的沟通按钮（未沟通过显示「立即沟通」，沟通过显示「继续沟通」）
    CHAT_BTN = ".job-detail-box .op-btn-chat, .job-detail-container .op-btn-chat"
    # 点「立即沟通」后弹窗里的「留在此页」
    STAY = re.compile(r"^\s*留在此页")
    # 弹窗容器
    DIALOG = "[class*='dialog']"
    # 当日投递次数用完的弹窗文案
    LIMIT = re.compile(r"上限|明天再来")
    # 沟通按钮是「继续沟通」时的结果
    CHATTED = "此前已沟通"
    # 每日投递上限
    DAILY_LIMIT = 150
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
        self._today = 0
        self._limit_hit = False
        self._day_factor = 1.0
        self._on_log: LogSink | None = None

    def request_stop(self) -> None:
        """请求停止当前投递。"""
        self._stop.set()

    async def search(
        self,
        targets: list[tuple[str, str]],
        *,
        pace: PaceProfile | None = None,
        keywords: KeywordFilter | None = None,
        reviewer: JobReviewer | None = None,
        on_job: Callable[[Job], Awaitable[None]] | None = None,
        on_log: LogSink | None = None,
    ) -> tuple[list[Job], str]:
        """按城市依次自动投递：``targets`` 为 [(城市名, 搜索 URL)]，一个城市看完换下一个。

        按节奏 ``pace`` 投递，``keywords`` 不符合的卡片跳过不点开；
        传了 ``reviewer`` 时，点开详情后再做一次 AI 复核，不通过的不投递。
        看过的岗位连同是否合适、原因一起入库，下次直接跳过；每天最多投递 ``DAILY_LIMIT`` 次。
        过程日志交给 ``on_log``（不打印到终端）。
        返回 (职位列表, 状态)；状态为 done / stopped / need_login / limit。
        """
        self._stop.clear()
        self._pace = pace or PaceProfile()
        self._keywords = keywords or KeywordFilter()
        self._reviewer = reviewer
        self._on_log = on_log
        self._saved = 0
        self._limit_hit = False
        self._today = JobRow.count_today()
        await self._log(f"今日已投递 {self._today} / {self.DAILY_LIMIT}")
        if self._today >= self.DAILY_LIMIT:
            return [], "limit"
        self._day_factor = PaceProfile.daily_factor(str(self.session.user_data_dir))
        page = await self.session.page()

        page.on("response", self._on_list_response)
        jobs: list[Job] = []
        try:
            for i, (city, url) in enumerate(targets):
                if i:
                    await self._log(f"{targets[i - 1][0]}的岗位已看完，切换到{city}")
                else:
                    await self._log(f"开始搜索{city}的岗位")
                state = await self._search_city(page, url, jobs, on_job)
                if state != "done":
                    return jobs, state
            return jobs, "done"
        finally:
            page.remove_listener("response", self._on_list_response)

    async def _search_city(
        self,
        page: Page,
        url: str,
        jobs: list[Job],
        on_job: Callable[[Job], Awaitable[None]] | None,
    ) -> str:
        """投递一个城市的搜索结果，投递成功的追加进 ``jobs``；返回状态。"""
        self._listed.clear()
        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector(self.CARD, timeout=20_000)
        except PlaywrightTimeoutError:
            need_login = await page.locator(self.LOGIN).is_visible()
            return "need_login" if need_login else "done"

        done: set[str] = set()
        idle = 0
        for _ in range(self.MAX_SCROLLS):
            seen = len(done)
            jobs.extend(await self._scrape_cards(page, done, on_job))
            idle = 0 if len(done) > seen else idle + 1
            if self._stop.is_set() or idle >= 2:
                break
            await self._load_more(page)
            await self._pause(self._pace.scroll)
        return self._end_state()

    async def _scrape_cards(
        self,
        page: Page,
        done: set[str],
        on_job: Callable[[Job], Awaitable[None]] | None,
    ) -> list[Job]:
        """逐个处理当前可见、未看过的卡片。

        库里已有的（职位 ID 或标题、公司、HR 相同）直接跳过；不符合关键词的记为不合适，
        不点开；其余点开取详情、AI 复核，合适的投递。判断结果和原因都入库。
        """
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
            name = f"{job.title} · {job.company}"
            if seen := JobRow.find_duplicate(job):
                note = f"：{seen.reason}" if seen.reason else ""
                await self._log(f"{name}（看过，{seen.result}{note}）", "dup")
                continue
            if reason := self._keywords.reject_reason(job.title, job.company):
                JobRow.record(job, suitable=False, reason=reason)
                await self._log(f"{name}（{reason}）", "skip")
                continue

            job = await self._open_detail(page, card, job)
            reason, score = "符合筛选条件", None
            if self._reviewer:
                try:
                    verdict = await self._reviewer.check(job)
                except AgentRunError as exc:
                    await self._log(f"{name}（AI 复核失败，下次再试：{exc}）", "warn")
                    await self._pause(self._pace.read)
                    continue
                reason, score = verdict.reason, verdict.score
                if not verdict.match:
                    JobRow.record(job, suitable=False, reason=reason, score=score)
                    await self._log(f"{name}（不合适：{reason}）", "skip")
                    await self._pause(self._pace.read)
                    continue

            await self._pause(self._pace.read)
            status = await self._apply(page)
            if status == self.CHATTED:
                JobRow.record(job, reason=reason, score=score)
            if status:
                level = "warn" if self._limit_hit else "skip"
                await self._log(f"{name}（{status}）", level)
                continue
            JobRow.record(job, reason=reason, score=score, applied=True)
            batch.append(job)
            self._saved += 1
            self._today += 1
            salary = job.salary or "薪资未知"
            match = "" if score is None else f" · 匹配 {score} 分"
            await self._log(f"{job.title} · {job.company} · {salary}{match}", "ok")
            if on_job is not None:
                await on_job(job)
            if self._today >= self.DAILY_LIMIT:
                self._hit_limit()
                break
            await self._rest_after(self._saved)
        return batch

    async def _apply(self, page: Page) -> str:
        """点右侧详情的「立即沟通」，再点弹窗里的「留在此页」。

        投递成功返回空串，否则返回原因；弹出次数上限对话框时同时停止投递。
        """
        button = page.locator(self.CHAT_BTN).first
        limit = page.locator(self.DIALOG).filter(has_text=self.LIMIT)
        stay = page.get_by_text(self.STAY)
        try:
            text = (await button.inner_text(timeout=5_000)).strip()
            if text != "立即沟通":
                return self.CHATTED if "继续" in text else f"沟通按钮为「{text}」"
            await button.click(timeout=5_000)
            await stay.or_(limit).first.wait_for(timeout=8_000)
            if await limit.first.is_visible():
                self._hit_limit()
                return "今日投递次数已达上限，停止投递"
            await stay.first.click(timeout=5_000)
        except PlaywrightError as exc:
            return f"投递失败：{str(exc).splitlines()[0]}"
        return ""

    def _hit_limit(self) -> None:
        """达到每日投递上限：停止投递。"""
        self._limit_hit = True
        self._stop.set()

    def _end_state(self) -> str:
        if self._limit_hit:
            return "limit"
        return "stopped" if self._stop.is_set() else "done"

    async def _rest_after(self, count: int) -> None:
        """投递一条后停顿；每满 ``rest_every`` 条再多歇一会。"""
        await self._pause(self._pace.read)
        every = self._pace.rest_every
        if every and count % every == 0:
            await self._log(f"已投递 {count} 条，休息一会")
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
        except (PlaywrightError, ValueError):
            await self._log(f"{job.title} 详情加载较慢，先按列表信息判断")
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
