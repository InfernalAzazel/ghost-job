from backend.boss.session import _should_stop_scroll


def test_stop_flag_ends_scroll():
    assert _should_stop_scroll(stop=True, empty_streak=0, batch_idx=0) is True


def test_two_empty_batches_end_scroll():
    assert _should_stop_scroll(stop=False, empty_streak=2, batch_idx=3) is True
    assert _should_stop_scroll(stop=False, empty_streak=1, batch_idx=3) is False


def test_max_batches_end_scroll():
    assert _should_stop_scroll(stop=False, empty_streak=0, batch_idx=20) is True
    assert _should_stop_scroll(stop=False, empty_streak=0, batch_idx=19) is False
