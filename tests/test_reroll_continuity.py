"""瞬时低识别读数的连续性：像素没变也必须重读失败列。

复现来源：upstream 9fe96f3 的 tests/test_reroll_continuity.py（去掉列轮换/饥饿
维护的三条，本 fork 的轻量检查没走那条优化），以及
.superpowers/upstream-review-2026-10-26/scratch/repro_current.py 的 A、A2：
两列失败一次后像素不再变化，旧代码把这一批空值缓存成否定结果，之后连 OCR 都不再调用，
真实 Engine._vision_loop 会在 0.93 s 后把 offer 藏起来；三批真实空读数才该过期。
"""
import numpy as np
import pytest

from test_ocr_stability import setup_detector


def change_columns(det, rect, strip, *columns, value=200):
    boxes = det.calibration.pixel_boxes(rect.width, rect.height)
    sr = det.strip_rect(rect)
    for i in columns:
        x0, y0, x1, y1 = boxes[i]
        strip[y0 - (sr.top - rect.top):y1 - (sr.top - rect.top),
              x0 - (sr.left - rect.left):x1 - (sr.left - rect.left)] = value


def test_two_transient_failures_retry_only_failed_columns_without_reset(monkeypatch):
    det, ocr, clock, rect, strip = setup_detector(monkeypatch)
    stable = det._stable
    change_columns(det, rect, strip, 0, 1)
    ocr.values = ["", ""]
    assert det.check_strip(strip, rect) is None
    assert det._stable is stable and det._low_match_reads == 1 and ocr.calls == 5
    # 同样的像素：必须真的再调 OCR，而不是复用缓存里的 None。
    ocr.values = ["甲甲", "乙乙"]
    clock[0] += .31
    assert det.check_strip(strip, rect).slots == ["0", "1", "2"]
    assert ocr.calls == 7 and det._low_match_reads == 0
    assert det.cost["full"] == 0


def test_three_real_negative_observations_end_retries(monkeypatch):
    det, ocr, clock, rect, strip = setup_detector(monkeypatch)
    change_columns(det, rect, strip, 0, 1)
    for attempt in range(3):
        ocr.values = ["", ""]
        clock[0] += .31
        assert det.check_strip(strip, rect) is None
        assert ocr.calls == 3 + 2 * (attempt + 1)
    assert det._stable is None
    calls = ocr.calls
    clock[0] += 30
    assert det.check_strip(strip, rect) is None and ocr.calls == calls


def test_recovery_on_third_observation_preserves_two_read_rule(monkeypatch):
    det, ocr, clock, rect, strip = setup_detector(monkeypatch)
    change_columns(det, rect, strip, 0, 1)
    for _ in range(2):
        ocr.values = ["", ""]
        clock[0] += .31
        assert det.check_strip(strip, rect) is None
    ocr.values = ["丁丁", "乙乙"]
    clock[0] += .31
    assert det.check_strip(strip, rect).slots == ["0", "1", "2"]
    ocr.values = ["丁丁"]
    clock[0] += .31
    assert det.check_strip(strip, rect).slots == ["3", "1", "2"]
    assert ocr.calls == 10


def test_full_two_card_recovery_invalidates_old_empty_strip_cache(monkeypatch):
    from lolhex.vision.detector import BAND
    from lolhex.vision.ocr import TextLine
    det, ocr, clock, rect, strip = setup_detector(monkeypatch)
    change_columns(det, rect, strip, 0, 1, 2)
    ocr.values = [""] * 9
    for _ in range(3):
        assert det.check_strip(strip, rect) is None
        clock[0] += .31
    x0, y0 = int(BAND[0] * rect.width), int(BAND[1] * rect.height)
    ocr.detect = lambda image: [TextLine(name, 1, (cx - 80 - x0, 430 - y0, cx + 80 - x0, 470 - y0))
                                for name, cx in zip(["甲甲", "乙乙"], [600, 960])]
    assert det.scan_full(np.zeros((rect.height, rect.width, 3), np.uint8)).matched() == 2
    calls = ocr.calls
    ocr.values = ["甲甲", "乙乙", "丙丙"]
    assert det.check_strip(strip, rect) is not None
    assert ocr.calls == calls + 3


@pytest.mark.parametrize("reset", ["tracking", "calibration", "size", "matcher", "move", "full"])
def test_context_change_resets_negative_confirmation(monkeypatch, reset):
    from lolhex.vision.detector import BAND
    from lolhex.vision.ocr import TextLine
    from lolhex.vision.window import Rect
    det, ocr, clock, rect, strip = setup_detector(monkeypatch)
    change_columns(det, rect, strip, 0, 1)
    ocr.values = ["", ""]
    assert det.check_strip(strip, rect) is None and det._low_match_reads == 1
    if reset == "tracking":
        det.clear_tracking()
    elif reset == "calibration":
        det.reset_calibration()
    elif reset == "size":
        det.ensure_calibration(2560, 1440)
    elif reset == "matcher":
        det.set_matcher(det.matcher)
    elif reset == "move":
        ocr.values = ["甲甲", "乙乙", "丙丙"]
        det.check_strip(strip, Rect(1, 0, rect.width, rect.height))
    else:
        x0, y0 = int(BAND[0] * rect.width), int(BAND[1] * rect.height)
        ocr.detect = lambda image: [TextLine(name, 1, (cx - 80 - x0, 430 - y0, cx + 80 - x0, 470 - y0))
                                    for name, cx in zip(["甲甲", "乙乙", "丙丙"], [600, 960, 1320])]
        assert det.scan_full(np.zeros((rect.height, rect.width, 3), np.uint8))
    assert det._low_match_reads == 0


@pytest.mark.parametrize("recover", [True, False])
def test_actual_engine_closes_only_after_new_negative_observations(monkeypatch, recover):
    import threading
    from types import SimpleNamespace

    from lolhex.engine import Engine
    from lolhex.vision import capture, window
    det, ocr, clock, rect, strip = setup_detector(monkeypatch)
    steps = [0]
    events = []

    class Stop:
        def is_set(self):
            return steps[0] >= 4

        def wait(self, delay):
            steps[0] += 1
            clock[0] += .31
            if steps[0] == 1:
                change_columns(det, rect, strip, 0, 1)
                ocr.values = ["", "", "甲甲", "乙乙"] if recover else [""] * 6

    monkeypatch.setattr(window, "find_game_window", lambda: 1)
    monkeypatch.setattr(window, "client_rect", lambda _: rect)
    monkeypatch.setattr(window, "is_foreground", lambda _: True)
    monkeypatch.setattr(window, "lower_thread_priority", lambda: None)
    monkeypatch.setattr(capture, "grab", lambda *args: strip)
    engine = Engine.__new__(Engine)
    engine._lock = threading.RLock()
    engine._stop = Stop()
    engine._rescan = threading.Event()
    engine._detector = det
    engine.state = {"phase": "ingame", "vision": {}}
    engine.settings = SimpleNamespace(scan_interval_ms=300, speed_factor=1,
                                      bootstrap_interval_s=3)
    engine._ocr_warned = None
    engine._save_offer_shot = lambda _rect: None
    engine._on_offer = lambda offer: events.append(offer.slots if offer else None)
    engine._vision_loop()
    assert (None in events) is not recover
    assert ocr.calls == (7 if recover else 9)
    assert det.cost["full"] == 0
