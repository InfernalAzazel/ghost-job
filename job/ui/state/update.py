"""导航栏的新版本提示，以及用系统浏览器打开外部链接。"""

from __future__ import annotations

import webbrowser

import reflex as rx

from job.utils import update


class UpdateState(rx.State):
    # 比当前新的版本号与 Release 页面；没有新版本时为空
    latest: str = ""
    url: str = ""

    @rx.event(background=True)
    async def check(self):
        release = await update.check()
        if release:
            async with self:
                self.latest = release.version
                self.url = release.url

    @rx.event
    def open_release(self):
        if self.url:
            webbrowser.open(self.url)

    @rx.event
    def open_link(self, url: str):
        """用系统浏览器打开链接（桌面窗口里的普通链接打不开外部网页）。"""
        webbrowser.open(url)
