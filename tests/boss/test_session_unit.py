"""BossSession 配置单元测试。"""

from pathlib import Path

from patchright.async_api import Error as PlaywrightError

from job.boss.session import BossSession

_INSTALL_HINT = "无法启动本机 Chrome（channel=chrome），请确认已安装 Google Chrome。"


def test_default_profile_dir_under_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
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
        f"Chrome profile 被占用：{tmp_path}，"
        "请关闭其它使用该目录的 Chrome 后重试。"
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
