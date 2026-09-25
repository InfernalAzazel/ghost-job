"""通用小工具。"""

from __future__ import annotations

from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    """是 dict 就原样返回，否则返回空 dict（接口数据防御用）。"""
    return value if isinstance(value, dict) else {}


def log(msg: str, tag: str = "boss") -> None:
    """带模块前缀打印一行日志，立即刷新。"""
    print(f"[{tag}] {msg}", flush=True)
