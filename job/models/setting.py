"""全局设置：键值表 + 大模型配置。"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_ai.providers.deepseek import DeepSeekProvider
from sqlmodel import Field, SQLModel


class SettingRow(SQLModel, table=True):
    """全局键值配置（与求职方案无关的设置）。"""

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


class LlmSettings(BaseModel):
    """大模型配置：先填 API Key，再拉取可用模型并选择；存在设置表里。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    # 设置表里的键前缀
    PREFIX: ClassVar[str] = "llm_"

    api_key: str = ""
    model: str = ""
    # 上次从 DeepSeek 拉到的可用模型
    models: list[str] = []

    @property
    def ready(self) -> bool:
        """Key 和模型都已配置。"""
        return bool(self.api_key and self.model)

    @field_validator("models", mode="before")
    @classmethod
    def _parse_models(cls, value: Any) -> Any:
        """设置表里存的是 JSON 字符串。"""
        return json.loads(value or "[]") if isinstance(value, str) else value

    @classmethod
    def load(cls) -> LlmSettings:
        keys = tuple(f"{cls.PREFIX}{f}" for f in cls.model_fields)
        stored = SettingRow.get_many(keys)
        return cls(**{k.removeprefix(cls.PREFIX): v for k, v in stored.items()})

    def save(self) -> None:
        data = {
            f"{self.PREFIX}{k}": v if isinstance(v, str) else json.dumps(v)
            for k, v in self.model_dump().items()
        }
        SettingRow.put_many(data)

    async def fetch_models(self) -> list[str]:
        """用当前 API Key 拉取 DeepSeek 可用模型；失败时抛 ``openai.APIError``。"""
        client = DeepSeekProvider(api_key=self.api_key).client
        return sorted([m.id async for m in client.models.list()])
