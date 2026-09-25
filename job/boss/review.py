"""AI 岗位意图复核：关键词过滤通过后，让 DeepSeek 按岗位职责判断是否符合求职要求。"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.deepseek import DeepSeekProvider

from job.models.setting import LlmSettings

if TYPE_CHECKING:
    from job.boss.jobs import Job


class Verdict(BaseModel):
    """岗位复核结论。"""

    match: bool = Field(description="岗位是否符合求职者的目标岗位要求")
    reason: str = Field(description="20 字以内的中文理由")


class JobReviewer(BaseModel):
    """用 Pydantic AI 调 DeepSeek 复核岗位；API Key 与模型来自配置中心「大模型」。"""

    INSTRUCTIONS: ClassVar[str] = (
        "你是求职助手，根据求职者的目标岗位要求判断岗位是否值得投递。"
        "只看岗位名称和岗位职责，命中明确排除的方向一律判不符合。"
    )

    requirement: str
    llm: LlmSettings = Field(default_factory=LlmSettings)
    timeout: float = 30

    @classmethod
    def from_plan(
        cls, plan: Mapping[str, Any], llm: LlmSettings
    ) -> JobReviewer | None:
        """方案开启复核且写了目标要求时返回复核器，否则返回 None。"""
        requirement = str(plan.get("ai_requirement") or "").strip()
        if not plan.get("ai_review") or not requirement:
            return None
        return cls(requirement=requirement, llm=llm)

    @cached_property
    def agent(self) -> Agent[None, Verdict]:
        """DeepSeek 结构化输出 Agent（关闭思考模式，输出更稳定）。"""
        model = OpenAIChatModel(
            self.llm.model,
            provider=DeepSeekProvider(api_key=self.llm.api_key),
        )
        return Agent(
            model,
            output_type=Verdict,
            instructions=self.INSTRUCTIONS,
            model_settings=OpenAIChatModelSettings(
                thinking=False, temperature=0, timeout=self.timeout
            ),
        )

    async def reject_reason(self, job: Job) -> str:
        """复核通过返回空串；不通过或调用异常时返回跳过原因。"""
        try:
            verdict = await self.review(job)
        except AgentRunError as exc:
            return f"AI 复核失败：{exc}"
        return "" if verdict.match else f"AI 复核不通过：{verdict.reason}"

    async def review(self, job: Job) -> Verdict:
        """调用模型给出结论；接口出错或输出不合规时抛 ``AgentRunError``。"""
        result = await self.agent.run(self._prompt(job))
        return result.output

    def _prompt(self, job: Job) -> str:
        return (
            f"目标岗位要求：\n{self.requirement}\n\n"
            f"岗位名称：{job.title}\n公司：{job.company}\n薪资：{job.salary}\n"
            f"岗位职责：\n{job.description}"
        )
