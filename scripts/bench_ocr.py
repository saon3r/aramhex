"""测量 OCR 引擎：走检测器真实路径，报耗时并打印每轮读到的卡。

用法（仓库根目录）：

    .venv\\Scripts\\python.exe scripts\\bench_ocr.py
    .venv\\Scripts\\python.exe scripts\\bench_ocr.py --captures <含 *-offer.png 的目录>

默认用 tests/fixtures/real-mayhem-augment-screen.png（2560x1440，随仓库发布、已打码）。
对局截图是 3840x2160，含其他玩家的名字，所以不进仓库；用 --captures 指到本地目录。

每次都打印这一轮认出来的卡（ID 与每列文字），避免「很快但是什么都没认出来」被当成快。
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import cv2

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252 控制台打印中文会崩

from lolhex.vision.detector import AugmentDetector, REC_HEIGHT, _resize  # noqa: E402
from lolhex.vision.matcher import NameMatcher                            # noqa: E402
from lolhex.vision.ocr import get_ocr                                    # noqa: E402
from lolhex.vision import window as winmod                               # noqa: E402
from lolhex import data as data_pkg                                      # noqa: E402


def _matcher() -> NameMatcher:
    """随程序发布的英文海克斯名表（和引擎在 en_US 下用的是同一套）。"""
    from lolhex.data import metadata

    return NameMatcher({aid: metadata.augment_en(aid) for aid in metadata.local_augment_ids()},
                       72.0, min_margin=6.0)


def bench(frame, label: str, rounds: int = 5) -> None:
    h, w = frame.shape[:2]
    matcher = _matcher()
    print(f"\n=== {label}  {w}x{h} ===")
    for name in ("Windows OCR",):
        try:
            backend = get_ocr("en_US")
        except Exception as e:      # 没有对应的识别语言包
            print(f"  {name:12s} 不可用：{e}")
            continue
        det = AugmentDetector(matcher, None, ocr=backend)
        det.ensure_calibration(w, h)
        rect = winmod.Rect(0, 0, w, h)
        region = det.strip_rect(rect)
        strip = frame[region.top:region.bottom, region.left:region.right]

        strip_times, outputs = [], []
        for _ in range(rounds):
            det._cells = [None] * 3      # 每轮强制重新认字，不让指纹缓存短路
            det._stable = None
            det._pending = [None] * 3
            t = time.perf_counter()
            offer = det._read_strip(strip, rect)
            strip_times.append((time.perf_counter() - t) * 1000)
            outputs.append((list(offer.slots) if offer else None,
                            list(offer.texts) if offer else None))

        per_card = []
        pb = det.calibration.pixel_boxes(w, h)
        sx, sy = region.left, region.top
        for x0, y0, x1, y1 in pb:
            crop = strip[y0 - sy:y1 - sy, x0 - sx:x1 - sx]
            scale = REC_HEIGHT / max(1, crop.shape[0])
            backend.recognize(_resize(crop, scale))          # 预热
            t = time.perf_counter()
            backend.recognize(_resize(crop, scale))
            per_card.append((time.perf_counter() - t) * 1000)

        full_times = []
        for _ in range(max(1, rounds // 2)):
            t = time.perf_counter()
            det.scan_full(frame, (rect.left, rect.top))
            full_times.append((time.perf_counter() - t) * 1000)

        read_rounds = [out for out in outputs if out[0]]
        print(f"  {name:12s} 标题条 3 张 中位 {statistics.median(strip_times):7.2f} ms"
              f"（最小 {min(strip_times):.2f}）"
              f" | 单张 中位 {statistics.median(per_card):5.2f} ms"
              f" | 整块扫描 中位 {statistics.median(full_times):7.2f} ms")
        if not read_rounds:
            # 一轮都没认出卡：这个耗时没有意义，必须说出来
            print(f"               ⚠ {rounds} 轮都没认出卡，上面的耗时不可当作识别成功")
            continue
        distinct = {tuple(out[0]) for out in read_rounds}
        print(f"               认出的卡（{len(read_rounds)}/{len(outputs)} 轮）：{sorted(distinct)}")
        print(f"               其中一轮的文字：{read_rounds[0][1]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR 引擎的实测耗时")
    ap.add_argument("--captures", help="含 *-offer.png 的对局截图目录（本地，不入库）")
    ap.add_argument("--rounds", type=int, default=5)
    args = ap.parse_args()

    fixture = REPO / "tests" / "fixtures" / "real-mayhem-augment-screen.png"
    frames = [("fixture", cv2.imread(str(fixture)))]
    if args.captures:
        folder = Path(args.captures)
        found = sorted(folder.glob("*-offer.png"))[:3]
        if not found:
            print(f"⚠ {folder} 里没有 *-offer.png：只测 fixture")
        for path in found:
            frames.append((path.name, cv2.imread(str(path))))
    for label, frame in frames:
        if frame is None:
            print(f"{label}: 读不到图片，跳过")
            continue
        bench(frame, label, args.rounds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
