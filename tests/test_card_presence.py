"""三卡面板像素证据的回归测试（issue #18）。

证据只读已有像素：三列卡框的金属竖边 + 卡内暗底，不需要标题亮度、OCR 或截图。
真实 fixture 是 2560×1440 的脱敏实机截图；下面的几何是它 scan_full 校准得到的真实
标题框（不使用 OCR，测试因此可离线复现）。标题被抹掉或移动时证据必须仍然成立；
普通场景、纯色、三个暗块、亮底、不确定棱彩都不能被当成三张卡。
"""
from pathlib import Path

import numpy as np
import pytest

from lolhex.vision.cardframe import card_presence, classify_card_frames, frame_strip_bounds

_FIXTURE = Path(__file__).parent / "fixtures" / "real-mayhem-augment-screen.png"
_FIXTURE_SIZE = (2560, 1440)
# 该 fixture 用真实 OCR 整块扫描得到的三个标题框（屏幕坐标），窗口 2560×1440。
_FIXTURE_BOXES = [(584, 570, 995, 615), (1074, 570, 1485, 615), (1563, 570, 1973, 615)]


def _load_fixture() -> np.ndarray:
    import cv2
    img = cv2.imdecode(np.fromfile(str(_FIXTURE), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None and img.shape[:2] == (_FIXTURE_SIZE[1], _FIXTURE_SIZE[0])
    return img


def _fixture_strip(img=None, boxes=None):
    img = _load_fixture() if img is None else img
    boxes = boxes or _FIXTURE_BOXES
    ox, oy, x1, y1 = frame_strip_bounds(boxes, _FIXTURE_SIZE[1])
    return img[oy:y1, ox:x1].copy(), boxes, (ox, oy)


def _title_mask(strip, boxes, origin):
    mask = np.zeros(strip.shape[:2], bool)
    ox, oy = origin
    for x0, y0, x1, y1 in boxes:
        sub = strip[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        mask[y0 - oy:y1 - oy, x0 - ox:x1 - ox] = sub.min(axis=2) >= 150
    return mask


def _blank_titles(strip, boxes, origin):
    out = strip.copy()
    out[_title_mask(out, boxes, origin)] = 16
    return out


def _shift_titles(strip, boxes, origin, dx, dy):
    """把标题亮像素整体平移，模拟标题位置变化；卡框像素不动。"""
    out = strip.copy()
    mask = _title_mask(out, boxes, origin)
    ys, xs = np.nonzero(mask)
    out[ys, xs] = 16
    h, w = out.shape[:2]
    out[np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)] = 210
    return out


def test_real_fixture_has_three_card_panels():
    strip, boxes, origin = _fixture_strip()
    labels = card_presence(strip, boxes, strip_origin=origin, window_height=_FIXTURE_SIZE[1])
    assert len(labels) == 3 and all(labels), labels
    assert set(labels) <= {"silver", "gold"}


@pytest.mark.parametrize("dx,dy", [(0, 0), (40, 0), (-40, 0), (70, 4), (-70, -4)])
def test_real_fixture_titles_shifted_or_blanked_still_show_three_panels(dx, dy):
    strip, boxes, origin = _fixture_strip()
    variant = _blank_titles(strip, boxes, origin) if (dx, dy) == (0, 0) else \
        _shift_titles(strip, boxes, origin, dx, dy)
    labels = card_presence(variant, boxes, strip_origin=origin, window_height=_FIXTURE_SIZE[1])
    assert len(labels) == 3 and all(labels), labels


def test_blanked_titles_keep_panel_evidence_but_not_rarity_classification():
    """标题识别/亮度不是面板证据的前提：classify 需要标题字形，card_presence 不需要。"""
    strip, boxes, origin = _fixture_strip()
    blanked = _blank_titles(strip, boxes, origin)
    assert all(card_presence(blanked, boxes, strip_origin=origin,
                             window_height=_FIXTURE_SIZE[1]))
    assert classify_card_frames(blanked, boxes, strip_origin=origin,
                                window_height=_FIXTURE_SIZE[1]) == [None] * 3


def test_partial_crop_does_not_claim_the_missing_card():
    strip, boxes, origin = _fixture_strip()
    labels = card_presence(strip[:, :-2], boxes, strip_origin=origin,
                           window_height=_FIXTURE_SIZE[1])
    assert labels[0] and labels[1] and labels[2] is None


# ---------- 合成负例：都使用真实像素运算，不接受“OCR 失败=有卡” ----------

def _synthetic_scene(height=1080, kind="three_cards", border="silver", interior=16):
    scale = height / 1080
    spacing = 369 * scale
    centers = [960 * scale + (i - 1) * spacing for i in range(3)]
    boxes = [(round(c - spacing * .42), round(430 * scale),
              round(c + spacing * .42), round(480 * scale)) for c in centers]
    bounds = frame_strip_bounds(boxes, height)
    ox, oy, x1, y1 = bounds
    image = np.full((y1 - oy, x1 - ox, 3), 12, np.uint8)
    colour = {"silver": (125, 126, 127), "gold": (114, 140, 173),
              "prismatic": (220, 140, 190), "blue": (200, 80, 40)}[border]
    if kind in {"three_cards", "bright_interior", "dark_boxes", "prismatic"}:
        for c, box in zip(centers, boxes):
            if kind != "dark_boxes":
                for sign in (-1, 1):
                    x = round(c + sign * spacing * .42) - ox
                    image[:, x - round(4 * scale):x + round(4 * scale) + 1] = colour
            if kind == "bright_interior":
                image[:, round(box[0] - ox) + 8:round(box[2] - ox) - 8] = 200
            if kind == "dark_boxes":
                image[:, round(box[0] - ox) + 8:round(box[2] - ox) - 8] = interior
    elif kind == "flat_dark":
        image[:] = 12
    elif kind == "flat_grey":
        image[:] = 125
    elif kind == "ordinary":
        rows = np.linspace(0, 1, image.shape[0])[:, None, None]
        top, bottom = np.array([60, 90, 140]), np.array([30, 50, 80])
        image[:] = (top * (1 - rows) + bottom * rows).astype(np.uint8)
        rng = np.random.default_rng(7)
        noise = rng.integers(-8, 9, image.shape, dtype=np.int16)
        image[:] = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return image, boxes, bounds


@pytest.mark.parametrize("kind", ["flat_dark", "flat_grey", "ordinary", "dark_boxes",
                                  "bright_interior", "prismatic"])
def test_negative_scenes_show_no_three_card_panels(kind):
    image, boxes, bounds = _synthetic_scene(kind=kind,
                                            border="prismatic" if kind == "prismatic" else "silver")
    labels = card_presence(image, boxes, strip_origin=bounds[:2], window_height=1080)
    assert labels == [None, None, None]


def test_noise_alone_is_not_evidence():
    image, boxes, bounds = _synthetic_scene(kind="three_cards")
    rng = np.random.default_rng(11)
    noisy = rng.integers(0, 255, image.shape, dtype=np.uint8)
    assert card_presence(noisy, boxes, strip_origin=bounds[:2], window_height=1080) == [None] * 3


def test_synthetic_three_cards_are_positive_control():
    image, boxes, bounds = _synthetic_scene(kind="three_cards")
    assert card_presence(image, boxes, strip_origin=bounds[:2], window_height=1080) == ["silver"] * 3


def test_invalid_geometry_or_window_height_is_never_positive():
    image, boxes, bounds = _synthetic_scene(kind="three_cards")
    assert card_presence(image, [boxes[0], None, boxes[2]], strip_origin=bounds[:2],
                         window_height=1080) == [None] * 3
    assert card_presence(image, boxes, strip_origin=bounds[:2], window_height=0) == [None] * 3
    assert card_presence(np.zeros((4, 4, 3), np.uint8), boxes, strip_origin=bounds[:2],
                         window_height=1080) == [None] * 3


def test_fixture_strip_bounds_match_recorded_geometry():
    assert frame_strip_bounds(_FIXTURE_BOXES, _FIXTURE_SIZE[1]) == (555, 570, 2003, 615)
