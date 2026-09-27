"""BOSS 聊天：守着聊天页，HR 发来新消息时按提示词和简历自动回复；消息入库并关联岗位。"""

from __future__ import annotations

import asyncio
import contextlib
import random
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from patchright.async_api import Error as PlaywrightError
from patchright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import (
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

from job.boss.filters import BASE_URL, KeywordFilter, ReplyPaceProfile
from job.boss.jobs import Job, LogSink
from job.models.chat import ChatMessage, ChatMessageRow, ChatRejectionRow
from job.models.job import JobRow
from job.models.setting import LlmSettings
from job.utils import as_dict, log

if TYPE_CHECKING:
    from patchright.async_api import Page, Response

    from job.boss.review import JobReviewer
    from job.boss.session import BossSession


class Friend(BaseModel):
    """会话列表接口 getGeekFriendList.json 里的一位 HR。"""

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
        str_strip_whitespace=True,
        coerce_numbers_to_str=True,
    )

    boss_id: str = Field("", validation_alias="encryptBossId")
    # HR 的数字 ID：最后一条消息的发送方是它，说明在等我回复
    uid: str = ""
    name: str = ""
    title: str = ""
    company: str = Field("", validation_alias="brandName")
    job_id: str = Field("", validation_alias="encryptJobId")
    unread: int = Field(0, validation_alias="unreadMsgCount")
    last_from: str = Field("", validation_alias=AliasPath("lastMessageInfo", "fromId"))
    last_mid: str = Field("", validation_alias=AliasPath("lastMessageInfo", "msgId"))

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_default(cls, value: Any, info: ValidationInfo) -> Any:
        """接口里的 null 按默认值处理。"""
        if value is not None:
            return value
        return 0 if info.field_name == "unread" else ""

    @property
    def waiting(self) -> bool:
        """最后一条是 HR 发的，在等我回复（在手机上看过也算）。"""
        return bool(self.uid) and self.last_from == self.uid

    @property
    def label(self) -> str:
        """日志里的称呼：「张女士 · 某科技」。"""
        return " · ".join(p for p in (self.name, self.company) if p)


def job_from_boss_data(payload: dict[str, Any]) -> Job:
    """打开会话时的 getBossData 接口 → 岗位（没有职位描述）。"""
    zp = as_dict(payload.get("zpData"))
    data, job = as_dict(zp.get("data")), as_dict(zp.get("job"))
    return Job(
        job_id=data.get("encryptJobId"),
        title=job.get("jobName"),
        salary=job.get("salaryDesc"),
        company=job.get("brandName") or data.get("companyName"),
        location=job.get("locationName"),
        experience=job.get("experienceName"),
        education=job.get("degreeName"),
        hr_name=data.get("name"),
        hr_title=data.get("title"),
    )


class ChatDecision(BaseModel):
    """AI 对这次回复的判断：会话走向与要发的回复。"""

    outcome: Literal["continue", "hr_rejected", "declined"] = Field(
        description=(
            "hr_rejected：HR 的最新消息表示我不合适、不考虑或岗位已招满；"
            "declined：我这条回复是在婉拒这个岗位；continue：其他情况，继续沟通"
        )
    )
    reply: str = Field(
        default="",
        description="要发给 HR 的回复正文，不加引号、署名或解释，不换行；hr_rejected 时留空",
    )


class ChatReplier(BaseModel):
    """按「自动回复」提示词、简历、岗位与聊天记录生成给 HR 的回复，并判断会话是否已结束。"""

    # 追加在用户提示词后面的输出约束
    OUTPUT_RULE: ClassVar[str] = (
        "先判断会话走向：HR 明确表示不合适、不考虑或岗位已招满时 outcome 为 hr_rejected，"
        "reply 留空；我按岗位判断婉拒这个岗位时 outcome 为 declined；其他情况为 continue。"
        "reply 只写要发给 HR 的回复正文，不要加引号、署名或任何解释，不要换行。"
    )
    # 附带给模型的最近消息条数
    HISTORY: ClassVar[int] = 20

    prompt: str
    resume: str
    llm: LlmSettings
    timeout: float = 60

    @cached_property
    def agent(self) -> Agent[None, ChatDecision]:
        model = OpenAIChatModel(self.llm.model, provider=self.llm.provider)
        return Agent(
            model,
            output_type=PromptedOutput(ChatDecision),
            instructions=f"{self.prompt}\n\n{self.OUTPUT_RULE}",
            model_settings=OpenAIChatModelSettings(
                thinking=False, temperature=0.7, timeout=self.timeout
            ),
        )

    async def reply(self, job: Job, history: list[ChatMessage], verdict: str) -> ChatDecision:
        """判断会话走向并生成回复（单行）；接口出错时抛 ``AgentRunError``。"""
        result = await self.agent.run(self.build_prompt(job, history, verdict))
        decision = result.output
        return decision.model_copy(update={"reply": " ".join(decision.reply.split())})

    def build_prompt(self, job: Job, history: list[ChatMessage], verdict: str) -> str:
        lines = [f"{'HR' if m.from_hr else '我'}：{m.text}" for m in history if m.text]
        parts = [
            f"我的简历：\n{self.resume}",
            (
                f"沟通的岗位：{job.title} · {job.company} · {job.salary or '薪资未知'}\n"
                f"岗位详情：\n{job.description or '（暂无）'}"
            ),
            f"岗位判断：{verdict}" if verdict else "",
            "聊天记录（从早到晚）：\n" + "\n".join(lines[-self.HISTORY :]),
            "请回复 HR 的最新消息。",
        ]
        return "\n\n".join(p for p in parts if p)


class ChatResponder:
    """在单独的标签页守着 BOSS 聊天页，逐个回复 HR 发来的新消息。

    聊天页只打开一次，之后在页面里直接查询最近的会话，不再刷新页面。
    流程：查询最近会话 → 找出等我回复的会话 → 打开会话读取岗位与消息 →
    新消息入库并打印 → HR 主动沟通的新岗位按投递规则判断后入库 → 按回复节奏等待 →
    AI 判断会话走向并生成回复 → 模拟打字发送；HR 已拒绝或我方婉拒的会话会被标记。
    """

    CHAT_URL = f"{BASE_URL}/web/geek/chat"
    # 打开会话时的 HR 与岗位接口
    BOSS_API = "getBossData"
    # 每次查询最近更新的会话数
    RECENT = 20
    # 在页面里查询最近会话：先按更新时间取会话 ID，再批量取详情；返回 {code, result}
    FRIENDS_JS = """
    async (limit) => {
      const ids = await fetch('/wapi/zprelation/friend/geekFilterByLabel?labelId=0')
        .then(r => r.json());
      if (ids.code !== 0) return {code: ids.code, result: []};
      const top = (ids.zpData?.friendList || []).slice(0, limit).map(f => f.friendId);
      if (!top.length) return {code: 0, result: []};
      const detail = await fetch('/wapi/zprelation/friend/getGeekFriendList.json', {
        method: 'POST',
        headers: {'content-type': 'application/x-www-form-urlencoded'},
        body: 'friendIds=' + encodeURIComponent(top.join(',')),
      }).then(r => r.json());
      return {code: detail.code, result: detail.zpData?.result || []};
    }
    """
    # 会话列表项
    ITEM = ".friend-content"
    # 当前会话的消息
    MESSAGE = ".chat-message li.message-item"
    INPUT = "#chat-input"
    SEND = ".btn-send"
    LOGIN = ".login-dialog-wrap"
    # 职位详情页的职位描述
    DESCRIPTION = ".job-sec-text"
    # 两次刷新会话列表之间的等待（秒）
    POLL: ClassVar[tuple[float, float]] = (60, 120)
    # 打字时每个字的间隔（毫秒）
    TYPING: ClassVar[tuple[float, float]] = (80, 220)
    # 读取当前会话消息：[{mid, from_hr, text}]，系统提示等既不是 HR 也不是我的跳过
    READ_JS = """
    (selector) => [...document.querySelectorAll(selector)]
      .filter(li => li.dataset.mid
        && (li.classList.contains('item-friend') || li.classList.contains('item-myself')))
      .map(li => ({
        mid: li.dataset.mid,
        from_hr: li.classList.contains('item-friend'),
        text: (li.querySelector('.text-content')?.innerText || '').trim(),
      }))
    """

    def __init__(self, session: BossSession) -> None:
        self.session = session
        self._stop = asyncio.Event()
        # 已处理过的 HR 最后一条消息，失败也不再重复处理
        self._handled: set[str] = set()
        self._replier: ChatReplier | None = None
        self._pace = ReplyPaceProfile()
        self._keywords = KeywordFilter()
        self._reviewer: JobReviewer | None = None
        self._on_log: LogSink | None = None
        self._replied = 0

    def request_stop(self) -> None:
        """请求停止自动回复。"""
        self._stop.set()

    async def run(
        self,
        replier: ChatReplier,
        *,
        pace: ReplyPaceProfile | None = None,
        keywords: KeywordFilter | None = None,
        reviewer: JobReviewer | None = None,
        on_log: LogSink | None = None,
    ) -> str:
        """一直守着聊天页直到请求停止；返回 stopped / need_login。

        只在回复时段内回复；HR 主动沟通的新岗位按 ``keywords`` 与 ``reviewer`` 判断是否合适后入库。
        """
        self._stop.clear()
        self._replier = replier
        self._pace = pace or ReplyPaceProfile()
        self._keywords = keywords or KeywordFilter()
        self._reviewer = reviewer
        self._on_log = on_log
        self._replied = 0
        log("启动浏览器", "chat")
        context = await self.session.open()
        page = await context.new_page()
        try:
            log("打开聊天页", "chat")
            if not await self._open_page(page):
                return "need_login"
            low, high = self.POLL
            await self._log(
                f"已打开聊天页，正在等待 HR 的新消息（每 {low / 60:g}–{high / 60:g} 分钟检查一次）"
            )
            while not self._stop.is_set():
                now = datetime.now().astimezone()
                if not self._pace.is_active(now):
                    start = self._pace.next_active(now)
                    await self._log(f"不在回复时段，{start:%m-%d %H:%M} 后继续回复")
                    await self._sleep((start - now).total_seconds())
                    continue
                friends = await self._recent_friends(page)
                if friends is None:
                    if not await self._open_page(page):
                        return "need_login"
                    continue
                pending = [
                    f for f in friends if f.waiting and f.last_mid not in self._handled
                ]
                if pending:
                    await self._log(f"发现 {len(pending)} 个会话有 HR 的新消息")
                for friend in pending:
                    if self._stop.is_set():
                        break
                    self._handled.add(friend.last_mid)
                    await self._handle(page, friend)
                await self._sleep(random.uniform(*self.POLL))
            return "stopped"
        finally:
            with contextlib.suppress(PlaywrightError):
                await page.close()

    async def _open_page(self, page: Page) -> bool:
        """打开聊天页并等会话列表出现；需要登录时返回 False。"""
        await page.goto(self.CHAT_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector(self.ITEM, timeout=20_000)
        except PlaywrightTimeoutError:
            return not (await page.locator(self.LOGIN).is_visible() or "login" in page.url)
        return True

    async def _recent_friends(self, page: Page) -> list[Friend] | None:
        """在页面里查询最近更新的会话；接口出错（如登录失效）返回 None。"""
        try:
            payload = as_dict(
                await asyncio.wait_for(page.evaluate(self.FRIENDS_JS, self.RECENT), 30)
            )
        except (PlaywrightError, TimeoutError) as exc:
            log(f"查询会话失败：{exc!r}", "chat")
            return None
        if payload.get("code") != 0:
            log(f"查询会话失败：code={payload.get('code')}", "chat")
            return None
        log(f"查询到 {len(payload.get('result') or [])} 个最近会话", "chat")
        return self.parse_friends(payload.get("result"))

    @staticmethod
    def parse_friends(items: Any) -> list[Friend]:
        """会话详情列表 → Friend；缺 HR ID 或格式不对的跳过。"""
        friends = []
        for item in items if isinstance(items, list) else []:
            with contextlib.suppress(ValidationError):
                friend = Friend.model_validate(item)
                if friend.boss_id:
                    friends.append(friend)
        return friends

    async def _handle(self, page: Page, friend: Friend) -> None:
        """处理一位 HR 的新消息：读取入库 → 判断岗位 → 等待 → 回复。"""
        job = await self._open_chat(page, friend)
        if job is None:
            # 会话列表是虚拟滚动，找不到时重新打开聊天页再试一次
            await self._open_page(page)
            job = await self._open_chat(page, friend)
        if job is None:
            await self._log(f"{friend.label}（打开会话失败，请手动查看）", "warn")
            return
        uid = JobRow.uid_for(job) if job.job_id else ""
        messages = await self._read_messages(page)
        fresh = ChatMessageRow.record_new(
            messages, job_uid=uid, boss_id=friend.boss_id, hr_name=friend.name
        )
        incoming = [m for m in fresh if m.from_hr and m.text]
        for message in incoming:
            await self._log(f"{friend.label}：{message.text}", "recv")
        pending = self.unanswered(messages)
        if not pending:
            return
        if not incoming and friend.boss_id in ChatRejectionRow.labels():
            await self._log(f"{friend.label}（已标记为不合适，没有新消息，跳过）", "skip")
            return

        verdict, job = await self._judge(page, job, uid)
        await self._sleep(random.uniform(*self._pace.delay))
        if self._stop.is_set():
            return
        assert self._replier is not None
        try:
            decision = await self._replier.reply(job, messages, verdict)
        except AgentRunError as exc:
            await self._log(f"{friend.label}（AI 回复失败，请手动回复：{exc}）", "warn")
            return
        await self._apply(page, friend, uid, decision, pending[-1].text)

    @staticmethod
    def unanswered(messages: list[ChatMessage]) -> list[ChatMessage]:
        """我最后一条消息之后 HR 发来的消息（上次入库后没来得及回复的也算）。"""
        tail: list[ChatMessage] = []
        for message in reversed(messages):
            if not message.from_hr:
                break
            if message.text:
                tail.append(message)
        return tail[::-1]

    async def _apply(
        self, page: Page, friend: Friend, uid: str, decision: ChatDecision, hr_text: str
    ) -> None:
        """按 AI 的判断处理：HR 已拒绝就只标记；否则发出回复，婉拒时标记、继续沟通时取消标记。"""
        if decision.outcome == "hr_rejected":
            ChatRejectionRow.mark(friend.boss_id, by="hr", text=hr_text)
            await self._log(f"{friend.label}（HR 已拒绝，不再回复）", "skip")
            return
        text = decision.reply
        if not text or not await self._send(page, text):
            await self._log(f"{friend.label}（发送失败，请手动回复）", "warn")
            return
        ChatMessageRow.record_new(
            await self._read_messages(page),
            job_uid=uid,
            boss_id=friend.boss_id,
            hr_name=friend.name,
            auto=True,
        )
        if decision.outcome == "declined":
            ChatRejectionRow.mark(friend.boss_id, by="me", text=text)
        else:
            ChatRejectionRow.clear(friend.boss_id)
        self._replied += 1
        tag = "（已婉拒）" if decision.outcome == "declined" else ""
        await self._log(f"回复 {friend.label}{tag}：{text}", "reply")
        await self._rest_after(self._replied)

    async def _open_chat(self, page: Page, friend: Friend) -> Job | None:
        """在会话列表里点开这位 HR，返回会话对应的岗位；找不到或加载失败返回 None。"""
        item = (
            page.locator(self.ITEM)
            .filter(has_text=friend.name)
            .filter(has_text=friend.company)
            .first
        )

        def is_boss_data(response: Response) -> bool:
            return response.status == 200 and self.BOSS_API in response.url

        try:
            async with page.expect_response(is_boss_data, timeout=10_000) as resp:
                await item.click(timeout=5_000)
            payload = as_dict(await (await resp.value).json())
            await page.wait_for_selector(self.MESSAGE, timeout=10_000)
        except (PlaywrightError, ValueError):
            return None
        job = job_from_boss_data(payload)
        if not job.job_id and friend.job_id:
            job = job.model_copy(update={"job_id": friend.job_id})
        return job

    async def _read_messages(self, page: Page) -> list[ChatMessage]:
        """读取当前会话里的消息（从早到晚）。"""
        try:
            items = await page.evaluate(self.READ_JS, self.MESSAGE)
        except PlaywrightError:
            return []
        messages = []
        for item in items or []:
            with contextlib.suppress(ValidationError):
                messages.append(ChatMessage.model_validate(item))
        return messages

    async def _judge(self, page: Page, job: Job, uid: str) -> tuple[str, Job]:
        """岗位是否合适的说明（给 AI 参考）与补全后的岗位。

        库里已有就沿用之前的判断；没有说明是 HR 主动沟通的新岗位，按投递规则判断后入库。
        """
        if uid and (row := JobRow.get_dict(uid)):
            job = job.model_copy(update={"description": row["description"]})
            return self._verdict(row["suitable"], row["reason"]), job
        if not uid:
            return "", job

        job = job.model_copy(update={"description": await self._description(page, job)})
        name = f"{job.title} · {job.company}"
        if reason := self._keywords.reject_reason(job.title, job.company):
            JobRow.record(job, suitable=False, reason=reason)
            await self._log(f"{name}（HR 主动沟通的新岗位，{reason}）", "skip")
            return self._verdict(False, reason), job
        suitable, reason, score = True, "HR 主动沟通", None
        if self._reviewer:
            try:
                result = await self._reviewer.check(job)
            except AgentRunError as exc:
                await self._log(f"{name}（AI 复核失败，先按合适处理：{exc}）", "warn")
            else:
                suitable, reason, score = result.match, result.reason, result.score
        JobRow.record(job, suitable=suitable, reason=reason, score=score)
        match = "" if score is None else f" · 匹配 {score} 分"
        await self._log(
            f"{name}（HR 主动沟通的新岗位，{'合适' if suitable else '不合适'}：{reason}{match}）",
            "info" if suitable else "skip",
        )
        return self._verdict(suitable, reason), job

    @staticmethod
    def _verdict(suitable: bool, reason: str) -> str:
        head = "合适" if suitable else "不合适"
        return f"{head}（{reason}）" if reason else head

    async def _description(self, page: Page, job: Job) -> str:
        """在新标签页打开职位详情读职位描述；读不到返回空串。"""
        if not job.link:
            return ""
        detail = await page.context.new_page()
        try:
            await detail.goto(job.link, wait_until="domcontentloaded")
            return (await detail.locator(self.DESCRIPTION).first.inner_text(timeout=10_000)).strip()
        except PlaywrightError:
            await self._log(f"{job.title} 职位详情加载失败，按已有信息判断", "warn")
            return ""
        finally:
            with contextlib.suppress(PlaywrightError):
                await detail.close()

    async def _send(self, page: Page, text: str) -> bool:
        """模拟打字输入回复并发送；发出后返回 True。"""
        mine = page.locator(f"{self.MESSAGE}.item-myself")
        try:
            before = await mine.count()
            box = page.locator(self.INPUT)
            await box.click(timeout=5_000)
            await box.press_sequentially(text, delay=random.uniform(*self.TYPING))
            await page.locator(self.SEND).click(timeout=5_000)
            for _ in range(20):
                if await mine.count() > before:
                    return True
                await page.wait_for_timeout(500)
        except PlaywrightError:
            return False
        return False

    async def _rest_after(self, count: int) -> None:
        """每回复满 ``rest_every`` 条歇一会（分钟）。"""
        every = self._pace.rest_every
        if every and count % every == 0:
            await self._log(f"已回复 {count} 条，休息一会")
            await self._sleep(random.uniform(*self._pace.rest) * 60)

    async def _log(self, text: str, level: str = "info") -> None:
        log(f"{level} {text}", "chat")
        if self._on_log is not None:
            await self._on_log(level, text)

    async def _sleep(self, seconds: float) -> None:
        """停顿；期间请求停止会立即返回。"""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), max(0.0, seconds))
