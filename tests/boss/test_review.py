"""Tests for AI job intent review."""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic_ai.exceptions import AgentRunError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider

from job.boss.jobs import Job
from job.boss.review import JobReviewer, Verdict
from job.models.setting import LlmSettings

LLM = LlmSettings(api_key="k", model="deepseek-v4-pro")
JOB = Job(title="AI Agent 开发工程师", company="某科技", description="搭建 LLM 智能体")


def _reviewer_answering(
    match: bool,
    reason: str,
    prompts: list[str] | None = None,
    *,
    score: int | None = None,
    resume: str = "",
):
    """复核器的模型换成本地函数：记录提示词，按给定结论回复 JSON 文本。"""

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert not info.output_tools, "不能走工具调用，DeepSeek 思考模式会拒绝"
        if prompts is not None:
            prompts.append(str(messages[-1].parts[-1].content))
        verdict = {"match": match, "reason": reason, "score": score}
        return ModelResponse(parts=[TextPart(json.dumps(verdict, ensure_ascii=False))])

    reviewer = JobReviewer(requirement="只投 Agent", resume=resume, llm=LLM)
    return reviewer, reviewer.agent.override(model=FunctionModel(answer))


def test_from_config_requires_switch_and_requirement():
    off = {"ai_review": False, "ai_requirement": "x"}
    blank = {"ai_review": True, "ai_requirement": "  "}
    assert JobReviewer.from_config(off, LLM) is None
    assert JobReviewer.from_config(blank, LLM) is None
    config = {"ai_review": True, "ai_requirement": " 只投 Agent "}
    reviewer = JobReviewer.from_config(config, LLM)
    assert reviewer is not None and reviewer.requirement == "只投 Agent"


def test_from_config_resume_match():
    config = {"resume_match": True, "resume_text": " Python / LangGraph "}
    reviewer = JobReviewer.from_config(config, LLM)
    assert reviewer is not None
    assert reviewer.resume == "Python / LangGraph" and reviewer.requirement == ""
    assert reviewer.checks == ["简历技术匹配"]
    assert "简历技术匹配" in reviewer.instructions
    assert "岗位意图" not in reviewer.instructions
    assert JobReviewer.from_config({"resume_match": True, "resume_text": ""}, LLM) is None
    assert JobReviewer.from_config({"resume_text": "Python"}, LLM) is None


def test_both_checks_in_one_prompt():
    config = {
        "ai_review": True,
        "ai_requirement": "只投 Agent",
        "resume_match": True,
        "resume_text": "Python LangGraph",
    }
    reviewer = JobReviewer.from_config(config, LLM)
    assert reviewer is not None and reviewer.checks == ["AI 岗位筛选", "简历技术匹配"]
    prompt = reviewer._prompt(JOB)
    assert "只投 Agent" in prompt and "Python LangGraph" in prompt
    assert "搭建 LLM 智能体" in prompt


def test_agent_uses_configured_model():
    reviewer = JobReviewer(requirement="只投 Agent", llm=LLM)
    assert reviewer.agent.model.model_name == "deepseek-v4-pro"


def test_match_passes_and_prompt_has_requirement():
    prompts: list[str] = []
    reviewer, override = _reviewer_answering(True, "Agent 开发", prompts)
    with override:
        assert asyncio.run(reviewer.check(JOB)) == Verdict(match=True, reason="Agent 开发")
    assert "只投 Agent" in prompts[0] and "搭建 LLM 智能体" in prompts[0]


def test_mismatch_rejects_with_reason():
    reviewer, override = _reviewer_answering(False, "销售岗")
    with override:
        assert asyncio.run(reviewer.check(JOB)) == Verdict(match=False, reason="销售岗")


def test_resume_match_returns_score():
    reviewer, override = _reviewer_answering(
        True, "技术吻合", score=85, resume="Python"
    )
    with override:
        assert asyncio.run(reviewer.check(JOB)) == Verdict(
            match=True, reason="技术吻合", score=85
        )


def test_min_score_from_config_only_when_enabled():
    config = {"resume_match": True, "resume_text": "Python", "min_score": 70}
    assert JobReviewer.from_config(config, LLM).min_score is None
    reviewer = JobReviewer.from_config({**config, "score_filter": True}, LLM)
    assert reviewer.min_score == 70
    assert reviewer.checks == ["简历技术匹配", "匹配度 ≥70"]


def test_low_score_rejected_by_min_score():
    reviewer, override = _reviewer_answering(
        True, "部分吻合", score=55, resume="Python"
    )
    with override:
        reviewer.min_score = 60
        assert asyncio.run(reviewer.check(JOB)) == Verdict(
            match=False, reason="匹配度 55 分，低于 60 分", score=55
        )
        reviewer.min_score = 50
        assert asyncio.run(reviewer.check(JOB)).match is True


def test_score_ignored_without_resume():
    reviewer, override = _reviewer_answering(True, "Agent 开发", score=85)
    with override:
        assert asyncio.run(reviewer.check(JOB)).score is None


def test_api_error_raises():
    def fail(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=401, model_name="deepseek-v4-flash")

    reviewer = JobReviewer(requirement="只投 Agent", llm=LLM)
    with (
        reviewer.agent.override(model=FunctionModel(fail)),
        pytest.raises(AgentRunError),
    ):
        asyncio.run(reviewer.check(JOB))


def test_api_key_is_trimmed():
    assert LlmSettings(api_key="  sk-1 \n").api_key == "sk-1"


def test_provider_defaults_to_deepseek():
    assert isinstance(LLM.provider, DeepSeekProvider)
    assert str(LLM.provider.client.base_url).startswith(LlmSettings.DEFAULT_BASE_URL)


def test_provider_uses_custom_base_url():
    llm = LlmSettings(base_url=" http://localhost:11434/v1 ", api_key="k", model="qwen3")
    assert isinstance(llm.provider, OpenAIProvider)
    assert str(llm.provider.client.base_url) == "http://localhost:11434/v1/"


def test_ready_needs_key_and_model():
    assert not LlmSettings(api_key="k").ready
    assert not LlmSettings(model="deepseek-v4-pro").ready
    assert LLM.ready
