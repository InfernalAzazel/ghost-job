"""Shared page chrome: fixed viewport, no document scroll."""

from __future__ import annotations

import reflex as rx

from job.ui.theme import BG, TEXT

# Applied once so the document itself never scrolls.
PAGE_ROOT_STYLE = {
    "colorScheme": "light",
    "overflow": "hidden",
}


def page_root(*children, max_width: str = "1100px") -> rx.Component:
    """Full-viewport shell: outer never scrolls; children fill remaining height."""
    return rx.box(
        rx.box(
            *children,
            max_width=max_width,
            width="100%",
            margin="0 auto",
            padding="1.25em 1.5em 1.25em",
            height="100%",
            display="flex",
            flex_direction="column",
            min_height="0",
            overflow="hidden",
        ),
        bg=BG,
        color=TEXT,
        height="100vh",
        width="100%",
        overflow="hidden",
        style=PAGE_ROOT_STYLE,
    )
