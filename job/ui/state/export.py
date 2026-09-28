"""导出文件：桌面端弹系统保存框选位置，普通浏览器（开发调试）改用浏览器下载。"""

from __future__ import annotations

import json
from pathlib import Path

# 保存框回传的标记：不在桌面端，改用浏览器下载
BROWSER_DOWNLOAD = "__browser_download__"


def save_dialog_script(filename: str, kind: str, extension: str) -> str:
    """弹出保存框的脚本，回传选中的路径；取消回传空，不在桌面端回传 ``BROWSER_DOWNLOAD``。"""
    options = {
        "defaultPath": str(Path.home() / "Downloads" / filename),
        "filters": [{"name": kind, "extensions": [extension]}],
    }
    return (
        f"window.__TAURI__?.dialog ? window.__TAURI__.dialog.save({json.dumps(options)})"
        f" : {json.dumps(BROWSER_DOWNLOAD)}"
    )
