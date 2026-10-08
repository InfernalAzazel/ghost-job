"""逐卡片处理：重复直接跳过，不合适的也带原因入库，AI 出错不入库。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from job import models as models_pkg
from job.boss.filters import KeywordFilter
from job.boss.jobs import Job, JobScraper
from job.boss.review import Verdict
from job.models import init_db, reset_engine
from job.models.job import JobRow

if TYPE_CHECKING:
    from typing import Any

    from patchright.async_api import Locator, Page

    from job.boss.review import JobReviewer
    from job.boss.session import BossSession


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


def _as_page(page: object) -> Page:
    return cast("Page", page)


def _as_boss(session: object) -> BossSession:
    return cast("BossSession", session)


def _as_reviewer(reviewer: object) -> JobReviewer:
    return cast("JobReviewer", reviewer)


def _row(uid: str) -> dict[str, Any]:
    row = JobRow.get_dict(uid)
    assert row is not None
    return row


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
    scraper = JobScraper(session=_as_boss(None))
    scraper._keywords = KeywordFilter(exclude=["实习"])
    scraper._reviewer = _as_reviewer(FakeReviewer())
    applied: list[int] = []
    logs: list[str] = []

    async def listed(card: Locator, index: int) -> Job | None:
        del card
        return jobs[index]

    async def detail(page: Page, card: Locator, job: Job) -> Job:
        del page, card
        return job

    async def apply(page: Page) -> str:
        del page
        applied.append(1)
        return ""

    async def pause(span: tuple[float, float]) -> None:
        del span

    async def on_log(_level: str, text: str) -> None:
        logs.append(text)

    scraper._listed_job_for = listed
    scraper._open_detail = detail
    scraper._apply = apply
    scraper._pause = pause
    scraper._on_log = on_log

    page = _as_page(FakePage(len(jobs)))
    batch = asyncio.run(scraper._scrape_cards(page, set(), None))

    assert [j.job_id for j in batch] == ["ok"] and len(applied) == 1
    assert JobRow.get_dict("dup") is None
    assert any("看过，不合适：外包公司" in line for line in logs)
    assert _row("kw")["result"] == "不合适"
    assert _row("kw")["reason"] == "职位名含排除词"
    assert _row("sale")["reason"] == "销售岗"
    assert JobRow.get_dict("err") is None
    ok = _row("ok")
    assert (ok["result"], ok["reason"]) == ("已投递", "Agent 方向吻合")


def test_stop_during_read_pause_does_not_send_application(tmp_db):
    scraper = JobScraper(session=_as_boss(None))
    job = Job(job_id="stopped", title="Java 实习生", company="某公司")
    applied: list[bool] = []

    async def listed(card: Locator, index: int) -> Job | None:
        del card, index
        return job

    async def detail(page: Page, card: Locator, job: Job) -> Job:
        del page, card
        return job

    async def pause(span: tuple[float, float]) -> None:
        del span
        scraper.request_stop()

    async def apply(page: Page) -> str:
        del page
        applied.append(True)
        return ""

    scraper._listed_job_for = listed
    scraper._open_detail = detail
    scraper._pause = pause
    scraper._apply = apply
    batch = asyncio.run(scraper._scrape_cards(_as_page(FakePage(1)), set(), None))
    assert batch == [] and applied == []
    assert JobRow.get_dict("stopped") is None
