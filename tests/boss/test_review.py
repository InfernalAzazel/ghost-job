"""Tests for AI job intent review."""

from __future__ import annotations

import asyncio

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from job.boss.jobs import Job
from job.boss.review import JobReviewer
from job.models.setting import LlmSettings

LLM = LlmSettings(api_key="k", model="deepseek-v4-pro")
JOB = Job(title="AI Agent 开发工程师", company="某科技", description="搭建 LLM 智能体")


def _reviewer_answering(match: bool, reason: str, prompts: list[str] | None = None):
    """复核器的模型换成本地函数：记录提示词，按给定结论调用输出工具。"""

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if prompts is not None:
            prompts.append(str(messages[-1].parts[-1].content))
        tool = info.output_tools[0].name
        args = {"match": match, "reason": reason}
        return ModelResponse(parts=[ToolCallPart(tool, args)])

    reviewer = JobReviewer(requirement="只投 Agent", llm=LLM)
    return reviewer, reviewer.agent.override(model=FunctionModel(answer))


def test_from_plan_requires_switch_and_requirement():
    off = {"ai_review": False, "ai_requirement": "x"}
    blank = {"ai_review": True, "ai_requirement": "  "}
    assert JobReviewer.from_plan(off, LLM) is None
    assert JobReviewer.from_plan(blank, LLM) is None
    plan = {"ai_review": True, "ai_requirement": " 只投 Agent "}
    reviewer = JobReviewer.from_plan(plan, LLM)
    assert reviewer is not None and reviewer.requirement == "只投 Agent"


def test_agent_uses_configured_model():
    reviewer = JobReviewer(requirement="只投 Agent", llm=LLM)
    assert reviewer.agent.model.model_name == "deepseek-v4-pro"


def test_match_passes_and_prompt_has_requirement():
    prompts: list[str] = []
    reviewer, override = _reviewer_answering(True, "Agent 开发", prompts)
    with override:
        assert asyncio.run(reviewer.reject_reason(JOB)) == ""
    assert "只投 Agent" in prompts[0] and "搭建 LLM 智能体" in prompts[0]


def test_mismatch_rejects_with_reason():
    reviewer, override = _reviewer_answering(False, "销售岗")
    with override:
        assert asyncio.run(reviewer.reject_reason(JOB)) == "AI 复核不通过：销售岗"


def test_api_error_rejects():
    def fail(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=401, model_name="deepseek-v4-flash")

    reviewer = JobReviewer(requirement="只投 Agent", llm=LLM)
    with reviewer.agent.override(model=FunctionModel(fail)):
        assert asyncio.run(reviewer.reject_reason(JOB)).startswith("AI 复核失败")


def test_api_key_is_trimmed():
    assert LlmSettings(api_key="  sk-1 \n").api_key == "sk-1"


def test_unknown_model_falls_back_to_default():
    assert LlmSettings(model="deepseek-chat").model == LlmSettings.MODELS[0]
