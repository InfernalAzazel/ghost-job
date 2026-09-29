"""历史消息接口：消息转换、自动回复顺带记录新会话、同步库里没有的会话与停止同步。"""

from __future__ import annotations

import asyncio
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
    """按脚本返回假的接口数据：3 个会话，其中 boss-1 已在库里。"""

    def __init__(self, syncer: ChatSyncer | None = None) -> None:
        self.opened: list[str] = []
        self._syncer = syncer

    async def evaluate(self, script: str, arg: Any = None) -> dict[str, Any]:
        if script == ChatSyncer.IDS_JS:
            ids = [{"friendId": n, "bossId": f"boss-{n}"} for n in (1, 2, 3)]
            return {"code": 0, "result": ids}
        if script == ChatSyncer.DETAIL_JS:
            assert arg == "2,3"
            return {
                "code": 0,
                "result": [
                    _friend("boss-2", "job-2", "刘女士"),
                    _friend("boss-3", "job-3", "外包李"),
                ],
            }
        boss_id = arg["bossId"]
        self.opened.append(boss_id)
        if self._syncer is not None:
            self._syncer.request_stop()
        n = boss_id[-1]
        title = "AI 应用工程师" if n == "2" else "外包 Java 开发"
        return {
            "code": 0,
            "messages": [_text(int(n) * 10, "您好")],
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
