"""游戏内标签只在游戏窗口前台时显示：切到别的程序就隐藏，点自己的浮窗（companion）不算离开，
回到游戏立刻恢复。用的都是现有的 `window.is_foreground`，不新增快捷键/钩子，也不改编排几何。
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


SNAP = {"phase": "ingame", "offer": {"boxes": []},
        "evaluation": {"slots": [], "advice": "", "best_index": None}}


def fake_overlay(monkeypatch, snap=None):
    """只建 _tick 需要的那几块，前台判定走真实的 window.is_foreground（ctypes 用假 user32）。"""
    from lolhex.ui import overlay as ov_module
    from lolhex.vision import window as win

    state = {"fg": 111, "game": 111}
    user32 = SimpleNamespace(GetForegroundWindow=lambda: state["fg"], IsIconic=lambda _h: 0)
    monkeypatch.setattr(win, "IS_WINDOWS", True)
    monkeypatch.setattr(win, "ctypes", SimpleNamespace(windll=SimpleNamespace(user32=user32)))
    monkeypatch.setattr(win, "_companions", set())
    rect = win.Rect(0, 0, 1600, 900)
    monkeypatch.setattr(win, "find_game_window", lambda: state["game"])
    monkeypatch.setattr(win, "client_rect", lambda _h: rect)
    monkeypatch.setattr(win, "window_rect", lambda _h: None)  # 无真窗口：标签按 Qt 坐标摆
    snap = SNAP if snap is None else snap
    ov = ov_module.Overlay.__new__(ov_module.Overlay)
    ov.engine = SimpleNamespace(snapshot=lambda: snap)
    ov.badges = ov_module.BadgeLayer()
    ov.champ = SimpleNamespace(update_from=lambda *a: None)
    ov.autoshot = SimpleNamespace(tick=lambda *a: None)
    ov.panel = SimpleNamespace(update_from=lambda *a: None, auto_hide=lambda *a: None,
                               isVisible=lambda: True, place=lambda *a, **k: None,
                               target_hwnd=0)
    return SimpleNamespace(ov=ov, state=state, win=win, snap=snap)


def test_game_badges_hide_in_background_and_return_without_rescan(app, monkeypatch):
    o = fake_overlay(monkeypatch, {"phase": "ingame", "offer": {"boxes": []},
                                   "evaluation": {"slots": [], "advice": "x", "best_index": None}})
    try:
        o.ov._tick()
        assert o.ov.badges.isVisible()
        o.state["fg"] = 333  # Alt-Tab 到浏览器/聊天
        o.ov._tick()
        assert not o.ov.badges.isVisible()
        assert o.snap["offer"] is not None and o.snap["evaluation"] is not None  # 状态没丢
        o.state["fg"] = o.state["game"]
        o.ov._tick()
        assert o.ov.badges.isVisible()  # 切回来马上显示，不用重新识别
    finally:
        o.ov.badges.close()
        app.processEvents()


def test_own_panel_focus_keeps_game_badges(app, monkeypatch):
    # 点右上角浮窗时前台是浮窗自己：游戏还在画面上，标签不能跟着闪掉（和选人标注一致）
    o = fake_overlay(monkeypatch)
    try:
        o.win.add_companion(222)
        o.state["fg"] = 222
        o.ov._tick()
        assert o.ov.badges.isVisible()
        o.state["fg"] = 333  # 别的程序：照常隐藏
        o.ov._tick()
        assert not o.ov.badges.isVisible()
    finally:
        o.ov.badges.close()
        app.processEvents()


def test_no_offer_hides_badges_even_in_foreground(app, monkeypatch):
    o = fake_overlay(monkeypatch, {"phase": "ingame", "offer": None, "evaluation": None})
    try:
        o.ov._tick()
        assert not o.ov.badges.isVisible()
        o.state["fg"] = 333
        o.ov._tick()
        assert not o.ov.badges.isVisible()
    finally:
        o.ov.badges.close()
        app.processEvents()
