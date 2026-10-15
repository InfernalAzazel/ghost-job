"""老库升级：新增的列要自动补齐，老数据不能丢。

``create_all`` 只建缺失的表，不会给已有的表加列；正式版用户手里的库是旧结构，
必须靠 ``models._add_missing_columns`` 幂等补齐，否则一启动就 ``no such column``。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from job import models as models_pkg
from job.boss.jobs import Job
from job.models import init_db, reset_engine
from job.models.job import JobRow
from job.models.search import SearchConfigRow


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "ghost-job.db"
    monkeypatch.setattr(models_pkg, "DB_PATH", db_path)
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    yield db_path
    reset_engine()


def _columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _drop_new_columns(db_path: Path) -> None:
    """把库退回到没有活跃度的旧结构（v0.6.8 及以前）。"""
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE search_config DROP COLUMN activity_json")
        conn.execute("ALTER TABLE job DROP COLUMN active_time")


def test_old_database_gets_activity_columns(tmp_db: Path):
    init_db()
    SearchConfigRow.save(query="Agent", activity=["今日活跃"])
    JobRow.record(Job(job_id="j1", title="AI 工程师", company="某公司"), applied=True)
    _drop_new_columns(tmp_db)
    assert "activity_json" not in _columns(tmp_db, "search_config")
    reset_engine()

    init_db()

    assert "activity_json" in _columns(tmp_db, "search_config")
    assert "active_time" in _columns(tmp_db, "job")


def test_migration_keeps_existing_rows_and_defaults(tmp_db: Path):
    init_db()
    SearchConfigRow.save(query="Agent", cities=["深圳"])
    JobRow.record(Job(job_id="j1", title="AI 工程师", company="某公司"), applied=True)
    _drop_new_columns(tmp_db)
    reset_engine()

    init_db()

    config = SearchConfigRow.load()
    assert config["query"] == "Agent" and config["cities"] == ["深圳"]
    assert config["activity"] == []
    row = JobRow.get_dict("j1")
    assert row is not None
    assert (row["result"], row["activeTime"]) == ("已投递", "")


def test_migration_is_idempotent_and_column_is_writable(tmp_db: Path):
    init_db()
    _drop_new_columns(tmp_db)
    reset_engine()

    init_db()
    init_db()
    reset_engine()
    init_db()

    assert SearchConfigRow.save(activity=["本周活跃", "今日活跃"])["activity"] == [
        "本周活跃",
        "今日活跃",
    ]
    JobRow.record(
        Job(
            job_id="j2",
            title="AI 平台工程师",
            company="某公司",
            active_time="刚刚活跃",
        )
    )
    row = JobRow.get_dict("j2")
    assert row is not None and row["activeTime"] == "刚刚活跃"
