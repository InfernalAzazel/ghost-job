"""配置中心「AI 服务」：接口地址（默认 DeepSeek）→ API Key → 拉取最新模型 → 选择模型。"""

from __future__ import annotations

import reflex as rx
from openai import APIError
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
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    model_options: list[str] = rx.field(default_factory=list)
    # 进行中的操作：fetch / test；空表示空闲
    action: str = ""

    def _settings(self) -> LlmSettings:
        return LlmSettings(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            models=self.model_options,
        )

    @rx.var
    def key_ready(self) -> bool:
        """是否已填写 API Key 并选好模型（AI 复核可用）。"""
        return bool(self.api_key.strip() and self.model)

    @rx.event
    def on_load(self):
        init_db()
        settings = LlmSettings.load()
        self.base_url = settings.base_url
        self.api_key = settings.api_key
        self.model = settings.model
        self.model_options = settings.models

    @rx.event
    def set_base_url(self, value: str):
        """换服务后旧模型列表不再适用，清空待重新获取。"""
        if value.strip() == self.base_url.strip():
            return
        self.base_url = value
        self.model = ""
        self.model_options = []
        self._settings().save()

    @rx.event
    def set_api_key(self, value: str):
        self.api_key = value
        self._settings().save()

    @rx.event
    def set_model(self, value: str):
        self.model = value
        self._settings().save()

    @rx.event(background=True)
    async def fetch_models(self):
        """用填写的接口地址和 Key 拉取最新模型列表。"""
        async with self:
            settings = self._settings()
            if not settings.api_key:
                return rx.toast.warning("请先填写 API Key")
            self.action = "fetch"
        try:
            models = await settings.fetch_models()
        except APIError as exc:
            async with self:
                self.action = ""
            return rx.toast.error(f"获取失败，请检查接口地址和 API Key：{exc.message}")
        async with self:
            self.action = ""
            if models:
                self.model_options = models
                if self.model not in models:
                    self.model = models[0]
                self._settings().save()
        return rx.toast.success(f"已获取 {len(models)} 个可用模型，请选择")

    @rx.event(background=True)
    async def test_connection(self):
        """用样例岗位真实调用一次，确认 Key 与模型可用。"""
        async with self:
            settings = self._settings()
            if not settings.ready:
                return rx.toast.warning("请先填写 API Key 并选择模型")
            self.action = "test"
        reviewer = JobReviewer(requirement="只投 AI 应用开发岗位", llm=settings)
        try:
            await reviewer.review(_SAMPLE_JOB)
        except AgentRunError as exc:
            async with self:
                self.action = ""
            return rx.toast.error(f"连接失败，请检查接口地址、API Key 和模型：{exc}")
        async with self:
            self.action = ""
        return rx.toast.success("连接成功，AI 服务可以正常使用")
