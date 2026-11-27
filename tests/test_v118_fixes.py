"""v1.1.8 维护更新测试：64 位句柄安全、原子写盘、数据切换恢复、命运之武器流派、浮窗背景、搜英雄焦点与自启同步。"""

from __future__ import annotations

import ctypes
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")


# ---------- 1. Win32 64-bit HWND & ClientToScreen ----------


def test_configure_user32_sets_hwnd_signatures_only_for_windll():
    from ctypes import wintypes
    from lolhex.vision import window as win

    fake_non_dll = SimpleNamespace(FindWindowW=lambda *_a: 0)
    win._configure_user32(fake_non_dll)  # 非 WinDLL 替身不动
    assert not hasattr(fake_non_dll.FindWindowW, "restype")

    if win.IS_WINDOWS:
        u = ctypes.windll.user32
        assert u.FindWindowW.restype is wintypes.HWND
        assert u.GetForegroundWindow.restype is wintypes.HWND
        assert u.IsWindow.argtypes == (wintypes.HWND,)
        assert u.ClientToScreen.restype is wintypes.BOOL


def test_client_rect_returns_none_when_client_to_screen_fails(monkeypatch):
    from lolhex.vision import window as win

    def get_client_rect(_h, ptr):
        rc = ptr._obj
        rc.left, rc.top, rc.right, rc.bottom = 0, 0, 1920, 1080
        return 1

    user32 = SimpleNamespace(
        IsIconic=lambda _h: 0,
        IsWindowVisible=lambda _h: 1,
        GetClientRect=get_client_rect,
        ClientToScreen=lambda _h, _p: 0,
    )
    monkeypatch.setattr(win, "IS_WINDOWS", True)
    monkeypatch.setattr(win, "ctypes", SimpleNamespace(windll=SimpleNamespace(user32=user32), byref=ctypes.byref))
    assert win.client_rect(1234) is None


def test_is_foreground_handles_none_hwnd(monkeypatch):
    from lolhex.vision import window as win

    user32 = SimpleNamespace(GetForegroundWindow=lambda: None, IsIconic=lambda _h: 0)
    monkeypatch.setattr(win, "IS_WINDOWS", True)
    monkeypatch.setattr(win, "ctypes", SimpleNamespace(windll=SimpleNamespace(user32=user32)))
    assert win.is_foreground(1234) is False


# ---------- 2. Atomic settings write & overlay_bg ----------


def test_atomic_write_text_retries_windows_permission_error_and_cleans_tmp(tmp_path, monkeypatch):
    from lolhex import config

    target = tmp_path / "config.json"
    calls = []
    real_replace = os.replace

    def flaky_replace(src, dst):
        calls.append((src, dst))
        if len(calls) < 3:
            raise PermissionError("locked")
        return real_replace(src, dst)

    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.setattr(config.os, "replace", flaky_replace)
    monkeypatch.setattr(config.time, "sleep", lambda _s: None)
    config.atomic_write_text(target, '{"ok": true}')
    assert target.read_text(encoding="utf-8") == '{"ok": true}'
    assert len(calls) == 3
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_cleans_tmp_on_permanent_failure(tmp_path, monkeypatch):
    from lolhex import config

    target = tmp_path / "config.json"
    monkeypatch.setattr(config.os, "replace", lambda *_a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        config.atomic_write_text(target, "hello")
    assert not target.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_settings_overlay_bg_validates_and_persists(tmp_path):
    from lolhex.config import Settings

    path = tmp_path / "config.json"
    path.write_text('{"overlay_bg": "dark"}', encoding="utf-8")
    assert Settings.load(path).overlay_bg == "dark"

    path.write_text('{"overlay_bg": "neon"}', encoding="utf-8")
    assert Settings.load(path).overlay_bg == "standard"


# ---------- 3. Safe dataset swap & _cached_folders recovery ----------


def test_download_restores_old_dataset_when_final_rename_fails(tmp_path, monkeypatch):
    import hashlib
    import json
    from lolhex.data import http, public

    files = {
        "meta.json": b'{"patch":"16.23","snapshot_at":"2026-11-26T09:00:00+08:00"}\n',
        "heroes.json": b'{"1":{"games":100,"wins":50,"win_rate":0.5}}\n',
        "hero_augments.json": b'{"1":{"1001":{"games":100,"wins":50,"win_rate":0.5}}}\n',
    }
    manifest = {
        "schema_version": 1,
        "patch": "16.23",
        "snapshot_at": "2026-11-26T09:00:00+08:00",
        "path": "patches/16.23/normal",
        "files": {n: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)} for n, b in files.items()},
    }
    dest = tmp_path / "public"
    dest.mkdir()
    (dest / "sentinel.txt").write_text("keep-me", encoding="utf-8")

    def fake_fetch(url, **_kw):
        if url.endswith(".pack.xz"):
            raise RuntimeError("no pack")
        name = url.rsplit("/", 1)[-1]
        return files[name]

    monkeypatch.setattr(http, "fetch", fake_fetch)
    real_rename = Path.rename

    def fail_on_new_rename(self, target):
        if self.name == "public.new" and Path(target) == dest:
            raise PermissionError("busy")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_on_new_rename)
    with pytest.raises(PermissionError, match="busy"):
        public.download("https://aramhex.com/u/data", manifest, dest)
    assert (dest / "sentinel.txt").read_text(encoding="utf-8") == "keep-me"
    assert not dest.with_name("public.new").exists()


def test_reload_dataset_recovers_from_old_backup_folder(tmp_path, store):
    import shutil
    from lolhex.data.public import PublicStore

    data_root = tmp_path / "data"
    old_dir = data_root / "public.old"
    shutil.copytree(store.dataset.folder, old_dir)
    ps = PublicStore(data_root, bundled=tmp_path / "empty-bundled")
    assert ps.dataset is not None
    assert ps.dataset.folder == old_dir


# ---------- 4. Weapon of Destiny (3081) build styles ----------


def test_destiny_style_v1_maps_styles_to_english_and_renders_cleanly(store):
    from lolhex.data.public import Dataset
    from lolhex.ui.overlay import BadgeLayer
    from test_public import _add_file

    store.static["items"] = {
        "2510": {"name": "Dusk and Dawn", "icon": ""},
        "2517": {"name": "Unending Hunger", "icon": ""},
        "3084": {"name": "Heartsteel", "icon": ""},
        "3107": {"name": "Redemption", "icon": ""},
        "4645": {"name": "Shadowflame", "icon": ""},
    }
    cfg = {
        "10": {"3081": {
            "source": "stats",
            "recommendation_style": "destiny_style_v1",
            "show_winrate": True,
            "items": [
                {"item": "2510", "name": "黄昏与黎明", "style": "AP", "games": 1891, "wins": 1119},
                {"item": "2517", "name": "无穷饥渴", "style": "AD", "games": 1239, "wins": 723},
                {"item": "3084", "name": "心之钢", "style": "坦克", "games": 500, "wins": 260},
                {"item": "3107", "name": "救赎", "style": "辅助", "games": 400, "wins": 210},
                {"item": "4645", "name": "影焰", "style": "未知", "games": 400, "wins": 210},
            ],
        }},
        "1": {"3081": {
            "source": "stats",
            "recommendation_style": "destiny_style_v1",
            "show_winrate": True,
            "items": [
                {"item": "4645", "name": "影焰", "style": "不拆", "games": 2314, "wins": 1191},
            ],
        }},
    }
    _add_file(store.dataset.folder, "hero_augment_items.json", cfg)
    store.dataset = Dataset(store.dataset.folder, store.dataset.origin)

    split = store.augment_items("10", "3081")
    assert split is not None and len(split["items"]) == 3
    assert [r["style"] for r in split["items"]] == ["ap", "ad", "tank"]
    labels = [BadgeLayer._item_hint_label(r) for r in split["items"]]
    assert labels == ["AP · Dusk and Dawn", "AD · Unending Hunger", "Tank · Heartsteel"]
    assert not any(CJK.search(t) for t in labels)

    unsplit = store.augment_items("1", "3081")
    assert unsplit is not None and "style" not in unsplit["items"][0]
    assert BadgeLayer._item_hint_label(unsplit["items"][0]) == "Shadowflame"


# ---------- 5. Detail panel background toggle ----------


def test_panel_background_button_cycles_and_persists(tmp_path, monkeypatch):
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from lolhex.config import Settings
    from lolhex.ui import overlay

    monkeypatch.setattr(overlay.win, "add_companion", lambda _h: None)
    monkeypatch.setattr(overlay.win, "set_no_activate", lambda *_a: True)
    monkeypatch.setattr(overlay.win, "give_focus", lambda _h: None)
    monkeypatch.setattr(overlay.win, "foreground_window", lambda: 0)

    cfg_path = tmp_path / "config.json"
    settings = Settings()
    saved_calls = []
    real_save = settings.save
    settings.save = lambda p=None: (saved_calls.append(settings.overlay_bg), real_save(p or cfg_path))[1]

    eng = SimpleNamespace(settings=settings, store=SimpleNamespace(heroes={}), icons=None)
    ov = overlay.Overlay.__new__(overlay.Overlay)
    ov.engine = eng
    ov.panel = overlay.ControlPanel(eng)
    ov._bg = None
    ov.panel.bg_picked.connect(ov._bg_picked)
    ov.apply_bg()
    try:
        assert ov.panel.bg_level == "standard"
        assert ov.panel.bg_btn.text() == "Background: Transparent"
        assert "#101318ee" in ov.panel.body.styleSheet()

        ov.panel.bg_btn.click()
        assert ov.panel.bg_level == "dark"
        assert ov.panel.bg_btn.text() == "Background: Semi-transparent"
        assert "#b3101318" in ov.panel.body.styleSheet()

        ov.panel.bg_btn.click()
        assert ov.panel.bg_level == "solid"
        assert ov.panel.bg_btn.text() == "Background: Opaque"
        assert "#ff101318" in ov.panel.body.styleSheet()

        ov.panel.bg_btn.click()
        assert ov.panel.bg_level == "standard"
        assert saved_calls == ["dark", "solid", "standard"]
        assert Settings.load(cfg_path).overlay_bg == "standard"
    finally:
        ov.panel.close()
        app.processEvents()


# ---------- 6. Champion search typing focus in Overlay._tick ----------


def test_typing_in_search_keeps_overlay_visible_only_when_opened_from_league(monkeypatch):
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from lolhex.ui import overlay
    from lolhex.vision import window as win

    state = {"fg": 111, "game": 111}
    user32 = SimpleNamespace(GetForegroundWindow=lambda: state["fg"], IsIconic=lambda _h: 0)
    monkeypatch.setattr(win, "IS_WINDOWS", True)
    monkeypatch.setattr(win, "ctypes", SimpleNamespace(windll=SimpleNamespace(user32=user32)))
    monkeypatch.setattr(win, "_companions", set())  # 补全弹窗不在 companion 里也能保住浮窗
    monkeypatch.setattr(win, "find_game_window", lambda: state["game"])
    monkeypatch.setattr(win, "client_rect", lambda _h: win.Rect(0, 0, 1600, 900))
    monkeypatch.setattr(win, "window_rect", lambda _h: None)
    monkeypatch.setattr(win, "set_no_activate", lambda *_a: True)
    monkeypatch.setattr(win, "give_focus", lambda h: state.__setitem__("fg", h))

    snap = {"phase": "ingame", "offer": {"boxes": []},
            "evaluation": {"slots": [], "advice": "x", "best_index": None}}
    eng = SimpleNamespace(
        snapshot=lambda: snap,
        settings=SimpleNamespace(overlay=True, overlay_corner="top-right", overlay_bg="standard"),
        store=SimpleNamespace(heroes={}),
        icons=None,
    )
    ov = overlay.Overlay.__new__(overlay.Overlay)
    ov.engine = eng
    ov.visible = True
    ov.badges = overlay.BadgeLayer()
    ov.champ = SimpleNamespace(update_from=lambda *a: None)
    ov.autoshot = SimpleNamespace(tick=lambda *a: None)
    ov.panel = overlay.ControlPanel(eng)
    ov.panel.show()
    try:
        # 从游戏里点进搜索框：前台切到详情窗口（不在 _companions 里），浮窗和标签都保留
        ov.panel._start_typing()
        assert ov.panel.typing_source() == 111
        ov._tick()
        assert ov.panel.isVisible() and ov.badges.isVisible()

        # 从别的程序点进搜索框：游戏不是来源，不把浮窗画到别的程序上
        ov.panel.give_back_focus()
        state["fg"] = 999
        ov.panel._start_typing()
        assert ov.panel.typing_source() == 999
        ov._tick()
        assert not ov.panel.isVisible() and not ov.badges.isVisible()
    finally:
        ov.badges.close()
        ov.panel.close()
        app.processEvents()


# ---------- 7. Autostart sync between Tray & MainWindow ----------


def test_autostart_syncs_between_tray_and_settings(store, tmp_path, monkeypatch):
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from lolhex.config import Settings
    from lolhex.engine import Engine
    from lolhex.ui import autostart, mainwindow

    reg = {"on": False, "fail": False}
    monkeypatch.setattr(autostart, "is_enabled", lambda: reg["on"])

    def fake_set(on):
        if reg["fail"]:
            raise OSError("access denied")
        reg["on"] = bool(on)

    monkeypatch.setattr(autostart, "set_enabled", fake_set)
    monkeypatch.setattr(mainwindow.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(mainwindow.QMessageBox, "warning", lambda *a, **k: None)

    eng = Engine(Settings(), home=tmp_path, store=store)
    ov = SimpleNamespace(set_visible=lambda *a: None, panel=SimpleNamespace(corner="top-right"))
    win = mainwindow.MainWindow(eng, ov)
    tray = mainwindow.Tray(eng, win, ov)
    win.tray = tray
    toasts = []
    monkeypatch.setattr(tray, "showMessage", lambda *a: toasts.append(a))
    try:
        assert not win.set_auto.isChecked() and not tray.act_auto.isChecked()
        tray.act_auto.setChecked(True)
        assert reg["on"] is True and win.set_auto.isChecked()

        # 托盘写入失败：回滚勾选并提示
        reg["fail"] = True
        tray.act_auto.setChecked(False)
        assert tray.act_auto.isChecked() is True and win.set_auto.isChecked() is True
        assert toasts

        # 设置页保存：同步回托盘
        reg["fail"] = False
        win.set_auto.setChecked(False)
        win._save_settings()
        assert reg["on"] is False and not tray.act_auto.isChecked()
    finally:
        tray.hide()
        win.hide()
        win.deleteLater()
        app.processEvents()
