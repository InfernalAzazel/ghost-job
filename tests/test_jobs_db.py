"""职位入库测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from job import models as models_pkg
from job.boss.jobs import Job
from job.models import init_db, reset_engine
from job.models.job import JobRow


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def test_upsert_from_inserts_then_updates(tmp_db):
    job = Job(job_id="xyz", title="AI 工程师", company="某公司", salary="20-30K")
    JobRow.upsert_from(job)
    JobRow.upsert_from(job.model_copy(update={"description": "负责落地"}))

    assert JobRow.count() == 1
    row = JobRow.get_dict("xyz")
    assert row is not None
    assert row["title"] == "AI 工程师"
    assert row["description"] == "负责落地"


def test_count_today(tmp_db):
    from datetime import UTC, datetime, timedelta

    from job.models import db_session

    JobRow.upsert_from(Job(job_id="new", title="今天", company="某公司"))
    JobRow.upsert_from(Job(job_id="old", title="前天", company="某公司"))
    with db_session() as session:
        row = session.get(JobRow, "old")
        row.scraped_at = datetime.now(UTC) - timedelta(days=2)
        session.add(row)
        session.commit()
    assert JobRow.count() == 2
    assert JobRow.count_today() == 1


def test_set_score(tmp_db):
    JobRow.upsert_from(Job(job_id="a", title="岗位a", company="某公司"))
    assert JobRow.set_score("a", 88)
    assert JobRow.get_dict("a")["matchStatus"] == "88 分"
    assert not JobRow.set_score("missing", 50)


def test_exists(tmp_db):
    job = Job(job_id="xyz", title="AI 工程师", company="某公司")
    assert not JobRow.exists(job)
    JobRow.upsert_from(job)
    assert JobRow.exists(job.model_copy(update={"title": "改名"}))


def test_analysis_filter_and_score_kept_on_rescrape(tmp_db):
    for uid, score in (("a", 90), ("b", 60), ("c", None)):
        JobRow.upsert_from(Job(job_id=uid, title=f"岗位{uid}", company="某公司"), score)
    _, analyzed, pending, high = JobRow.ANALYSIS_FILTERS

    assert JobRow.count() == 3
    assert JobRow.count(analysis=analyzed) == 2
    assert JobRow.count(analysis=pending) == 1
    assert [r["uid"] for r in JobRow.list_dicts(analysis=high)] == ["a"]
    assert JobRow.get_dict("a")["matchStatus"] == "90 分"
    assert JobRow.get_dict("a")["matchHigh"] is True
    assert JobRow.get_dict("c")["matchStatus"] == "未分析"

    JobRow.upsert_from(Job(job_id="a", title="岗位a", company="某公司"))
    assert JobRow.get_dict("a")["matchStatus"] == "90 分"
    JobRow.upsert_from(Job(job_id="a", title="岗位a", company="某公司"), 70)
    assert JobRow.get_dict("a")["matchStatus"] == "70 分"
