"""issue #18 的集成回归：持续正像素证据 + 零识别 → 每局一次提示。

证据来自已有标题条/整帧像素（三张卡的金属竖边 + 卡内暗底），不依赖 OCR、标题文字或
额外截图。只有连续 ≥3 次真实捕获观察且持续 ≥1.5 秒零匹配才会触发；任何一次识别出
标题、卡片证据不足、暂停/后台、改分辨率、缺识别器、对局结束都会重置候选，避免误报。
提示只在当前仍成立时留在面板上；托盘与日志每局最多一次，下一局重新武装。
"""
from __future__ import annotations

import os
import threading
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lolhex.engine import CardFailureTracker, Engine  # noqa: E402
from lolhex.vision.window import Rect  # noqa: E402

W, H = 2560, 1440
_FIXTURE_BOXES = [(584, 570, 995, 615), (1074, 570, 1485, 615), (1563, 570, 1973, 615)]


def _fixture():
    import cv2
    from pathlib import Path
    path = Path(__file__).parent / "fixtures" / "real-mayhem-augment-screen.png"
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def _calibration(boxes=_FIXTURE_BOXES, size=(W, H)):
    from lolhex.vision.detector import Calibration
    w, h = size
    return Calibration([(x0 / w, y0 / h, x1 / w, y1 / h) for x0, y0, x1, y1 in boxes], size)


class _RaisingOcr:
    def recognize(self, image):
        raise AssertionError("card evidence must not run OCR")

    def detect(self, image):
        raise AssertionError("card evidence must not run OCR")


# ---------- detector: pixels only, raw matched count independent of Offer ----------

def test_card_evidence_reads_only_existing_pixels(monkeypatch):
    from lolhex.vision.detector import AugmentDetector
    from lolhex.vision.matcher import NameMatcher
    import lolhex.vision.capture as capture

    det = AugmentDetector(NameMatcher({}), ocr=_RaisingOcr())
    det.calibration = _calibration()
    monkeypatch.setattr(capture, "grab", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("card evidence must not capture")))
    frame = _fixture()
    from lolhex.vision.cardframe import frame_strip_bounds
    ox, oy, x1, y1 = frame_strip_bounds(det.calibration.pixel_boxes(W, H), H)
    strip = frame[oy:y1, ox:x1]
    evidence = det.card_evidence(strip, Rect(0, 0, W, H))
    assert evidence["cards"] == 3 and evidence["frame"] == "strip"
    assert evidence["width"] == W and evidence["height"] == H


def test_card_evidence_from_full_existing_frame():
    from lolhex.vision.detector import AugmentDetector
    from lolhex.vision.matcher import NameMatcher

    det = AugmentDetector(NameMatcher({}), ocr=_RaisingOcr())
    det.calibration = _calibration()
    evidence = det.card_evidence(_fixture(), Rect(0, 0, W, H), full=True)
    assert evidence["cards"] == 3 and evidence["frame"] == "full"


def test_card_evidence_stays_zero_on_ordinary_pixels():
    from lolhex.vision.detector import AugmentDetector
    from lolhex.vision.matcher import NameMatcher

    det = AugmentDetector(NameMatcher({}), ocr=_RaisingOcr())
    det.calibration = _calibration()
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    assert det.card_evidence(noise, Rect(0, 0, W, H), full=True)["cards"] == 0
    flat = np.full((H, W, 3), 120, np.uint8)
    assert det.card_evidence(flat, Rect(0, 0, W, H), full=True)["cards"] == 0
    # 未知几何（校准尺寸不符）也不能靠猜。
    other = det.card_evidence(_fixture(), Rect(0, 0, 1920, 1080), full=True)
    assert other["cards"] == 0


def test_raw_matched_count_is_independent_of_publishable_offer(monkeypatch):
    from lolhex.vision.detector import AugmentDetector
    from lolhex.vision.matcher import NameMatcher

    class OCR:
        calls = 0
        values = ["甲甲", "", ""]

        def recognize(self, image):
            self.calls += 1
            return self.values.pop(0), 1.0

    det = AugmentDetector(NameMatcher({"0": "甲甲", "1": "乙乙", "2": "丙丙"}), ocr=OCR())
    det.ensure_calibration(1920, 1080)
    rect = Rect(0, 0, 1920, 1080)
    strip = np.zeros((det.strip_rect(rect).height, det.strip_rect(rect).width, 3), np.uint8)
    assert det.check_strip(strip, rect) is None          # 1/3 不能发布
    assert det.last_read["matched"] == 1                  # 但原始识别到 1 个标题
    calls = det.ocr.calls
    assert det.check_strip(strip, rect) is None and det.ocr.calls == calls
    assert det.last_read["matched"] == 1                  # 缓存读数保持真实值


def test_raw_matched_count_from_two_card_full_scan():
    from lolhex.vision.detector import AugmentDetector
    from lolhex.vision.matcher import NameMatcher
    from lolhex.vision.ocr import TextLine

    class OCR:
        def detect(self, image):
            return [TextLine("甲甲", 1, (290, 322, 490, 362)),
                    TextLine("乙乙", 1, (650, 322, 850, 362))]

    det = AugmentDetector(NameMatcher({"0": "甲甲", "1": "乙乙"}), ocr=OCR())
    assert det.scan_full(np.zeros((1080, 1920, 3), np.uint8)).matched() == 2
    assert det.last_read["matched"] == 2


# ---------- pure tracker ----------

def test_tracker_needs_three_observations_and_one_and_a_half_seconds():
    from lolhex.engine import CardFailureTracker
    tracker = CardFailureTracker()
    t = 100.0
    states = []
    for _ in range(3):                       # 3 次观察只过了 0.6 秒
        t += 0.3
        states.append(tracker.observe(t, cards=3, matched=0))
    assert [s["active"] for s in states] == [False, False, False]
    for _ in range(3):                       # 第 6 次观察才满 1.5 秒
        t += 0.3
        states.append(tracker.observe(t, cards=3, matched=0))
    assert states[-1]["active"] and states[-1]["fired"]
    assert sum(1 for s in states if s["fired"]) == 1
    t += 0.3
    assert tracker.observe(t, cards=3, matched=0)["fired"] is False   # 同局只触发一次


def test_tracker_resets_on_one_match_or_uncertain_cards():
    from lolhex.engine import CardFailureTracker
    tracker = CardFailureTracker()
    t = 100.0
    for cards, matched in ((3, 0), (3, 0), (3, 1), (3, 0), (2, 0), (3, 0)):
        t += 1.0
        tracker.observe(t, cards=cards, matched=matched)
    assert tracker.observations <= 1


def test_tracker_latch_clears_for_a_new_game():
    from lolhex.engine import CardFailureTracker
    tracker = CardFailureTracker()
    t = 100.0
    for _ in range(6):
        t += 0.3
        tracker.observe(t, cards=3, matched=0)
    assert tracker.fired
    tracker.new_game()
    assert not tracker.fired and tracker.observations == 0


def test_tracker_counter_stays_bounded_on_a_long_failure_sequence():
    """持续很久也不让报数无界增长；每局仍然只触发一次。"""
    from lolhex.engine import CardFailureTracker
    tracker = CardFailureTracker()
    t = 100.0
    for _ in range(5000):
        t += 0.3
        status = tracker.observe(t, cards=3, matched=0)
    assert tracker.observations == CardFailureTracker.MAX_OBSERVATIONS
    assert tracker.observations <= 1000
    assert tracker.fired and status["active"] and status["fired"] is False


# ---------- engine: exactly once, recovery, lifecycle ----------

def _engine(store, tmp_path):
    from lolhex.config import Settings
    from lolhex.engine import Engine
    eng = Engine(Settings(), home=tmp_path, store=store)
    eng._set(phase="ingame")
    return eng


def _observe(eng, clock, rect=None, cards=3, matched=0, frame="strip"):
    rect = rect or Rect(0, 0, 1920, 1080)
    clock[0] += 0.3
    eng._on_card_evidence({"cards": cards, "matched": matched, "frame": frame,
                           "width": rect.width, "height": rect.height}, rect, clock[0])


def _warnings(caplog):
    from lolhex.messages import tr
    text = tr("warning.cards_unrecognised")
    return [r for r in caplog.records if r.levelname == "WARNING" and text in r.getMessage()]


def test_engine_warns_once_then_clears_after_recovery(store, tmp_path, caplog):
    eng = _engine(store, tmp_path)
    clock = [100.0]
    with caplog.at_level("INFO"):
        for _ in range(6):
            _observe(eng, clock)
        vision = eng.snapshot()["vision"]
        event = dict(vision["cards_unrecognised_event"])
        assert vision["cards_unrecognised"] is not None
        assert set(event) == {"id", "observations", "elapsed", "cards", "matched", "frame",
                              "width", "height"}
        assert event["observations"] == 6 and event["elapsed"] >= 1.5 and event["matched"] == 0
        for _ in range(4):                    # 继续不识别也不重复
            _observe(eng, clock)
        assert eng.snapshot()["vision"]["cards_unrecognised_event"] == event
        assert len(_warnings(caplog)) == 1
        _observe(eng, clock, matched=1)       # 认出一个标题：立刻恢复正常状态
        vision = eng.snapshot()["vision"]
        assert vision["cards_unrecognised"] is None
        assert vision["cards_unrecognised_event"] == event   # 事件是锁存的，不是常驻状态
    assert len(_warnings(caplog)) == 1
    log_text = _warnings(caplog)[0].getMessage()
    from lolhex.messages import tr
    assert log_text.startswith(tr("warning.cards_unrecognised"))
    assert "observations=" in log_text and "geometry=1920x1080" in log_text
    assert "甲" not in log_text


def test_engine_short_transition_does_not_warn(store, tmp_path, caplog):
    eng = _engine(store, tmp_path)
    clock = [100.0]
    with caplog.at_level("INFO"):
        for _ in range(3):                    # 0.6 秒：不足 1.5 秒
            _observe(eng, clock)
        assert eng.snapshot()["vision"]["cards_unrecognised_event"] is None
    assert not _warnings(caplog)


@pytest.mark.parametrize("cards,matched", [(3, 1), (2, 0), (1, 0)])
def test_engine_never_warns_without_three_cards_and_zero_matches(store, tmp_path, caplog, cards, matched):
    eng = _engine(store, tmp_path)
    clock = [100.0]
    with caplog.at_level("INFO"):
        for _ in range(8):
            _observe(eng, clock, cards=cards, matched=matched)
        vision = eng.snapshot()["vision"]
        assert vision["cards_unrecognised"] is None and vision["cards_unrecognised_event"] is None
    assert not _warnings(caplog)


def test_engine_resets_candidate_on_resize_and_phase_end(store, tmp_path, caplog):
    eng = _engine(store, tmp_path)
    clock = [100.0]
    with caplog.at_level("INFO"):
        for _ in range(5):
            _observe(eng, clock)
        _observe(eng, clock, rect=Rect(0, 0, 2560, 1440))     # 改分辨率：重新计数
        for _ in range(4):
            _observe(eng, clock, rect=Rect(0, 0, 2560, 1440))
        assert eng.snapshot()["vision"]["cards_unrecognised_event"] is None
        eng._set(phase="client")
        clock[0] += 30
        _observe(eng, clock, rect=Rect(0, 0, 2560, 1440))     # 退出对局后不得发布
        assert eng.snapshot()["vision"]["cards_unrecognised_event"] is None
    assert not _warnings(caplog)


def test_engine_rearms_notice_next_game(store, tmp_path, caplog):
    eng = _engine(store, tmp_path)
    clock = [100.0]
    with caplog.at_level("INFO"):
        for _ in range(6):
            _observe(eng, clock)
        first = dict(eng.snapshot()["vision"]["cards_unrecognised_event"])
        assert first["id"] == 1
        eng._on_game_end()
        assert eng.snapshot()["vision"]["cards_unrecognised_event"] is None
        eng._set(phase="ingame")
        for _ in range(6):
            _observe(eng, clock)
        second = dict(eng.snapshot()["vision"]["cards_unrecognised_event"])
        assert second["id"] == 2 and second["id"] != first["id"]
        assert len(_warnings(caplog)) == 2
    assert eng.snapshot()["vision"]["cards_unrecognised"] is not None


def test_engine_suppress_clears_candidate_but_keeps_the_game_latch(store, tmp_path, caplog):
    eng = _engine(store, tmp_path)
    clock = [100.0]
    with caplog.at_level("INFO"):
        for _ in range(6):
            _observe(eng, clock)
        event = dict(eng.snapshot()["vision"]["cards_unrecognised_event"])
        eng._suppress_cards_notice()          # 后台 / 缺识别器 / 暂停
        vision = eng.snapshot()["vision"]
        assert vision["cards_unrecognised"] is None
        assert vision["cards_unrecognised_event"] == event
        assert eng._card_failure.observations == 0
        for _ in range(3):
            _observe(eng, clock)              # 恢复后仍属同一局：不再提醒
        assert eng.snapshot()["vision"]["cards_unrecognised_event"] == event
        assert len(_warnings(caplog)) == 1


# ---------- engine loop: one observation per existing capture, no extra work ----------

class _Stop:
    def __init__(self, steps, clock, after=None):
        self.steps = 0
        self.limit = steps
        self.clock = clock
        self.after = after

    def is_set(self):
        return self.steps >= self.limit

    def wait(self, delay):
        self.steps += 1
        self.clock[0] += 0.3
        if self.after:
            self.after(self.steps)


class _Detector:
    def __init__(self, evidence=None, raise_ocr=False):
        self.cost = {"strip": 0, "strip_s": 0.0, "strip_cpu": 0.0, "strip_ocr": 0,
                     "full": 0, "full_s": 0.0, "full_cpu": 0.0}
        self.evidence = evidence or {"cards": 3, "matched": 0, "frame": "strip"}
        self.evidence_calls = 0
        self.raise_ocr = raise_ocr
        self.after_scan = None          # 扫描途中/之后注入状态变化
        self.offer = None               # check_strip 返回的成功识别
        self.evidence_raises = False
        self.last_read = {"matched": 0}

    def ensure_calibration(self, w, h):
        return None

    def calibrated_for(self, w, h):
        return True

    def confirmed_for(self, w, h):
        return True

    def strip_rect(self, rect):
        return rect

    def check_strip(self, strip, rect):
        if self.raise_ocr:
            from lolhex.vision.ocr_win import OcrUnavailable
            raise OcrUnavailable("en-GB")
        if self.after_scan:
            self.after_scan()
        return self.offer

    def scan_full(self, frame, origin=(0, 0)):
        self.last_read = {"matched": 0}
        return None

    def card_evidence(self, image, rect, full=False, origin=None):
        self.evidence_calls += 1
        if self.evidence_raises:
            raise RuntimeError("evidence boom")
        return dict(self.evidence)

    def clear_tracking(self):
        return None


class _WindowState:
    def __init__(self, rect):
        self.rect = rect
        self.foreground = True


def _loop_engine(det, clock, steps, monkeypatch, foreground=True, state=None):
    from lolhex.engine import Engine
    from lolhex.vision import capture, window
    import lolhex.engine as engine_module
    monkeypatch.setattr(engine_module.time, "monotonic", lambda: clock[0])
    state = state or _WindowState(Rect(0, 0, 1920, 1080))
    state.foreground = foreground
    shots = []
    offers = []
    engine = Engine.__new__(Engine)
    engine._lock = threading.RLock()
    engine._stop = _Stop(steps, clock)
    engine._rescan = threading.Event()
    engine._detector = det
    engine.state = {"phase": "ingame", "vision": {}}
    engine.settings = SimpleNamespace(scan_interval_ms=250, speed_factor=1,
                                      bootstrap_interval_s=3, game_lang="en_GB")
    engine._ocr_warned = None
    engine._vision_error = None
    engine._evidence_error = None
    engine._save_offer_shot = lambda _rect: shots.append(_rect)
    engine._on_offer = lambda offer: offers.append(offer)
    engine._card_failure = CardFailureTracker()
    engine._cards_event_seq = 0
    engine._last_vision_rect = None
    grabs = []

    def grab(_rect, **kw):
        grabs.append(_rect)
        return np.zeros((45, 600, 3), np.uint8)

    monkeypatch.setattr(window, "find_game_window", lambda: 1)
    monkeypatch.setattr(window, "client_rect", lambda _hwnd: state.rect)
    monkeypatch.setattr(window, "is_foreground", lambda _hwnd: state.foreground)
    monkeypatch.setattr(window, "lower_thread_priority", lambda: None)
    monkeypatch.setattr(capture, "grab", grab)
    engine._vision_loop()
    return engine, grabs, shots, offers


def test_engine_loop_counts_one_observation_per_capture(monkeypatch, caplog):
    clock = [1.0]
    det = _Detector()
    with caplog.at_level("INFO"):
        eng, grabs, shots, offers = _loop_engine(det, clock, 8, monkeypatch)
        event = eng.state["vision"]["cards_unrecognised_event"]
        assert event and event["id"] == 1
        assert det.evidence_calls == len(grabs) == 8
        assert shots == [] and offers == []
    assert len(_warnings(caplog)) == 1


def test_engine_loop_paused_window_never_observes(monkeypatch, caplog):
    clock = [100.0]
    det = _Detector()
    with caplog.at_level("INFO"):
        eng, grabs, shots, offers = _loop_engine(det, clock, 4, monkeypatch, foreground=False)
    assert det.evidence_calls == 0 and grabs == []
    assert eng.state["vision"].get("cards_unrecognised_event") is None
    assert not _warnings(caplog)


def test_engine_loop_missing_recognizer_suppresses_notice(monkeypatch, caplog):
    clock = [100.0]
    det = _Detector(raise_ocr=True)
    with caplog.at_level("INFO"):
        eng, grabs, shots, offers = _loop_engine(det, clock, 4, monkeypatch)
    assert eng.state["vision"]["error"]["code"] == "ocr_unavailable"
    assert eng.state["vision"].get("cards_unrecognised_event") is None
    assert not _warnings(caplog)


# ---------- post-scan context changes and diagnostic isolation ----------

def test_postscan_background_change_never_records_or_notifies(monkeypatch, caplog):
    """慢扫描途中切到后台：旧像素证据作废，不能事后提示一次。"""
    clock = [1.0]
    state = _WindowState(Rect(0, 0, 1920, 1080))
    det = _Detector()
    det.after_scan = lambda: setattr(state, "foreground", False)
    with caplog.at_level("INFO"):
        eng, grabs, shots, offers = _loop_engine(det, clock, 8, monkeypatch, state=state)
    assert det.evidence_calls == 0
    assert eng._card_failure.observations == 0
    assert eng.state["vision"].get("cards_unrecognised_event") is None
    assert not _warnings(caplog)


def test_postscan_window_move_never_records_or_notifies(monkeypatch, caplog):
    """窗口在扫描途中移动/改尺寸：几何已变，旧证据不能累计。"""
    clock = [1.0]
    a = Rect(0, 0, 1920, 1080)
    b = Rect(120, 60, 1920, 1080)
    state = _WindowState(a)
    det = _Detector()

    def move():
        state.rect = b if state.rect == a else a

    det.after_scan = move
    with caplog.at_level("INFO"):
        eng, grabs, shots, offers = _loop_engine(det, clock, 8, monkeypatch, state=state)
    assert det.evidence_calls == 0
    assert eng._card_failure.observations == 0
    assert eng.state["vision"].get("cards_unrecognised_event") is None
    assert not _warnings(caplog)


def test_evidence_failure_does_not_discard_a_valid_offer(monkeypatch, caplog):
    """证据自己的异常只算未知；已经识别出的 offer 必须照常发布，且日志有界。"""
    from lolhex.vision.detector import Offer

    clock = [1.0]
    det = _Detector()
    det.evidence_raises = True
    offer = Offer(["2128", "1029", "1373"], ["a", "b", "c"], [1, 1, 1], [None] * 3)
    det.offer = offer
    with caplog.at_level("DEBUG"):
        eng, grabs, shots, offers = _loop_engine(det, clock, 4, monkeypatch)
    assert offers and offers[0] is offer
    assert eng._card_failure.observations == 0
    assert eng.state["vision"].get("cards_unrecognised_event") is None
    errors = [r for r in caplog.records if "卡面证据异常" in r.getMessage()]
    assert len(errors) == 1                      # 同一原因只记一次堆栈


# ---------- overlay: one line, one tray notice, rearmed by a new event id ----------

def test_notice_helper_uses_the_frozen_catalog_text():
    pytest.importorskip("PySide6.QtWidgets")
    from lolhex.messages import tr
    from lolhex.ui.overlay import cards_unrecognised_notice
    text = tr("warning.cards_unrecognised")
    assert cards_unrecognised_notice({"cards_unrecognised": {"id": 1}}) == text
    assert cards_unrecognised_notice({"cards_unrecognised": None}) is None
    assert cards_unrecognised_notice({}) is None


def test_overlay_notifies_once_per_event_and_rearms_next_game():
    pytest.importorskip("PySide6.QtWidgets")
    from lolhex.messages import tr
    from lolhex.ui.overlay import Overlay

    ov = Overlay.__new__(Overlay)
    notes = []
    ov.notify = notes.append
    ov._cards_notice_key = None
    snap = lambda event: {"vision": {"cards_unrecognised_event": event}}
    ov._notify_vision_warnings(snap({"id": 1}))
    ov._notify_vision_warnings(snap({"id": 1}))
    assert notes == [tr("warning.cards_unrecognised")]
    ov._notify_vision_warnings(snap(None))          # 恢复：不提示，也不再重复
    ov._notify_vision_warnings(snap({"id": 2}))      # 下一局/下一次触发
    assert notes == [tr("warning.cards_unrecognised")] * 2


def test_panel_shows_one_warning_line_while_the_condition_holds():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from lolhex.messages import tr
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from lolhex.ui import overlay

    class FakeEngine:
        store = SimpleNamespace(heroes={}, resolve_hero=lambda key: None)
        icons = None
        settings = SimpleNamespace(overlay_corner="top-right")

        def hero_panel(self, _hid):
            return None

        def hero_brief(self, _hid):
            return {}

    panel = overlay.ControlPanel(FakeEngine())
    panel.expanded = True
    try:
        panel.update_from({"hero_id": None, "vision": {"cards_unrecognised": {"id": 1}},
                           "data": {}})
        assert tr("warning.cards_unrecognised") in panel.info.text()
        panel.update_from({"hero_id": None, "vision": {"cards_unrecognised": None},
                           "data": {}})
        assert tr("warning.cards_unrecognised") not in panel.info.text()
    finally:
        panel.close()
        app.processEvents()
