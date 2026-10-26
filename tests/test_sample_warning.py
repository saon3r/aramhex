"""样本可信度提示：三张都不满 1000 局、单张样本偏少、分段按全体局数判断；PBE、全英雄兜底和
不完整的三选一不能误报「三张样本都偏少」。分数、名次、首选和结论都不变，只多一句仅供参考。

这里断言的是玩家真正看到的字符串（建议、卡片标签、游戏内标签），目录默认英文。
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from lolhex import recommend
from lolhex.messages import set_language, tr

IDS = ["2128", "1029", "1373"]


@pytest.fixture(autouse=True)
def _english():
    set_language("en_GB")
    yield
    set_language("en_GB")


def fill(store, games, wins) -> dict:
    """把提莫这组卡改成指定的局数和胜率；返回数据行，方便调用方再改。"""
    rows = store.dataset.table(None)[1]["17"]
    for aid, n, win in zip(IDS, games, wins):
        rows[aid] = {"games": n, "wins": round(n * win), "win_rate": win}
    return rows


def test_all_three_small_samples_say_reference_only(store):
    # 旧行为：三张都不满 1000 局时没有任何提示，照样写「Best pick」。现在要明说只是仅供参考。
    fill(store, [380, 804, 729], [0.90, 0.52, 0.51])
    ev = recommend.evaluate(store, "17", IDS)
    base = ev["base_win"]
    assert ev["best_index"] == 0  # 首选没变
    assert ev["advice"] == tr("advice.sample_all", name=ev["slots"][0]["name"])
    assert tr("advice.best", name="") not in ev["advice"]
    assert tr("advice.all_bad", name="") not in ev["advice"]
    # 分数仍是同一套平滑公式；名次和结论不变
    assert [s["verdict"] for s in ev["slots"]] == ["best", "reroll", "reroll"]
    assert [(s.get("rank"), s.get("rank_total")) for s in ev["slots"]] == [(1, 3), (2, 3), (3, 3)]
    assert [s["sample"] for s in ev["slots"]] == ["medium", "medium", "medium"]
    for row, games, win in zip(ev["slots"], [380, 804, 729], [0.90, 0.52, 0.51]):
        assert row["sample_warning"] is True and not row.get("thin")
        assert (row["games"], row["win"]) == (games, win)
        assert row["score"] == round(recommend.smoothed_delta(win, games, base, 300), 2)
        assert tr("reason.sample_reference") in row["reasons"]


def test_low_sample_rows_flagged_but_reliable_best_kept(store):
    # 同屏有样本充足的海克斯：原有的「样本太少 / 样本偏少」规则和首选都不动，只多一个仅供参考标记。
    fill(store, [260, 3000, 999], [0.90, 0.52, 0.51])
    ev = recommend.evaluate(store, "17", IDS)
    assert ev["best_index"] == 1
    assert ev["slots"][0]["thin"] == "too_few" and ev["slots"][2]["thin"] == "few"
    assert ev["advice"].startswith(tr("advice.best", name=ev["slots"][1]["name"]))
    assert tr("advice.sample_all", name="") not in ev["advice"]
    assert [bool(r.get("sample_warning")) for r in ev["slots"]] == [True, False, True]
    # 「样本太少 / 样本偏少」已有自己的提醒，不再重复一句「样本偏少、仅供参考」
    assert any(tr("reason.too_few_vs_screen", games=260) == x for x in ev["slots"][0]["reasons"])
    assert any(tr("reason.few_games", games=999) == x for x in ev["slots"][2]["reasons"])
    assert tr("reason.sample_reference") not in ev["slots"][0]["reasons"]
    assert tr("reason.sample_reference") not in ev["slots"][2]["reasons"]


def test_three_reliable_samples_keep_normal_advice(store):
    fill(store, [1000, 2000, 3000], [0.90, 0.52, 0.51])
    ev = recommend.evaluate(store, "17", IDS)
    assert ev["best_index"] == 0
    assert ev["advice"] == tr("advice.best", name=ev["slots"][0]["name"])
    assert all(not r.get("sample_warning") and not r.get("thin") for r in ev["slots"])


@pytest.mark.parametrize("games,level,warn", [(250, "medium", True), (999, "medium", True),
                                              (1000, "high", False)])
def test_sample_warning_boundary(store, games, level, warn):
    fill(store, [games, 1500, 1800], [0.60, 0.52, 0.51])
    row = recommend.evaluate(store, "17", IDS)["slots"][0]
    assert row["sample"] == level
    assert bool(row.get("sample_warning")) is warn


def test_band_reliability_uses_all_players_games(store):
    # 选了分段：显示的是分段局数（500），可信度要按全体局数（40000）判断，否则每张都会误报。
    store.set_band("high")
    row = recommend.evaluate(store, "17", ["1029", None, None])["slots"][0]
    assert row["games"] == 500 and row["games_all"] == 40000
    assert abs(row["win"] - 0.56) < 1e-9 and row["sample"] == "high"
    assert not row.get("sample_warning")
    # 全体也不足 1000 局时才提示；分段的原始局数和胜率照旧
    store.dataset.table(None)[1]["17"]["1029"]["games"] = 900
    row = recommend.evaluate(store, "17", ["1029", None, None])["slots"][0]
    assert abs(row["win"] - 0.56) < 1e-9 and row["sample_warning"] is True


def test_pbe_option_is_not_counted_as_third_small_sample(store):
    fill(store, [380, 804, 729], [0.90, 0.52, 0.51])
    store.dataset.meta["provisional_augments"] = {"3086": {"games": 5000, "win_rate": 0.56}}
    store.augments["3086"] = {"id": "3086", "name": "Demo PBE", "rarity": "gold", "new": True}
    ev = recommend.evaluate(store, "17", [IDS[0], IDS[1], "3086"])
    assert ev["slots"][2]["basis"] == "pbe" and not ev["slots"][2].get("sample_warning")
    # 测试服那一张不是正式服小样本：不能说「三张样本都偏少」
    assert tr("advice.sample_all", name="") not in ev["advice"]
    assert ev["slots"][0]["sample_warning"] and ev["slots"][1]["sample_warning"]


def test_all_champs_fallback_is_not_a_small_sample(store):
    fill(store, [1500, 1500, 1500], [0.52, 0.51, 0.50])
    store.ranks["augments"]["1001"] = {"win": 0.5, "games": 5000}
    ev = recommend.evaluate(store, "17", ["2128", "1029", "1001"])
    row = ev["slots"][2]
    assert row["basis"] == "global_win" and not row.get("sample_warning")
    assert all(not r.get("sample_warning") for r in ev["slots"])
    assert tr("advice.sample_all", name="") not in ev["advice"]


def test_incomplete_offer_never_claims_all_three(store):
    fill(store, [380, 804, 729], [0.90, 0.52, 0.51])
    ev = recommend.evaluate(store, "17", [IDS[0], IDS[1], None])
    assert ev["slots"][2]["verdict"] == "unknown"
    assert tr("advice.sample_all", name="") not in ev["advice"]
    assert ev["advice"] == tr("advice.sample_best", name=ev["slots"][0]["name"])
    assert ev["slots"][0]["sample_warning"] and ev["slots"][1]["sample_warning"]


@pytest.fixture
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_main_cards_mark_reference_only_best(store, app):
    from PySide6.QtWidgets import QLabel

    from lolhex.ui.mainwindow import MainWindow
    fill(store, [380, 804, 729], [0.90, 0.52, 0.51])
    ev = recommend.evaluate(store, "17", IDS)
    target = SimpleNamespace(offer_advice=QLabel(), offer_cards=[QLabel() for _ in range(3)])
    MainWindow._render_offer(target, ev, True)
    assert tr("advice.sample_all", name=ev["slots"][0]["name"]) in target.offer_advice.text()
    best = target.offer_cards[0].text()
    assert tr("sample.best_reference") in best and tr("verdict.best") not in best
    assert all(tr("sample.few") in card.text() for card in target.offer_cards)


def test_badge_labels_reference_only_best(store, app, monkeypatch):
    from PySide6.QtGui import QPainter

    from lolhex.ui import overlay
    from lolhex.vision import window as win

    drawn: list[str] = []

    class Painter(QPainter):
        def drawText(self, *args):  # noqa: N802 - Qt 的接口名
            drawn.append(args[-1])
            return super().drawText(*args)

    monkeypatch.setattr(overlay, "QPainter", Painter)
    fill(store, [380, 804, 729], [0.90, 0.52, 0.51])
    ev = recommend.evaluate(store, "17", IDS)
    boxes = [[440, 420, 750, 470], [810, 420, 1120, 470], [1180, 420, 1490, 470]]
    layer = overlay.BadgeLayer()
    try:
        layer.update_from({"evaluation": ev, "offer": {"boxes": boxes}, "settings": {}},
                          win.Rect(0, 0, 1920, 1080))
        app.processEvents()
        drawn.clear()  # 显示时可能已经画过一次：只看这次 grab 画的
        layer.grab()
        assert tr("sample.best_reference") in drawn
        assert sum(tr("sample.few") in text for text in drawn) == 3, drawn
        assert tr("verdict.best") not in drawn
    finally:
        layer.hide()
        layer.deleteLater()
