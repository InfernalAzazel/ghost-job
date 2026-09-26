"""AI 岗位复核：关键词过滤通过后，让大模型按岗位详情判断意图与简历技术是否匹配。"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings

from job.models.setting import LlmSettings

if TYPE_CHECKING:
    from job.boss.jobs import Job


class Verdict(BaseModel):
    """岗位复核结论。"""

    match: bool = Field(description="岗位是否通过全部复核项")
    reason: str = Field(
        description="20 字以内的中文理由：通过时说明为什么合适，不通过时说明哪一项不满足"
    )
    score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="简历技术匹配度 0–100，没给简历时为 null",
    )


class JobReviewer(BaseModel):
    """用 Pydantic AI 调大模型复核岗位；接口地址、API Key 与模型来自配置中心「AI 服务」。

    两项复核可单独或同时开启，同时开启时一次调用判断：
    ``requirement`` 岗位意图（目标岗位要求），``resume`` 简历技术匹配。
    """

    BASE: ClassVar[str] = (
        "你是求职助手，判断岗位是否值得投递，任一复核项不满足即判不符合。"
    )
    INTENT: ClassVar[str] = (
        "岗位意图：对照目标岗位要求，只看岗位名称和岗位职责，"
        "命中明确排除的方向判不符合。"
    )
    TECH: ClassVar[str] = (
        "简历技术匹配：提取岗位详情里要求的核心技术栈，与简历中的技术对比，"
        "按覆盖程度给出 0–100 的匹配度 score；"
        "核心技术大部分简历里没有则判不符合，加分项技术不要求全部具备。"
    )

    requirement: str = ""
    resume: str = ""
    # 最低匹配度；None 表示不按匹配度过滤
    min_score: int | None = None
    llm: LlmSettings = Field(default_factory=LlmSettings)
    timeout: float = 30

    @classmethod
    def from_config(
        cls, config: Mapping[str, Any], llm: LlmSettings
    ) -> JobReviewer | None:
        """求职配置开启了至少一项复核（且内容非空）时返回复核器，否则返回 None。"""
        requirement = str(config.get("ai_requirement") or "").strip()
        resume = str(config.get("resume_text") or "").strip()
        requirement = requirement if config.get("ai_review") else ""
        resume = resume if config.get("resume_match") else ""
        if not requirement and not resume:
            return None
        min_score = config.get("min_score") if config.get("score_filter") else None
        return cls(
            requirement=requirement, resume=resume, min_score=min_score, llm=llm
        )

    @property
    def checks(self) -> list[str]:
        """已开启的复核项名称。"""
        names = (
            ("AI 岗位筛选", self.requirement),
            ("简历技术匹配", self.resume),
            (f"匹配度 ≥{self.min_score}", self.resume and self.min_score is not None),
        )
        return [name for name, on in names if on]

    @property
    def instructions(self) -> str:
        """按已开启的复核项拼系统提示词。"""
        rules = ((self.INTENT, self.requirement), (self.TECH, self.resume))
        return "\n".join([self.BASE, *(rule for rule, on in rules if on)])

    @cached_property
    def agent(self) -> Agent[None, Verdict]:
        """复核 Agent；服务由配置决定（默认 DeepSeek，也可是任意 OpenAI 兼容接口）。

        结论走提示词 JSON 输出而非工具调用：DeepSeek 思考模式拒绝强制 ``tool_choice``，
        而 Pydantic AI 对不认识的模型名（如 ``deepseek-flash``）无法关闭思考；
        不少兼容接口也不支持工具调用。
        """
        model = OpenAIChatModel(self.llm.model, provider=self.llm.provider)
        return Agent(
            model,
            output_type=PromptedOutput(Verdict),
            instructions=self.instructions,
            model_settings=OpenAIChatModelSettings(
                thinking=False, temperature=0, timeout=self.timeout
            ),
        )

    async def check(self, job: Job) -> Verdict:
        """复核岗位：是否合适、原因与匹配度（含最低匹配度判断）。

        未开启简历技术匹配时匹配度为 None；接口出错时抛 ``AgentRunError``。
        """
        verdict = await self.review(job)
        score = verdict.score if self.resume else None
        low = score is not None and self.min_score is not None and score < self.min_score
        if verdict.match and low:
            reason = f"匹配度 {score} 分，低于 {self.min_score} 分"
            return Verdict(match=False, reason=reason, score=score)
        return verdict.model_copy(update={"score": score})

    async def review(self, job: Job) -> Verdict:
        """调用模型给出结论；接口出错或输出不合规时抛 ``AgentRunError``。"""
        result = await self.agent.run(self._prompt(job))
        return result.output

    def _prompt(self, job: Job) -> str:
        parts = [
            f"目标岗位要求：\n{self.requirement}" if self.requirement else "",
            f"求职者简历：\n{self.resume}" if self.resume else "",
            (
                f"岗位名称：{job.title}\n公司：{job.company}\n薪资：{job.salary}\n"
                f"岗位详情：\n{job.description}"
            ),
        ]
        return "\n\n".join(p for p in parts if p)
