"""Task 7 wave 1：`ui/buildview.py` 的英文渲染（只测渲染器本身，不动数据来源）。
数据都是本地假数据：没有网络、没有截图、不启动界面。
"""

from __future__ import annotations

import pytest

from lolhex.messages import DEFAULT_UI_LANG, set_language
from lolhex.ui import buildview


@pytest.fixture(autouse=True)
def _english():
    """其他用例可能切过界面语言；这里固定回默认英文再跑。"""
    set_language(DEFAULT_UI_LANG)
    yield
    set_language(DEFAULT_UI_LANG)


class _Icons:
    """只对已知的图标给路径：同一条用例里既能测图标，也能测文字回退。"""

    def __init__(self, known=()):
        self.known = set(known)

    def local(self, kind, ident, icon):
        return f"/icons/{kind}/{ident}.png" if (kind, ident) in self.known else None


def _panel(**extra):
    d = {"summoners": [{"spells": [{"id": "4", "name": "Flash"}, {"id": "32", "name": "Mark"}],
                       "win": 0.534, "pick": 0.9}],
         "summoner_source": "sampled", "summoner_source_date": "2026-10-17",
         "item_stats": [{"item": {"id": "3115", "name": "Nashor's Tooth"}, "win": 0.54}]}
    d.update(extra)
    return d


def test_headers_and_stats_render_in_english():
    html = "<br>".join(buildview.lines(_panel(), None, True))
    assert "Summoner spells: sampled · 2026-10-17" in html
    assert "<b>Summoner spells</b>" in html
    assert "<b>Common items</b>" in html
    assert "Win rate 53.4% · Pick rate 90.0%" in html
    assert "Flash" in html and "Mark" in html


def test_hiding_win_rate_leaves_pick_rate_only():
    off = "".join(buildview.lines(_panel(), None, False))
    assert "Win rate" not in off
    assert "Pick rate 90.0%" in off
    assert "54.0%" not in off  # 关掉胜率后装备那一行也不带百分比


def test_unknown_date_and_missing_item_percent_are_graceful():
    d = _panel(summoner_source_date=None,
               item_stats=[{"item": {"id": "3115", "name": "Nashor's Tooth"}}])
    html = "".join(buildview.lines(d, None, True))
    assert "Summoner spells: sampled · date unknown" in html
    assert "Win rate 53.4% · Pick rate 90.0%" in html
    assert "—" in html  # 没有胜率数据时占位，不抛错


def test_compact_rows_keep_alignment_and_shape():
    d = _panel(summoners=[{"spells": [{"id": "4", "name": "Flash"}], "win": 0.534, "pick": 0.9},
                          {"spells": [{"id": "6", "name": "Ghost"}], "win": 0.51, "pick": 0.1}])
    rows = buildview.lines(d, None, True, compact=True)
    assert isinstance(rows, list) and all(isinstance(x, str) for x in rows)
    assert len(rows) == 4  # 来源一行 + 每组技能一行 + 装备一行
    assert rows[0].startswith("<span style='color:")
    assert "<b>Summoner spells</b>" in rows[1]
    assert "color:transparent" in rows[2] and "<b>Summoner spells</b>" in rows[2]
    assert "Win rate 51.0% · Pick rate 10.0%" in rows[2]


def test_untrusted_values_are_escaped_before_the_catalog_template():
    d = _panel(summoner_source="<b>x & y</b>",
               item_stats=[{"item": {"id": "1", "name": "A & B <C>"}, "win": 0.5}])
    html = "".join(buildview.lines(d, None, True))
    assert "&lt;b&gt;x &amp; y&lt;/b&gt;" in html
    assert "A &amp; B &lt;C&gt;" in html
    assert "<b>x" not in html


def test_missing_metadata_falls_back_to_ids_without_raising():
    d = {"summoners": [{"spells": [{"id": "4"}, {"id": "32", "name": "Mark"}]}],
         "summoner_source": "sampled",
         "item_stats": [{"item": {"id": "3115"}}]}
    html = "".join(buildview.lines(d, None, True))
    assert "3115" in html and "Mark" in html
    assert buildview.item(None, {"id": "3115", "name": None}, 24) == "3115"
    assert buildview.item(None, {"id": "3115", "name": "Nashor's Tooth"}, 24) == "Nashor's Tooth"


def test_item_rows_are_capped_and_icons_win_over_text():
    items = [{"item": {"id": str(1000 + i), "name": f"Item {i}"}, "win": 0.5} for i in range(8)]
    d = _panel(item_stats=items)
    assert buildview.lines(d, None, True)[-1].count("/icons/item/") == 0
    assert "Item 5" in buildview.lines(d, None, True)[-1]
    assert "Item 6" not in buildview.lines(d, None, True)[-1]
    compact = buildview.lines(d, None, True, compact=True)[-1]
    assert "Item 3" in compact and "Item 4" not in compact
    icons = _Icons({("item", str(1000 + i)) for i in range(8)})
    assert "/icons/item/1000.png" in buildview.lines(d, icons, True)[-1]
