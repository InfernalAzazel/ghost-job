"""Tests for search plan persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from job import models as models_pkg
from job.models import init_db, reset_engine
from job.models.plan import SearchPlanRow
from job.models.setting import LlmSettings


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(models_pkg, "DB_PATH", db_path)
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield db_path
    reset_engine()


def test_seed_default_plan(tmp_db: Path):
    plans = SearchPlanRow.list_dicts()
    assert len(plans) == 1
    assert plans[0]["is_default"] is True
    assert plans[0]["is_active"] is True
    assert plans[0]["query"]
    active = SearchPlanRow.get_active_dict()
    assert active["id"] == plans[0]["id"]


def test_create_and_switch_active(tmp_db: Path):
    first = SearchPlanRow.get_active_dict()
    second = SearchPlanRow.create("惠州方案")
    assert second["is_active"] is True
    assert second["name"] == "惠州方案"
    refreshed_first = SearchPlanRow.get_dict(first["id"])
    assert refreshed_first is not None
    assert refreshed_first["is_active"] is False
    SearchPlanRow.set_active(first["id"])
    assert SearchPlanRow.get_active_dict()["id"] == first["id"]


def test_set_default_unique(tmp_db: Path):
    a = SearchPlanRow.get_active_dict()
    b = SearchPlanRow.create("B")
    SearchPlanRow.set_default(b["id"])
    plans = {p["id"]: p for p in SearchPlanRow.list_dicts()}
    assert plans[b["id"]]["is_default"] is True
    assert plans[a["id"]]["is_default"] is False


def test_delete_last_plan_rejected(tmp_db: Path):
    only = SearchPlanRow.get_active_dict()
    with pytest.raises(ValueError, match="至少保留"):
        SearchPlanRow.delete(only["id"])


def test_delete_active_switches(tmp_db: Path):
    a = SearchPlanRow.get_active_dict()
    b = SearchPlanRow.create("B")
    assert b["is_active"] is True
    active_after = SearchPlanRow.delete(b["id"])
    assert active_after["id"] == a["id"]
    assert len(SearchPlanRow.list_dicts()) == 1


def test_update_filters_and_duplicate(tmp_db: Path):
    plan = SearchPlanRow.get_active_dict()
    updated = SearchPlanRow.update_filters(
        plan["id"],
        query="Agent 工程师",
        city_code="101280300",
        experience=["1-3年"],
        scale=["20-99人", "100-499人"],
    )
    assert updated["query"] == "Agent 工程师"
    assert updated["experience"] == ["1-3年"]
    assert updated["scale"] == ["20-99人", "100-499人"]
    copy = SearchPlanRow.duplicate(plan["id"])
    assert copy["query"] == "Agent 工程师"
    assert copy["id"] != plan["id"]
    assert "副本" in copy["name"]


def test_pace_defaults_to_normal_and_persists(tmp_db: Path):
    active = SearchPlanRow.get_active_dict()
    assert active["pace"] == "normal"
    updated = SearchPlanRow.update_filters(active["id"], pace="slow")
    assert updated["pace"] == "slow"
    assert SearchPlanRow.create("复制速率")["pace"] == "slow"


def test_custom_pace_params_persist_and_copy(tmp_db: Path):
    active = SearchPlanRow.get_active_dict()
    assert active["pace_params"] == {}
    params = {"read_min": 10.0, "read_max": 20.0}
    SearchPlanRow.update_filters(active["id"], pace="custom", pace_params=params)
    assert SearchPlanRow.get_active_dict()["pace_params"] == params
    assert SearchPlanRow.create("复制自定义")["pace_params"] == params


def test_old_db_gets_pace_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import sqlite3

    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE search_plan (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL,"
            " is_default BOOLEAN NOT NULL, is_active BOOLEAN NOT NULL,"
            " query VARCHAR NOT NULL, city_code VARCHAR NOT NULL,"
            " job_type VARCHAR NOT NULL, salary VARCHAR NOT NULL,"
            " experience_json VARCHAR NOT NULL, education_json VARCHAR NOT NULL,"
            " funding_json VARCHAR NOT NULL, scale_json VARCHAR NOT NULL,"
            " updated_at DATETIME NOT NULL)"
        )
        conn.execute(
            "INSERT INTO search_plan VALUES ('p1','老方案',1,1,'ai','101280100',"
            "'1901','','[]','[]','[]','[]','2026-01-01 00:00:00')"
        )
    monkeypatch.setattr(models_pkg, "DB_PATH", db_path)
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    try:
        init_db()
        assert SearchPlanRow.get_active_dict()["pace"] == "normal"
    finally:
        reset_engine()


def test_industry_and_keywords_persist_and_copy(tmp_db: Path):
    active = SearchPlanRow.get_active_dict()
    assert active["industry"] == [] and active["exclude_companies"] == []
    SearchPlanRow.update_filters(
        active["id"], industry=["互联网"], include_keywords=["agent"]
    )
    refreshed = SearchPlanRow.get_active_dict()
    assert refreshed["industry"] == ["互联网"]
    assert refreshed["include_keywords"] == ["agent"]
    copied = SearchPlanRow.create("复制行业")
    assert copied["industry"] == ["互联网"]


def test_ai_review_persist_and_copy(tmp_db: Path):
    active = SearchPlanRow.get_active_dict()
    assert active["ai_review"] is False and active["ai_requirement"] == ""
    SearchPlanRow.update_filters(
        active["id"], ai_review=True, ai_requirement="只投 Agent"
    )
    refreshed = SearchPlanRow.get_active_dict()
    assert refreshed["ai_review"] is True
    assert refreshed["ai_requirement"] == "只投 Agent"
    copied = SearchPlanRow.create("复制复核")
    assert copied["ai_review"] is True and copied["ai_requirement"] == "只投 Agent"


def test_llm_settings_save_and_load(tmp_db: Path):
    assert LlmSettings.load() == LlmSettings()
    LlmSettings(api_key="sk-1", model="deepseek-v4-pro").save()
    latest = LlmSettings(
        api_key="sk-2",
        model="deepseek-v4-pro",
        models=["deepseek-v4-flash", "deepseek-v4-pro"],
    )
    latest.save()
    assert LlmSettings.load() == latest


def test_update_filters_rejects_unknown_list_field(tmp_db: Path):
    active = SearchPlanRow.get_active_dict()
    with pytest.raises(TypeError):
        SearchPlanRow.update_filters(active["id"], bogus=["x"])


def test_resume_persist_and_copy(tmp_db: Path):
    active = SearchPlanRow.get_active_dict()
    assert active["resume_text"] == "" and active["resume_match"] is False
    assert active["score_filter"] is False and active["min_score"] == 60
    SearchPlanRow.update_filters(
        active["id"],
        resume_match=True,
        score_filter=True,
        min_score=75,
        resume_path="/tmp/cv.pdf",
        resume_text="张三 Agent 工程师",
    )
    refreshed = SearchPlanRow.get_active_dict()
    assert refreshed["resume_path"] == "/tmp/cv.pdf"
    copied = SearchPlanRow.create("复制简历")
    assert copied["resume_text"] == "张三 Agent 工程师"
    assert copied["resume_match"] is True
    assert copied["score_filter"] is True and copied["min_score"] == 75
