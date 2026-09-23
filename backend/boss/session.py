from __future__ import annotations

import os

from patchright.async_api import Browser, Page, async_playwright

from backend.boss.jobs import (
    CARD_SELECTOR,
    DEFAULT_SEARCH_URL,
    Job,
    looks_like_login_wall,
    parse_jobs_from_html,
)

DEFAULT_CDP_URL = "http://127.0.0.1:9222"

_CDP_HINT = (
    "无法连接 Chrome CDP。请先完全退出 Chrome，再用调试端口启动，例如：\n"
    '/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222'
)


def resolve_cdp_url() -> str:
    return os.environ.get("GHOSTJOB_CDP_URL", DEFAULT_CDP_URL)


class BossSession:
    def __init__(self, cdp_url: str | None = None) -> None:
        self.cdp_url = cdp_url or resolve_cdp_url()
        self._playwright = None
        self._browser: Browser | None = None

    @property
    def is_open(self) -> bool:
        return self._browser is not None

    async def open(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
        except Exception as exc:  # noqa: BLE001
            await self.close()
            raise RuntimeError(f"{_CDP_HINT}\n当前 CDP：{self.cdp_url}\n原因：{exc}") from exc

    async def close(self) -> None:
        # 只断开 CDP，不关闭用户 Chrome
        self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None

    async def _page(self) -> Page:
        if self._browser is None:
            raise RuntimeError("BossSession 未连接，请先 boss.open")
        contexts = self._browser.contexts
        if not contexts:
            raise RuntimeError("CDP 已连接但没有 browser context")
        # Prefer a fresh tab so we never navigate away from the user's active page.
        return await contexts[0].new_page()

    async def search(self, url: str | None = None) -> tuple[str, list[Job], str]:
        if self._browser is None:
            await self.open()
        target = url or DEFAULT_SEARCH_URL
        page = await self._page()
        await page.goto(target, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector(CARD_SELECTOR, timeout=20_000)
        except Exception:  # noqa: BLE001
            html = await page.content()
            final = page.url
            if looks_like_login_wall(html, final):
                return final, [], "need_login"
            return final, parse_jobs_from_html(html), "done"
        html = await page.content()
        final = page.url
        if looks_like_login_wall(html, final):
            return final, [], "need_login"
        return final, parse_jobs_from_html(html), "done"
