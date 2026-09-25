"""全局设置：键值表 + 大模型配置。"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator
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
    """大模型配置：API Key 与模型都在配置中心「大模型」填写，存在设置表里。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    MODELS: ClassVar[tuple[str, ...]] = ("deepseek-v4-flash", "deepseek-v4-pro")
    # 设置表里的键前缀
    PREFIX: ClassVar[str] = "llm_"

    api_key: str = ""
    model: str = MODELS[0]

    @field_validator("model")
    @classmethod
    def _known_model(cls, value: str) -> str:
        """不在可选列表里的模型名（如旧版本存的）回落到默认模型。"""
        return value if value in cls.MODELS else cls.MODELS[0]
    @classmethod
    def load(cls) -> LlmSettings:
        keys = tuple(f"{cls.PREFIX}{f}" for f in cls.model_fields)
        stored = SettingRow.get_many(keys)
        return cls(**{k.removeprefix(cls.PREFIX): v for k, v in stored.items()})

    def save(self) -> None:
        data = self.model_dump()
        SettingRow.put_many({f"{self.PREFIX}{k}": v for k, v in data.items()})
