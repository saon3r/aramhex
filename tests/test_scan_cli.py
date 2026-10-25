"""--scan-image 输出的证据字段：basis/rate_label/source，且无数据卡不造假数字。"""

import json
from types import SimpleNamespace

import cv2
import numpy as np

from lolhex import __main__ as cli


class _Image:
    shape = (10, 20, 3)


class _Detector:
    calibration = None

    def __init__(self, _matcher, **_kwargs):   # 真检测器还接 game_lang 等参数
        pass

    def scan_full(self, _img):
        return SimpleNamespace(slots=["2128", "5555"], texts=["x"], calibration=None)


def test_scan_image_serializes_basis_label_and_no_false_numbers(store, monkeypatch, capsys):
    monkeypatch.setattr(cv2, "imdecode", lambda _buf, _flags: _Image())
    monkeypatch.setattr(np, "fromfile", lambda _path, dtype=None: np.zeros(1, dtype=np.uint8))
    monkeypatch.setattr("lolhex.vision.detector.AugmentDetector", _Detector)
    monkeypatch.setattr("lolhex.engine.augment_matcher", lambda _store, _settings: object())
    monkeypatch.setattr(store, "refresh", lambda *a, **k: None)
    engine = SimpleNamespace(store=store, settings=SimpleNamespace(smoothing_games=300))

    assert cli._scan_image(engine, "unused.png", "1") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sources"]["win_source"]
    global_card, no_data_card = out["cards"]

    # 本英雄没有这张卡：用全英雄合计，明确标 all champs，并保留证据字段。
    assert global_card["basis"] == "global_win" and global_card["rate_label"] == "all champs"
    assert global_card["source"] == "public" and isinstance(global_card["win"], float)
    assert "tier" not in global_card

    # 统计里完全没有：不给数字，只给状态字段（JSON null，而不是 0/假百分比）。
    assert no_data_card["verdict"] == "nodata" and no_data_card["basis"] in ("new", "nodata")
    assert no_data_card["win"] is None and no_data_card["games"] is None
    assert no_data_card["score"] is None and no_data_card["rate_label"] is None
    assert no_data_card["source"] is None and "tier" not in no_data_card
    assert "%" not in json.dumps(no_data_card, ensure_ascii=False)
