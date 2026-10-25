"""复核：诊断用的三选一截图只在调试模式下保存，普通运行连屏幕都不截。"""

import numpy as np

from lolhex.config import Settings
from lolhex.engine import Engine
from lolhex.vision import capture
from lolhex.vision.window import Rect

RECT = Rect(0, 0, 640, 360)


def _engine(tmp_path, store, debug: bool) -> Engine:
    settings = Settings()
    settings.debug_mode = debug
    return Engine(settings, home=tmp_path, store=store)


def _frame() -> np.ndarray:
    return np.full((40, 60, 3), 128, np.uint8)


def test_non_debug_offer_shot_neither_captures_nor_deletes_existing(tmp_path, store, monkeypatch):
    eng = _engine(tmp_path, store, debug=False)
    folder = tmp_path / "shots"
    folder.mkdir()
    old = folder / "offer_20260101_120000.jpg"
    old.write_bytes(b"private capture from an earlier run")
    grabs = []
    monkeypatch.setattr(capture, "grab", lambda *a, **k: grabs.append(1) or _frame())

    eng._save_offer_shot(RECT)

    assert grabs == []                       # 普通运行不能截屏
    assert old.read_bytes() == b"private capture from an earlier run"  # 也不删旧截图
    assert list(folder.glob("offer_*.jpg")) == [old]


def test_debug_offer_shot_saves_within_its_bound(tmp_path, store, monkeypatch):
    eng = _engine(tmp_path, store, debug=True)
    grabs = []
    monkeypatch.setattr(capture, "grab", lambda *a, **k: grabs.append(k.get("mask")) or _frame())

    class SyncThread:                         # 保存线程同步执行，测试不用等
        def __init__(self, target, **kwargs):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("lolhex.engine.threading.Thread", SyncThread)

    eng._save_offer_shot(RECT)

    files = sorted((tmp_path / "shots").glob("offer_*.jpg"))
    assert len(files) == 1 and grabs == [False]

    for i in range(eng.SHOTS_KEEP - 1):       # 已存满上限：不再截屏
        (tmp_path / "shots" / f"offer_20260101_00000{i}.jpg").write_bytes(b"x")
    grabs.clear()
    eng._save_offer_shot(RECT)
    assert grabs == []
    assert len(list((tmp_path / "shots").glob("offer_*.jpg"))) == eng.SHOTS_KEEP
