"""复核：缺 OCR 语言包时只警告一次、状态里说清楚、界面用英文提示，装好后恢复。"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace

import numpy as np
import pytest

from lolhex.config import Settings
from lolhex.engine import Engine
from lolhex.messages import set_language, tr
from lolhex.vision import capture, ocr
from lolhex.vision.ocr_win import OcrUnavailable
from lolhex.vision.window import Rect

WINDOW = Rect(0, 0, 1920, 1080)


def _engine(tmp_path, store, lang: str = "zh_CN") -> Engine:
    settings = Settings()
    settings.game_lang = lang
    return Engine(settings, home=tmp_path, store=store)


def _missing_recognizer(monkeypatch, lang: str = "zh_CN") -> None:
    def boom(*args, **kwargs):
        raise OcrUnavailable(f"no Windows OCR recognizer for {lang!r}; installed: ['en-GB']")

    monkeypatch.setattr(ocr, "get_ocr", boom)


def _client_in_foreground(monkeypatch) -> None:
    import lolhex.engine as module

    monkeypatch.setattr(module.win, "find_game_window", lambda: None)
    monkeypatch.setattr(module.win, "find_client_window", lambda: 42)
    monkeypatch.setattr(module.win, "is_foreground", lambda hwnd: True)
    monkeypatch.setattr(module.win, "client_rect", lambda hwnd: WINDOW)
    monkeypatch.setattr(capture, "grab", lambda *a, **k: np.zeros((80, 120, 3), np.uint8))
    monkeypatch.setattr(capture, "is_blank", lambda img: False)


def _warnings(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and "Windows OCR unavailable" in r.getMessage()]


def _traces(caplog) -> list[logging.LogRecord]:
    """带堆栈的日志记录：缺识别包是预期情况，不该在日志里长得像崩溃。"""
    return [r for r in caplog.records if r.exc_info]


def test_observer_repeats_do_not_log_or_announce_every_scan(tmp_path, store, monkeypatch, caplog):
    eng = _engine(tmp_path, store)
    _client_in_foreground(monkeypatch)
    _missing_recognizer(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="lolhex.engine"):
        for _ in range(3):
            assert eng._observe_tick() == 3.0

    assert len(_warnings(caplog)) == 1
    assert _traces(caplog) == []
    assert eng.state["vision"]["error"] == {"code": "ocr_unavailable", "language": "zh_CN"}
    assert eng.state["vision"]["blank"] is False       # 缺识别器不是全屏，不能报全屏警告


def test_warm_up_without_recognizer_warns_once_without_traceback(tmp_path, store, monkeypatch, caplog):
    """启动预热碰上缺识别包：状态要记、警告只要一条，不是一屏堆栈。"""
    eng = _engine(tmp_path, store)
    monkeypatch.setattr(eng, "_load_icons", lambda **kw: None)
    _missing_recognizer(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="lolhex.engine"):
        eng._warm_up()

    assert len(_warnings(caplog)) == 1
    assert _traces(caplog) == []
    assert eng.state["vision"]["error"] == {"code": "ocr_unavailable", "language": "zh_CN"}


class _StopAfter:
    """跑够指定轮数就让 vision 线程退出的事件替身。"""

    def __init__(self, iterations: int):
        self.left = iterations

    def is_set(self) -> bool:
        if self.left <= 0:
            return True
        self.left -= 1
        return False

    def wait(self, timeout: float) -> bool:
        return False


class _FailingDetector:
    game_lang = "zh_CN"
    _ocr = None
    cost = {"strip": 0, "strip_s": 0.0, "strip_cpu": 0.0, "strip_ocr": 0,
            "full": 0, "full_s": 0.0, "full_cpu": 0.0}

    def set_matcher(self, matcher) -> None:
        pass

    def ensure_calibration(self, w: int, h: int) -> None:
        pass

    def calibrated_for(self, w: int, h: int) -> bool:
        return True

    def confirmed_for(self, w: int, h: int) -> bool:
        return True

    def strip_rect(self, rect):
        return rect

    def check_strip(self, strip, rect):
        raise OcrUnavailable("no Windows OCR recognizer for 'zh_CN'; installed: ['en-GB']")


def test_vision_repeats_warn_once_and_never_claim_fullscreen(tmp_path, store, monkeypatch, caplog):
    import lolhex.engine as module

    eng = _engine(tmp_path, store)
    eng._set(phase="ingame")
    _missing_recognizer(monkeypatch)
    monkeypatch.setattr(module.win, "lower_thread_priority", lambda: None)
    monkeypatch.setattr(module.win, "find_game_window", lambda: 7)
    monkeypatch.setattr(module.win, "client_rect", lambda hwnd: WINDOW)
    monkeypatch.setattr(module.win, "is_foreground", lambda hwnd: True)
    monkeypatch.setattr(capture, "grab", lambda *a, **k: np.zeros((1080, 1920, 3), np.uint8))
    monkeypatch.setattr(capture, "is_blank", lambda img: False)
    eng._detector = _FailingDetector()
    eng._stop = _StopAfter(2)

    with caplog.at_level(logging.WARNING, logger="lolhex.engine"):
        eng._vision_loop()

    assert len(_warnings(caplog)) == 1
    assert _traces(caplog) == []
    assert eng.state["vision"]["error"] == {"code": "ocr_unavailable", "language": "zh_CN"}
    assert eng.state["vision"]["blank"] is False


def test_language_switch_and_a_successful_recognizer_clear_the_warning(tmp_path, store, monkeypatch):
    eng = _engine(tmp_path, store)
    eng._note_ocr_unavailable(OcrUnavailable("missing"))
    assert eng.state["vision"]["error"]["code"] == "ocr_unavailable"

    eng.set_game_lang("en_US")
    assert eng.state["vision"]["error"] is None

    eng.state["vision"]["error"] = {"code": "ocr_unavailable", "language": "en_US"}
    engine = object()
    monkeypatch.setattr(ocr, "get_ocr", lambda *a, **k: engine)
    assert eng._ocr() is engine
    assert eng.state["vision"]["error"] is None


def test_player_visible_warning_is_english_and_not_the_fullscreen_hint(store, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from lolhex.ui.mainwindow import MainWindow

    set_language("en_GB")
    app = QApplication.instance() or QApplication([])
    eng = _engine(tmp_path, store)
    window = MainWindow(eng, SimpleNamespace(set_visible=lambda *a: None))
    try:
        window.show()
        eng.state["vision"]["error"] = {"code": "ocr_unavailable", "language": "zh_CN"}
        window.refresh()
        app.processEvents()
        status = window.status.text()
        assert "OCR" in status
        # 说清 Windows 里要装什么、在哪装，以及那块语言在 Windows 里叫什么
        assert "Optical character recognition" in status
        assert "Time &amp; language" in status or "Time & language" in status
        assert "Chinese (Simplified, China)" in status and "zh-CN" in status
        assert "zh_CN" not in status          # 内部代码 Windows 界面里没有
        assert "full-screen" not in status.lower()
        assert not any("\u3400" <= ch <= "\u9fff" for ch in status)
    finally:
        window.hide()
        window.deleteLater()


def test_overlay_notifies_once_per_condition_and_again_after_recovery():
    set_language("en_GB")
    from lolhex.ui import overlay

    said = []
    snap = {"vision": {"error": {"code": "ocr_unavailable", "language": "zh_CN"}, "blank": False}}
    ov = SimpleNamespace(visible=True, notify=said.append,
                         engine=SimpleNamespace(snapshot=lambda: snap))

    def tick():
        try:
            overlay.Overlay._tick(ov)
        except AttributeError:
            pass  # 这次只验证提示：后面的窗口/面板部分用替身对象跑不到

    for _ in range(3):
        tick()
    assert len(said) == 1
    assert "OCR" in said[0] and "Optical character recognition" in said[0]
    assert "Chinese (Simplified, China)" in said[0] and "zh-CN" in said[0]
    assert "zh_CN" not in said[0]
    assert "full-screen" not in said[0].lower()

    snap["vision"]["error"] = None
    tick()
    snap["vision"]["error"] = {"code": "ocr_unavailable", "language": "zh_CN"}
    tick()
    assert len(said) == 2


@pytest.mark.parametrize("code,name,tag", [
    ("zh_CN", "Chinese (Simplified, China)", "zh-CN"),
    ("ja_JP", "Japanese", "ja-JP"),
])
def test_ocr_pack_name_uses_the_windows_language_name(code, name, tag):
    """内部代码 → Windows 设置里能看到的语言名和标签（三种语言一张表，不再各写一份）。"""
    from lolhex import i18n

    set_language("en_GB")
    text = i18n.ocr_pack_name(code)
    assert name in text and tag in text


def test_ocr_pack_name_for_english_lists_both_recognizers():
    """英文客户端 Windows 认 en-US 和 en-GB 两种识别包，不能说成只要美式。"""
    from lolhex import i18n

    set_language("en_GB")
    for code in ("en_US", "en_GB"):
        text = i18n.ocr_pack_name(code)
        assert "English (United States)" in text and "en-US" in text
        assert "English (United Kingdom)" in text and "en-GB" in text


def test_ocr_pack_name_never_invents_a_language():
    """目录里没有的代码原样给出，不能因为 normalize 回退就声称是中文。"""
    from lolhex import i18n

    set_language("en_GB")
    assert i18n.ocr_pack_name("fr_FR") == "fr_FR"
    assert i18n.ocr_pack_name(None) == "?"


def test_warning_text_exists_in_both_catalogs():
    from lolhex import messages

    set_language("en_GB")
    catalog = messages._load()
    english = catalog["en_GB"]["warning.ocr_unavailable"]
    chinese = catalog["zh_CN"]["warning.ocr_unavailable"]
    assert "{language}" in english and "{language}" in chinese
    assert not any("\u3400" <= ch <= "\u9fff" for ch in english)
    # 要说出 Windows 里真正的功能名和位置，不只是「设置里装一下」
    assert "Optical character recognition" in english
    assert "Time & language" in english
    assert "光学字符识别" in chinese and "语言" in chinese
    assert tr("warning.ocr_unavailable", language="zh_CN") == english.format(language="zh_CN")


def test_chinese_catalog_warning_uses_chinese_names():
    from lolhex import i18n
    from lolhex import messages

    set_language("zh_CN")
    text = i18n.ocr_unavailable_notice("zh_CN")
    assert "光学字符识别" in text
    assert "中文（简体，中国）" in text and "zh-CN" in text
    messages.set_language(messages.DEFAULT_UI_LANG)
