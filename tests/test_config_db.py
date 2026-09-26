"""Tests for search config persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from job import models as models_pkg
from job.models import init_db, reset_engine
from job.models.search import SearchConfigRow
from job.models.setting import AutoReplySettings, LlmSettings


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(models_pkg, "DB_PATH", db_path)
    monkeypatch.setattr(models_pkg, "DATA_DIR", tmp_path)
    reset_engine()
    init_db()
    yield db_path
    reset_engine()


def test_seed_default_config(tmp_db: Path):
    config = SearchConfigRow.load()
    assert config["query"]
    assert config["cities"] == ["广州"]
    assert config["pace"] == "normal" and config["pace_params"] == {}


def test_init_db_keeps_single_row(tmp_db: Path):
    init_db()
    SearchConfigRow.ensure()
    with sqlite3.connect(tmp_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM search_config").fetchone()[0] == 1


def test_save_filters(tmp_db: Path):
    updated = SearchConfigRow.save(
        query="Agent 工程师",
        cities=["深圳", "广州"],
        experience=["1-3年"],
        scale=["20-99人", "100-499人"],
    )
    assert updated["query"] == "Agent 工程师"
    assert updated["cities"] == ["深圳", "广州"]
    assert updated["experience"] == ["1-3年"]
    assert SearchConfigRow.load()["scale"] == ["20-99人", "100-499人"]


def test_save_keeps_unspecified_fields(tmp_db: Path):
    SearchConfigRow.save(query="Agent", industry=["互联网"])
    SearchConfigRow.save(pace="slow")
    config = SearchConfigRow.load()
    assert config["query"] == "Agent" and config["industry"] == ["互联网"]
    assert config["pace"] == "slow"


def test_custom_pace_params_persist(tmp_db: Path):
    params = {"read_min": 10.0, "read_max": 20.0}
    SearchConfigRow.save(pace="custom", pace_params=params)
    assert SearchConfigRow.load()["pace_params"] == params


def test_ai_review_and_resume_persist(tmp_db: Path):
    config = SearchConfigRow.load()
    assert config["resume_text"] == "" and config["resume_match"] is False
    assert config["score_filter"] is False and config["min_score"] == 60
    SearchConfigRow.save(
        ai_review=True,
        ai_requirement="只投 Agent",
        resume_match=True,
        score_filter=True,
        min_score=175,
        resume_path="/tmp/cv.pdf",
        resume_text="Agent 工程师",
    )
    config = SearchConfigRow.load()
    assert config["ai_review"] is True and config["ai_requirement"] == "只投 Agent"
    assert config["resume_match"] is True and config["score_filter"] is True
    assert config["min_score"] == 100
    assert config["resume_path"] == "/tmp/cv.pdf"
    assert config["resume_text"] == "Agent 工程师"


def test_save_rejects_unknown_list_field(tmp_db: Path):
    with pytest.raises(TypeError):
        SearchConfigRow.save(bogus=["x"])


def test_llm_settings_save_and_load(tmp_db: Path):
    assert LlmSettings.load() == LlmSettings()
    LlmSettings(api_key="sk-1", model="deepseek-v4-pro").save()
    latest = LlmSettings(
        base_url="https://api.moonshot.cn/v1",
        api_key="sk-2",
        model="deepseek-v4-pro",
        models=["deepseek-v4-flash", "deepseek-v4-pro"],
    )
    latest.save()
    assert LlmSettings.load() == latest


def test_auto_reply_settings_default_and_roundtrip(tmp_db: Path):
    default = AutoReplySettings.load()
    assert not default.enabled
    assert default.prompt == AutoReplySettings.DEFAULT_PROMPT

    saved = AutoReplySettings(
        enabled=True,
        prompt="  语气轻松一点  ",
        pace="custom",
        pace_params={"start_hour": 10, "end_hour": 18},
    )
    saved.save()
    loaded = AutoReplySettings.load()
    assert loaded == saved and loaded.prompt == "语气轻松一点"
    assert (loaded.pace_profile.start_hour, loaded.pace_profile.end_hour) == (10, 18)
    assert LlmSettings.load() == LlmSettings()
