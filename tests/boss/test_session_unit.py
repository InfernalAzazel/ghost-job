"""BossSession 配置单元测试。"""

from pathlib import Path

from job.boss.session import BossSession


def test_default_profile_dir_under_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = BossSession.default_profile_dir()
    assert d == tmp_path / ".ghost-job" / "chrome-profile"
