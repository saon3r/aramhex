"""浮窗/选人标注的界面文案：默认英文、用目录里的键；层名是 ASCII 机器码；画法和登记不变。"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from lolhex.messages import tr  # noqa: E402
from lolhex.ui import overlay  # noqa: E402
from lolhex.vision import window as win  # noqa: E402


def test_layer_names_are_ascii_codes():
    assert (overlay._Layer.name, overlay.BadgeLayer.name, overlay.ChampSelectLayer.name) == \
        ("BadgeLayer", "AugmentBadge", "ChampSelectBadge")


def test_overlay_catalog_keys_exist_in_english():
    keys = [
        "app.name", "verdict.best", "verdict.ok", "verdict.reroll", "verdict.unknown", "verdict.nodata",
        "rarity.silver", "rarity.gold", "rarity.prismatic", "augment.note.nodata", "sample.few",
        "overlay.badge.pbe", "overlay.badge.rarity_rank", "overlay.badge.rarity_win_rank",
        "overlay.badge.too_few", "overlay.button.tooltip", "overlay.item_hint.footer",
        "overlay.item_hint.row", "overlay.item_hint.title", "overlay.item_hint.source.stats",
        "overlay.item_hint.source.community", "overlay.item_hint.source.manual", "overlay.link.quit",
        "overlay.search.not_found", "overlay.search.placeholder", "overlay.version.updated",
        "champselect.cards.best", "champselect.cards.win_rank", "champselect.summary.bench",
        "champselect.summary.cards", "champselect.summary.mine", "champselect.team.me",
        "champselect.team.rank", "stats.grade", "stats.win_rank_short", "stats.winrate", "stats.pickrate",
        "augment.recommended_label", "common.confirm", "common.list_separator", "common.rescan",
        "hero.none_selected", "warning.fullscreen", "dialog.single_instance.title",
        "dialog.single_instance.body", "dialog.welcome.title", "dialog.welcome.body",
    ]
    for key in keys:
        value = tr(key, **{name: "" for name in ("rank", "total", "name", "grade", "win", "pct", "games",
                                                 "source", "version", "day", "month_name", "rarity")})
        assert value != key, key
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in value), (key, value)


def test_champ_select_summary_uses_english_display_names():
    cs = {"mine": "1", "team": [{"hero_id": "1", "name": "韦鲁斯", "win": 0.47, "grade": "C"}],
          "bench": [{"hero_id": "2", "name": "奥拉夫", "win": 0.464, "grade": "C"},
                    {"hero_id": "3", "name": "霞", "win": 0.492, "grade": "B"}]}
    text = overlay.champ_select_summary(cs)
    assert "Annie" in text and "Galio" in text and "Olaf" in text
    assert "you: Annie" in text and "↑2.2" in text
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in text)
    cards = overlay.champ_select_summary(
        {"cards": [{"hero_id": "1", "name": "韦鲁斯", "win": 0.51, "grade": "A"}]})
    assert "Starting champion:" in cards and cards.index("Annie") > cards.index("Starting champion:")


def test_badge_paints_machine_codes_through_english_labels(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(win, "_drawn", {})
    layer = overlay.BadgeLayer()
    boxes = [[100, 400, 300, 440], [400, 400, 600, 440], [700, 400, 900, 440]]
    rows = [
        {"index": 0, "verdict": "best", "score": 2.0, "win": 0.53, "rarity": "gold", "rank": 1,
         "rank_total": 10, "rank_basis": "hero_rarity_win_rate", "thin": "few", "basis": "pbe",
         "pbe_games": 100, "pbe_win": 0.53,
         "item_hint": {"source": "stats", "items": [{"item": "3135", "name": "Void Staff",
                                                     "win": 0.55, "games": 1000}]}},
        {"index": 1, "verdict": "reroll", "basis": "excluded"},
        {"index": 2, "verdict": "ok", "score": 1.0, "thin": "too_few"},
    ]
    layer.update_from({"evaluation": {"slots": rows}, "offer": {"boxes": boxes}, "settings": {}},
                      win.Rect(0, 0, 1920, 1080))
    app.processEvents()
    layer.grab()
    # 三张卡的标签 + 首件装备提示都登记为「自己画的」，仍在游戏画面范围内
    rects = win.drawn_rects()
    assert len(rects) == 4
    assert all(0 <= r.top < 1080 and r.left + r.width > 0 for r in rects)
    layer.hide()
    win.set_drawn("ControlPanel", [])
