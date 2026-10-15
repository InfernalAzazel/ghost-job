"""Tests for search config persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from job import models as models_pkg
from job.boss.filters import Activity
from job.models import init_db, reset_engine
from job.models.search import SearchConfigRow
from job.models.setting import AutoReplySettings, LlmSettings
from job.ui.state.config import ConfigState


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
    assert config["activity"] == ""
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


def test_activity_threshold_roundtrip(tmp_db: Path):
    """活跃度阈值存单值：读回来是字符串，不是列表。"""
    assert SearchConfigRow.load()["activity"] == ""

    SearchConfigRow.save(activity_min="本周活跃")
    assert SearchConfigRow.load()["activity"] == "本周活跃"

    SearchConfigRow.save(activity_min="")
    assert SearchConfigRow.load()["activity"] == ""


def test_legacy_activity_list_reads_as_unlimited(tmp_db: Path):
    """老库里 activity_json 是多选数组，升级后不能报错，按「不限」处理。"""
    SearchConfigRow.ensure()
    with sqlite3.connect(tmp_db) as conn:
        conn.execute(
            "UPDATE search_config SET activity_json = ?",
            ('["刚刚活跃", "本月活跃"]',),
        )
        conn.commit()

    assert SearchConfigRow.load()["activity"] == ""

    SearchConfigRow.save(activity_min="3日内活跃")
    assert SearchConfigRow.load()["activity"] == "3日内活跃"


def test_broken_activity_json_reads_as_unlimited(tmp_db: Path):
    """activity_json 不是合法 JSON 时也不能抛，同样按「不限」处理。"""
    SearchConfigRow.ensure()
    with sqlite3.connect(tmp_db) as conn:
        conn.execute("UPDATE search_config SET activity_json = ?", ("不是 JSON",))
        conn.commit()

    assert SearchConfigRow.load()["activity"] == ""

    SearchConfigRow.save(activity_min="今日活跃")
    assert SearchConfigRow.load()["activity"] == "今日活跃"


def test_state_switch_turns_on_for_stored_level(tmp_db: Path):
    """库里已经有档位时，_load 要把开关打开。

    否则「开关关闭」这个默认值会让之后任意一次保存把阈值抹成「不限」。
    """
    SearchConfigRow.save(activity_min="3日内活跃")

    state = ConfigState(_reflex_internal_init=True)
    state._load(SearchConfigRow.load())
    assert state.activity_on is True
    assert state.activity_index == Activity.index("3日内活跃")

    # 改别的字段保存一次，阈值必须还在
    state.query = "Agent"
    state._save()
    assert SearchConfigRow.load()["activity"] == "3日内活跃"


def test_state_load_legacy_list_falls_back_to_unlimited(tmp_db: Path):
    """老库里的多选数组：开关关闭、滑条回到默认档，不能把数组当成档位。"""
    SearchConfigRow.ensure()
    with sqlite3.connect(tmp_db) as conn:
        conn.execute(
            "UPDATE search_config SET activity_json = ?",
            ('["刚刚活跃", "本月活跃"]',),
        )
        conn.commit()

    state = ConfigState(_reflex_internal_init=True)
    state._load(SearchConfigRow.load())
    assert state.activity_on is False
    assert state.activity_index == Activity.index(Activity.DEFAULT_LEVEL)


def test_state_saving_with_switch_off_clears_stored_level(tmp_db: Path):
    """关掉开关后保存，库里要真的回到「不限」。"""
    SearchConfigRow.save(activity_min="本周活跃")

    state = ConfigState(_reflex_internal_init=True)
    state._load(SearchConfigRow.load())
    state.activity_on = False
    state._save()

    assert SearchConfigRow.load()["activity"] == ""
