"""三选一标签位置示意图的界面文案：标签和预览文字都走文案表，机器码和画法不变。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from lolhex.messages import DEFAULT_UI_LANG, set_language, tr  # noqa: E402
from lolhex.ui import badgepos  # noqa: E402


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(autouse=True)
def _english_afterwards():
    set_language(DEFAULT_UI_LANG)
    yield
    set_language(DEFAULT_UI_LANG)


def test_positions_keep_machine_codes_and_use_catalog_labels():
    positions = list(badgepos.POSITIONS)
    assert [code for code, _ in positions] == ["top", "bottom"]
    assert [label for _, label in positions] == [tr("settings.badge.top"),
                                                 tr("settings.badge.bottom")]
    assert len(badgepos.POSITIONS) == 2


def test_positions_labels_are_english_by_default():
    labels = [label for _, label in badgepos.POSITIONS]
    assert labels[0].startswith("Above the card")
    assert labels[1].startswith("Below the card")
    assert all(ord(ch) < 0x2E80 for label in labels for ch in label)


def test_positions_labels_follow_language_switch():
    set_language("zh_CN")
    assert [label for _, label in badgepos.POSITIONS] == ["卡片上方（默认，压在图标下半）",
                                                          "卡片下方（描述下面的空白处）"]
    set_language(DEFAULT_UI_LANG)
    assert [code for code, _ in badgepos.POSITIONS] == ["top", "bottom"]


def test_preview_paints_catalog_text_and_keeps_geometry(monkeypatch):
    _app()
    seen: list[str] = []
    real = badgepos.tr

    def spy(key, **values):
        seen.append(key)
        return real(key, **values)

    monkeypatch.setattr(badgepos, "tr", spy)
    w = badgepos.BadgePosPreview("bottom")
    assert w.size().width() == 112 and w.size().height() == 150
    assert not w.grab().isNull()
    assert "badgepos.preview" in seen
    w.set_position("top")
    assert w.position == "top"
    assert not w.grab().isNull()
