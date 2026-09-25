import reflex as rx
from reflex_desktop import DesktopPlugin

config = rx.Config(
    app_name="job",
    app_module_import="job.ui.app",
    cors_allowed_origins=["*"],
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
