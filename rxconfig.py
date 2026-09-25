import reflex as rx
from reflex_desktop import DesktopPlugin

config = rx.Config(
    app_name="job",
    app_module_import="job.ui.app",
    cors_allowed_origins=["*"],
    plugins=[
        DesktopPlugin(
            backend="remote",
            product_name="Ghost Job",
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
