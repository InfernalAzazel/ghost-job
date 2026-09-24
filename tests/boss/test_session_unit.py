from pathlib import Path

from backend.boss.session import default_user_data_dir


def test_default_user_data_dir_under_home(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    d = default_user_data_dir()
    assert d == tmp_path / ".ghostjob" / "chrome-profile"
