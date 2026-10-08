"""多城市轮换：一个城市看完自动换下一个，遇到停止 / 上限 / 登录就结束。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from job import models as models_pkg
from job.boss.jobs import Job, JobScraper
from job.models import init_db, reset_engine

if TYPE_CHECKING:
    from patchright.async_api import Page

    from job.boss.session import BossSession


class FakePage:
    def on(self, *_args) -> None:
        pass

    def remove_listener(self, *_args) -> None:
        pass


class FakeSession:
    user_data_dir = Path("profile")

    async def page(self) -> FakePage:
        return FakePage()


def _as_boss(session: object) -> BossSession:
    return cast("BossSession", session)


def _as_page(page: object) -> Page:
    return cast("Page", page)


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
    scraper = JobScraper(_as_boss(FakeSession()))
    visited: list[str] = []
    logs: list[str] = []

    async def fake_city(page: object, url: str, jobs: list[Job], on_job: object) -> str:
        del page, on_job
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


@pytest.mark.parametrize("stop", ["stopped", "limit", "need_login", "load_failed"])
def test_stops_rotation_on_non_done_state(tmp_db, stop: str):
    visited, jobs, state, _ = _run({"广州": "done", "深圳": stop, "惠州": "done"})
    assert visited == ["广州", "深圳"]
    assert len(jobs) == 2 and state == stop


class SearchPage:
    """无需真实浏览器，区分页面导航、登录元素与列表等待。"""

    def __init__(self, *, url: str = "https://www.zhipin.com/web/geek/job"):
        self.url = url
        self.goto = AsyncMock()
        self.wait_for_selector = AsyncMock()
        self.login_visible = [False]
        self.checked_selectors: list[str] = []
        self.remove_listener = Mock()

    def on(self, *_args) -> None:
        pass

    def locator(self, selector: str):
        self.checked_selectors.append(selector)
        login = Mock()
        login.count = AsyncMock(return_value=len(self.login_visible))
        login.nth.side_effect = lambda index: Mock(
            is_visible=AsyncMock(return_value=self.login_visible[index])
        )
        return login


def _scraper(page: SearchPage) -> tuple[JobScraper, AsyncMock]:
    """返回投递器和替换 ``_scrape_cards`` 的 mock（直接断言 mock，类型检查才认得）。"""
    session = FakeSession()
    session.page = AsyncMock(return_value=page)
    scraper = JobScraper(_as_boss(session))
    cards = AsyncMock(return_value=[])
    scraper._scrape_cards = cards  # type: ignore[method-assign]
    scraper._load_more = AsyncMock()  # type: ignore[method-assign]
    scraper._pause = AsyncMock()  # type: ignore[method-assign]
    return scraper, cards


@pytest.mark.parametrize(
    "url",
    [
        "https://www.zhipin.com/web/user/login",
        "https://www.zhipin.com/web/user/?ka=header-login",
        "https://www.zhipin.com/web/user/",
        "https://www.zhipin.com/web/common/security-check.html",
        "https://www.zhipin.com/passport/qr",
        "https://www.zhipin.com/verify/index",
        "https://www.zhipin.com/captcha/",
    ],
)
def test_login_or_verification_page_stops_city_rotation(tmp_db, url: str):
    page = SearchPage(url=url)
    scraper, cards = _scraper(page)
    jobs, state = asyncio.run(scraper.search([("广州", "first"), ("深圳", "second")]))
    assert jobs == [] and state == "need_login"
    page.goto.assert_awaited_once()
    page.wait_for_selector.assert_not_awaited()
    cards.assert_not_awaited()
    page.remove_listener.assert_called_once()


def test_visible_login_form_stops_even_when_job_cards_exist(tmp_db):
    page = SearchPage()
    page.login_visible = [False, True]
    scraper, cards = _scraper(page)
    _, state = asyncio.run(scraper.search([("广州", "first"), ("深圳", "second")]))
    assert state == "need_login"
    page.wait_for_selector.assert_not_awaited()
    cards.assert_not_awaited()


@pytest.mark.parametrize("login", [True, False])
def test_card_timeout_distinguishes_login_from_load_failure(tmp_db, login: bool):
    page = SearchPage()

    async def timeout(*_args, **_kwargs):
        page.login_visible = [login]
        raise PlaywrightTimeoutError("job cards did not load")

    page.wait_for_selector.side_effect = timeout
    scraper, cards = _scraper(page)
    _, state = asyncio.run(scraper.search([("广州", "first"), ("深圳", "second")]))
    assert state == ("need_login" if login else "load_failed")
    page.goto.assert_awaited_once()
    cards.assert_not_awaited()


def test_stop_during_timeout_takes_priority_over_login(tmp_db):
    page = SearchPage()
    scraper, _ = _scraper(page)

    async def timeout(*_args, **_kwargs):
        scraper.request_stop()
        page.url = "https://www.zhipin.com/web/user/login"
        raise PlaywrightTimeoutError("job cards did not load")

    page.wait_for_selector.side_effect = timeout
    _, state = asyncio.run(scraper.search([("广州", "first"), ("深圳", "second")]))
    assert state == "stopped"
    page.goto.assert_awaited_once()


@pytest.mark.parametrize("action", ["goto", "wait_for_selector"])
def test_stop_interrupts_navigation_and_card_wait(tmp_db, action: str):
    async def run():
        page = SearchPage()
        scraper, cards = _scraper(page)
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def block(*_args, **_kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        getattr(page, action).side_effect = block
        task = asyncio.create_task(
            scraper.search([("广州", "first"), ("深圳", "second")])
        )
        await asyncio.wait_for(entered.wait(), 2)
        scraper.request_stop()
        jobs, state = await asyncio.wait_for(task, 2)
        assert jobs == [] and state == "stopped"
        assert cancelled.is_set()
        page.goto.assert_awaited_once()
        cards.assert_not_awaited()
        page.remove_listener.assert_called_once()

    asyncio.run(run())


def test_stop_between_cities_prevents_next_city_navigation(tmp_db):
    scraper = JobScraper(_as_boss(FakeSession()))
    visited: list[str] = []

    async def fake_city(page: object, url: str, jobs: list[Job], on_job: object) -> str:
        del page, jobs, on_job
        visited.append(url)
        scraper.request_stop()
        return "done"

    scraper._search_city = fake_city
    _, state = asyncio.run(scraper.search([("广州", "first"), ("深圳", "second")]))
    assert state == "stopped" and visited == ["first"]


def test_stop_before_city_search_does_not_navigate():
    page = SearchPage()
    scraper, _ = _scraper(page)
    scraper.request_stop()
    state = asyncio.run(scraper._search_city(_as_page(page), "first", [], None))
    assert state == "stopped"
    page.goto.assert_not_awaited()


def test_ready_list_still_completes_normally(tmp_db):
    page = SearchPage()
    scraper, cards = _scraper(page)
    _, state = asyncio.run(scraper.search([("广州", "first"), ("深圳", "second")]))
    assert state == "done"
    assert page.goto.await_count == 2
    assert cards.await_count == 4


def test_login_appearing_after_card_wait_is_not_processed(tmp_db):
    page = SearchPage()

    async def show_login(*_args, **_kwargs):
        page.login_visible = [True]

    page.wait_for_selector.side_effect = show_login
    scraper, cards = _scraper(page)
    _, state = asyncio.run(scraper.search([("广州", "first"), ("深圳", "second")]))
    assert state == "need_login"
    page.goto.assert_awaited_once()
    cards.assert_not_awaited()


def test_external_cancellation_cleans_up_pending_browser_wait(tmp_db):
    async def run():
        page = SearchPage()
        scraper, _ = _scraper(page)
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def block(*_args, **_kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        page.wait_for_selector.side_effect = block
        task = asyncio.create_task(scraper.search([("广州", "first")]))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        page.remove_listener.assert_called_once()

    asyncio.run(run())
