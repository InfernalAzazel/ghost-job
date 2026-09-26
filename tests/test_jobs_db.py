"""职位入库测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from job import models as models_pkg
from job.boss.jobs import Job
from job.models import db_session, init_db, reset_engine
from job.models.job import JobRow


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield tmp_path / "test.db"
    reset_engine()


def _job(uid: str, **kw) -> Job:
    return Job(job_id=uid, title=kw.pop("title", f"岗位{uid}"), company="某公司", **kw)


def test_record_inserts_then_updates_keeping_created_at(tmp_db):
    job = Job(job_id="xyz", title="AI 工程师", company="某公司", salary="20-30K")
    first = JobRow.record(job, reason="符合筛选条件", applied=True)
    second = JobRow.record(job.model_copy(update={"description": "负责落地"}))

    assert JobRow.count() == 1
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    row = JobRow.get_dict("xyz")
    assert row["title"] == "AI 工程师" and row["description"] == "负责落地"


def test_result_and_reason(tmp_db):
    JobRow.record(_job("a"), reason="技术栈吻合", applied=True)
    JobRow.record(_job("b"), suitable=False, reason="外包公司")
    JobRow.record(_job("c"), reason="符合筛选条件")

    a, b, c = (JobRow.get_dict(u) for u in "abc")
    assert (a["result"], a["reason"]) == ("已投递", "技术栈吻合")
    assert (b["result"], b["reason"]) == ("不合适", "外包公司")
    assert c["result"] == "已沟通过"
    assert (a["suitable"], b["suitable"]) == (True, False)
    assert JobRow.count_applied() == 1
    everything, yes, no = JobRow.SUITABLE_FILTERS
    assert JobRow.count(suitable=everything) == 3
    assert JobRow.count(suitable=yes) == 2
    assert [r["uid"] for r in JobRow.list_dicts(suitable=no)] == ["b"]


def test_count_today_only_counts_applied(tmp_db):
    JobRow.record(_job("new"), applied=True)
    JobRow.record(_job("old"), applied=True)
    JobRow.record(_job("skip"), suitable=False, reason="外包公司")
    with db_session() as session:
        row = session.get(JobRow, "old")
        row.created_at = datetime.now(UTC) - timedelta(days=2)
        session.add(row)
        session.commit()
    assert JobRow.count() == 3
    assert JobRow.count_today() == 1


def test_find_duplicate_by_id_or_title_company_hr(tmp_db):
    JobRow.record(_job("a", title="AI 工程师", hr_name="张女士"), suitable=False)

    assert JobRow.find_duplicate(_job("a", title="改名")) is not None
    same = _job("b", title="AI 工程师", hr_name="张女士")
    assert JobRow.find_duplicate(same).uid == "a"
    assert JobRow.find_duplicate(_job("c", title="AI 工程师", hr_name="李先生")) is None
    assert JobRow.find_duplicate(_job("d", title="Java", hr_name="张女士")) is None


def test_set_verdict(tmp_db):
    JobRow.record(_job("a"), score=70, applied=True)
    assert JobRow.set_verdict("a", suitable=False, reason="外包公司", score=88)
    row = JobRow.get_dict("a")
    assert (row["suitable"], row["reason"], row["matchStatus"]) == (False, "外包公司", "88 分")
    assert JobRow.set_verdict("a", suitable=True, reason="Agent 方向", score=None)
    assert JobRow.get_dict("a")["matchStatus"] == "88 分"
    assert not JobRow.set_verdict("missing", suitable=True, reason="", score=None)


def test_analysis_filter_and_score_kept_on_rescrape(tmp_db):
    for uid, score in (("a", 90), ("b", 60), ("c", None)):
        JobRow.record(_job(uid), score=score)
    _, analyzed, pending, high = JobRow.ANALYSIS_FILTERS

    assert JobRow.count(analysis=analyzed) == 2
    assert JobRow.count(analysis=pending) == 1
    assert [r["uid"] for r in JobRow.list_dicts(analysis=high)] == ["a"]
    assert JobRow.get_dict("a")["matchHigh"] is True
    assert JobRow.get_dict("c")["matchStatus"] == "未分析"

    JobRow.record(_job("a"))
    assert JobRow.get_dict("a")["matchStatus"] == "90 分"
    JobRow.record(_job("a"), score=70)
    assert JobRow.get_dict("a")["matchStatus"] == "70 分"
