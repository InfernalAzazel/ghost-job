"""同步会话：把 BOSS 上聊过、库里还没有的会话读进来，消息和岗位入库，不回复。

全程在聊天页里调 BOSS 自己的接口，不逐个点开会话；岗位只按关键词判断，
不打开详情页、不调 AI，避免批量访问触发 BOSS 的异常访问检测。
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from patchright.async_api import Error as PlaywrightError
from pydantic import BaseModel

from job.boss.chat import ChatResponder, Friend, job_from_boss_data
from job.boss.filters import KeywordFilter
from job.models.chat import ChatMessageRow
from job.models.job import JobRow
from job.utils import as_dict, log

if TYPE_CHECKING:
    from patchright.async_api import Page

    from job.boss.session import BossSession

# 同步进度：已处理数、总数、当前会话
ProgressSink = Callable[[int, int, str], Awaitable[None]]


class SyncResult(BaseModel):
    """一次同步的结果。"""

    state: Literal["done", "stopped", "need_login"] = "done"
    # 新入库的会话数、岗位数与读取失败的会话数
    chats: int = 0
    jobs: int = 0
    failed: int = 0


class ChatSyncer:
    """逐个读取库里没有的会话：历史消息 → 岗位 → 入库；每个会话之间随机停顿，可随时停止。"""

    # 全部会话的 ID：[{friendId, bossId}]
    IDS_JS = """
    async () => {
      const r = await fetch('/wapi/zprelation/friend/geekFilterByLabel?labelId=0').then(r => r.json());
      const list = r.zpData?.friendList || [];
      return {code: r.code, result: list.map(f => ({friendId: f.friendId, bossId: f.encryptFriendId}))};
    }
    """
    # 一批会话的详情（HR、公司、securityId 等）
    DETAIL_JS = """
    async (friendIds) => {
      const r = await fetch('/wapi/zprelation/friend/getGeekFriendList.json', {
        method: 'POST',
        headers: {'content-type': 'application/x-www-form-urlencoded'},
        body: 'friendIds=' + encodeURIComponent(friendIds),
      }).then(r => r.json());
      return {code: r.code, result: r.zpData?.result || []};
    }
    """
    # 每次查详情的会话数
    BATCH = 50
    # 一个会话最多翻的历史消息页数（每页 20 条）
    PAGES = 25
    # 两个会话之间的停顿（秒）
    GAP: ClassVar[tuple[float, float]] = (3, 6)
    # 同步进来的新岗位（关键词没拦下）的判断描述
    SYNCED = "同步的会话，待 AI 分析"

    def __init__(self, session: BossSession) -> None:
        self.session = session
        self.running = False
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(
        self, keywords: KeywordFilter, on_progress: ProgressSink
    ) -> SyncResult:
        """同步库里没有的全部会话；打开聊天页或读会话列表失败时抛 ``RuntimeError``。"""
        self._stop.clear()
        self.running = True
        result = SyncResult()
        page: Page | None = None
        try:
            page = await (await self.session.open()).new_page()
            opened = await ChatResponder.open_page(page)
            if opened is None:
                raise RuntimeError("网络异常，打开聊天页失败，请稍后重试")
            if not opened:
                return result.model_copy(update={"state": "need_login"})
            known = ChatMessageRow.boss_ids()
            todo = [
                i
                for i in map(as_dict, await self._query(page, self.IDS_JS))
                if i.get("bossId") and i["bossId"] not in known
            ]
            log(f"同步：BOSS 上有 {len(todo)} 个会话库里还没有", "chat")
            for start in range(0, len(todo), self.BATCH):
                ids = ",".join(
                    str(i["friendId"]) for i in todo[start : start + self.BATCH]
                )
                friends = ChatResponder.parse_friends(
                    await self._query(page, self.DETAIL_JS, ids)
                )
                for n, friend in enumerate(friends, start + 1):
                    if self._stop.is_set():
                        return result.model_copy(update={"state": "stopped"})
                    await on_progress(n, len(todo), friend.label)
                    await self._sync_one(page, friend, keywords, result)
                    await self._sleep(random.uniform(*self.GAP))
            return result
        finally:
            self.running = False
            if page is not None:
                with contextlib.suppress(PlaywrightError):
                    await page.close()

    async def _sync_one(
        self, page: Page, friend: Friend, keywords: KeywordFilter, result: SyncResult
    ) -> None:
        """读一个会话的消息和岗位入库；读取失败只记数，不中断同步。"""
        try:
            data = as_dict(
                await asyncio.wait_for(
                    page.evaluate(
                        ChatResponder.HISTORY_JS,
                        {
                            "bossId": friend.boss_id,
                            "securityId": friend.security_id,
                            "pages": self.PAGES,
                            "withBoss": True,
                        },
                    ),
                    60,
                )
            )
        except (PlaywrightError, TimeoutError) as exc:
            data = {"code": repr(exc)}
        if data.get("code") != 0:
            log(f"同步 {friend.label} 失败：{data.get('code')}", "chat")
            result.failed += 1
            return
        job = job_from_boss_data(as_dict(data.get("boss")))
        if not job.job_id and friend.job_id:
            job = job.model_copy(update={"job_id": friend.job_id})
        uid = JobRow.uid_for(job) if job.job_id else ""
        if uid and JobRow.get_dict(uid) is None:
            reason = keywords.reject_reason(job.title, job.company)
            JobRow.record(job, suitable=not reason, reason=reason or self.SYNCED)
            result.jobs += 1
        messages = ChatResponder.parse_history(data.get("messages"), friend.uid)
        if ChatMessageRow.record_new(
            messages, job_uid=uid, boss_id=friend.boss_id, hr_name=friend.name
        ):
            result.chats += 1

    @staticmethod
    async def _query(page: Page, script: str, arg: Any = None) -> list[Any]:
        """在聊天页里执行接口查询，返回 result 列表；接口出错时抛 ``RuntimeError``。"""
        try:
            payload = as_dict(await asyncio.wait_for(page.evaluate(script, arg), 30))
        except (PlaywrightError, TimeoutError) as exc:
            raise RuntimeError(f"读取会话列表失败：{exc}") from exc
        if payload.get("code") != 0:
            raise RuntimeError(
                f"读取会话列表失败（code={payload.get('code')}），请确认 BOSS 已登录"
            )
        result = payload.get("result")
        return result if isinstance(result, list) else []

    async def _sleep(self, seconds: float) -> None:
        """停顿；期间请求停止会立即返回。"""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), max(0.0, seconds))
