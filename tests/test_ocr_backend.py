"""OCR 后端的选择：默认 Windows 引擎，可强制 RapidOCR，Windows 用不了时自动退回。

RapidOCR 在实机对局通过之前一直留着，就是靠这里的选择逻辑兜底。
"""

import pytest


@pytest.fixture(autouse=True)
def _clean_engines():
    from lolhex.vision import ocr

    ocr.reset_engines()
    yield
    ocr.reset_engines()


def _has_windows_engine() -> bool:
    try:
        from lolhex.vision.ocr_win import WinOCR

        WinOCR("en_US")
        return True
    except Exception:
        return False


def test_default_backend_is_the_windows_engine():
    from lolhex.vision import ocr

    inst = ocr.get_ocr("en_US")
    if _has_windows_engine():
        assert type(inst).__name__ == "WinOCR", "有 Windows 引擎时默认就该用它"
    else:
        pytest.skip("这台机器没有 Windows OCR 识别器")


def test_env_can_force_rapidocr(monkeypatch):
    from lolhex.vision import ocr

    monkeypatch.setenv("ARAMHEX_OCR", "rapid")
    assert type(ocr.get_ocr("en_US")).__name__ == "OCR"


def test_windows_unavailable_falls_back_to_rapidocr(monkeypatch):
    from lolhex.vision import ocr, ocr_win

    def unavailable(_lang):
        raise ocr_win.OcrUnavailable("no recognizer")

    monkeypatch.setattr(ocr_win, "WinOCR", unavailable)
    assert type(ocr.get_ocr("en_US")).__name__ == "OCR"


def test_same_language_reuses_one_engine():
    from lolhex.vision import ocr

    assert ocr.get_ocr("en_US") is ocr.get_ocr("en_US")
    assert ocr.get_ocr("en_US") is not ocr.get_ocr("zh_CN")

def test_missing_language_pack_never_uses_a_wrong_script_engine():
    """中文/日文客户端但没装对应识别包时，必须退回 RapidOCR，不能拿英文引擎凑数。

    英文引擎认不了中文卡面，结果是一张卡都认不出——看起来就像「OCR 坏了」。
    """
    from lolhex.vision import ocr

    inst = ocr.get_ocr("zh_CN")
    if type(inst).__name__ == "WinOCR":
        assert inst.language.lower().startswith("zh"), f"中文客户端拿到 {inst.language}"
    else:
        assert type(inst).__name__ == "OCR"


def test_winocr_refuses_a_mismatched_recognizer():
    from lolhex.vision import ocr_win

    installed = [tag.lower() for tag in ocr_win.available_languages()]
    if any(tag.startswith("zh") for tag in installed):
        pytest.skip("这台机器装了中文识别包，构造不出「语言包缺失」")
    with pytest.raises(ocr_win.OcrUnavailable):
        ocr_win.WinOCR("zh_CN")


def test_language_switch_reaches_the_detector(store, tmp_path):
    """设置里换语言后，检测器下次重建必须用新语言，不能留着构造时的旧语言。"""
    from types import SimpleNamespace

    from lolhex.config import Settings
    from lolhex.engine import Engine
    from lolhex.vision.ocr import get_ocr

    engine = Engine(Settings(), home=tmp_path, store=store)
    engine._detector = SimpleNamespace(game_lang="en_US", _ocr=get_ocr("en_US"),
                                       set_matcher=lambda _m: None, _last_fp=object())
    engine.set_game_lang("zh_CN")
    assert engine.settings.game_lang == "zh_CN"
    assert engine._detector.game_lang == "zh_CN", "检测器还在用旧语言"
    assert engine._detector._ocr is None, "换语言后要重建识别器"
