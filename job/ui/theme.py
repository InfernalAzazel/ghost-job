"""Shared UI tokens for Ghost Job."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import reflex as rx

if TYPE_CHECKING:
    from reflex_components_radix.themes.base import LiteralAccentColor

ACCENT = "#2B6DE5"
BG = "#F4F6F9"
CARD = "#FFFFFF"
TEXT = "#1F2937"
MUTED = "#6B7280"
BORDER = "#E5E7EB"
ACCENT_SOFT = "#E8F0FE"


def color_by(
    value: rx.Var[str],
    colors: dict[str, LiteralAccentColor],
    default: LiteralAccentColor = "gray",
) -> rx.Var[LiteralAccentColor]:
    """按取值选标签颜色（用于 color_scheme）。

    分支全是字符串时 rx.match 返回的是 Var，只是类型标注为 Component | Var。
    """
    return cast("rx.Var[LiteralAccentColor]", rx.match(value, *colors.items(), default))
