"""自动回复节奏：预设、回复时段与自定义明细。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from job.boss.filters import Pace, ReplyPaceProfile

CST = timezone(timedelta(hours=8))


def test_every_preset_label_has_profile():
    codes = set(Pace.options.values()) - {ReplyPaceProfile.CUSTOM}
    assert codes == set(ReplyPaceProfile.PRESETS)
    for code in codes:
        ReplyPaceProfile.preset(code)


def test_active_hours_and_next_active():
    pace = ReplyPaceProfile()
    night = datetime(2026, 9, 26, 3, 0, tzinfo=CST)
    morning = datetime(2026, 9, 26, 10, 30, tzinfo=CST)
    late = datetime(2026, 9, 26, 22, 0, tzinfo=CST)
    assert not pace.is_active(night)
    assert pace.is_active(morning)
    assert not pace.is_active(late)
    assert pace.next_active(night) == datetime(2026, 9, 26, 9, 0, tzinfo=CST)
    assert pace.next_active(morning) == morning
    assert pace.next_active(late) == datetime(2026, 9, 27, 9, 0, tzinfo=CST)


def test_end_hour_must_be_after_start():
    with pytest.raises(ValidationError):
        ReplyPaceProfile(start_hour=22, end_hour=9)


def test_from_saved_custom_or_fallback():
    assert ReplyPaceProfile.from_saved("fast", {"delay_min": 1}) == ReplyPaceProfile.preset("fast")
    custom = ReplyPaceProfile.from_saved("custom", {"start_hour": 10, "end_hour": 18})
    assert (custom.start_hour, custom.end_hour) == (10, 18)
    assert ReplyPaceProfile.from_saved("custom", {"end_hour": 0}) == ReplyPaceProfile()


def test_describe_mentions_hours_and_delay():
    text = ReplyPaceProfile().describe()
    assert "9:00–22:00" in text and "30–180 秒" in text and "10 条歇 5–15 分钟" in text
