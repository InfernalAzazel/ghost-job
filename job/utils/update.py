"""检查 GitHub 上是否有新版本。"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from packaging.version import InvalidVersion, Version

from job import __version__

REPO_URL = "https://github.com/InfernalAzazel/ghost-job"
# 用网页的跳转而不是 api.github.com：国内网络常连不上 API
LATEST_URL = f"{REPO_URL}/releases/latest"
TAG_PATH = "/releases/tag/"


@dataclass(frozen=True)
class Release:
    version: str
    url: str


async def latest_release() -> Release | None:
    """最新正式版（取 releases/latest 跳转到的 tag 页面）；网络异常或没有跳转时返回 None。"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.head(LATEST_URL)
    except httpx.HTTPError:
        return None
    url = resp.headers.get("location", "")
    if not resp.is_redirect or TAG_PATH not in url:
        return None
    return Release(version=url.rsplit(TAG_PATH, 1)[1].removeprefix("v"), url=url)


_checked = False
_newer: Release | None = None


async def check() -> Release | None:
    """比当前版本新的正式版；请求成功后本进程不再请求，失败则下次调用重试。"""
    global _checked, _newer
    if not _checked:
        release = await latest_release()
        _checked = release is not None
        try:
            _newer = (
                release
                if release and Version(release.version) > Version(__version__)
                else None
            )
        except InvalidVersion:
            _newer = None
    return _newer
