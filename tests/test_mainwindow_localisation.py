"""主界面、托盘和设置下拉的英文界面（真实 Qt 控件文本）。

只核对界面本身的文案和英文英雄名；推荐建议、胜率文本仍用 Task 8 延后的生产者原文，
这里不做整页 CJK 断言，免得把延后项当成回归。
"""

import re
from types import SimpleNamespace

CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")


def _window(store, tmp_path):
    from PySide6.QtWidgets import QApplication
    from lolhex.config import Settings
    from lolhex.engine import Engine
    from lolhex.ui.mainwindow import MainWindow
    app = QApplication.instance() or QApplication([])
    eng = Engine(Settings(), home=tmp_path, store=store)
    window = MainWindow(eng, SimpleNamespace(set_visible=lambda *a: None))
    window.show()
    window.refresh()
    app.processEvents()
    return app, eng, window


def test_main_window_chrome_is_english(store, tmp_path):
    app, eng, window = _window(store, tmp_path)
    try:
        assert window.windowTitle().startswith("AramHex ARAM Mayhem Companion v")
        assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
            "Items & spells", "Augment pick", "Settings"]
        assert window.search.placeholderText() == "Search champions"
        buttons = {b.text() for b in window.findChildren(type(window.btn_dash))}
        assert {"Help", "Clear", "Rescan", "Recalibrate card positions",
                "Save settings"} <= buttons
        status = window.status.text()
        assert "Status:" in status and "Augment scan:" in status and "Data:" in status
        labels = {lab.text() for lab in window.findChildren(type(window.status))}
        assert {"Game language", "Scan rate", "Overlay position", "Augment badge"} <= labels
        chrome = [window.windowTitle(), status, *buttons,
                  *[window.tabs.tabText(i) for i in range(window.tabs.count())]]
        assert not any(CJK.search(text) for text in chrome)
    finally:
        window.hide()
        window.deleteLater()


def test_settings_dropdowns_are_english_not_producer_labels(store, tmp_path):
    app, eng, window = _window(store, tmp_path)
    try:
        assert [window.band_box.itemText(i) for i in range(window.band_box.count())] == [
            "All players", "Casual", "Mid elo", "Top 5%"]
        # 下拉标签由界面按机器码取目录，不显示 config.SPEEDS / i18n.LANGS 里的中文标签。
        assert [window.set_speed.itemText(i) for i in range(window.set_speed.count())] == [
            "Standard (recommended)", "Power saving: slower scanning",
            "Low-end PC: slowest scanning, least CPU"]
        assert [window.set_lang.itemText(i) for i in range(window.set_lang.count())] == [
            "Chinese, Simplified & Traditional (CN, TW servers)",
            "English (NA, EU and other servers)", "Japanese (JP server)"]
        assert [window.set_corner.itemText(i) for i in range(window.set_corner.count())] == [
            "Top right", "Top left"]
        assert [window.set_badge.itemText(i) for i in range(window.set_badge.count())] == [
            "Above the card (default, over the lower half of the icon)",
            "Below the card (in the gap under the description)"]
        assert window.set_lang.currentData() == "en_US"  # 识别语言仍是 en_US，与界面语言无关
        dropdowns = [window.band_box, window.set_speed, window.set_lang,
                     window.set_corner, window.set_badge]
        assert not any(CJK.search(box.itemText(i))
                       for box in dropdowns for i in range(box.count()))
    finally:
        window.hide()
        window.deleteLater()


def test_about_stays_offline_with_attribution_links(store, tmp_path):
    app, eng, window = _window(store, tmp_path)
    try:
        html = window.about_label.text()
        assert "czgreat/aramhex" in html and "MIT" in html
        assert "czgreat/aramhex-data" in html and "CC BY-NC 4.0" in html
        assert "CN" in html and "Riot Games" in html
        assert window.about_label.openExternalLinks()
        assert not CJK.search(html)
        assert not CJK.search(window.about_data.text())
    finally:
        window.hide()
        window.deleteLater()


def test_proper_names_come_from_metadata_ids(store, tmp_path):
    app, eng, window = _window(store, tmp_path)
    try:
        eng.set_hero("17")
        eng._set(hero_candidates=["17", "1"])
        window.refresh()
        app.processEvents()
        assert "Teemo" in window.hero_label.text()
        assert "the Swift Scout" in window.hero_label.text()
        assert "Recommended augments" in window.tab_hero.text()
        assert "Ethereal Weapon" in window.tab_hero.text()
        candidates = [window.cands.itemAt(i).widget().text()
                      for i in range(window.cands.count())
                      if window.cands.itemAt(i).widget()]
        assert {"Candidates:", "Teemo", "Annie"} <= set(candidates)
        assert not CJK.search(window.hero_label.text())
        assert not CJK.search(window.tab_hero.text())
        eng._on_game_end()
        window.refresh()
        app.processEvents()
        assert "No champion recognised" in window.hero_label.text()
        assert "No champion selected yet" in window.tab_hero.text()
        assert "Not picking an augment" in window.offer_advice.text()
    finally:
        window.hide()
        window.deleteLater()


def test_tray_menu_is_english(store, tmp_path):
    from lolhex.ui.mainwindow import Tray
    app, eng, window = _window(store, tmp_path)
    overlay = SimpleNamespace(set_visible=lambda *a: None, panel=SimpleNamespace(corner=""))
    tray = Tray(eng, window, overlay)
    try:
        assert [a.text() for a in tray.contextMenu().actions() if a.text()] == [
            "Open main window", "Show in-game overlay", "Rescan", "Start with Windows", "Quit"]
        assert tray.toolTip().startswith("AramHex ARAM Mayhem Companion v")
        eng.set_hero("17")
        eng._set(phase="ingame")
        tray._tooltip()
        assert "In game" in tray.toolTip()
        assert "Champion: Teemo" in tray.toolTip()
        assert not CJK.search(tray.toolTip())
    finally:
        tray.hide()
        window.hide()
        window.deleteLater()
