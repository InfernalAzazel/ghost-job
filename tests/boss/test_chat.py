"""BOSS 聊天：会话列表解析、消息入库去重、回复提示词与 HR 主动沟通的新岗位入库。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from job import models as models_pkg
from job.boss.chat import ChatReplier, ChatResponder, Friend, job_from_boss_data
from job.boss.filters import KeywordFilter
from job.boss.jobs import Job
from job.boss.review import Verdict
from job.models import init_db, reset_engine
from job.models.chat import ChatMessage, ChatMessageRow
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


def test_friend_waiting_only_when_hr_sent_unread():
    friend = Friend.model_validate(FRIEND)
    assert friend.waiting and friend.label == "王女士 · 示例科技"
    assert not Friend.model_validate({**FRIEND, "unreadMsgCount": 0}).waiting
    mine = {**FRIEND, "lastMessageInfo": {"fromId": 2002}}
    assert not Friend.model_validate(mine).waiting


def test_friend_tolerates_nulls():
    friend = Friend.model_validate(
        {**FRIEND, "unreadMsgCount": None, "lastMessageInfo": None, "brandName": None}
    )
    assert friend.unread == 0 and friend.company == "" and not friend.waiting


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
        return ModelResponse(parts=[TextPart("可以的，\n我马上发送附件简历。")])

    with replier.agent.override(model=FunctionModel(answer)):
        text = asyncio.run(replier.reply(job, history, ""))
    assert text == "可以的， 我马上发送附件简历。"


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


class FakeResponse:
    def __init__(self, url: str, payload: dict) -> None:
        self.status, self.url, self._payload = 200, url, payload

    async def json(self) -> dict:
        return self._payload


def test_friend_list_listener_collects_friends():
    responder, _ = _responder()
    payload = {"zpData": {"result": [FRIEND, {**FRIEND, "encryptBossId": ""}, {"uid": []}]}}
    asyncio.run(responder._on_friend_list(FakeResponse("https://x/getGeekFriendList.json", payload)))
    assert list(responder._friends) == ["boss-1"]
