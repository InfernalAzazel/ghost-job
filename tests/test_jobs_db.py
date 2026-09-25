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
