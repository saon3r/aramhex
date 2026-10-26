"""三选一校准几何的回归测试。

复现来源：upstream 9fe96f3 的 tests/test_calibration_geometry.py，以及
.superpowers/upstream-review-2026-10-26/scratch/repro_current.py 的 B、C：
172 那台机器记录下来的 3840x2160 错误几何（前两个标题框重叠 339 px）今天会被
接受、写入 calibration.json 并照它发 offer；同一海克斯在两处被识别时也算两张卡。

校准必须有限、在客户区内、从左到右、像素宽度非零且互不重叠；载入和写入前都要查，
候选被拒不能覆盖已有校准。这里刻意用 detect_scale（本 fork 的固定 1600 px 归一化），
不用上游的 min(1.0, …)。
"""
import json

import numpy as np
import pytest

from lolhex.vision.detector import BAND, DETECT_MAX_W, AugmentDetector, Calibration, detect_scale
from lolhex.vision.matcher import NameMatcher
from lolhex.vision.ocr import TextLine

# 172 的 4K 实机错误校准：前两框中心 ≈1155 / 1459，标题框重叠 339 px。
BAD_BOXES = [(.21689713541666666, .3851851851851852, .3844049479166667, .4351851851851852),
             (.29619401041666666, .3851851851851852, .4637018229166667, .4351851851851852),
             (.6157252604166668, .3851851851851852, .7832330729166667, .4351851851851852)]

NAMES3 = {"0": "甲甲", "1": "乙乙", "2": "丙丙", "3": "丁丁"}


def detector_with_centers(centers, path=None, names=("甲甲", "乙乙", "丙丙")):
    width, height = 3840, 2160
    x0, y0 = int(BAND[0] * width), int(BAND[1] * height)
    scale = detect_scale(int(BAND[2] * width) - x0)

    class OCR:
        def detect(self, image):
            return [TextLine(name, 1, tuple(int(v * scale) for v in
                                            (cx - 80 - x0, 865 - y0, cx + 80 - x0, 905 - y0)))
                    for name, cx in zip(names, centers)]

    return AugmentDetector(NameMatcher(NAMES3), calib_path=path, ocr=OCR())


def test_recorded_left_shift_is_rejected_before_publish_or_save(tmp_path, caplog):
    path = tmp_path / "calibration.json"
    good = Calibration.default(3840, 2160)
    good.guess = False
    path.write_text(json.dumps({"boxes": good.boxes, "size": good.size}), encoding="utf-8")
    before = path.read_bytes()
    centers = [(b[0] + b[2]) * 3840 / 2 for b in BAD_BOXES]
    det = detector_with_centers(centers, path)
    original = det.calibration
    det._low_match_reads = 1
    assert det.scan_full(np.zeros((2160, 3840, 3), np.uint8)) is None
    assert det.calibration is original
    assert det._low_match_reads == 1
    assert path.read_bytes() == before
    assert "拒绝三选一校准" in caplog.text


def test_recorded_bad_saved_calibration_is_not_reused(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"boxes": BAD_BOXES, "size": [3840, 2160]}), encoding="utf-8")
    det = detector_with_centers([1180, 1920, 2660], path)
    assert det.calibration is None
    # 原文件保留下来供诊断，等一次有效的整块扫描再替换。
    assert json.loads(path.read_text(encoding="utf-8"))["boxes"][1][0] == BAD_BOXES[1][0]
    assert det.scan_full(np.zeros((2160, 3840, 3), np.uint8)).matched() == 3
    assert det.calibration.valid()


@pytest.mark.parametrize("payload", [
    {"boxes": BAD_BOXES, "size": [3840, 2160]},                       # 重叠
    {"boxes": [[float("nan"), .3, .4, .4], [.45, .3, .55, .4], [.65, .3, .75, .4]],
     "size": [3840, 2160]},                                           # 非有限
    {"boxes": [[.1, .3, .2, .4]], "size": [3840, 2160]},              # 框数不对
    {"boxes": [[.1, .3, .4], [.45, .3, .55], [.65, .3, .75]], "size": [3840, 2160]},
    {"boxes": [["a", "b", "c", "d"], [.45, .3, .55, .4], [.65, .3, .75, .4]],
     "size": [3840, 2160]},                                           # 类型不对
    {"boxes": [1, 2, 3], "size": [3840, 2160]},                       # 无法转 tuple
    {"boxes": Calibration.default(3840, 2160).boxes, "size": [0, 2160]},   # 尺寸为 0
    {"boxes": Calibration.default(3840, 2160).boxes, "size": [float("inf"), 2160]},
    {"boxes": Calibration.default(3840, 2160).boxes, "size": [3840]},      # 尺寸畸形
    {"boxes": Calibration.default(3840, 2160).boxes},                      # 缺字段
    [1, 2, 3],                                                             # 顶层不是对象
    "not-a-calibration",
])
def test_hostile_saved_calibration_is_ignored_without_touching_the_file(tmp_path, payload):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    det = AugmentDetector(NameMatcher(NAMES3), calib_path=path)
    assert det.calibration is None
    assert path.read_bytes() == before


@pytest.mark.parametrize("centers", [[1180, 1920, 2660], [1180, 1830, 2660], [1180, 2010, 2660]])
def test_safe_unequal_spacing_is_still_allowed(centers):
    det = detector_with_centers(centers)
    assert det.scan_full(np.zeros((2160, 3840, 3), np.uint8)).matched() == 3
    assert det.calibration.valid()


@pytest.mark.parametrize("size", [(1366, 768), (1920, 1080), (2560, 1440), (3440, 1440),
                                  (3840, 2160), (5120, 1440)])
def test_default_geometry_stays_valid_at_common_resolutions(size):
    assert Calibration.default(*size).valid()


def test_existing_valid_saved_calibration_still_loads(tmp_path):
    path = tmp_path / "calibration.json"
    saved = Calibration.default(3840, 2160)
    saved.guess = False
    path.write_text(json.dumps({"boxes": saved.boxes, "size": saved.size}), encoding="utf-8")
    det = AugmentDetector(NameMatcher(NAMES3), calib_path=path)
    assert det.calibration is not None and det.calibration.valid()
    assert det.confirmed_for(3840, 2160)


@pytest.mark.parametrize("box", [(float("nan"), .3, .4, .4), (-.1, .3, .2, .4),
                                 (.2, .3, .1, .4), (.2, .3, .4, 1.1),
                                 (.2, .3, .2, .4), (float("inf"), .3, .4, .4)])
def test_invalid_box_is_rejected(box):
    calibration = Calibration([box, (.45, .3, .55, .4), (.65, .3, .75, .4)], (3840, 2160))
    assert not calibration.valid()


@pytest.mark.parametrize("size", [(float("nan"), 2160), (3840, float("inf")), (0, 2160), (3840, -1)])
def test_invalid_size_is_rejected(size):
    assert not Calibration(Calibration.default(3840, 2160).boxes, size).valid()


def test_subpixel_empty_crop_is_rejected():
    boxes = [(.2, .3, .20000001, .4), (.45, .3, .55, .4), (.65, .3, .75, .4)]
    assert not Calibration(boxes, (3840, 2160)).valid()


def test_overlapping_and_reversed_boxes_are_rejected():
    assert not Calibration([(.2, .3, .5, .4), (.4, .3, .6, .4), (.65, .3, .75, .4)],
                           (3840, 2160)).valid()
    assert not Calibration([(.5, .3, .6, .4), (.45, .3, .55, .4), (.65, .3, .75, .4)],
                           (3840, 2160)).valid()


def test_invalid_calibration_is_never_written(tmp_path):
    path = tmp_path / "calibration.json"
    det = AugmentDetector(NameMatcher(NAMES3), calib_path=path)
    det.calibration = Calibration(BAD_BOXES, (3840, 2160))
    det._save_calibration()
    assert not path.exists()


@pytest.mark.parametrize("names", [["甲甲", "户", "甲甲"], ["甲甲", "甲甲", "甲甲"]])
def test_duplicate_identity_does_not_count_as_distinct_cards(names):
    """同一海克斯在两处命中（172 日志里的 ['死亡之舞', '', '死亡之舞']）不是两张卡。"""
    det = detector_with_centers([1180, 1920, 2660], names=names)
    assert det.scan_full(np.zeros((2160, 3840, 3), np.uint8)) is None
    assert det.calibration is None


def test_duplicate_identity_does_not_write_a_calibration(tmp_path):
    path = tmp_path / "calibration.json"
    det = detector_with_centers([1180, 1920, 2660], path, names=["甲甲", "甲甲", "甲甲"])
    assert det.scan_full(np.zeros((2160, 3840, 3), np.uint8)) is None
    assert not path.exists()
