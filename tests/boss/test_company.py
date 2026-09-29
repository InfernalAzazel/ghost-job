"""查企业：公司 ID、工商信息整理、网上搜索、AI 评估与整体流程。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from job import models as models_pkg
from job.boss.company import (
    CompanyChecker,
    CompanyPage,
    CompanyReviewer,
    CompanySearch,
    CompanyVerdict,
    SearchHit,
)
from job.boss.jobs import Job
from job.models import init_db, reset_engine
from job.models.company import CompanyRow
from job.models.job import JobRow


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models_pkg, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield
    reset_engine()


@pytest.mark.parametrize(
    ("href", "brand_id"),
    [
        ("/gongsi/a829a7bf61d7263c1nx_3dS0GVM~.html", "a829a7bf61d7263c1nx_3dS0GVM~"),
        ("https://www.zhipin.com/gongsi/0d95f6f97cab53ac1Hdz0t61.html?ka=x", "0d95f6f97cab53ac1Hdz0t61"),
        ("/gongsi/job/a829a7bf61d7263c1nx_3dS0GVM~.html", ""),
        ("https://www.zhipin.com/gongsi/", ""),
    ],
)
def test_brand_id_from_link(href: str, brand_id: str):
    assert CompanyPage.brand_id_from(href) == brand_id


def test_parse_business_pairs():
    pairs = [["企业名称：", " 广州昊誉信息科技有限公司 "], ["曾用名：", "-"], ["所属行业：", ""], ["经营状态：", "在营"]]
    assert CompanyPage.parse_business(pairs) == {"企业名称": "广州昊誉信息科技有限公司", "经营状态": "在营"}


def test_search_runs_all_queries_and_dedupes():
    asked: list[str] = []

    def text(query: str) -> list[dict[str, str]]:
        asked.append(query)
        if "失信" in query:
            raise RuntimeError("限流")
        return [
            {"title": "同一篇", "href": "https://a.com/1", "body": "摘要"},
            {"title": f"{query} 独有", "href": f"https://b.com/{len(asked)}", "body": ""},
        ]

    steps, on_step = _steps()
    hits = asyncio.run(CompanySearch(text=text).search("广州昊誉信息科技有限公司", on_step))
    assert len(asked) == len(CompanySearch.QUERIES)
    assert len(steps) == len(CompanySearch.QUERIES) and "（1/3" in steps[0]
    assert all(q.startswith("广州昊誉信息科技有限公司 ") for q in asked)
    assert [h.href for h in hits].count("https://a.com/1") == 1
    assert len(hits) == 3


def test_search_all_failed_raises():
    def text(_query: str) -> list[dict[str, str]]:
        raise RuntimeError("网络不通")

    with pytest.raises(RuntimeError, match="搜索失败"):
        asyncio.run(CompanySearch(text=text).search("某公司"))


def test_reviewer_prompt_has_name_info_and_hits():
    prompt = CompanyReviewer()._prompt(
        "昊誉",
        "广州昊誉信息科技有限公司",
        {"经营状态": "在营"},
        [SearchHit(title="欠薪传闻", href="https://a.com", body="拖欠工资", query="拖欠工资")],
    )
    assert "广州昊誉信息科技有限公司" in prompt
    assert "经营状态：在营" in prompt
    assert "欠薪传闻" in prompt and "https://a.com" in prompt
    assert "未取得工商信息" in CompanyReviewer()._prompt("昊誉", "", {}, [])


class FakePage:
    def __init__(self, brand_id: str = "b1", info: dict[str, str] | None = None) -> None:
        self._brand_id, self._info = brand_id, info or {}
        self.looked_up: list[str] = []
        self.opened: list[str] = []

    async def brand_id(self, link: str) -> str:
        self.looked_up.append(link)
        return self._brand_id

    async def business(self, brand_id: str) -> dict[str, str]:
        self.opened.append(brand_id)
        return self._info


class FakeSearch:
    def __init__(self) -> None:
        self.names: list[str] = []

    async def search(self, name: str, _on_step=None) -> list[SearchHit]:
        self.names.append(name)
        return [SearchHit(title="评价", href="https://a.com", body="还行", query="员工评价")]


class FakeReviewer:
    async def review(self, *_args) -> CompanyVerdict:
        return CompanyVerdict(risk="low", summary="未见负面", points=[])


def _steps() -> tuple[list[str], object]:
    steps: list[str] = []

    async def on_step(text: str) -> None:
        steps.append(text)

    return steps, on_step


def test_checker_reads_searches_reviews_and_saves(tmp_db):
    JobRow.record(Job(job_id="j1", title="AI 工程师", company="昊誉", brand_id="b1"))
    page, search = FakePage(info={"企业名称": "广州昊誉信息科技有限公司"}), FakeSearch()
    steps, on_step = _steps()
    brand_id = asyncio.run(CompanyChecker(page, search, FakeReviewer()).check("j1", on_step))

    assert brand_id == "b1"
    assert (page.looked_up, page.opened) == ([], ["b1"])
    assert search.names == ["广州昊誉信息科技有限公司"]
    saved = CompanyRow.get_dict("b1")
    assert (saved["risk"], saved["summary"], saved["name"]) == ("low", "未见负面", "昊誉")
    assert steps


def test_checker_works_without_ai(tmp_db):
    JobRow.record(Job(job_id="j1", title="AI 工程师", company="昊誉", brand_id="b9"))
    search = FakeSearch()
    _, on_step = _steps()
    asyncio.run(CompanyChecker(FakePage(), search, None).check("j1", on_step))

    assert search.names == ["昊誉"]
    saved = CompanyRow.get_dict("b9")
    assert saved["risk"] == "unknown"
    assert "AI 服务" in saved["summary"]


def test_checker_looks_up_missing_brand_id(tmp_db):
    JobRow.record(Job(job_id="j1", title="AI 工程师", company="昊誉"))
    page = FakePage(brand_id="b2")
    _, on_step = _steps()
    assert asyncio.run(CompanyChecker(page, FakeSearch(), None).check("j1", on_step)) == "b2"

    assert (page.looked_up, page.opened) == ([JobRow.get_dict("j1")["link"]], ["b2"])
    assert JobRow.get_dict("j1")["brandId"] == "b2"


def test_checker_without_company_page_raises(tmp_db):
    JobRow.record(Job(job_id="j1", title="AI 工程师", company="昊誉"))
    _, on_step = _steps()
    with pytest.raises(RuntimeError, match="公司主页"):
        asyncio.run(CompanyChecker(FakePage(brand_id=""), FakeSearch(), None).check("j1", on_step))
