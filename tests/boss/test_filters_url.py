"""BOSS 搜索 URL 拼装测试。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from job.boss.filters import City, Defaults, Experience, Scale, SearchUrl


def test_search_url_minimal():
    url = SearchUrl.build({"query": "Agent 工程师", "city_code": City.code("惠州")})
    parsed = urlparse(url)
    assert parsed.path.endswith("/web/geek/jobs")
    qs = parse_qs(parsed.query)
    assert qs["query"] == ["Agent 工程师"]
    assert qs["city"] == [City.code("惠州")]
    assert "jobType" not in qs


def test_search_url_full_filters():
    url = SearchUrl.build(
        {
            "query": "ai应用开发",
            "city_code": Defaults.CITY_CODE,
            "job_type": "1901",
            "salary": "406",
            "experience": ["1-3年", "3-5年"],
            "education": ["本科"],
            "funding": ["A轮"],
            "scale": ["20-99人", "100-499人"],
        }
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["query"] == ["ai应用开发"]
    assert qs["city"] == [Defaults.CITY_CODE]
    assert qs["jobType"] == ["1901"]
    assert qs["salary"] == ["406"]
    assert qs["experience"] == [
        f"{Experience.code('1-3年')},{Experience.code('3-5年')}"
    ]
    assert "degree" in qs
    assert "stage" in qs
    assert qs["scale"] == [f"{Scale.code('20-99人')},{Scale.code('100-499人')}"]


def test_search_url_ignores_blank_multiselect_labels():
    url = SearchUrl.build(
        {
            "query": "x",
            "city_code": "101280100",
            "experience": ["不限", "未知标签"],
        }
    )
    qs = parse_qs(urlparse(url).query)
    assert "experience" not in qs
