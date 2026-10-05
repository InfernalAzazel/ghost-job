import logging
import os
import sys
from pathlib import Path

import reflex as rx
from reflex_desktop import DesktopPlugin

# Windows GUI launches have no stdout/stderr (None), which crashes uvicorn's logging
# setup; macOS GUI launches point them at /dev/null. Installed builds (embedded
# backend) log to a file.
if (
    sys.stdout is None
    or sys.stderr is None
    or os.environ.get("REFLEX_DESKTOP_APP_ROOT")
):
    _log = Path.home() / ".ghost-job" / "logs" / "backend.log"
    _log.parent.mkdir(parents=True, exist_ok=True)
    _big = _log.exists() and _log.stat().st_size > 5 * 1024 * 1024
    _stream = _log.open("w" if _big else "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _stream
    # Outside the reflex CLI no handler is attached, so backend exceptions would vanish
    _handler = logging.StreamHandler(_stream)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    _handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(_handler)

config = rx.Config(
    app_name="job",
    app_module_import="job.ui.app",
    cors_allowed_origins=["*"],
    show_built_with_reflex=False,
    # 界面状态默认 1 小时没访问就被清掉：最小化挂机时自动投递/回复仍在跑，界面却变回「未开启」
    # 名字带 redis，但未配置 Redis 时的内存状态也读这个值，不需要安装 Redis
    redis_token_expiration=60 * 60 * 24 * 30,
    plugins=[
        DesktopPlugin(
            # 发布包内置 Python 后端；`reflex-desktop dev` 会自动改用本地 dev 服务
            backend="embedded",
            product_name="Ghost Job",
            identifier="com.infernalazazel.ghostjob",
            window_title="Ghost Job",
            window_width=1180,
            window_height=820,
            center=True,
            # 导出 CSV 用系统保存对话框
            tauri_plugins=("dialog",),
            # Do NOT set icon= here: DesktopPlugin copies the source over 32x32.png
            # etc. without resizing. Generate sizes with:
            #   cd tauri-dev/src-tauri && cargo tauri icon ../../assets/icon.png
        ),
        rx.plugins.SitemapPlugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(
                appearance="light",
                accent_color="blue",
                radius="large",
                has_background=True,
            ),
        ),
    ],
)
