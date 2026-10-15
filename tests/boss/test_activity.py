"""Boss 活跃度：措辞归一成档位，以及多选过滤的判定。

文案取值来自真实接口（``job/detail.json`` 的 ``zpData.bossInfo.activeTimeDesc``）：
同一批岗位里实测出现过下面 ``REAL_TEXTS`` 里的十几种写法，所以这里按档位比对，
而不是按字面量逐字比对。
"""

from __future__ import annotations

import pytest

from job.boss.filters import Activity, ActivityFilter

# 真实接口里实测出现过的文案
REAL_TEXTS = (
    "刚刚活跃",
    "今日活跃",
    "3日内活跃",
    "本周活跃",
    "2周内活跃",
    "本月活跃",
    "2月内活跃",
    "3月内活跃",
    "4月内活跃",
    "5月内活跃",
    "近半年活跃",
    "半年前活跃",
)


def test_labels_cover_every_group_in_order():
    assert Activity.labels() == [
        Activity.ONLINE,
        *(name for name, _ in Activity.GROUPS),
    ]


def test_wordings_lists_every_wording_of_a_level():
    """按档位筛选历史岗位时，要把该档的全部措辞都算上。"""
    assert Activity.wordings("3日内活跃") == (
        "3日内活跃",
        "三日内活跃",
        "日内活跃",
        "昨日活跃",
        "昨天活跃",
    )
    assert Activity.wordings("本周活跃") == ("本周活跃", "这周活跃")
    assert Activity.wordings("没这个档") == ("没这个档",)


@pytest.mark.parametrize("text", REAL_TEXTS)
def test_real_texts_map_to_their_own_level(text: str):
    assert Activity.of(text) == text


def test_unknown_wording_falls_back_to_nearest_level():
    """没登记过的写法按「N 日 / N 周 / N 个月」推一个最接近的档位。"""
    assert Activity.of("6日内活跃") == "本周活跃"
    assert Activity.of("10日内活跃") == "2周内活跃"
    assert Activity.of("7个月活跃") == "近半年活跃"
    assert Activity.of("1年内活跃") == "半年前活跃"


def test_unrecognized_text_is_unknown():
    assert Activity.of("") == Activity.UNKNOWN
    assert Activity.of("最近很忙") == Activity.UNKNOWN


def test_online_wording_and_online_flag():
    """文案里出现「在线」、或接口的 bossOnline 为真，都算在线。"""
    assert Activity.of("在线") == Activity.ONLINE
    assert Activity.of("3分钟前在线") == Activity.ONLINE
    assert Activity.of("", online=True) == Activity.ONLINE
    assert Activity.of("今日活跃", online=True) == "今日活跃"


def test_clean_strips_invisible_and_restores_private_digits():
    """零宽字符会被去掉，私用区数字还原成 0-9（BOSS 防抓取的老手段）。"""
    assert Activity.clean("\u200b3日\u200c内活跃\ufeff") == "3日内活跃"
    assert Activity.of("\ue034日内活跃") == "3日内活跃"


def test_empty_selection_does_not_filter():
    activity = ActivityFilter()
    assert not activity.active
    assert activity.reject_reason("半年前活跃") == ""


def test_selected_levels_are_matched():
    activity = ActivityFilter(levels=["刚刚活跃", "今日活跃"])
    assert activity.active
    assert activity.reject_reason("刚刚活跃") == ""
    assert activity.reject_reason("今日活跃") == ""
    assert activity.reject_reason("半年前活跃") == "活跃度不符（半年前活跃）"


def test_online_option_matches_online_flag_only():
    """只勾「在线」时，只有在线命中；没在线但文案是别的档位不算。"""
    activity = ActivityFilter(levels=["在线"])
    assert activity.reject_reason("", online=True) == ""
    assert activity.reject_reason("刚刚活跃", online=True) == ""
    assert activity.reject_reason("今日活跃") == "活跃度不符（今日活跃）"


def test_unknown_activity_is_allowed_through():
    """读不到活跃度就放行，不因为读不到而丢掉岗位。"""
    activity = ActivityFilter(levels=["今日活跃"])
    assert activity.reject_reason("") == ""
    assert activity.reject_reason("未知") == ""
    assert activity.reject_reason("", online=False) == ""


def test_unknown_levels_in_config_are_ignored():
    """配置里混进无效档位时按「没有有效档位」处理，即不过滤。"""
    activity = ActivityFilter(levels=["昨天下午"])
    assert not activity.active
    assert activity.reject_reason("半年前活跃") == ""


def test_from_config_reads_activity_list():
    assert ActivityFilter.from_config({"activity": ["本周活跃"]}).levels == ["本周活跃"]
    assert ActivityFilter.from_config({}).levels == []
    assert ActivityFilter.from_config({"activity": None}).levels == []
