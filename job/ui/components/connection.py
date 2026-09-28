"""连不上后端时的全屏遮罩，替换 Reflex 默认的英文连接错误提示。"""

from __future__ import annotations

import reflex as rx

from job.ui.theme import ACCENT, BG, MUTED, TEXT


def connection_overlay() -> rx.Component:
    """打包后的程序窗口先于内置后端就绪，启动的几秒里会连不上；连上后自动消失。

    这一层包在 Radix 主题外面，只用原生元素和内联样式。
    """
    return rx.connection_banner(
        rx.el.div(
            rx.el.div(
                style={
                    "width": "28px",
                    "height": "28px",
                    "border": f"3px solid {ACCENT}33",
                    "border_top_color": ACCENT,
                    "border_radius": "50%",
                    "animation": "ghost-spin 0.8s linear infinite",
                },
            ),
            rx.el.div(
                "Ghost Job 正在启动，请稍候…",
                style={"font_weight": "600", "color": TEXT, "font_size": "15px"},
            ),
            rx.el.div(
                "刚打开程序时需要几秒钟连接后台服务",
                style={"color": MUTED, "font_size": "13px"},
            ),
            rx.el.style("@keyframes ghost-spin { to { transform: rotate(360deg); } }"),
            style={
                "position": "fixed",
                "top": "0",
                "left": "0",
                "width": "100vw",
                "height": "100vh",
                "z_index": "9999",
                "display": "flex",
                "flex_direction": "column",
                "align_items": "center",
                "justify_content": "center",
                "gap": "12px",
                "background": BG,
                "font_family": "system-ui, -apple-system, sans-serif",
            },
        )
    )
