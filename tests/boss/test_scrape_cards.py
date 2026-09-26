"""逐卡片处理：重复直接跳过，不合适的也带原因入库，AI 出错不入库。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from job import models as models_pkg
from job.boss.filters import KeywordFilter
from job.boss.jobs import Job, JobScraper
from job.boss.review import Verdict
from job.models import init_db, reset_engine
from job.models.job import JobRow


class FakeCards:
    def __init__(self, n: int) -> None:
        self.n = n

    async def count(self) -> int:
        return self.n

    def nth(self, i: int) -> int:
        return i


class FakePage:
    def __init__(self, n: int) -> None:
        self.cards = FakeCards(n)

    def locator(self, _selector: str) -> FakeCards:
        return self.cards


class FakeReviewer:
    """按职位名给结论：含「销售」不合适，含「出错」抛异常。"""

    async def check(self, job: Job) -> Verdict:
        if "出错" in job.title:
            raise UnexpectedModelBehavior("接口超时")
        if "销售" in job.title:
            return Verdict(match=False, reason="销售岗")
        return Verdict(match=True, reason="Agent 方向吻合")


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def test_scrape_cards_records_every_decision(tmp_db):
    jobs = [
        Job(job_id="dup", title="AI 工程师", company="老公司", hr_name="张女士"),
        Job(job_id="kw", title="AI 实习生", company="某公司"),
        Job(job_id="sale", title="AI 销售", company="某公司"),
        Job(job_id="err", title="AI 出错", company="某公司"),
        Job(job_id="ok", title="AI Agent 工程师", company="某公司"),
    ]
    JobRow.record(
        Job(job_id="old", title="AI 工程师", company="老公司", hr_name="张女士"),
        suitable=False,
        reason="外包公司",
    )
    scraper = JobScraper(session=None)  # type: ignore[arg-type]
    scraper._keywords = KeywordFilter(exclude=["实习"])
    scraper._reviewer = FakeReviewer()  # type: ignore[assignment]
    applied: list[int] = []
    logs: list[str] = []

    async def listed(_card, i: int) -> Job:
        return jobs[i]

    async def detail(_page, _card, job: Job) -> Job:
        return job

    async def apply(_page) -> str:
        applied.append(1)
        return ""

    async def pause(_span) -> None:
        pass

    async def on_log(_level: str, text: str) -> None:
        logs.append(text)

    scraper._listed_job_for = listed  # type: ignore[method-assign]
    scraper._open_detail = detail  # type: ignore[method-assign]
    scraper._apply = apply  # type: ignore[method-assign]
    scraper._pause = pause  # type: ignore[method-assign]
    scraper._on_log = on_log

    batch = asyncio.run(scraper._scrape_cards(FakePage(len(jobs)), set(), None))

    assert [j.job_id for j in batch] == ["ok"] and len(applied) == 1
    assert JobRow.get_dict("dup") is None
    assert any("看过，不合适：外包公司" in line for line in logs)
    assert JobRow.get_dict("kw")["result"] == "不合适"
    assert JobRow.get_dict("kw")["reason"] == "职位名含排除词"
    assert JobRow.get_dict("sale")["reason"] == "销售岗"
    assert JobRow.get_dict("err") is None
    ok = JobRow.get_dict("ok")
    assert (ok["result"], ok["reason"]) == ("已投递", "Agent 方向吻合")
