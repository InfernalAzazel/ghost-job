"""多城市轮换：一个城市看完自动换下一个，遇到停止 / 上限 / 登录就结束。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from job import models as models_pkg
from job.boss.jobs import Job, JobScraper
from job.models import init_db, reset_engine


class FakePage:
    def on(self, *_args) -> None:
        pass

    def remove_listener(self, *_args) -> None:
        pass


class FakeSession:
    user_data_dir = Path("profile")

    async def page(self) -> FakePage:
        return FakePage()


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


def _run(states: dict[str, str]) -> tuple[list[str], list[Job], str, list[str]]:
    """按城市返回预设状态，记录访问过的 URL 与日志。"""
    scraper = JobScraper(FakeSession())  # type: ignore[arg-type]
    visited: list[str] = []
    logs: list[str] = []

    async def fake_city(_page, url, jobs, _on_job) -> str:
        visited.append(url)
        jobs.append(Job(job_id=url, title="AI 工程师", company="某公司"))
        return states[url]

    async def on_log(_level: str, text: str) -> None:
        logs.append(text)

    scraper._search_city = fake_city  # type: ignore[method-assign]
    targets = [(city, city) for city in states]
    jobs, state = asyncio.run(scraper.search(targets, on_log=on_log))
    return visited, jobs, state, logs


def test_switches_to_next_city_when_list_ends(tmp_db):
    visited, jobs, state, logs = _run({"广州": "done", "深圳": "done", "惠州": "done"})
    assert visited == ["广州", "深圳", "惠州"]
    assert len(jobs) == 3 and state == "done"
    assert "广州的岗位已看完，切换到深圳" in logs


@pytest.mark.parametrize("stop", ["stopped", "limit", "need_login"])
def test_stops_rotation_on_non_done_state(tmp_db, stop: str):
    visited, jobs, state, _ = _run({"广州": "done", "深圳": stop, "惠州": "done"})
    assert visited == ["广州", "深圳"]
    assert len(jobs) == 2 and state == stop
