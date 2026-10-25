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
