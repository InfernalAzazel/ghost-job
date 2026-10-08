"""历史消息接口：消息转换、自动回复顺带记录新会话、同步库里没有的会话与停止同步。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from job import models as models_pkg
from job.boss.chat import ChatResponder
from job.boss.chat_sync import ChatSyncer, SyncResult
from job.boss.filters import KeywordFilter
from job.boss.jobs import Job
from job.models import init_db, reset_engine
from job.models.chat import ChatMessage, ChatMessageRow
from job.models.job import JobRow

if TYPE_CHECKING:
    from patchright.async_api import Page

    from job.boss.session import BossSession

HR_UID = "1001"


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def _text(mid: int, text: str, *, hr: bool = True, template: int = 1) -> dict[str, Any]:
    sender = HR_UID if hr else "2002"
    return {
        "mid": mid,
        "from": {"uid": sender},
        "body": {"type": 1, "templateId": template, "text": text},
    }


def test_parse_history_keeps_texts_and_dialog_cards():
    items = [
        _text(3, "好的，简历发您了", hr=False),
        _text(1, "[hi] 你好啊，可以聊一聊~"),
        {
            "mid": 2,
            "from": {"uid": HR_UID},
            "body": {"type": 7, "dialog": {"text": "我想要一份您的附件简历"}},
        },
        {"mid": 4, "from": {"uid": HR_UID}, "body": {"type": 8, "jobDesc": {}}},
        {"mid": 5, "from": {"uid": HR_UID}, "body": {"type": 12, "hyperLink": {}}},
        _text(6, "对方已查看了您的附件简历", template=3),
        _text(7, "邓先生撤回了一条消息"),
        _text(8, "[微笑]"),
    ]
    assert ChatResponder.parse_history(items, HR_UID) == [
        ChatMessage(mid="1", from_hr=True, text="你好啊，可以聊一聊~"),
        ChatMessage(mid="2", from_hr=True, text="我想要一份您的附件简历"),
        ChatMessage(mid="3", from_hr=False, text="好的，简历发您了"),
    ]
    assert ChatResponder.parse_history(None, HR_UID) == []


def test_history_messages_keep_boss_time_and_order(tmp_db):
    old = int(datetime(2026, 9, 1, 2, 0, tzinfo=UTC).timestamp() * 1000)
    new = int(datetime(2026, 9, 2, 3, 30, tzinfo=UTC).timestamp() * 1000)
    # 新会话先入库，旧会话后入库：列表仍按 BOSS 上的时间排
    for boss_id, mid, ms in (("boss-new", 20, new), ("boss-old", 10, old)):
        messages = ChatResponder.parse_history(
            [{**_text(mid, "您好"), "time": ms}], HR_UID
        )
        assert messages[0].sent_at == datetime.fromtimestamp(ms / 1000, UTC)
        ChatMessageRow.record_new(
            messages, job_uid="", boss_id=boss_id, hr_name="刘女士"
        )

    assert [c["boss_id"] for c in ChatMessageRow.conversations()] == [
        "boss-new",
        "boss-old",
    ]
    local = datetime.fromtimestamp(old / 1000, UTC).astimezone()
    assert ChatMessageRow.list_for_boss("boss-old")[0]["time"] == local.strftime(
        "%m-%d %H:%M"
    )


def test_page_message_gets_boss_time_from_history(tmp_db):
    def record(message: ChatMessage) -> None:
        ChatMessageRow.record_new(
            [message], job_uid="", boss_id="boss-1", hr_name="刘女士"
        )

    record(ChatMessage(mid="1", from_hr=True, text="您好"))
    sent = datetime(2026, 9, 1, 2, 0, tzinfo=UTC)
    record(ChatMessage(mid="1", from_hr=True, text="您好", sent_at=sent))

    [row] = ChatMessageRow.list_for_boss("boss-1")
    assert row["time"] == sent.astimezone().strftime("%m-%d %H:%M")


def _friend(boss_id: str, job_id: str, name: str) -> dict[str, Any]:
    return {
        "encryptBossId": boss_id,
        "uid": HR_UID,
        "name": name,
        "brandName": "示例科技",
        "encryptJobId": job_id,
        "securityId": f"sec-{boss_id}",
    }


def _boss(job_id: str, title: str) -> dict[str, Any]:
    return {
        "zpData": {
            "data": {"encryptJobId": job_id},
            "job": {"jobName": title, "brandName": "示例科技"},
        }
    }


class FakePage:
    """按脚本返回假的接口数据：3 个会话，默认每个会话只有一条「您好」。"""

    def __init__(self, syncer: ChatSyncer | None = None) -> None:
        self.opened: list[str] = []
        self._syncer = syncer
        self.friends = {
            "1": _friend("boss-1", "job-1", "王女士"),
            "2": _friend("boss-2", "job-2", "刘女士"),
            "3": _friend("boss-3", "job-3", "外包李"),
        }
        # HR → 历史消息，不在这里的用默认消息
        self.messages: dict[str, list[dict[str, Any]]] = {}
        # 历史消息是否已经翻到最早一条
        self.complete = True

    async def evaluate(self, script: str, arg: Any = None) -> dict[str, Any]:
        if script == ChatSyncer.IDS_JS:
            ids = [{"friendId": n, "bossId": f"boss-{n}"} for n in self.friends]
            return {"code": 0, "result": ids}
        if script == ChatSyncer.DETAIL_JS:
            return {
                "code": 0,
                "result": [self.friends[n] for n in arg.split(",")],
            }
        boss_id = arg["bossId"]
        self.opened.append(boss_id)
        if self._syncer is not None:
            self._syncer.request_stop()
        n = boss_id[-1]
        title = "外包 Java 开发" if n == "3" else "AI 应用工程师"
        return {
            "code": 0,
            "messages": self.messages.get(boss_id, [_text(int(n) * 10, "您好")]),
            "complete": self.complete,
            "boss": _boss(f"job-{n}", title),
        }

    async def close(self) -> None:
        pass


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    async def new_page(self) -> FakePage:
        return self._page


class FakeSession:
    def __init__(self, page: FakePage) -> None:
        self._context = FakeContext(page)

    async def open(self) -> FakeContext:
        return self._context


def _syncer(page: FakePage) -> ChatSyncer:
    return ChatSyncer(cast("BossSession", cast(object, FakeSession(page))))


def _run(
    page: FakePage, syncer: ChatSyncer, monkeypatch: pytest.MonkeyPatch
) -> tuple[SyncResult, list[str]]:
    async def open_page(_page: Any) -> bool:
        return True

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ChatResponder, "open_page", open_page)
    monkeypatch.setattr(syncer, "_sleep", no_sleep)
    progress: list[str] = []

    async def on_progress(done: int, total: int, label: str) -> None:
        progress.append(f"{done}/{total} {label}")

    result = asyncio.run(syncer.run(KeywordFilter(exclude=["外包"]), on_progress))
    return result, progress


def test_sync_only_missing_chats_and_records_jobs_by_keywords(
    tmp_db, monkeypatch: pytest.MonkeyPatch
):
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=True, text="旧消息")],
        job_uid="",
        boss_id="boss-1",
        hr_name="王女士",
    )
    page = FakePage()
    syncer = _syncer(page)
    result, progress = _run(page, syncer, monkeypatch)

    assert result == SyncResult(state="done", chats=2, jobs=2, failed=0)
    assert page.opened == ["boss-2", "boss-3"]
    assert progress == ["1/2 刘女士 · 示例科技", "2/2 外包李 · 示例科技"]
    assert not syncer.running
    good, bad = JobRow.get_dict("job-2"), JobRow.get_dict("job-3")
    assert good is not None and bad is not None
    assert (good["suitable"], good["reason"], good["matchStatus"]) == (
        True,
        ChatSyncer.SYNCED,
        "未分析",
    )
    assert (bad["suitable"], bad["reason"]) == (False, "职位名含排除词")
    assert [m["text"] for m in ChatMessageRow.list_for_boss("boss-2")] == ["您好"]
    assert ChatMessageRow.conversations()[0]["job_uid"] in ("job-2", "job-3")


def test_sync_skips_chats_without_messages_next_time(
    tmp_db, monkeypatch: pytest.MonkeyPatch
):
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=True, text="旧消息")],
        job_uid="",
        boss_id="boss-1",
        hr_name="王女士",
    )
    page = FakePage()
    # boss-3 只有职位卡片和撤回提示，没有可入库的消息
    page.friends["3"] = {**page.friends["3"], "lastMessageInfo": {"msgId": "31"}}
    page.messages["boss-3"] = [
        {"mid": 30, "from": {"uid": HR_UID}, "body": {"type": 8}},
        _text(31, "你撤回了一条消息", hr=False),
    ]
    first, _progress = _run(page, _syncer(page), monkeypatch)
    assert (first.chats, first.empty) == (1, 1)
    assert page.opened == ["boss-2", "boss-3"]

    page.opened.clear()
    second, progress = _run(page, _syncer(page), monkeypatch)
    assert second == SyncResult(state="done")
    assert page.opened == [] and progress == []


def test_sync_reads_new_greeting_in_existing_chat(
    tmp_db, monkeypatch: pytest.MonkeyPatch
):
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=False, text="旧岗位打招呼")],
        job_uid="job-old",
        boss_id="boss-1",
        hr_name="王女士",
    )
    JobRow.record(
        Job(job_id="job-1", title="AI 应用工程师", company="示例科技"), applied=True
    )
    page = FakePage()
    # 同一个 HR 的新岗位：打招呼进了原来的会话
    page.friends["1"] = {**page.friends["1"], "lastMessageInfo": {"msgId": "15"}}
    page.messages["boss-1"] = [
        _text(1, "旧岗位打招呼", hr=False),
        _text(15, "您好，我对新岗位很感兴趣", hr=False),
    ]
    result, _progress = _run(page, _syncer(page), monkeypatch)

    assert (result.chats, result.updated) == (2, 1)
    assert page.opened == ["boss-1", "boss-2", "boss-3"]
    assert [m["text"] for m in ChatMessageRow.list_for_boss("boss-1")] == [
        "旧岗位打招呼",
        "您好，我对新岗位很感兴趣",
    ]
    chat = next(c for c in ChatMessageRow.conversations() if c["boss_id"] == "boss-1")
    assert chat["job_uid"] == "job-1"

    page.opened.clear()
    _run(page, _syncer(page), monkeypatch)
    assert page.opened == []


@pytest.mark.parametrize(
    ("complete", "history", "texts"),
    [
        # BOSS 打招呼新岗位时清掉了旧消息：本地跟着删
        (True, [15], ["新岗位打招呼"]),
        # 没翻到最早一条：不知道更早的消息还在不在，不删
        (False, [15], ["旧岗位打招呼", "新岗位打招呼"]),
    ],
)
def test_sync_removes_messages_gone_from_boss(
    tmp_db,
    monkeypatch: pytest.MonkeyPatch,
    complete: bool,
    history: list[int],
    texts: list[str],
):
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=False, text="旧岗位打招呼")],
        job_uid="job-old",
        boss_id="boss-1",
        hr_name="王女士",
    )
    page = FakePage()
    page.complete = complete
    page.friends["1"] = {**page.friends["1"], "lastMessageInfo": {"msgId": "15"}}
    page.messages["boss-1"] = [
        {"mid": 14, "from": {"uid": HR_UID}, "body": {"type": 8}},
        *[_text(mid, "新岗位打招呼", hr=False) for mid in history],
    ]
    _run(page, _syncer(page), monkeypatch)

    assert [m["text"] for m in ChatMessageRow.list_for_boss("boss-1")] == texts


def test_prune_keeps_messages_when_boss_returns_nothing(tmp_db):
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=False, text="您好")],
        job_uid="",
        boss_id="boss-1",
        hr_name="王女士",
    )
    ChatResponder.prune_history("boss-1", {"code": 0, "messages": [], "complete": True})

    assert len(ChatMessageRow.list_for_boss("boss-1")) == 1


def test_sync_stops_after_current_chat(tmp_db, monkeypatch: pytest.MonkeyPatch):
    page = FakePage()
    syncer = _syncer(page)
    page._syncer = syncer
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=True, text="旧消息")],
        job_uid="",
        boss_id="boss-1",
        hr_name="王女士",
    )
    result, _progress = _run(page, syncer, monkeypatch)

    assert result.state == "stopped" and result.chats == 1
    assert page.opened == ["boss-2"]


class HistoryPage:
    """历史消息接口：boss-2 只有投递时我发的打招呼，boss-3 只有职位卡片。"""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def evaluate(self, script: str, arg: Any = None) -> dict[str, Any]:
        assert script == ChatResponder.HISTORY_JS
        self.calls.append(arg)
        if arg["bossId"] == "boss-2":
            return {
                "code": 0,
                "messages": [_text(20, "您好，我对这份工作非常感兴趣", hr=False)],
            }
        return {
            "code": 0,
            "messages": [{"mid": 30, "body": {"type": 8, "jobDesc": {}}}],
        }


def test_responder_records_new_quiet_chats(tmp_db, monkeypatch: pytest.MonkeyPatch):
    JobRow.record(
        Job(job_id="job-2", title="AI 应用工程师", company="示例科技"), applied=True
    )
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=True, text="旧消息")],
        job_uid="",
        boss_id="boss-1",
        hr_name="王女士",
    )
    waiting = {
        **_friend("boss-4", "job-4", "赵先生"),
        "lastMessageInfo": {"fromId": HR_UID},
    }
    friends = ChatResponder.parse_friends(
        [
            _friend("boss-1", "job-1", "王女士"),
            _friend("boss-2", "job-2", "刘女士"),
            _friend("boss-3", "job-3", "李先生"),
            waiting,
        ]
    )
    responder = ChatResponder(cast("BossSession", cast(object, None)))

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(responder, "_sleep", no_sleep)
    page = HistoryPage()
    for _ in range(2):
        asyncio.run(responder._record_quiet(cast("Page", cast(object, page)), friends))

    assert [c["bossId"] for c in page.calls] == ["boss-2", "boss-3"]
    assert page.calls[0] == {
        "bossId": "boss-2",
        "securityId": "sec-boss-2",
        "pages": 1,
        "withBoss": False,
    }
    chat = ChatMessageRow.conversations()[0]
    assert (chat["boss_id"], chat["hr_name"], chat["job_uid"]) == (
        "boss-2",
        "刘女士",
        "job-2",
    )
    assert (
        chat["last_text"] == "您好，我对这份工作非常感兴趣" and not chat["last_from_hr"]
    )
    assert ChatMessageRow.boss_ids() == {"boss-1", "boss-2"}


def test_responder_records_new_greeting_in_existing_chat(
    tmp_db, monkeypatch: pytest.MonkeyPatch
):
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=False, text="旧岗位打招呼")],
        job_uid="",
        boss_id="boss-2",
        hr_name="刘女士",
    )
    ChatMessageRow.record_new(
        [ChatMessage(mid="5", from_hr=False, text="没有新消息的会话")],
        job_uid="",
        boss_id="boss-1",
        hr_name="王女士",
    )
    friends = ChatResponder.parse_friends(
        [
            {
                **_friend("boss-2", "job-2", "刘女士"),
                "lastMessageInfo": {"fromId": "2002", "msgId": "20"},
            },
            {
                **_friend("boss-1", "job-1", "王女士"),
                "lastMessageInfo": {"fromId": "2002", "msgId": "5"},
            },
        ]
    )
    responder = ChatResponder(cast("BossSession", cast(object, None)))

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(responder, "_sleep", no_sleep)
    page = HistoryPage()
    for _ in range(2):
        asyncio.run(responder._record_quiet(cast("Page", cast(object, page)), friends))

    assert [c["bossId"] for c in page.calls] == ["boss-2"]
    assert [m["text"] for m in ChatMessageRow.list_for_boss("boss-2")] == [
        "旧岗位打招呼",
        "您好，我对这份工作非常感兴趣",
    ]
