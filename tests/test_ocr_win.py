"""Windows.Media.Ocr 后端：真截图认得出三张卡，行框是整行，标题优先于类别标签。

这些断言直接跑在实机截图上，不走检测器；后端本身坏了这里最先红。
"""

from pathlib import Path

import pytest

pytest.importorskip("winrt.windows.media.ocr")

import cv2        # noqa: E402
import numpy as np  # noqa: E402

from lolhex.vision.ocr_win import OcrUnavailable, WinOCR  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real-mayhem-augment-screen.png"
TITLES = ("Juiced", "Adaptive Ward", "Snowday")


@pytest.fixture(scope="module")
def engine():
    try:
        return WinOCR("en_US")
    except OcrUnavailable as e:
        pytest.skip(f"这台机器没有可用的 Windows OCR 识别器：{e}")


def test_reads_the_three_card_titles(engine):
    frame = cv2.imread(str(FIXTURE))
    texts = [line.text for line in engine.detect(frame)]
    for want in TITLES:
        assert want in texts, f"{want} 没认出来，实际读到 {texts}"


def test_line_box_covers_the_whole_line_not_just_the_first_word(engine):
    """行框是整行：pick_my_hero 用行高判断「自己的英雄字号最大」，拿单个词的框会判反。"""
    frame = cv2.imread(str(FIXTURE))
    line = next(ln for ln in engine.detect(frame) if ln.text == "Adaptive Ward")
    assert line.h >= 20
    assert line.box[2] - line.box[0] >= 150      # 两个词加起来的宽度
    assert line.box[0] < line.cx < line.box[2]
    assert line.score == 1.0                     # 系统引擎没有置信度：认到就是 1.0


def test_recognize_prefers_the_title_over_the_category_tag(engine):
    """标题条里还有 General/Resilience/Utility 小字：标题字号更大，必须取标题。"""
    frame = cv2.imread(str(FIXTURE))
    crop = frame[560:640, 1140:1420]
    text, score = engine.recognize(crop)
    assert text == "Adaptive Ward"
    assert score == 1.0


def test_degenerate_inputs_do_not_raise(engine):
    assert engine.detect(np.zeros((0, 0, 3), np.uint8)) == []
    assert engine.detect(np.zeros((1, 1, 3), np.uint8)) == []
    assert engine.recognize(np.zeros((1, 1, 3), np.uint8)) == ("", 0.0)


def test_greyscale_and_rgba_inputs_work(engine):
    """截图偶尔是灰度或带 alpha；两种都要能认，不能直接抛。"""
    frame = cv2.imread(str(FIXTURE))
    crop = frame[560:640, 1140:1420]
    grey_text, _ = engine.recognize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
    rgba_text, _ = engine.recognize(cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA))
    assert grey_text == "Adaptive Ward"
    assert rgba_text == "Adaptive Ward"
