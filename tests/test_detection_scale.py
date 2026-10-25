"""整块扫描的分辨率无关性（issue #22）。

检测器对整块画面做 OCR 前必须把扫描带归一到同一个宽度：以前只用 min(1.0, ...) 缩小，
2560/4K 送 1600 像素宽，1600/1366 送原始像素、1920 送 1459 像素，每个分辨率喂给识别
引擎的像素都不一样，1080p 就出现了别的分辨率没有的识别失败。
"""
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).parent.parent
_FIXTURE = _ROOT / "tests" / "fixtures" / "real-mayhem-augment-screen.png"


class RecordingOcr:
    """记下每次 detect 收到的图尺寸；不认字，只验证送进去的像素。"""

    language = "en-US"

    def __init__(self):
        self.sizes: list[tuple[int, int]] = []

    def detect(self, img):
        self.sizes.append(tuple(img.shape[:2]))
        return []

    def recognize(self, img):
        return "", 0.0


@pytest.mark.parametrize("size", [(3840, 2160), (2560, 1440), (1920, 1080), (1600, 900), (1366, 768)])
def test_full_scan_feeds_the_same_ocr_width_at_every_resolution(size):
    from lolhex.vision.detector import DETECT_MAX_W, AugmentDetector
    from lolhex.vision.matcher import NameMatcher

    ocr = RecordingOcr()
    det = AugmentDetector(NameMatcher({}), ocr=ocr)
    det.scan_full(np.zeros((size[1], size[0], 3), np.uint8))
    assert ocr.sizes, "scan_full 没有调用 OCR"
    assert [w for _, w in ocr.sizes] == [DETECT_MAX_W], (
        f"{size[0]}x{size[1]} 送进 OCR 的是 {ocr.sizes}，不是固定宽度")


def _at_width(width: int) -> np.ndarray:
    import cv2

    img = cv2.imdecode(np.fromfile(str(_FIXTURE), dtype=np.uint8), cv2.IMREAD_COLOR)
    height = round(img.shape[0] * width / img.shape[1])
    return cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize("width", [2560, 1920, 1600, 1366])
def test_real_capture_reads_three_cards_at_every_resolution(width):
    """真实截图（2560×1440 实机）缩放到四种常见分辨率都要读出同样三张卡。"""
    import json

    from lolhex.vision.detector import AugmentDetector
    from lolhex.vision.matcher import NameMatcher

    i18n = json.loads((_ROOT / "lolhex" / "data" / "i18n.json").read_text(encoding="utf-8"))
    names = {aid: rec["en_US"] for aid, rec in i18n["augments"].items() if rec.get("en_US")}
    offer = AugmentDetector(NameMatcher(names)).scan_full(_at_width(width))
    assert offer is not None, f"{width} 宽没识别到三选一画面"
    assert list(offer.slots) == ["2016", "2138", "2088"], (
        f"{width} 宽读成 {[names.get(s) if s else None for s in offer.slots]}")
