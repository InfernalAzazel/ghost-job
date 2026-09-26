"""抓取速率：预设、自定义明细参数与可中断停顿。"""

from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta

from job.boss.filters import Pace, PaceProfile
from job.boss.jobs import JobScraper


def test_every_preset_label_has_profile():
    codes = set(Pace.options.values()) - {PaceProfile.CUSTOM}
    assert codes == set(PaceProfile.PRESETS)


def test_default_profile_is_default_label():
    assert PaceProfile() == PaceProfile.preset(Pace.code(Pace.default_label))
    assert PaceProfile.preset("nope") == PaceProfile()


def test_presets_differ_in_speed():
    slow, fast = PaceProfile.preset("slow"), PaceProfile.preset("fast")
    assert slow.read[0] > PaceProfile().read[0] > fast.read[0]
    assert "每 15 条歇" in PaceProfile().describe()
    assert "歇" not in fast.describe()


def test_from_config_reads_custom_params():
    config = {"pace": "custom", "pace_params": {"read_min": 10, "read_max": 20}}
    pace = PaceProfile.from_config(config)
    assert pace.read == (10, 20)
    assert pace.scroll == PaceProfile().scroll


def test_from_config_ignores_params_for_presets_and_bad_custom():
    params = {"read_min": 10}
    assert PaceProfile.from_config({"pace": "fast", "pace_params": params}) == (
        PaceProfile.preset("fast")
    )
    bad = {"pace": "custom", "pace_params": {"read_min": -1}}
    assert PaceProfile.from_config(bad) == PaceProfile()


def test_daily_factor_stable_within_day_and_varies_across_days():
    day = date(2026, 9, 25)
    factor = PaceProfile.daily_factor("profile-a", day)
    assert 0.85 <= factor <= 1.2
    assert PaceProfile.daily_factor("profile-a", day) == factor
    week = {PaceProfile.daily_factor("profile-a", day + timedelta(d)) for d in range(7)}
    assert len(week) > 1
    assert PaceProfile.daily_factor("profile-b", day) != factor


def test_reversed_min_max_still_forms_range():
    assert PaceProfile(read_min=9, read_max=4).read == (4, 9)


def test_pause_returns_immediately_when_stopped():
    scraper = JobScraper(session=None)  # type: ignore[arg-type]

    async def run() -> float:
        start = time.monotonic()
        task = asyncio.create_task(scraper._pause((5, 5)))
        await asyncio.sleep(0.05)
        scraper.request_stop()
        await task
        return time.monotonic() - start

    assert asyncio.run(run()) < 1
