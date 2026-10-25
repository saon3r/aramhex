"""验收探针：实机截图 → 真实 OCR/匹配 → 真实引擎评估 → 真实浮窗绘制三张标签。

只给两样东西：`tests/fixtures/real-mayhem-augment-screen.png` 的像素，和一份本地种子
`PublicStore`（不联网、不下载）。识别、名字匹配、评分、绘制全部走产品代码，不换 OCR、
不伪造 Offer、不改写评估结果。

环境约束（测试自己保证，不依赖开发机）：
- `ARAMHEX_HOME` 由 tests/conftest.py 的 autouse fixture 指到本次临时目录，设置只写在那里；
- `no_network` 把 HTTP 全部堵死，本文件再加一层 socket 守卫，记录任何外连尝试；
- 不需要真实游戏窗口：绘制矩形直接按截图的物理像素给（`window.Rect`），
  所以本文件**不构成** Live GUI 验收，只验证像素→识别→评估→绘制这条链路。
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import cv2
import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real-mayhem-augment-screen.png"
# 截图里三张卡的顺序（左→中→右），英文名由 i18n.json 的 en_US 表提供：
# 2016 Juiced / 2138 Adaptive Ward / 2088 Snowday
EXPECTED_IDS = ["2016", "2138", "2088"]
# 非零原点：标签是屏幕物理像素坐标，偏移必须原样带到登记表里
ORIGIN = (640, 180)


@pytest.fixture
def connect_attempts(monkeypatch):
    """在创建任何产品对象之前堵死外连；有尝试就记下来，最后断言一次也没有。"""

    attempts: list[str] = []

    def deny(*args, **kwargs):
        attempts.append(repr(args[:1] or kwargs)[:160])
        raise AssertionError("验收测试不应发起任何网络连接")

    # connect(self, address)；create_connection(address, ...)：第一个位置参数都是目标地址
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    return attempts


def test_fixture_offline_three_badges(connect_attempts, store, no_network, tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from lolhex.config import Settings, app_home
    from lolhex.engine import Engine
    from lolhex.recommend import win_text
    from lolhex.ui.overlay import BadgeLayer
    from lolhex.vision import window
    from lolhex.vision.detector import AugmentDetector

    app = QApplication.instance() or QApplication([])

    home = tmp_path / "home"
    home.mkdir()  # 校准文件写在 home 下，目录必须先存在

    # ---------- 截图与设置：英文客户端默认值，设置只落到临时 ARAMHEX_HOME ----------
    frame = cv2.imread(str(FIXTURE), cv2.IMREAD_COLOR)
    assert frame is not None and frame.ndim == 3
    height, width = frame.shape[:2]
    assert width > 0 and height > 0

    settings = Settings()
    assert settings.game_lang == "en_US"      # 英文匹配表；中文默认会一条都认不出
    assert settings.save()
    assert str(app_home()).startswith(str(tmp_path))   # 没写到开发机的 config.json

    engine = Engine(settings, home=home, store=store)
    assert engine.store is store and store.dataset is not None   # 有本地统计数据，但没有联网

    # ---------- 真实识别：整块扫描截图（引擎自己也是这么建检测器的） ----------
    detector = AugmentDetector(engine._augment_matcher(), home / "calibration.json",
                               rarities={aid: a.get("rarity") for aid, a in store.augments.items()})
    detector.ensure_calibration(width, height)
    rect = window.Rect(ORIGIN[0], ORIGIN[1], width, height)
    offer = detector.scan_full(frame, (rect.left, rect.top))
    assert offer is not None, "截图里没识别出三选一"
    assert offer.slots == EXPECTED_IDS
    assert offer.matched() == 3 and offer.padded and offer.source == "full"
    assert detector.confirmed_for(width, height)   # 三张齐全即完成本机校准

    # 标题框必须都在窗口内、左右分开（绘制和判断都以这组框为准）
    boxes = offer.boxes
    assert len(boxes) == 3 and all(boxes)
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        assert rect.left <= x0 < x1 <= rect.right
        assert rect.top <= y0 < y1 <= rect.bottom
        if i:
            assert boxes[i - 1][2] < x0

    # ---------- 真实评估：走引擎自己的发布路径 ----------
    engine._set(phase="ingame")
    engine._on_offer(offer)
    snap = engine.snapshot()
    assert snap["phase"] == "ingame" and snap["hero_id"] is None   # 没选英雄：口径只能按 all champs
    assert snap["offer"]["boxes"] == boxes
    ev = snap["evaluation"]
    assert ev and [s["augment_id"] for s in ev["slots"]] == EXPECTED_IDS

    # 数据口径诚实：官方层级已移除；有分数才给胜率，没数据写 ?，全英雄口径写明 all champs
    for row in ev["slots"]:
        assert "tier" not in row
        if row["score"] is None:
            assert row["verdict"] == "nodata"
            assert win_text(row) == "?"
        else:
            assert row["verdict"] in {"best", "ok", "reroll"}
            assert row["basis"] in {"hero_win", "global_win", "pbe"}
            if row["basis"] == "global_win":
                assert win_text(row).startswith("all champs")
    if ev["best_index"] is not None:
        scores = [s["score"] for s in ev["slots"] if s["score"] is not None]
        assert ev["slots"][ev["best_index"]]["score"] == max(scores)

    # ---------- 真实绘制：只隔离本次绘制的登记表（模块级副作用），不动别的产品状态 ----------
    monkeypatch.setattr(window, "_drawn", {})
    layer = BadgeLayer()
    try:
        layer.update_from(snap, rect)
        canvas = QImage(width, height, QImage.Format_ARGB32)
        canvas.fill(0)
        layer.render(canvas)
        drawn = window.drawn_rects()
    finally:
        layer.close()
        app.processEvents()

    assert len(drawn) == 3, f"应画三张标签，实际 {len(drawn)} 张"
    order = sorted(drawn, key=lambda r: r.left)
    for r in order:
        assert r.width > 0 and r.height > 0
        assert rect.left - 8 <= r.left and r.right <= rect.right + 8
        assert rect.top - 8 <= r.top and r.bottom <= rect.bottom + 8
    for a, b in zip(order, order[1:]):
        assert a.right <= b.left
    for r, (x0, y0, x1, y1) in zip(order, boxes):
        cx = (x0 + x1) / 2
        assert abs((r.left + r.width / 2) - cx) <= 4          # 每张标签对着各自那一列
        assert r.top < y0                                     # 在标题上方
        # 只用到校准框上侧的留白（(y1-y0)*2/9），不压标题文字
        assert r.bottom <= y0 + (y1 - y0) * 2 / 9 + 4

    assert connect_attempts == []   # 全程没有任何外连尝试：系统 OCR 引擎，本地模型也不用下载
