"""OCR 后端：只有 Windows.Media.Ocr 一个实现，按界面语言缓存，缺语言包时明确报错。

RapidOCR 已经删除；现在最危险的失败方式是「拿错语言的识别器」——中文客户端用英文引擎会
一张卡都认不出，看起来就像 OCR 坏了。这里钉住它必须报错而不是硬撑。
"""

import pytest


@pytest.fixture(autouse=True)
def _clean_engines():
    from lolhex.vision import ocr

    ocr.reset_engines()
    yield
    ocr.reset_engines()


def _installed() -> list[str]:
    from lolhex.vision.ocr_win import available_languages

    return [tag.lower() for tag in available_languages()]


def test_default_backend_is_the_system_engine():
    from lolhex.vision import ocr

    if not any(tag.startswith("en") for tag in _installed()):
        pytest.skip("这台机器没有英文识别包")
    inst = ocr.get_ocr("en_US")
    assert type(inst).__name__ == "WinOCR"
    assert inst.language.lower().startswith("en")


def test_same_language_reuses_one_engine():
    from lolhex.vision import ocr

    if not any(tag.startswith("en") for tag in _installed()):
        pytest.skip("这台机器没有英文识别包")
    assert ocr.get_ocr("en_US") is ocr.get_ocr("en_US")
    ocr.reset_engines()
    assert ocr.get_ocr("en_US") is not None       # reset 之后重新建一个


def test_missing_language_pack_raises_instead_of_reading_nothing():
    """没有中文识别包时：宁可报错（这一局没有标签），也不能拿英文引擎硬认中文。"""
    from lolhex.vision import ocr
    from lolhex.vision.ocr_win import OcrUnavailable

    if any(tag.startswith("zh") for tag in _installed()):
        pytest.skip("这台机器装了中文识别包")
    with pytest.raises(OcrUnavailable):
        ocr.get_ocr("zh_CN")


def test_failed_engine_is_not_cached():
    """装语言包之前失败过，装好之后（reset 或换语言）要能重新成功。"""
    from lolhex.vision import ocr, ocr_win

    calls = {"n": 0}
    real = ocr_win.WinOCR

    def flaky(lang):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ocr_win.OcrUnavailable("first try fails")
        return real(lang)

    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ocr_win, "WinOCR", flaky)
            with pytest.raises(ocr_win.OcrUnavailable):
                ocr.get_ocr("en_US")
            if not any(tag.startswith("en") for tag in _installed()):
                pytest.skip("这台机器没有英文识别包")
            assert type(ocr.get_ocr("en_US")).__name__ == "WinOCR"
    finally:
        pass


def test_language_switch_reaches_the_detector(store, tmp_path):
    """设置里换语言后，检测器下次重建必须用新语言，不能留着构造时的旧语言。"""
    from types import SimpleNamespace

    from lolhex.config import Settings
    from lolhex.engine import Engine

    engine = Engine(Settings(), home=tmp_path, store=store)
    engine._detector = SimpleNamespace(game_lang="en_US", _ocr=object(),
                                       set_matcher=lambda _m: None, _last_fp=object())
    engine.set_game_lang("zh_CN")
    assert engine.settings.game_lang == "zh_CN"
    assert engine._detector.game_lang == "zh_CN", "检测器还在用旧语言"
    assert engine._detector._ocr is None, "换语言后要重建识别器"
