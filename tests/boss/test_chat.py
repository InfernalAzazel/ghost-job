"""BOSS 聊天：会话列表解析、消息入库去重、回复提示词与 HR 主动沟通的新岗位入库。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from job import models as models_pkg
from job.boss.chat import (
    ChatDecision,
    ChatReplier,
    ChatResponder,
    Friend,
    job_from_boss_data,
)
from job.boss.filters import KeywordFilter
from job.boss.jobs import Job
from job.boss.review import Verdict
from job.models import init_db, reset_engine
from job.models.chat import ChatMessage, ChatMessageRow, ChatStatusRow
from job.models.job import JobRow
from job.models.setting import LlmSettings

FRIEND = {
    "encryptBossId": "boss-1",
    "uid": 1001,
    "name": "王女士",
    "title": "HR",
    "brandName": "示例科技",
    "encryptJobId": "job-1",
    "unreadMsgCount": 2,
    "lastMessageInfo": {"fromId": 1001, "toId": 2002, "msgId": 9},
}
BOSS_DATA = {
    "zpData": {
        "data": {"encryptJobId": "job-1", "name": "王女士", "title": "HR", "companyName": "示例科技有限公司"},
        "job": {
            "jobName": "AI 应用工程师",
            "salaryDesc": "20-30K",
            "brandName": "示例科技",
            "locationName": "广州",
            "experienceName": "3-5年",
            "degreeName": "本科",
        },
    }
}


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def test_friend_waiting_when_hr_sent_last():
    friend = Friend.model_validate(FRIEND)
    assert friend.label == "王女士 · 示例科技" and friend.last_mid == "9"
    assert friend.waiting
    assert Friend.model_validate({**FRIEND, "unreadMsgCount": 0}).waiting

    mine = {**FRIEND["lastMessageInfo"], "fromId": 2002}
    assert not Friend.model_validate({**FRIEND, "lastMessageInfo": mine}).waiting


def test_friend_tolerates_nulls():
    friend = Friend.model_validate(
        {**FRIEND, "unreadMsgCount": None, "lastMessageInfo": None, "brandName": None}
    )
    assert friend.company == "" and friend.last_from == ""
    assert not friend.waiting


def test_job_from_boss_data():
    job = job_from_boss_data(BOSS_DATA)
    assert (job.job_id, job.title, job.company, job.salary) == (
        "job-1", "AI 应用工程师", "示例科技", "20-30K"
    )
    assert (job.location, job.experience, job.education) == ("广州", "3-5年", "本科")
    assert (job.hr_name, job.hr_title) == ("王女士", "HR")
    assert job.link.endswith("/job_detail/job-1.html")


def test_record_new_skips_known_messages(tmp_db):
    first = [ChatMessage(mid="1", from_hr=False, text="您好"), ChatMessage(mid="2", from_hr=True, text="在吗")]
    kwargs = {"job_uid": "job-1", "boss_id": "boss-1", "hr_name": "王女士"}
    assert [m.mid for m in ChatMessageRow.record_new(first, **kwargs)] == ["1", "2"]

    more = [*first, ChatMessage(mid="3", from_hr=False, text="在的")]
    fresh = ChatMessageRow.record_new(more, auto=True, **kwargs)
    assert [m.mid for m in fresh] == ["3"]
    history = ChatMessageRow.list_for_boss("boss-1")
    assert [(h["mid"], h["from_hr"], h["auto"]) for h in history] == [
        ("1", False, False), ("2", True, False), ("3", False, True)
    ]


def test_record_new_fills_empty_card_text(tmp_db):
    kwargs = {"job_uid": "", "boss_id": "boss-1", "hr_name": "钟女士"}
    ChatMessageRow.record_new([ChatMessage(mid="1", from_hr=True, text="")], **kwargs)

    card = ChatMessage(mid="1", from_hr=True, text="我想要一份您的附件简历，您是否同意")
    assert ChatMessageRow.record_new([card], **kwargs) == []
    assert ChatMessageRow.list_for_boss("boss-1")[0]["text"] == card.text


def test_record_new_replaces_temporary_mid_of_auto_reply(tmp_db):
    kwargs = {"job_uid": "job-1", "boss_id": "boss-1", "hr_name": "林女士"}
    hr = ChatMessage(mid="1", from_hr=True, text="发下简历")
    ChatMessageRow.record_new([hr, ChatMessage(mid="temp", from_hr=False, text="简历已发您")], auto=True, **kwargs)

    fresh = ChatMessageRow.record_new([hr, ChatMessage(mid="2", from_hr=False, text="简历已发您")], **kwargs)
    assert [m.mid for m in fresh] == ["2"]
    history = ChatMessageRow.list_for_boss("boss-1")
    assert [(h["mid"], h["auto"]) for h in history] == [("1", False), ("2", True)]


def test_conversations_join_job_and_filter(tmp_db):
    JobRow.record(Job(job_id="job-1", title="AI 应用工程师", company="示例科技", hr_title="HR"))
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=True, text="您好")], job_uid="job-1", boss_id="boss-1", hr_name="王女士"
    )
    ChatMessageRow.record_new(
        [ChatMessage(mid="2", from_hr=False, text="您好，简历已发")], job_uid="", boss_id="boss-2", hr_name="李先生"
    )

    items = ChatMessageRow.conversations()
    assert [i["boss_id"] for i in items] == ["boss-2", "boss-1"]
    first = items[1]
    assert (first["company"], first["title"], first["hr_title"]) == ("示例科技", "AI 应用工程师", "HR")
    assert first["last_text"] == "您好" and first["last_from_hr"]
    assert items[0]["company"] == ""
    assert [i["boss_id"] for i in ChatMessageRow.conversations("示例")] == ["boss-1"]


def test_replier_prompt_and_single_line_output():
    replier = ChatReplier(prompt="语气礼貌", resume="Python 五年", llm=LlmSettings(api_key="k", model="m"))
    job = job_from_boss_data(BOSS_DATA)
    history = [ChatMessage(mid="1", from_hr=False, text="您好"), ChatMessage(mid="2", from_hr=True, text="方便发简历吗")]
    prompt = replier.build_prompt(job, history, "合适（技术栈吻合）")
    assert "Python 五年" in prompt and "AI 应用工程师 · 示例科技 · 20-30K" in prompt
    assert "岗位判断：合适（技术栈吻合）" in prompt
    assert prompt.index("我：您好") < prompt.index("HR：方便发简历吗")

    def answer(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        out = {"outcome": "continue", "reply": "可以的，\n我马上发送附件简历。", "interview": True}
        return ModelResponse(parts=[TextPart(json.dumps(out, ensure_ascii=False))])

    with replier.agent.override(model=FunctionModel(answer)):
        decision = asyncio.run(replier.reply(job, history, ""))
    assert decision == ChatDecision(outcome="continue", reply="可以的， 我马上发送附件简历。", interview=True)


def test_status_mark_and_clear(tmp_db):
    ChatMessageRow.record_new(
        [ChatMessage(mid="1", from_hr=True, text="不合适")], job_uid="", boss_id="boss-1", hr_name="王女士"
    )
    ChatStatusRow.mark("boss-1", "hr_rejected", text="不合适")
    assert ChatMessageRow.conversations()[0]["status_label"] == "HR 已拒绝"
    ChatStatusRow.mark("boss-1", "declined", text="感谢，暂不考虑")
    assert ChatMessageRow.conversations()[0]["status_label"] == "我婉拒"
    assert ChatStatusRow.ended("boss-1")
    ChatStatusRow.clear("boss-1")
    assert ChatMessageRow.conversations()[0]["status_label"] == ""
    assert not ChatStatusRow.ended("boss-1")


@pytest.mark.parametrize(
    ("before", "outcome", "interview", "after"),
    [
        ("", "continue", True, "invited"),
        ("", "continue", False, ""),
        ("", "hr_rejected", False, "hr_rejected"),
        ("", "declined", True, "declined"),
        ("hr_rejected", "continue", False, ""),
        ("declined", "continue", True, "invited"),
        ("invited", "continue", False, "invited"),
        ("invited", "hr_rejected", False, "hr_rejected"),
        ("done", "hr_rejected", True, "done"),
        ("passed", "continue", True, "passed"),
        ("failed", "declined", False, "failed"),
    ],
)
def test_status_follow_ai(tmp_db, before, outcome, interview, after):
    if before:
        ChatStatusRow.mark("boss-1", before)
    changed = ChatStatusRow.follow_ai("boss-1", outcome=outcome, interview=interview, text="t")
    assert ChatStatusRow.statuses().get("boss-1", "") == after
    assert changed == (after if after != before else None)


def test_conversations_filter_by_status(tmp_db):
    for boss_id, name in (("boss-1", "王女士"), ("boss-2", "李先生"), ("boss-3", "赵女士")):
        ChatMessageRow.record_new(
            [ChatMessage(mid=boss_id, from_hr=True, text="您好")], job_uid="", boss_id=boss_id, hr_name=name
        )
    ChatStatusRow.mark("boss-1", "invited", source="auto")
    ChatStatusRow.mark("boss-2", "failed")
    ChatStatusRow.mark("boss-3", "hr_rejected")

    items = {i["boss_id"]: i for i in ChatMessageRow.conversations()}
    assert (items["boss-1"]["status"], items["boss-1"]["status_label"]) == ("invited", "有面试")
    assert [i["boss_id"] for i in ChatMessageRow.conversations(status="有面试")] == ["boss-1"]
    assert {i["boss_id"] for i in ChatMessageRow.conversations(status="所有面试")} == {"boss-1", "boss-2"}
    assert len(ChatMessageRow.conversations(status="全部")) == 3
    assert ChatMessageRow.conversations("王", status="面试不通过") == []


def test_legacy_tags_are_migrated(tmp_path, monkeypatch):
    import sqlite3

    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        conn.execute("create table chat_rejection (boss_id text primary key, by text, text text, created_at text)")
        conn.execute("insert into chat_rejection values ('boss-1', 'hr', '不合适', '2026-09-28 06:00:00')")
        conn.execute("insert into chat_rejection values ('boss-2', 'me', '暂不考虑', '2026-09-28 06:00:00')")
        conn.execute("create table chat_interview (boss_id text primary key, status text, source text, updated_at text)")
        conn.execute("insert into chat_interview values ('boss-3', 'done', 'manual', '2026-09-28 06:00:00')")
    monkeypatch.setattr(models_pkg, "DB_PATH", db)
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    try:
        assert ChatStatusRow.statuses() == {"boss-1": "hr_rejected", "boss-2": "declined", "boss-3": "done"}
        with sqlite3.connect(db) as conn:
            tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        assert not tables & {"chat_rejection", "chat_interview"}
    finally:
        reset_engine()


class FakeReviewer:
    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict

    async def check(self, _job: Job) -> Verdict:
        return self.verdict


def _responder(**kwargs) -> tuple[ChatResponder, list[tuple[str, str]]]:
    responder = ChatResponder(session=None)  # type: ignore[arg-type]
    logs: list[tuple[str, str]] = []

    async def on_log(level: str, text: str) -> None:
        logs.append((level, text))

    async def description(_page, _job) -> str:
        return "负责大模型应用落地"

    responder._on_log = on_log
    responder._description = description  # type: ignore[method-assign]
    for key, value in kwargs.items():
        setattr(responder, f"_{key}", value)
    return responder, logs


def test_new_job_from_hr_is_reviewed_and_recorded(tmp_db):
    responder, logs = _responder(reviewer=FakeReviewer(Verdict(match=True, reason="方向吻合", score=85)))
    job = job_from_boss_data(BOSS_DATA)
    verdict, job = asyncio.run(responder._judge(None, job, "job-1"))

    assert verdict == "合适（方向吻合）" and job.description == "负责大模型应用落地"
    row = JobRow.get_dict("job-1")
    assert row["suitable"] and row["reason"] == "方向吻合" and row["matchStatus"] == "85 分"
    assert row["result"] == "已沟通过"
    assert logs[-1][0] == "info" and "HR 主动沟通的新岗位" in logs[-1][1]


def test_new_job_rejected_by_keywords(tmp_db):
    responder, logs = _responder(keywords=KeywordFilter(exclude_companies=["示例"]))
    verdict, _job = asyncio.run(responder._judge(None, job_from_boss_data(BOSS_DATA), "job-1"))
    assert verdict == "不合适（公司名含排除词）"
    assert not JobRow.get_dict("job-1")["suitable"]
    assert logs[-1][0] == "skip"


def test_known_job_keeps_previous_verdict(tmp_db):
    JobRow.record(
        Job(job_id="job-1", title="AI 应用工程师", company="示例科技", description="原描述"),
        suitable=False,
        reason="外包公司",
    )
    responder, logs = _responder()
    verdict, job = asyncio.run(responder._judge(None, job_from_boss_data(BOSS_DATA), "job-1"))
    assert verdict == "不合适（外包公司）" and job.description == "原描述"
    assert logs == []


def test_known_job_without_description_is_filled(tmp_db):
    JobRow.record(
        Job(job_id="job-1", title="AI 应用工程师", company="示例科技"),
        reason="可投",
        score=80,
        applied=True,
    )
    responder, _logs = _responder()
    verdict, job = asyncio.run(responder._judge(None, job_from_boss_data(BOSS_DATA), "job-1"))
    assert verdict == "合适（可投）" and job.description == "负责大模型应用落地"
    row = JobRow.get_dict("job-1")
    assert row["description"] == "负责大模型应用落地"
    assert row["suitable"] and row["reason"] == "可投" and row["matchStatus"] == "80 分"
    assert row["result"] == "已投递"


def _sending_responder(
    resume_ok: bool = True, request_pending: bool = False
) -> tuple[ChatResponder, list[tuple[str, str]], list[str]]:
    responder, logs = _responder()
    sent: list[str] = []

    async def send(_page, text: str) -> bool:
        sent.append(text)
        return True

    async def accept_resume_request(_page) -> bool:
        if request_pending:
            sent.append("<同意>")
        return request_pending

    async def send_resume(_page) -> bool:
        sent.append("<简历>")
        return resume_ok

    async def read(_page) -> list[ChatMessage]:
        return [ChatMessage(mid=f"me-{i}", from_hr=False, text=t) for i, t in enumerate(sent)]

    responder._send = send  # type: ignore[method-assign]
    responder._accept_resume_request = accept_resume_request  # type: ignore[method-assign]
    responder._send_resume = send_resume  # type: ignore[method-assign]
    responder._read_messages = read  # type: ignore[method-assign]
    return responder, logs, sent


def test_hr_rejection_is_marked_without_reply(tmp_db):
    responder, logs, sent = _sending_responder()
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="hr_rejected")
    asyncio.run(responder._apply(None, friend, "job-1", decision, "暂时不符合我们的需求"))
    assert sent == []
    assert ChatStatusRow.statuses() == {"boss-1": "hr_rejected"}
    assert logs[-1][0] == "skip" and "HR 已拒绝" in logs[-1][1]


def test_decline_is_sent_then_marked(tmp_db):
    responder, logs, sent = _sending_responder()
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="declined", reply="感谢，这个岗位暂不考虑")
    asyncio.run(responder._apply(None, friend, "job-1", decision, "考虑吗"))
    assert sent == ["感谢，这个岗位暂不考虑"]
    assert ChatStatusRow.statuses() == {"boss-1": "declined"}
    assert logs[-1][0] == "reply"


def test_continue_reply_clears_mark(tmp_db):
    ChatStatusRow.mark("boss-1", "declined", text="暂不考虑")
    responder, _logs, sent = _sending_responder()
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="continue", reply="好的，这个岗位可以聊聊")
    asyncio.run(responder._apply(None, friend, "job-1", decision, "换个岗位看看？"))
    assert sent == ["好的，这个岗位可以聊聊"]
    assert ChatStatusRow.statuses() == {}


def test_resume_is_sent_after_reply_when_hr_asks(tmp_db):
    responder, logs, sent = _sending_responder()
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="continue", reply="好的，简历发您了", send_resume=True)
    asyncio.run(responder._apply(None, friend, "job-1", decision, "方便发份简历吗"))
    assert sent == ["好的，简历发您了", "<简历>"]
    assert any(level == "reply" and "已发送附件简历" in text for level, text in logs)


def test_hr_resume_request_is_accepted_instead_of_sending(tmp_db):
    responder, logs, sent = _sending_responder(request_pending=True)
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="continue", reply="好的，已同意", send_resume=True)
    asyncio.run(responder._apply(None, friend, "job-1", decision, "我想要一份您的附件简历，您是否同意"))
    assert sent == ["好的，已同意", "<同意>"]
    assert any(level == "reply" and "已同意 HR 的附件简历请求" in text for level, text in logs)


def test_resume_failure_asks_for_manual_send(tmp_db):
    responder, logs, sent = _sending_responder(resume_ok=False)
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="continue", reply="好的", send_resume=True)
    asyncio.run(responder._apply(None, friend, "job-1", decision, "发下简历"))
    assert sent == ["好的", "<简历>"]
    assert any(level == "warn" and "手动发送" in text for level, text in logs)


def test_interview_invitation_is_marked(tmp_db):
    responder, logs, _sent = _sending_responder()
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="continue", reply="好的，周三下午可以", interview=True)
    asyncio.run(responder._apply(None, friend, "job-1", decision, "周三下午来面试可以吗"))
    assert ChatStatusRow.statuses() == {"boss-1": "invited"}
    assert any(level == "info" and "已标记有面试" in text for level, text in logs)


def test_interview_detection_keeps_manual_status(tmp_db):
    ChatStatusRow.mark("boss-1", "done")
    responder, logs, _sent = _sending_responder()
    friend = Friend.model_validate(FRIEND)
    decision = ChatDecision(outcome="hr_rejected", interview=True)
    asyncio.run(responder._apply(None, friend, "job-1", decision, "面试没通过，不好意思"))
    assert ChatStatusRow.statuses() == {"boss-1": "done"}
    assert not any("已标记有面试" in text for _level, text in logs)


def test_resume_not_sent_by_default(tmp_db):
    responder, _logs, sent = _sending_responder()
    friend = Friend.model_validate(FRIEND)
    asyncio.run(responder._apply(None, friend, "job-1", ChatDecision(outcome="continue", reply="好的"), "你好"))
    assert sent == ["好的"]


def test_unanswered_is_hr_messages_after_my_last():
    msgs = [
        ChatMessage(mid="1", from_hr=True, text="你好"),
        ChatMessage(mid="2", from_hr=False, text="您好"),
        ChatMessage(mid="3", from_hr=True, text="要有证书"),
        ChatMessage(mid="4", from_hr=True, text=""),
        ChatMessage(mid="5", from_hr=True, text="有吗"),
    ]
    assert [m.mid for m in ChatResponder.unanswered(msgs)] == ["3", "5"]
    assert ChatResponder.unanswered(msgs[:2]) == []


def test_reopen_retries_until_network_recovers():
    responder, logs = _responder()
    results = iter([None, None, True])
    waits: list[float] = []

    async def open_page(_page) -> bool | None:
        return next(results)

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    responder._open_page = open_page  # type: ignore[method-assign]
    responder._sleep = sleep  # type: ignore[method-assign]
    assert asyncio.run(responder._reopen(None))
    assert waits == [ChatResponder.RETRY] * 2
    assert [level for level, _text in logs] == ["warn", "warn"]


def test_reopen_stops_waiting_when_stopped():
    responder, _logs = _responder()

    async def open_page(_page) -> bool | None:
        return None

    async def sleep(_seconds: float) -> None:
        responder.request_stop()

    responder._open_page = open_page  # type: ignore[method-assign]
    responder._sleep = sleep  # type: ignore[method-assign]
    assert asyncio.run(responder._reopen(None))


def test_parse_friends_skips_invalid():
    friends = ChatResponder.parse_friends([FRIEND, {**FRIEND, "encryptBossId": ""}, {"uid": []}])
    assert [f.boss_id for f in friends] == ["boss-1"]
    assert ChatResponder.parse_friends(None) == []
