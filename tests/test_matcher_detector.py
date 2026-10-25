import json
from pathlib import Path

import pytest

from lolhex.vision.matcher import NameMatcher, normalize

_I18N = json.loads((Path(__file__).parent.parent / "lolhex" / "data" / "i18n.json")
                   .read_text(encoding="utf-8"))
NAMES = {aid: rec["en_US"] for aid, rec in _I18N["augments"].items() if rec.get("en_US")}


def test_normalize():
    assert normalize("质变：棱彩阶") == normalize("质变:棱彩阶") == "质变棱彩阶"


def test_matcher_tolerates_ocr_noise():
    # 中文客户端仍然按中文名匹配（识别器要装中文包）；这里单独建一份中文名表来测容错。
    cn = {aid: rec["zh_CN"] for aid, rec in _I18N["augments"].items() if rec.get("zh_CN")}
    m = NameMatcher(cn)
    assert m.match("虚幻武器")[0] == "1029"
    assert m.match("质变:棱彩阶")[0] == "1238"
    assert m.match("炽燃利忌")[0] == "2128"          # 一个字识别错
    assert m.match("获得1个随机强化符文。")[0] is None  # 描述文字不应命中
    assert m.match("A")[0] is None


synth = pytest.importorskip("synth")
if not synth.fonts_available():
    pytest.skip("没有可用字体，跳过合成画面测试", allow_module_level=True)


@pytest.fixture(scope="module")
def detector():
    from lolhex.vision.detector import AugmentDetector
    return AugmentDetector(NameMatcher(NAMES))


def names(offer):
    return [NAMES.get(s) if s else None for s in offer.slots]


@pytest.mark.parametrize("size", [(3840, 2160), (1920, 1080)])
def test_full_scan_calibrates_and_strip_tracks_reroll(detector, size):
    from lolhex.vision.window import Rect
    detector.calibration = None
    offer = detector.scan_full(synth.render_offer(["Transmute: Prismatic", "Combusting Interest", "Ethereal Weapon"], size))
    assert names(offer) == ["Transmute: Prismatic", "Combusting Interest", "Ethereal Weapon"]
    assert detector.calibrated_for(*size)

    win = Rect(0, 0, *size)
    sr = detector.strip_rect(win)
    frame = synth.render_offer(["Titan's Resolve", "Combusting Interest", "Ethereal Weapon"], size, seed=3)
    offer2 = detector.check_strip(frame[sr.top:sr.bottom, sr.left:sr.right], win)
    assert names(offer2) == names(offer)  # 首个变化读数暂不改变整组推荐。
    offer2 = detector.check_strip(frame[sr.top:sr.bottom, sr.left:sr.right], win)
    assert names(offer2) == ["Titan's Resolve", "Combusting Interest", "Ethereal Weapon"]

    empty = synth.render_offer([None, None, None], size, seed=4)
    assert detector.check_strip(empty[sr.top:sr.bottom, sr.left:sr.right], win) is None

    # 点击位置映射到卡片列
    b = detector.calibration.pixel_boxes(*size)[2]
    assert detector.column_of((b[0] + b[2]) // 2, b[3] + 50, win) == 2


def test_two_cards_are_placed_by_symmetry(detector):
    size = (3840, 2160)
    assert names(detector.scan_full(synth.render_offer(["Combusting Interest", None, "Ethereal Weapon"], size))) == ["Combusting Interest", None, "Ethereal Weapon"]
    assert names(detector.scan_full(synth.render_offer([None, "Combusting Interest", "Ethereal Weapon"], size))) == [None, "Combusting Interest", "Ethereal Weapon"]


def test_no_offer_on_plain_screen(detector):
    assert detector.scan_full(synth.render_offer([None, None, None], (3840, 2160), seed=9)) is None


@pytest.mark.parametrize("size", [(3840, 2160), (1920, 1080), (2560, 1600)])
def test_default_calibration_reads_first_offer(tmp_path, size):
    """没校准过也能直接走轻量检查；三张都对上后存成本机校准。"""
    from lolhex.vision.detector import AugmentDetector
    from lolhex.vision.window import Rect
    det = AugmentDetector(NameMatcher(NAMES), tmp_path / "calibration.json")
    det.ensure_calibration(*size)
    assert det.calibrated_for(*size) and not det.confirmed_for(*size)
    win = Rect(0, 0, *size)
    sr = det.strip_rect(win)
    frame = synth.render_offer(["Transmute: Prismatic", "Combusting Interest", "Ethereal Weapon"], size)
    offer = det.check_strip(frame[sr.top:sr.bottom, sr.left:sr.right], win)
    assert names(offer) == ["Transmute: Prismatic", "Combusting Interest", "Ethereal Weapon"]
    assert det.confirmed_for(*size)
    assert AugmentDetector(NameMatcher(NAMES), tmp_path / "calibration.json").confirmed_for(*size)


def test_vision_cost_logged_per_game(detector, caplog):
    from lolhex.engine import Engine
    from lolhex.vision.window import Rect
    size = (1920, 1080)
    detector.calibration = None
    detector._last_fp = None                          # 不受前面测试留下的画面指纹影响
    detector.cost = dict.fromkeys(detector.cost, 0)
    detector.scan_full(synth.render_offer(["Combusting Interest", "Ethereal Weapon", "Titan's Resolve"], size))
    win = Rect(0, 0, *size)
    sr = detector.strip_rect(win)
    strip = synth.render_offer(["Combusting Interest", "Ethereal Weapon", "Titan's Resolve"], size, seed=5)[sr.top:sr.bottom, sr.left:sr.right]
    detector.check_strip(strip, win)
    detector.check_strip(strip, win)                 # 画面没变：不再认字，不算次数
    assert detector.cost["full"] == 1 and detector.cost["strip"] == 1
    with caplog.at_level("INFO"):
        Engine._log_vision_cost(detector)
    assert "标题条 1 次" in caplog.text and "整块扫描 1 次" in caplog.text and "CPU" in caplog.text
    assert detector.cost["strip"] == 0 and detector.cost["full"] == 0
