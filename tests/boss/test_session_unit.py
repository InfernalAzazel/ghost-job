"""BossSession 配置单元测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, cast

from patchright.async_api import Error as PlaywrightError

from job.boss.session import BossSession

if TYPE_CHECKING:
    from patchright.async_api import BrowserContext, Page

_INSTALL_HINT = "无法启动本机 Chrome（channel=chrome），请确认已安装 Google Chrome。"


def test_default_profile_dir_under_home(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    d = BossSession.default_profile_dir()
    assert d == tmp_path / ".ghost-job" / "chrome-profile"


def test_launch_error_profile_in_use_despite_chrome_path(tmp_path: Path):
    session = BossSession(user_data_dir=tmp_path)
    exc = PlaywrightError(
        "BrowserType.launch_persistent_context: Failed to create a ProcessSingleton "
        "for your profile directory. This usually means that the profile is already "
        "in use by another instance of Chromium.\n"
        "Call log:\n"
        "  - <launching> /opt/google/chrome/chrome --user-data-dir="
        f"{tmp_path} --remote-debugging-pipe about:blank\n"
        f"  - [err] Failed to create {tmp_path}/SingletonLock: File exists (17)\n"
    )
    msg = session._launch_error(exc)
    assert msg == (
        f"Chrome profile 被占用：{tmp_path}，请关闭其它使用该目录的 Chrome 后重试。"
    )
    assert _INSTALL_HINT not in msg


def test_launch_error_chrome_distribution_not_found(tmp_path: Path):
    session = BossSession(user_data_dir=tmp_path)
    exc = PlaywrightError(
        "BrowserType.launch_persistent_context: Chromium distribution 'chrome' "
        "is not found at /opt/google/chrome/chrome\n"
        'Run "npx playwright install chrome"'
    )
    assert session._launch_error(exc) == _INSTALL_HINT


def test_launch_error_spawn_failure_is_not_profile_in_use(tmp_path: Path):
    """Playwright 启动参数里的 BlockOriginHeader... 含「lock」，不能因此误报占用。"""
    session = BossSession(user_data_dir=tmp_path)
    chrome = r"C:\Users\Admin\AppData\Local\Google\Chrome\Application\chrome.exe"
    exc = PlaywrightError(
        "BrowserType.launch_persistent_context: spawn UNKNOWN\n"
        "Call log:\n"
        f"  - <launching> {chrome} "
        "--disable-features=BlockOriginHeaderModificationOnRedirect "
        f"--user-data-dir={tmp_path} --remote-debugging-pipe about:blank\n"
    )
    assert session._launch_error(exc) == f"启动 Chrome 失败：spawn UNKNOWN（{chrome}）"


def _install_chrome(prefix: Path, *, complete: bool) -> Path:
    app = prefix / "Google" / "Chrome" / "Application"
    version = app / "154.0.8037.58"
    version.mkdir(parents=True)
    (app / "chrome.exe").write_bytes(b"")
    if complete:
        (version / "chrome.dll").write_bytes(b"")
    return app / "chrome.exe"


def test_windows_skips_leftover_chrome(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("sys.platform", "win32")
    _install_chrome(tmp_path / "local", complete=False)
    system = _install_chrome(tmp_path / "program", complete=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))
    for name in ("PROGRAMFILES(X86)", "HOMEDRIVE"):
        monkeypatch.delenv(name, raising=False)
    assert BossSession.chrome_executable() == system


def test_windows_without_usable_chrome_falls_back_to_channel(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr("sys.platform", "win32")
    _install_chrome(tmp_path / "local", complete=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "HOMEDRIVE"):
        monkeypatch.delenv(name, raising=False)
    assert BossSession.chrome_executable() is None


def test_closed_browser_is_not_reused(tmp_path: Path):
    session = BossSession(user_data_dir=tmp_path)
    context, stale = _as_context(object()), _as_context(object())
    session._context = context
    session._on_closed(stale)
    assert session.is_open
    session._on_closed(context)
    assert not session.is_open


class FakeTab:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    def is_closed(self) -> bool:
        return self.closed


class FakeContext:
    def __init__(self) -> None:
        self.pages = [FakeTab("启动时的标签")]

    async def new_page(self) -> FakeTab:
        self.pages.append(FakeTab(f"新标签{len(self.pages)}"))
        return self.pages[-1]


def _as_context(context: object) -> BrowserContext:
    return cast("BrowserContext", context)


def _as_page(page: object) -> Page:
    return cast("Page", page)


def test_job_page_never_takes_chat_tab(tmp_path: Path):
    session = BossSession(user_data_dir=tmp_path)
    context = FakeContext()
    first = context.pages[0]
    session._context = _as_context(context)
    session._job_page = _as_page(first)
    assert asyncio.run(session.page()) is first

    chat = asyncio.run(context.new_page())  # 自动回复自己开的聊天页
    first.closed = True
    context.pages.remove(first)
    job = asyncio.run(session.page())
    assert job is not chat and job is context.pages[-1]
    assert asyncio.run(session.page()) is job


def test_non_windows_uses_channel(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert BossSession.chrome_executable() is None
