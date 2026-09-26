"""全局设置：键值表 + 大模型配置 + 自动回复配置。"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider
from sqlmodel import Field, SQLModel

from job.boss.filters import Defaults, ReplyPaceProfile


class SettingRow(SQLModel, table=True):
    """全局键值配置（与求职配置无关的设置）。"""

    __tablename__ = "app_setting"

    key: str = Field(primary_key=True)
    value: str = ""

    @classmethod
    def get_many(cls, keys: tuple[str, ...]) -> dict[str, str]:
        """批量读取；没存过的键不出现在结果里。"""
        from job.models import db_session

        with db_session() as session:
            return {k: row.value for k in keys if (row := session.get(cls, k))}

    @classmethod
    def put_many(cls, values: dict[str, str]) -> None:
        """批量写入（有则覆盖）。"""
        from job.models import db_session

        with db_session() as session:
            for key, value in values.items():
                session.merge(cls(key=key, value=value))
            session.commit()


class KeyValueSettings(BaseModel):
    """存在设置表里的一组配置：每个字段存为 ``<PREFIX><字段名>`` 一行。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    # 设置表里的键前缀，子类必须覆盖
    PREFIX: ClassVar[str] = ""

    @classmethod
    def load(cls) -> Self:
        """读取已保存的字段；非字符串字段存的是 JSON，解析失败的按默认值。"""
        keys = tuple(f"{cls.PREFIX}{f}" for f in cls.model_fields)
        data: dict[str, Any] = {}
        for key, raw in SettingRow.get_many(keys).items():
            name = key.removeprefix(cls.PREFIX)
            if cls.model_fields[name].annotation is str:
                data[name] = raw
                continue
            try:
                data[name] = json.loads(raw)
            except json.JSONDecodeError:
                continue
        return cls(**data)

    def save(self) -> None:
        data = {
            f"{self.PREFIX}{k}": v if isinstance(v, str) else json.dumps(v)
            for k, v in self.model_dump().items()
        }
        SettingRow.put_many(data)


class AutoReplySettings(KeyValueSettings):
    """自动回复配置：是否启用与回复提示词；需已开通 AI 服务并配置简历。"""

    PREFIX: ClassVar[str] = "reply_"
    DEFAULT_PROMPT: ClassVar[str] = (
        "你是正在求职的我，在 BOSS 直聘上和 HR 沟通。请根据我的简历回复 HR 的最新消息：\n"
        "1. 语气礼貌、真诚、简洁，每次回复不超过 100 字\n"
        "2. 只根据简历里的真实经历回答，不编造经历和技能\n"
        "3. HR 索要简历时，回复可以发送附件简历\n"
        "4. 薪资、到岗时间等简历里没有的信息，委婉表示可以进一步沟通\n"
        "5. 岗位明显不合适时，礼貌说明并感谢对方"
    )

    enabled: bool = False
    prompt: str = DEFAULT_PROMPT
    # 回复节奏档位（slow / normal / fast / custom），明细见 ``ReplyPaceProfile``
    pace: str = Defaults.PACE
    # 「自定义」档的明细参数
    pace_params: dict[str, float] = {}

    @property
    def pace_profile(self) -> ReplyPaceProfile:
        """当前档位对应的回复节奏。"""
        return ReplyPaceProfile.from_saved(self.pace, self.pace_params)


class LlmSettings(KeyValueSettings):
    """大模型配置：接口地址、API Key，再拉取可用模型并选择；存在设置表里。

    接口地址为空时用 DeepSeek 官方服务，填写后按 OpenAI 兼容接口调用。
    """

    PREFIX: ClassVar[str] = "llm_"
    # 默认服务（接口地址留空时）
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.deepseek.com"

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    # 上次拉到的可用模型
    models: list[str] = []

    @property
    def ready(self) -> bool:
        """Key 和模型都已配置。"""
        return bool(self.api_key and self.model)

    @property
    def provider(self) -> DeepSeekProvider | OpenAIProvider:
        """模型服务：接口地址为空用 DeepSeek，否则用 OpenAI 兼容接口。"""
        if not self.base_url:
            return DeepSeekProvider(api_key=self.api_key)
        return OpenAIProvider(base_url=self.base_url, api_key=self.api_key)

    async def fetch_models(self) -> list[str]:
        """拉取当前服务的可用模型；失败时抛 ``openai.APIError``。"""
        client = self.provider.client
        return sorted([m.id async for m in client.models.list()])
