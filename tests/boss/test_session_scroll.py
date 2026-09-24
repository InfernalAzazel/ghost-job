from backend.boss.jobs import JobInfo
from backend.boss.session import _next_empty_streak, _seen_key, _should_stop_scroll


def test_stop_flag_ends_scroll():
    assert _should_stop_scroll(stop=True, empty_streak=0, batch_idx=0) is True


def test_two_empty_batches_end_scroll():
    assert _should_stop_scroll(stop=False, empty_streak=2, batch_idx=3) is True
    assert _should_stop_scroll(stop=False, empty_streak=1, batch_idx=3) is False


def test_max_batches_end_scroll():
    assert _should_stop_scroll(stop=False, empty_streak=0, batch_idx=20) is True
    assert _should_stop_scroll(stop=False, empty_streak=0, batch_idx=19) is False


def test_seen_key_prefers_job_id_then_link_then_title_index():
    with_id = JobInfo(title="T", link="https://example.test/a", job_id="enc1")
    assert _seen_key(with_id, 0) == "enc1"

    with_link = JobInfo(title="T", link="https://example.test/a", job_id=None)
    assert _seen_key(with_link, 3) == "https://example.test/a"

    bare = JobInfo(title="Backend", link="", job_id=None)
    assert _seen_key(bare, 7) == "Backend|7"


def test_next_empty_streak_resets_or_increments():
    assert _next_empty_streak(2, dom_grew=True, got_new_jobs=False) == 0
    assert _next_empty_streak(2, dom_grew=False, got_new_jobs=True) == 0
    assert _next_empty_streak(1, dom_grew=False, got_new_jobs=False) == 2
    assert _next_empty_streak(0, dom_grew=True, got_new_jobs=True) == 0
