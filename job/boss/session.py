"""BOSS 浏览器会话：只管 Playwright / Chrome 的启动、复用与关闭。"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

from patchright.async_api import BrowserContext, Page, Playwright, async_playwright
from patchright.async_api import Error as PlaywrightError

from job.utils import log


class BrowserClosed(Exception):
    """浏览器在运行中被关掉（手动关闭或崩溃）。"""


class BossSession:
    """持久化 Chrome profile 的浏览器会话。"""

    # Chrome 自己报 profile 被占用时的特征（Playwright 启动参数里的 BlockOrigin... 也含 lock，不能只搜 lock）
    IN_USE_SIGNS = ("processsingleton", "singletonlock", "already in use")

    def __init__(self, user_data_dir: Path | None = None) -> None:
        self.user_data_dir = user_data_dir or self.default_profile_dir()
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._job_page: Page | None = None

    @staticmethod
    def default_profile_dir() -> Path:
        """默认 Chrome 用户数据目录。"""
        return Path.home() / ".ghost-job" / "chrome-profile"

    @staticmethod
    def chrome_executable() -> Path | None:
        """Windows 上挑一个能用的 Chrome；其他系统或找不到时返回 None，交给 channel 查找。

        Playwright 按 LOCALAPPDATA → Program Files 的顺序取第一个存在的 chrome.exe，
        卸载残留的旧版（只剩 chrome.exe、没有 chrome.dll）也会被选中而启动失败。
        """
        if sys.platform != "win32":
            return None
        drive = os.environ.get("HOMEDRIVE")
        prefixes = [
            os.environ.get("LOCALAPPDATA"),
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            drive and f"{drive}\\Program Files",
            drive and f"{drive}\\Program Files (x86)",
        ]
        for prefix in filter(None, prefixes):
            app = Path(prefix) / "Google" / "Chrome" / "Application"
            exe = app / "chrome.exe"
            if exe.is_file() and any(app.glob("*/chrome.dll")):
                return exe
        return None

    @property
    def is_open(self) -> bool:
        """浏览器是否已打开。"""
        return self._context is not None

    async def open(self) -> BrowserContext:
        """启动本机 Chrome；已打开则直接复用。"""
        if self._context is None:
            # Chrome 被手动关掉或崩溃后还留着 Playwright，先清理再重新启动
            await self.close()
            self._context = await self._launch()
            self._context.on("close", self._on_closed)
            self._job_page = next(iter(self._context.pages), None)
        return self._context

    def _on_closed(self, context: BrowserContext) -> None:
        if self._context is context:
            self._context = None

    async def page(self) -> Page:
        """投递专用的标签页：浏览器启动时自带的那个，被关掉就新开一个。

        自动回复、同步、查企业都另开自己的标签页；不能按「第一个标签页」取，
        启动时的标签被关掉后，第一个就是自动回复的聊天页，两边会互相跳转。
        """
        context = await self.open()
        if self._job_page is None or self._job_page.is_closed():
            self._job_page = await context.new_page()
        return self._job_page

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
        exe = self.chrome_executable()
        browser: dict[str, Any] = (
            {"executable_path": str(exe)} if exe else {"channel": "chrome"}
        )
        try:
            self._playwright = await async_playwright().start()
            return await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=False,
                no_viewport=True,
                **browser,
            )
        except PlaywrightError as exc:
            await self.close()
            raise RuntimeError(self._launch_error(exc)) from exc

    def _launch_error(self, exc: PlaywrightError) -> str:
        """把启动异常翻译成可读的中文提示。"""
        text = str(exc)
        msg = text.lower()
        if any(k in msg for k in self.IN_USE_SIGNS):
            return (
                f"Chrome profile 被占用：{self.user_data_dir}，"
                "请关闭其它使用该目录的 Chrome 后重试。"
            )
        if "distribution" in msg and "is not found" in msg:
            return "无法启动本机 Chrome（channel=chrome），请确认已安装 Google Chrome。"
        # 只留首行原因（去掉「BrowserType.xxx:」前缀），附上实际启动的 Chrome 路径
        reason = text.splitlines()[0].split(": ", 1)[-1] if text else "未知错误"
        if launched := re.search(r"<launching> (.+?) --", text):
            return f"启动 Chrome 失败：{reason}（{launched.group(1)}）"
        return f"启动 Chrome 失败：{reason}"

    @staticmethod
    async def _quietly(aw: Awaitable[None], what: str) -> None:
        """清理阶段的失败只打印，不向外抛。"""
        try:
            await aw
        except PlaywrightError as exc:
            log(f"{what}失败: {exc}")
