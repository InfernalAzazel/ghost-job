"""BOSS 聊天：守着聊天页，HR 发来新消息时按提示词和简历自动回复；消息入库并关联岗位。"""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
from datetime import datetime
from functools import cached_property
from itertools import takewhile
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from patchright.async_api import Error as PlaywrightError
from patchright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import (
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

from job.boss.filters import BASE_URL, KeywordFilter, ReplyPaceProfile
from job.boss.jobs import Job, LogSink, read_description
from job.models.chat import ChatMessage, ChatMessageRow, ChatStatusRow
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

    boss_id: str = Field(default="", validation_alias="encryptBossId")
    # HR 的数字 ID：最后一条消息的发送方是它，说明在等我回复
    uid: str = ""
    name: str = ""
    company: str = Field(default="", validation_alias="brandName")
    job_id: str = Field(default="", validation_alias="encryptJobId")
    # 调历史消息、岗位接口时要带上
    security_id: str = Field(default="", validation_alias="securityId")
    last_from: str = Field(
        default="", validation_alias=AliasPath("lastMessageInfo", "fromId")
    )
    last_mid: str = Field(
        default="", validation_alias=AliasPath("lastMessageInfo", "msgId")
    )

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_empty(cls, value: Any) -> Any:
        """接口里的 null 按空串处理。"""
        return "" if value is None else value

    @property
    def waiting(self) -> bool:
        """最后一条是 HR 发的，在等我回复（在手机上看过也算）。"""
        return bool(self.uid) and self.last_from == self.uid

    @property
    def label(self) -> str:
        """日志里的称呼：「张女士 · 某科技」。"""
        return " · ".join(p for p in (self.name, self.company) if p)


def _validate_all[M: BaseModel](model: type[M], items: Any) -> list[M]:
    """列表里的每一项 → ``model``；格式不对的跳过。"""
    result = []
    for item in items if isinstance(items, list) else []:
        with contextlib.suppress(ValidationError):
            result.append(model.model_validate(item))
    return result


def job_from_boss_data(payload: dict[str, Any]) -> Job:
    """打开会话时的 getBossData 接口 → 岗位（没有职位描述）。"""
    zp = as_dict(payload.get("zpData"))
    data, job = as_dict(zp.get("data")), as_dict(zp.get("job"))
    return Job.model_validate(
        {
            "job_id": data.get("encryptJobId"),
            "title": job.get("jobName"),
            "salary": job.get("salaryDesc"),
            "company": job.get("brandName") or data.get("companyName"),
            "brand_id": job.get("encryptBrandId") or data.get("encryptBrandId"),
            "location": job.get("locationName"),
            "experience": job.get("experienceName"),
            "education": job.get("degreeName"),
            "hr_name": data.get("name"),
            "hr_title": data.get("title"),
        }
    )


# 文档字符串与字段说明会作为输出要求发给模型
class ChatDecision(BaseModel):
    """这次回复的判断：会话走向与要发给 HR 的回复。"""

    outcome: Literal["continue", "hr_rejected", "declined"] = Field(
        description=(
            "hr_rejected：HR 明确表示我不合适、不考虑或岗位已招满；"
            "declined：我按岗位判断婉拒这个岗位；continue：其他情况，继续沟通"
        )
    )
    reply: str = Field(
        default="",
        description="要发给 HR 的回复正文，不加引号、署名或任何解释，不换行；hr_rejected 时留空",
    )
    send_resume: bool = Field(
        default=False,
        description="HR 在索要简历时为 true，回复发出后会自动发送附件简历",
    )
    interview: bool = Field(
        default=False,
        description=(
            "只看 HR 说了什么：HR 主动邀请面试，或 HR 在和我确认面试时间、地点、方式时为 true；"
            "HR 还没邀请、只是我方在回复里提出或询问面试（如「方便先线上面试吗」），"
            "HR 只是介绍面试流程（如「我们是线下面试」），或我方婉拒时都为 false"
        ),
    )

    @field_validator("reply")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return " ".join(value.split())


class ChatReplier(BaseModel):
    """按「自动回复」提示词、简历、岗位与聊天记录生成给 HR 的回复，并判断会话是否已结束。"""

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
            instructions=self.prompt,
            model_settings=OpenAIChatModelSettings(
                thinking=False, temperature=0.7, timeout=self.timeout
            ),
        )

    async def reply(
        self, job: Job, history: list[ChatMessage], verdict: str
    ) -> ChatDecision:
        """判断会话走向并生成回复；接口出错时抛 ``AgentRunError``。"""
        return (await self.agent.run(self.build_prompt(job, history, verdict))).output

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
    流程：查询最近会话 → 库里还没有的新会话（如刚投递的）读历史消息入库 →
    找出等我回复的会话 → 打开会话读取岗位与消息 →
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
    # 一个会话的历史消息（从早到晚，最多翻 pages 页）；withBoss 时带上岗位接口 getBossData 的原始返回
    HISTORY_JS = """
    async ({bossId, securityId, pages, withBoss}) => {
      let messages = [], maxMsgId = '0';
      for (let i = 0; i < pages; i++) {
        const q = new URLSearchParams({bossId, groupId: bossId, maxMsgId, c: '20', page: '1',
          src: '0', securityId});
        const r = await fetch('/wapi/zpchat/geek/historyMsg?' + q).then(r => r.json());
        if (r.code !== 0) return {code: r.code};
        const batch = r.zpData?.messages || [];
        messages = batch.concat(messages);
        if (!r.zpData?.hasMore || !batch.length) break;
        maxMsgId = String(r.zpData.minMsgId);
      }
      if (!withBoss) return {code: 0, messages};
      const q = new URLSearchParams({bossId, bossSource: '0', securityId});
      const boss = await fetch('/wapi/zpchat/geek/getBossData?' + q).then(r => r.json());
      return {code: 0, messages, boss};
    }
    """
    # BOSS 表情在消息里是「[微笑]」这样的代码，聊天页显示成图片，入库时去掉
    EMOJI = re.compile(r"\[[^\[\]\s]{1,6}\]")
    RECALLED = "撤回了一条消息"
    # 读新会话历史消息前的停顿（秒）
    QUIET_GAP: ClassVar[tuple[float, float]] = (1, 3)
    # 会话列表项
    ITEM = ".friend-content"
    # 当前会话的消息
    MESSAGE = ".chat-message li.message-item"
    INPUT = "#chat-input"
    SEND = ".btn-send"
    # 工具栏的「发简历」按钮与点开后的确认面板
    RESUME_BUTTON = ".chat-controls .toolbar-btn"
    RESUME_PANEL = ".panel-resume"
    RESUME_SENT = "附件简历请求已发送"
    # HR 主动索要附件简历的卡片，带「拒绝 / 同意」按钮
    RESUME_REQUEST = "附件简历"
    LOGIN = ".login-dialog-wrap"
    # 两次刷新会话列表之间的等待（秒）
    POLL: ClassVar[tuple[float, float]] = (60, 120)
    # 打开聊天页遇到网络异常时的重试间隔（秒）
    RETRY = 60
    # 打字时每个字的间隔（毫秒）
    TYPING: ClassVar[tuple[float, float]] = (80, 220)
    # 读取当前会话消息：[{mid, from_hr, text}]，系统提示等既不是 HR 也不是我的跳过
    # HR 索要简历、交换微信等卡片没有 .text-content，去掉时间、头像和按钮后取剩下的文字
    READ_JS = """
    (selector) => {
      const NOISE = '.message-time, .time, .figure, .avatar, img, button, [class*="btn"],'
        + ' [class*="status"], [class*="operate"]';
      const BUTTONS = new Set(['拒绝', '同意', '接受', '查看', '确定', '取消']);
      const cardText = (li) => {
        const parts = [];
        const noisy = (el) => {
          const hit = el.closest(NOISE);
          return hit && hit !== li && li.contains(hit);
        };
        const walker = document.createTreeWalker(li, NodeFilter.SHOW_TEXT);
        for (let node; (node = walker.nextNode());) {
          const text = node.textContent.trim();
          if (text && !noisy(node.parentElement) && !BUTTONS.has(text)
              && !/^\\d{1,2}:\\d{2}$/.test(text)) parts.push(text);
        }
        return parts.join(' ');
      };
      return [...document.querySelectorAll(selector)]
        .filter(li => li.dataset.mid
          && (li.classList.contains('item-friend') || li.classList.contains('item-myself')))
        .map(li => {
          const text = li.querySelector('.text-content')?.innerText?.trim();
          return {
            mid: li.dataset.mid,
            from_hr: li.classList.contains('item-friend'),
            text: text || cardText(li),
          };
        });
    }
    """

    def __init__(self, session: BossSession) -> None:
        self.session = session
        self._stop = asyncio.Event()
        # 已处理过的 HR 最后一条消息，失败也不再重复处理
        self._handled: set[str] = set()
        # 已读过历史消息的新会话（没有可入库的消息时不再重复读）
        self._seen: set[str] = set()
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
        # 重新开启时再检查一遍，上次停止前没回复完的会话不会被漏掉
        self._handled.clear()
        self._seen.clear()
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
            if not await self._reopen(page):
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
                    if not await self._reopen(page):
                        return "need_login"
                    continue
                await self._record_quiet(page, friends)
                pending = [
                    f for f in friends if f.waiting and f.last_mid not in self._handled
                ]
                if pending:
                    # 最后一条是 HR 发的也可能只是系统消息（如发简历后的提示），打开后才确定
                    log(f"检查 {len(pending)} 个最后一条来自 HR 的会话", "chat")
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

    async def _reopen(self, page: Page) -> bool:
        """打开聊天页，网络异常时每隔一段时间重试，直到恢复或请求停止；需要登录时返回 False。"""
        while (opened := await self.open_page(page)) is None:
            await self._log(f"网络异常，打开聊天页失败，{self.RETRY} 秒后重试", "warn")
            await self._sleep(self.RETRY)
            if self._stop.is_set():
                return True
        return opened

    @classmethod
    async def open_page(cls, page: Page) -> bool | None:
        """打开聊天页并等会话列表出现；需要登录时返回 False，网络异常返回 None。"""
        try:
            await page.goto(cls.CHAT_URL, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            log(f"打开聊天页失败：{exc!r}", "chat")
            return None
        try:
            await page.wait_for_selector(cls.ITEM, timeout=20_000)
        except PlaywrightTimeoutError:
            return not (
                await page.locator(cls.LOGIN).is_visible() or "login" in page.url
            )
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
        return [f for f in _validate_all(Friend, items) if f.boss_id]

    @classmethod
    def parse_history(cls, items: Any, hr_uid: str) -> list[ChatMessage]:
        """历史消息接口 → 聊天记录（从早到晚），与从聊天页读到的一致。

        只要文字消息和 HR 索要简历等对话卡片；系统提示、职位卡片、附件简历卡片与撤回提示跳过。
        """
        messages = []
        for item in items if isinstance(items, list) else []:
            item = as_dict(item)
            body = as_dict(item.get("body"))
            if body.get("type") == 1 and body.get("templateId") == 1:
                text = str(body.get("text") or "")
            elif body.get("type") == 7:
                text = str(as_dict(body.get("dialog")).get("text") or "")
            else:
                continue
            text = cls.EMOJI.sub("", text).strip()
            if not item.get("mid") or not text or text.endswith(cls.RECALLED):
                continue
            sender = str(as_dict(item.get("from")).get("uid") or "")
            messages.append(
                ChatMessage(mid=str(item["mid"]), from_hr=sender == hr_uid, text=text)
            )
        return sorted(messages, key=lambda m: int(m.mid) if m.mid.isdigit() else 0)

    async def _record_quiet(self, page: Page, friends: list[Friend]) -> None:
        """库里还没有、也不在等我回复的会话（如投递后 BOSS 替我发的打招呼），读历史消息入库。

        不点开会话，只调历史消息接口；岗位按会话里的职位 ID 关联库里已有的岗位。
        """
        skip = ChatMessageRow.boss_ids() | self._seen
        for friend in friends:
            if friend.waiting or friend.boss_id in skip or self._stop.is_set():
                continue
            await self._sleep(random.uniform(*self.QUIET_GAP))
            try:
                data = as_dict(
                    await asyncio.wait_for(
                        page.evaluate(
                            self.HISTORY_JS,
                            {
                                "bossId": friend.boss_id,
                                "securityId": friend.security_id,
                                "pages": 1,
                                "withBoss": False,
                            },
                        ),
                        30,
                    )
                )
            except (PlaywrightError, TimeoutError) as exc:
                log(f"读取 {friend.label} 的消息失败：{exc!r}", "chat")
                continue
            if data.get("code") != 0:
                log(f"读取 {friend.label} 的消息失败：code={data.get('code')}", "chat")
                continue
            self._seen.add(friend.boss_id)
            uid = (
                friend.job_id
                if friend.job_id and JobRow.get_dict(friend.job_id)
                else ""
            )
            if self._record(
                self.parse_history(data.get("messages"), friend.uid), friend, uid
            ):
                log(f"{friend.label} 的新会话已入库", "chat")

    async def _handle(self, page: Page, friend: Friend) -> None:
        """处理一位 HR 的新消息：读取入库 → 判断岗位 → 等待 → 回复。"""
        job = await self._open_chat(page, friend)
        if job is None:
            # 会话列表是虚拟滚动，找不到时重新打开聊天页再试一次
            await self.open_page(page)
            job = await self._open_chat(page, friend)
        if job is None:
            await self._log(f"{friend.label}（打开会话失败，请手动查看）", "warn")
            return
        uid = JobRow.uid_for(job) if job.job_id else ""
        messages = await self._read_messages(page)
        incoming = [
            m for m in self._record(messages, friend, uid) if m.from_hr and m.text
        ]
        for message in incoming:
            await self._log(f"{friend.label}：{message.text}", "recv")
        if not (pending := self.unanswered(messages)):
            log(f"{friend.label} 没有待回复的消息（最后一条是系统消息），跳过", "chat")
            return
        if not incoming and ChatStatusRow.ended(friend.boss_id):
            await self._log(f"{friend.label}（会话已结束，没有新消息，跳过）", "skip")
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
        tail = takewhile(lambda m: m.from_hr, reversed(messages))
        return [m for m in reversed(list(tail)) if m.text]

    @staticmethod
    def _record(
        messages: list[ChatMessage], friend: Friend, uid: str, *, auto: bool = False
    ) -> list[ChatMessage]:
        """消息入库并关联岗位，返回新入库的。"""
        return ChatMessageRow.record_new(
            messages,
            job_uid=uid,
            boss_id=friend.boss_id,
            hr_name=friend.name,
            auto=auto,
        )

    async def _apply(
        self, page: Page, friend: Friend, uid: str, decision: ChatDecision, hr_text: str
    ) -> None:
        """按 AI 的判断处理：HR 已拒绝就只更新沟通状态；否则发出回复，发出后再更新沟通状态。"""
        if decision.outcome == "hr_rejected":
            ChatStatusRow.follow_ai(
                friend.boss_id,
                outcome=decision.outcome,
                interview=decision.interview,
                text=hr_text,
            )
            await self._log(f"{friend.label}（HR 已拒绝，不再回复）", "skip")
            return
        text = decision.reply
        if not text or not await self._send(page, text):
            await self._log(f"{friend.label}（发送失败，请手动回复）", "warn")
            return
        self._record(await self._read_messages(page), friend, uid, auto=True)
        declined = decision.outcome == "declined"
        status = ChatStatusRow.follow_ai(
            friend.boss_id,
            outcome=decision.outcome,
            interview=decision.interview,
            text=text,
        )
        if status == "invited":
            await self._log(f"{friend.label}（识别到面试邀请，已标记有面试）")
        self._replied += 1
        await self._log(
            f"回复 {friend.label}{'（已婉拒）' if declined else ''}：{text}", "reply"
        )
        if decision.send_resume:
            if await self._accept_resume_request(page):
                await self._log(f"{friend.label}（已同意 HR 的附件简历请求）", "reply")
            elif await self._send_resume(page):
                await self._log(
                    f"{friend.label}（已发送附件简历请求，对方确认后发到邮箱）", "reply"
                )
            else:
                await self._log(f"{friend.label}（发简历失败，请手动发送）", "warn")
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
            return _validate_all(
                ChatMessage, await page.evaluate(self.READ_JS, self.MESSAGE)
            )
        except PlaywrightError:
            return []

    async def _judge(self, page: Page, job: Job, uid: str) -> tuple[str, Job]:
        """岗位是否合适的说明（给 AI 参考）与补全后的岗位。

        库里已有就沿用之前的判断；没有说明是 HR 主动沟通的新岗位，按投递规则判断后入库。
        """
        if uid and (row := JobRow.get_dict(uid)):
            description = row["description"]
            # 投递时详情接口偶尔没返回描述，这里补读并回写
            if not description and (description := await self._description(page, job)):
                JobRow.set_description(uid, description)
            job = job.model_copy(update={"description": description})
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
        """在新标签页打开职位详情读职位描述（失败会重试）；读不到返回空串。"""
        if not job.link:
            return ""
        if not (description := await read_description(page.context, job.link)):
            await self._log(f"{job.title} 职位详情加载失败，按已有信息判断", "warn")
        return description

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

    async def _accept_resume_request(self, page: Page) -> bool:
        """HR 发来「我想要一份您的附件简历」卡片时点「同意」；没有待处理的请求或点完按钮没消失返回 False。"""
        card = page.locator(
            f"{self.MESSAGE}.item-friend", has_text=self.RESUME_REQUEST
        ).last
        agree = card.get_by_text("同意", exact=True)
        try:
            if not await agree.count() or not await agree.first.is_visible():
                return False
            await agree.first.click(timeout=5_000)
            for _ in range(20):
                if not await agree.count() or not await agree.first.is_visible():
                    return True
                await page.wait_for_timeout(500)
        except PlaywrightError:
            return False
        return False

    async def _send_resume(self, page: Page) -> bool:
        """点「发简历」并在弹出的面板里确定，聊天里出现「附件简历请求已发送」才算发出。

        按钮不可用（双方还没互动）、面板没出现或没等到提示时返回 False。
        """
        button = page.locator(self.RESUME_BUTTON, has_text="发简历").first
        panel = page.locator(self.RESUME_PANEL)
        sent = page.locator(".message-item", has_text=self.RESUME_SENT)
        try:
            if "unable" in (await button.get_attribute("class", timeout=5_000) or ""):
                return False
            before = await sent.count()
            await button.click(timeout=5_000)
            await panel.locator(".btn-v2", has_text="确定").first.click(timeout=5_000)
            for _ in range(20):
                if await sent.count() > before:
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
