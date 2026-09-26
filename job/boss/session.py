"""BOSS 浏览器会话：只管 Playwright / Chrome 的启动、复用与关闭。"""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path

from patchright.async_api import BrowserContext, Page, Playwright, async_playwright
from patchright.async_api import Error as PlaywrightError

from job.utils import log


class BossSession:
    """持久化 Chrome profile 的浏览器会话。"""

    def __init__(self, user_data_dir: Path | None = None) -> None:
        self.user_data_dir = user_data_dir or self.default_profile_dir()
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None

    @staticmethod
    def default_profile_dir() -> Path:
        """默认 Chrome 用户数据目录。"""
        return Path.home() / ".ghost-job" / "chrome-profile"

    @property
    def is_open(self) -> bool:
        """浏览器是否已打开。"""
        return self._context is not None

    async def open(self) -> BrowserContext:
        """启动本机 Chrome；已打开则直接复用。"""
        if self._context is None:
            self._context = await self._launch()
        return self._context

    async def page(self) -> Page:
        """复用第一个标签页，没有就新建。"""
        context = await self.open()
        return context.pages[0] if context.pages else await context.new_page()

    async def close(self) -> None:
        """关闭浏览器与 Playwright。"""
        ctx, self._context = self._context, None
        pw, self._playwright = self._playwright, None
        if ctx is not None:
            await self._quietly(ctx.close(), "关闭浏览器")
        if pw is not None:
            await self._quietly(pw.stop(), "停止 Playwright")

    async def _launch(self) -> BrowserContext:
        """启动 Playwright 并打开持久化 Chrome。"""
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._playwright = await async_playwright().start()
            return await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                channel="chrome",
                headless=False,
                no_viewport=True,
            )
        except PlaywrightError as exc:
            await self.close()
            raise RuntimeError(self._launch_error(exc)) from exc

    def _launch_error(self, exc: PlaywrightError) -> str:
        """把启动异常翻译成可读的中文提示。"""
        msg = str(exc).lower()
        # 启动失败日志几乎总会带上 chrome 可执行路径，须先识别 profile 占用。
        if any(k in msg for k in ("user data", "lock", "in use", "singleton")):
            return (
                f"Chrome profile 被占用：{self.user_data_dir}，"
                "请关闭其它使用该目录的 Chrome 后重试。"
            )
        if "channel" in msg or "chrome" in msg:
            return "无法启动本机 Chrome（channel=chrome），请确认已安装 Google Chrome。"
        return f"启动 Chrome 失败：{exc}"

    @staticmethod
    async def _quietly(aw: Awaitable[None], what: str) -> None:
        """清理阶段的失败只打印，不向外抛。"""
        try:
            await aw
        except PlaywrightError as exc:
            log(f"{what}失败: {exc}")
