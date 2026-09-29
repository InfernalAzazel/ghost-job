"""查企业：打开 BOSS 公司主页读工商信息，用公司全称上网搜负面信息，再让大模型评估风险。

点「查企业」才会触发，结果按公司 ID 存进 ``CompanyRow``，岗位和会话共用。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

from ddgs import DDGS
from ddgs.exceptions import DDGSException
from patchright.async_api import Error as PlaywrightError
from pydantic import BaseModel, Field
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

from job.boss.filters import BASE_URL
from job.models.company import CompanyRow
from job.models.job import JobRow
from job.models.setting import LlmSettings

if TYPE_CHECKING:
    from patchright.async_api import Page

    from job.boss.session import BossSession


class SearchHit(BaseModel):
    """一条搜索结果。"""

    title: str = ""
    href: str = ""
    body: str = ""
    # 命中的是哪组关键词
    query: str = ""


class CompanyPoint(BaseModel):
    """评估依据。"""

    text: str = Field(description="一条依据，30 字以内")
    href: str = Field(
        default="", description="依据来自哪条搜索结果的链接；来自工商信息时留空"
    )


# 文档字符串与字段说明会作为输出要求发给模型
class CompanyVerdict(BaseModel):
    """对这家公司的风险评估。"""

    risk: Literal["low", "medium", "high", "unknown"] = Field(
        description=(
            "low：没有与该公司相关的负面信息；medium：有少量或较早的劳动纠纷、差评；"
            "high：欠薪、大规模裁员、失信被执行、诈骗或经营异常等严重问题；"
            "unknown：搜索结果几乎都与该公司无关，无法判断"
        )
    )
    summary: str = Field(description="一句话结论，40 字以内")
    points: list[CompanyPoint] = Field(
        default_factory=list, description="最多 5 条依据"
    )


class CompanyPage:
    """在已登录的浏览器里另开标签页读公司信息，读完就关，不打扰投递和回复。"""

    # 岗位详情页里的公司链接
    COMPANY_LINK = ".company-info a[href*='/gongsi/']"
    # 公司主页「工商信息」的每一项：<li><span class="t">企业名称：</span>值</li>
    BUSINESS = ".business-detail li"
    LINK_ID = re.compile(r"/gongsi/(?!job/)([\w~-]+)\.html")
    # 页面最长等待（毫秒）
    TIMEOUT = 20_000

    def __init__(self, session: BossSession) -> None:
        self._session = session

    @staticmethod
    def url(brand_id: str) -> str:
        return f"{BASE_URL}/gongsi/{brand_id}.html"

    @classmethod
    def brand_id_from(cls, href: str) -> str:
        """公司链接 → 公司 ID；不是公司主页链接返回空串。"""
        match = cls.LINK_ID.search(href)
        return match.group(1) if match else ""

    @staticmethod
    def parse_business(pairs: list[list[str]]) -> dict[str, str]:
        """[[字段名：, 值]] → {字段名: 值}，空值和「-」不要。"""
        info = {}
        for label, value in pairs:
            key, value = label.strip().rstrip("：:"), value.strip()
            if key and value and value != "-":
                info[key] = value
        return info

    async def brand_id(self, job_link: str) -> str:
        """打开岗位详情页，从公司链接里取公司 ID；找不到返回空串。"""
        if not job_link:
            return ""

        async def read(page: Page) -> str:
            link = await page.wait_for_selector(self.COMPANY_LINK, timeout=self.TIMEOUT)
            return (
                self.brand_id_from(await link.get_attribute("href") or "")
                if link
                else ""
            )

        return await self._read(job_link, read, "")

    async def business(self, brand_id: str) -> dict[str, str]:
        """打开公司主页读工商信息；页面上没有时返回空字典。"""

        async def read(page: Page) -> dict[str, str]:
            await page.wait_for_selector(self.BUSINESS, timeout=self.TIMEOUT)
            pairs = await page.eval_on_selector_all(
                self.BUSINESS,
                """items => items.map(li => {
                    const label = li.querySelector('.t');
                    const name = label ? label.innerText : '';
                    return [name, li.innerText.slice(name.length)];
                })""",
            )
            return self.parse_business(pairs)

        return await self._read(self.url(brand_id), read, {})

    async def _read[T](
        self, url: str, read: Callable[[Page], Awaitable[T]], empty: T
    ) -> T:
        context = await self._session.open()
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            return await read(page)
        except PlaywrightError:
            return empty
        finally:
            await page.close()


class CompanySearch:
    """用 ddgs 以公司全称逐组搜负面关键词，合并去重。

    关键词要短：堆太多词搜出来的都是通用维权文章；多组并行也会被搜索服务排队，不比逐组快。
    """

    QUERIES: ClassVar[tuple[str, ...]] = ("欠薪 裁员", "怎么样", "失信 被执行")
    backend: str = "yandex"
    region: str = "cn-zh"
    max_results: int = 8
    timeout: int = 20

    def __init__(
        self, text: Callable[[str], list[dict[str, Any]]] | None = None
    ) -> None:
        # 测试时可换成假的搜索函数
        self._text = text or self._ddgs

    def _ddgs(self, query: str) -> list[dict[str, Any]]:
        return DDGS(timeout=self.timeout).text(
            query,
            region=self.region,
            backend=self.backend,
            max_results=self.max_results,
        )

    async def search(
        self, name: str, on_step: Callable[[str], Awaitable[None]] | None = None
    ) -> list[SearchHit]:
        """搜索失败的组跳过；全部失败时抛 ``RuntimeError``。"""
        hits: dict[str, SearchHit] = {}
        failed = 0
        for i, query in enumerate(self.QUERIES, 1):
            if on_step is not None:
                await on_step(
                    f"正在网上搜索「{name}」（{i}/{len(self.QUERIES)}：{query}）…"
                )
            try:
                items = await asyncio.to_thread(self._text, f"{name} {query}")
            except (DDGSException, OSError, RuntimeError):
                failed += 1
                continue
            for item in items:
                hit = SearchHit(
                    title=str(item.get("title") or ""),
                    href=str(item.get("href") or ""),
                    body=str(item.get("body") or ""),
                    query=query,
                )
                if hit.href and hit.href not in hits:
                    hits[hit.href] = hit
        if failed == len(self.QUERIES):
            raise RuntimeError("网络搜索失败，请稍后重试")
        return list(hits.values())


class CompanyReviewer(BaseModel):
    """让大模型结合工商信息和搜索结果评估公司风险；服务来自配置中心「AI 服务」。"""

    INSTRUCTIONS: ClassVar[str] = (
        "你是求职者的背景调查助手，评估这家公司是否值得去面试。"
        "搜索结果里常混有同名或名字相近的其他公司、与该公司无关的通用维权文章，"
        "只采信明确指向该公司（全称或简称与所在地、行业一致）的内容，其余忽略。"
        "结合工商信息判断：经营状态异常（吊销、注销、停业）、成立时间很短或注册资本极低也要提示。"
        "依据要具体，能对应到搜索结果的附上它的链接。"
    )

    llm: LlmSettings = Field(default_factory=LlmSettings)
    timeout: float = 60

    @cached_property
    def agent(self) -> Agent[None, CompanyVerdict]:
        """结论走提示词 JSON 输出，理由同 ``JobReviewer.agent``。"""
        model = OpenAIChatModel(self.llm.model, provider=self.llm.provider)
        return Agent(
            model,
            output_type=PromptedOutput(CompanyVerdict),
            instructions=self.INSTRUCTIONS,
            model_settings=OpenAIChatModelSettings(
                thinking=False, temperature=0, timeout=self.timeout
            ),
        )

    async def review(
        self, name: str, full_name: str, info: dict[str, str], hits: list[SearchHit]
    ) -> CompanyVerdict:
        """接口出错或输出不合规时抛 ``AgentRunError``。"""
        result = await self.agent.run(self._prompt(name, full_name, info, hits))
        return result.output

    def _prompt(
        self, name: str, full_name: str, info: dict[str, str], hits: list[SearchHit]
    ) -> str:
        business = "\n".join(f"{k}：{v}" for k, v in info.items()) or "未取得工商信息"
        results = (
            "\n\n".join(
                f"[{i}] {h.title}\n{h.href}\n{h.body}" for i, h in enumerate(hits, 1)
            )
            or "没有搜索结果"
        )
        return (
            f"公司简称：{name}\n企业全称：{full_name or '未知'}\n\n"
            f"工商信息：\n{business}\n\n搜索结果：\n{results}"
        )


class Pages(Protocol):
    async def brand_id(self, job_link: str) -> str: ...

    async def business(self, brand_id: str) -> dict[str, str]: ...


class Searcher(Protocol):
    async def search(
        self, name: str, on_step: Callable[[str], Awaitable[None]] | None = None
    ) -> list[SearchHit]: ...


class Reviewer(Protocol):
    async def review(
        self, name: str, full_name: str, info: dict[str, str], hits: list[SearchHit]
    ) -> CompanyVerdict: ...


class CompanyChecker:
    """串起整个查询：公司 ID → 工商信息 → 网上搜索 → AI 评估 → 入库。"""

    NO_AI: ClassVar[str] = "未开通 AI 服务，只展示工商信息和搜索结果"

    def __init__(
        self, page: Pages, search: Searcher, reviewer: Reviewer | None
    ) -> None:
        self._page = page
        self._search = search
        self._reviewer = reviewer

    async def check(
        self, job_uid: str, on_step: Callable[[str], Awaitable[None]]
    ) -> str:
        """查这个岗位所属的公司，返回公司 ID；找不到公司或搜索全部失败时抛 ``RuntimeError``。"""
        job = JobRow.get_dict(job_uid)
        if job is None:
            raise RuntimeError("岗位不存在")
        name, brand_id = job["company"], job["brandId"]
        if not brand_id:
            await on_step("正在打开岗位详情页，查找公司主页…")
            brand_id = await self._page.brand_id(job["link"])
            if not brand_id:
                raise RuntimeError("岗位详情页里没有找到公司主页，岗位可能已下线")
            JobRow.set_brand_id(job_uid, brand_id)

        await on_step("正在读取工商信息…")
        info = await self._page.business(brand_id)
        full_name = info.get("企业名称", "")

        hits = await self._search.search(full_name or name, on_step)

        if self._reviewer is None:
            verdict = CompanyVerdict(risk="unknown", summary=self.NO_AI)
        else:
            await on_step("AI 正在分析…")
            verdict = await self._reviewer.review(name, full_name, info, hits)

        CompanyRow.save(
            brand_id,
            name=name,
            full_name=full_name,
            info=info,
            hits=[h.model_dump() for h in hits],
            risk=verdict.risk,
            summary=verdict.summary,
            points=[p.model_dump() for p in verdict.points],
        )
        return brand_id
