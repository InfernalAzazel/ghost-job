"""配置中心「大模型」：DeepSeek API Key 与模型。"""

from __future__ import annotations

import reflex as rx
from pydantic_ai.exceptions import AgentRunError

from job.boss.jobs import Job
from job.boss.review import JobReviewer
from job.models import init_db
from job.models.setting import LlmSettings

# 测试连接用的样例岗位
_SAMPLE_JOB = Job(
    title="AI Agent 开发工程师",
    company="示例科技",
    description="基于大模型搭建智能体与 RAG 系统，使用 Python 开发工具调用和工作流。",
)


class LlmState(rx.State):
    api_key: str = ""
    model: str = LlmSettings.MODELS[0]
    test_hint: str = ""
    testing: bool = False

    model_options: list[str] = list(LlmSettings.MODELS)

    def _settings(self) -> LlmSettings:
        return LlmSettings(api_key=self.api_key, model=self.model)

    @rx.var
    def key_ready(self) -> bool:
        """是否已填写 API Key。"""
        return bool(self.api_key.strip())

    @rx.var
    def key_hint(self) -> str:
        """API Key 输入框下的说明。"""
        if self.api_key.strip():
            return "已保存在本机数据库，只用于调用 DeepSeek"
        return "在 DeepSeek 开放平台创建 API Key 后粘贴到这里"

    @rx.event
    def on_load(self):
        init_db()
        settings = LlmSettings.load()
        self.api_key = settings.api_key
        self.model = settings.model
        self.test_hint = ""

    @rx.event
    def set_api_key(self, value: str):
        self.api_key = value
        self._settings().save()
        self.test_hint = ""

    @rx.event
    def set_model(self, value: str):
        self.model = value
        self._settings().save()
        self.test_hint = ""

    @rx.event(background=True)
    async def test_connection(self):
        """用样例岗位真实调用一次，确认 Key 与模型可用。"""
        async with self:
            settings = self._settings()
            if not settings.api_key:
                self.test_hint = "请先填写 API Key"
                return
            self.testing = True
            self.test_hint = "测试中…"
        reviewer = JobReviewer(requirement="只投 AI 应用开发岗位", llm=settings)
        try:
            verdict = await reviewer.review(_SAMPLE_JOB)
            hint = f"连接成功（样例判断：{verdict.reason or verdict.match}）"
        except AgentRunError as exc:
            hint = f"连接失败：{exc}"
        async with self:
            self.test_hint = hint
            self.testing = False
