"""海克斯三选一画面的识别与低负载跟踪。

怎么判定"现在要选海克斯"：不依赖固定坐标，而是看画面里是否同时出现
≥2 个能匹配到海克斯字典的文字，且它们在同一水平线上、左右排开。

负载控制分三级：
1. 未校准：每 bootstrap_interval 秒截取画面中部，缩小后做一次"检测+识别"（单线程约 1 秒）。
   一旦完整识别到三张，就记住三个标题的位置（按窗口比例保存，换分辨率自动失效）。
2. 已校准：每 scan_interval 只截三个标题所在的一条窄带；先算缩略图指纹，
   和上次一样就直接复用结果（几乎零开销）；变了才对三个小块做"仅识别"（每块约 20ms）。
3. 已校准但识别不到：说明没在选海克斯，保持第 2 级的轻量检查。
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from .matcher import NameMatcher
from .ocr import TextLine, get_ocr
from .window import Rect

log = logging.getLogger(__name__)

# 未校准时扫描的区域（相对窗口）：三张卡片都在屏幕中部。
BAND = (0.12, 0.10, 0.88, 0.85)  # x0, y0, x1, y1
DETECT_MAX_W = 1600               # 检测前把扫描带归一到这个宽度：放大缩小都做，识别引擎每次都拿到同样的像素
REC_HEIGHT = 48                   # 识别前把标题块缩放到这个高度
# 没有本机校准时先用的默认标题位置：国服 4K（16:9）实机多次校准的结果，按窗口比例。
# 游戏界面按高度缩放、水平居中，其他宽高比按这个规律换算。猜错了也没关系：
# 识别不到就照常整块扫描，扫到三张后换成本机的校准结果。
DEFAULT_BOXES = [(0.2309, 0.3869, 0.3923, 0.4335), (0.4231, 0.3869, 0.5845, 0.4335),
                 (0.6152, 0.3869, 0.7767, 0.4335)]


@dataclass
class Calibration:
    """三个标题框，存为相对窗口的比例坐标 (x0, y0, x1, y1)。guess：默认位置，还没在本机确认过。"""
    boxes: list[tuple[float, float, float, float]]
    size: tuple[int, int]
    guess: bool = False

    @classmethod
    def default(cls, w: int, h: int) -> "Calibration":
        k = (16 / 9) * h / max(1, w)  # 16:9 → 1；更宽的屏幕卡片往中间收
        boxes = [(0.5 + (x0 - 0.5) * k, y0, 0.5 + (x1 - 0.5) * k, y1) for x0, y0, x1, y1 in DEFAULT_BOXES]
        return cls(boxes, (w, h), guess=True)

    def pixel_boxes(self, w: int, h: int) -> list[tuple[int, int, int, int]]:
        return [(int(a * w), int(b * h), int(c * w), int(d * h)) for a, b, c, d in self.boxes]

    def valid(self) -> bool:
        """标题区域必须有限、在客户区内、从左到右且互不重叠；不要求固定间距。

        载入存档、整块扫描的候选定位、写盘前都走这里。故意把类型检查写得很宽：
        calibration.json 是玩家机器上的文件，坏字段只能被判无效，不能抛异常
        （上游 1.1.1 记错过一次 339 px 重叠的 4K 校准，就是没查几何）。
        """
        try:
            if not isinstance(self.size, (tuple, list)) or len(self.size) != 2:
                return False
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) and v > 0 for v in self.size):
                return False
            if not isinstance(self.boxes, (tuple, list)) or len(self.boxes) != 3:
                return False
            width, height = int(self.size[0]), int(self.size[1])
            prev_right = None
            for box in self.boxes:
                if not isinstance(box, (tuple, list)) or len(box) != 4:
                    return False
                if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           and math.isfinite(v) for v in box):
                    return False
                a, b, c, d = (float(v) for v in box)
                if not (0 <= a < c <= 1 and 0 <= b < d <= 1):
                    return False
                # 比例上非空不代表像素上非空：窄窗口里一个极窄的框会截出 0 像素。
                if int(c * width) <= int(a * width) or int(d * height) <= int(b * height):
                    return False
                if prev_right is not None and prev_right > a:
                    return False
                prev_right = c
            return True
        except (TypeError, ValueError, OverflowError):
            return False


@dataclass
class Offer:
    slots: list[str | None]
    texts: list[str]
    scores: list[float]
    boxes: list[tuple[int, int, int, int] | None]  # 屏幕坐标下的标题框
    at: float = field(default_factory=time.time)
    padded: bool = False  # boxes 是否为带上下留白的校准框；原始 OCR 字框不含留白
    source: str = "full"
    observation: int = 0  # 真实 OCR 批次；指纹缓存返回不增加。

    def key(self) -> tuple:
        return tuple(self.slots)

    def matched(self) -> int:
        return sum(1 for s in self.slots if s)


def _resize(img: np.ndarray, scale: float) -> np.ndarray:
    if abs(scale - 1.0) < 1e-3:
        return img
    import cv2
    h, w = img.shape[:2]
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=interp)


def detect_scale(band_width: int) -> float:
    """扫描带 → 送进 OCR 的缩放。固定宽度，放大缩小都做。

    以前这里只缩小（min(1.0, …)）：4K/2560 缩到 1600，1920 送 1459，1600 送 1216，
    1366 送 1039。同一个卡面在每个分辨率下喂给识别引擎的像素都不一样；1366 下实测
    整张卡都认不出来（issue #22）。现在每个分辨率都得到 DETECT_MAX_W 宽。
    """
    return DETECT_MAX_W / max(1, band_width)


def fit_width(img: np.ndarray, width: int) -> np.ndarray:
    """把图缩放到恰好 width 宽（高度按比例）。缩小时用 AREA 防混叠，放大时用 LANCZOS4。

    放大用 LANCZOS4 是量出来的：在一局真实游戏的 14 张有效卡面截图里，CUBIC / LINEAR
    放大都会让 1600×900 那一档偶发少认出卡，LANCZOS4 四档全对。高度用截断而不是四舍
    五入：4K 下和改动前的小数缩放得到完全相同的 1600×887，本机 4K 的识别像素一个字节
    都没变。
    """
    import cv2
    h, w = img.shape[:2]
    if w == width:
        return img
    interp = cv2.INTER_AREA if width < w else cv2.INTER_LANCZOS4
    return cv2.resize(img, (width, max(1, int(h * width / max(1, w)))), interpolation=interp)


def fingerprint(img: np.ndarray) -> np.ndarray:
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return cv2.resize(g, (96, 12), interpolation=cv2.INTER_AREA).astype(np.int16)


def fp_changed(a: np.ndarray | None, b: np.ndarray) -> bool:
    """只换了一张卡时整体均值变化很小，所以看局部：任一格子明显变化就算变了。"""
    if a is None or a.shape != b.shape:
        return True
    d = np.abs(a - b)
    return float(d.max()) > 24 or float(d.mean()) > 3


class AugmentDetector:
    def __init__(self, matcher: NameMatcher, calib_path: Path | None = None, ocr=None,
                 rarities: dict[str, str] | None = None, game_lang: str = "en_US"):
        self.matcher = matcher
        self.calib_path = calib_path
        self._ocr = ocr
        self.game_lang = game_lang
        self.rarities = rarities or {}
        self.calibration: Calibration | None = None
        self._last_fp: np.ndarray | None = None
        self._last_result: Offer | None = None
        self._last_window: Rect | None = None
        self._cells: list[dict | None] = [None] * 3
        self._stable: Offer | None = None
        self._pending: list[dict | None] = [None] * 3
        self._low_match_reads = 0  # 已稳定后，有限次数的真实低识别批次；指纹缓存空值不算。
        self._observation = 0
        # 最近一次真实读数（缓存命中沿用上次的像素结论）：matched 是原始识别到的标题数，
        # 与能不能发布 Offer 无关；engine 用它判断「一个标题都没认出来」。
        self.last_read: dict = {"matched": 0, "fresh": False, "source": None, "observation": 0}
        # 这局花在认字上的次数和时间（秒），对局结束写进日志，玩家说卡的时候看
        # *_cpu 是本线程实际算了多久（单线程推理在调用线程上跑）；比 *_s（墙钟）小很多说明线程在排队等 CPU
        self.cost = {"strip": 0, "strip_s": 0.0, "strip_cpu": 0.0, "strip_ocr": 0,
                     "full": 0, "full_s": 0.0, "full_cpu": 0.0}
        if calib_path and calib_path.exists():
            try:
                d = json.loads(calib_path.read_text(encoding="utf-8"))
                calibration = Calibration([tuple(b) for b in d["boxes"]], tuple(d["size"]))
                if calibration.valid():
                    self.calibration = calibration
                else:
                    # 文件留着供诊断；先用默认位置，等一次有效的整块扫描再替换。
                    log.warning("忽略无效三选一校准：标题区域越界、重叠或顺序错误")
            except (OSError, ValueError, KeyError, TypeError):
                self.calibration = None

    @property
    def ocr(self):
        if self._ocr is None:
            self._ocr = get_ocr(self.game_lang)
        return self._ocr

    def clear_tracking(self) -> None:
        """离开对局时保留定位校准，丢弃上一局标题与待确认读数。"""
        self._last_fp = self._last_result = self._last_window = None
        self._cells = [None]*3
        self._stable = None
        self._pending = [None]*3
        self._low_match_reads = 0

    def set_matcher(self, matcher: NameMatcher) -> None:
        self.matcher = matcher
        self._last_fp = None
        self._cells = [None] * 3
        self._low_match_reads = 0

    def calibrated_for(self, w: int, h: int) -> bool:
        return self.calibration is not None and tuple(self.calibration.size) == (w, h)

    def confirmed_for(self, w: int, h: int) -> bool:
        return self.calibrated_for(w, h) and not self.calibration.guess

    def ensure_calibration(self, w: int, h: int) -> None:
        """这个窗口大小还没校准过：先用默认位置，第一次选海克斯就能走轻量检查。"""
        if not self.calibrated_for(w, h):
            self.calibration = Calibration.default(w, h)
            self._last_fp = None
            self._cells = [None] * 3
            self._stable = None
            self._pending = [None] * 3
            self._low_match_reads = 0

    def reset_calibration(self) -> None:
        self.calibration = None
        self._last_fp = None
        self._cells = [None] * 3
        self._stable = None
        self._pending = [None] * 3
        self._low_match_reads = 0
        if self.calib_path and self.calib_path.exists():
            self.calib_path.unlink()

    def _save_calibration(self) -> None:
        # 写盘前再查一次：任何路径都不该把坏几何留在玩家机器上。
        if self.calib_path and self.calibration and self.calibration.valid():
            self.calib_path.write_text(json.dumps({"boxes": self.calibration.boxes,
                                                   "size": self.calibration.size}), encoding="utf-8")

    # ---------- 1. 全区域扫描 ----------

    def scan_full(self, frame: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Offer | None:
        """frame 为整个游戏客户区。找到 ≥2 张卡返回 Offer；3 张齐全时顺便校准。"""
        t0, c0 = time.perf_counter(), time.thread_time()
        try:
            return self._scan_full(frame, origin)
        finally:
            self.cost["full"] += 1
            self.cost["full_s"] += time.perf_counter() - t0
            self.cost["full_cpu"] += time.thread_time() - c0

    def _scan_full(self, frame: np.ndarray, origin: tuple[int, int]) -> Offer | None:
        H, W = frame.shape[:2]
        if not self.calibrated_for(W, H):
            self._stable = None
            self._pending = [None]*3
        x0, y0, x1, y1 = int(BAND[0] * W), int(BAND[1] * H), int(BAND[2] * W), int(BAND[3] * H)
        band = frame[y0:y1, x0:x1]
        scale = detect_scale(band.shape[1])
        lines = self.ocr.detect(fit_width(band, DETECT_MAX_W))
        hits: list[tuple[TextLine, str, float]] = []
        for ln in lines:
            aid, sc = self.matcher.match(ln.text)
            if aid:
                bx = tuple(int(v / scale) for v in ln.box)
                hits.append((TextLine(ln.text, ln.score, (bx[0] + x0, bx[1] + y0, bx[2] + x0, bx[3] + y0)), aid, sc))
        group = self._pick_row(hits, H)
        # 原始识别计数先记下：即使几何被拒/不足两张，也说明标题文字是认出来的。
        self.last_read = {"matched": len({aid for _, aid, _ in group if aid}),
                          "fresh": True, "source": "full", "observation": self._observation}
        if len(group) < 2:
            return None
        # 同一个海克斯在两处命中不算两张卡（1.1.1 日志里出现过 ['死亡之舞', '', '死亡之舞']）。
        if len({aid for _, aid, _ in group if aid}) < 2:
            now = time.monotonic()
            if now - getattr(self, "_duplicate_rejected_at", float("-inf")) >= 60:
                self._duplicate_rejected_at = now
                log.info("拒绝整块识别：匹配列=%d，但不足两个不同海克斯名", len(group))
            return None
        group.sort(key=lambda t: t[0].cx)
        slots, texts, scores, boxes = self._assign_columns(group, W)
        if len(group) == 3:
            if not self._calibrate(group, W, H):
                return None  # 不发布错误位置，也不污染已确认的校准。
            boxes = self.calibration.pixel_boxes(W, H)
        else:
            # 整块扫描已经看到卡片，旧条带的空缓存不能遮住这次恢复。
            self._last_fp = self._last_result = self._last_window = None
            self._cells = [None] * 3
        self._low_match_reads = 0
        ox, oy = origin
        sboxes = [None if b is None else (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy) for b in boxes]
        self._observation += 1
        offer = Offer(slots, texts, scores, sboxes, padded=len(group) == 3,
                      source="full", observation=self._observation)
        offer = self._stabilize(offer, [True]*3)
        log.debug("海克斯OCR source=full observation=%d raw=%r matches=%r scores=%r",
                  offer.observation, texts, slots, scores)
        return offer

    @staticmethod
    def _pick_row(hits, H):
        """同一水平线上、横向分开的匹配项；一张卡只取分数最高的一条。"""
        best: list = []
        for ln, _, _ in hits:
            row = [t for t in hits if abs(t[0].cy - ln.cy) < 0.03 * H]
            # 同一张卡上可能匹配到多行（标题 + 描述里提到别的海克斯名），按横向距离去重。
            # 同名（同一 aid）在两处命中时只留分数最高的一条：它不该挤掉真正的中卡。
            row.sort(key=lambda t: -t[2])
            uniq: list = []
            for t in row:
                if all(abs(t[0].cx - u[0].cx) > 0.08 * H and t[1] != u[1] for u in uniq):
                    uniq.append(t)
            if len(uniq) > len(best):
                best = uniq
        return best[:3]

    @staticmethod
    def _assign_columns(group, W):
        """把识别到的卡片放进左/中/右三个位置。只有两张时按左右对称推断缺的是哪张。"""
        slots: list[str | None] = [None, None, None]
        texts = ["", "", ""]
        scores = [0.0, 0.0, 0.0]
        boxes: list = [None, None, None]
        if len(group) == 3:
            idx = [0, 1, 2]
        else:
            a, b = group[0][0].cx, group[1][0].cx
            mid = W / 2
            gap = b - a
            if abs((a + b) / 2 - mid) < 0.25 * gap:
                idx = [0, 2]          # 左右两张，中间缺
            elif abs(a - mid) < 0.25 * gap:
                idx = [1, 2]          # 中、右
            else:
                idx = [0, 1]          # 左、中
        for i, (ln, aid, sc) in zip(idx, group):
            slots[i], texts[i], scores[i], boxes[i] = aid, ln.text, sc, ln.box
        return slots, texts, scores, boxes

    @staticmethod
    def _calibration_candidate(group, W, H) -> Calibration:
        centers = [t[0].cx for t in group]
        spacing = (centers[2] - centers[0]) / 2
        th = int(np.median([t[0].h for t in group]))
        cy = float(np.median([t[0].cy for t in group]))
        half_w = 0.42 * spacing
        half_h = 0.9 * th
        boxes = [((c - half_w) / W, (cy - half_h) / H, (c + half_w) / W, (cy + half_h) / H) for c in centers]
        return Calibration(boxes, (W, H))

    def _calibrate(self, group, W, H) -> bool:
        candidate = self._calibration_candidate(group, W, H)
        if not candidate.valid():
            # 拒绝时不改 self.calibration、不写盘：旧的有效校准继续用。
            now = time.monotonic()
            if now - getattr(self, "_geometry_rejected_at", float("-inf")) >= 60:
                self._geometry_rejected_at = now
                log.warning("拒绝三选一校准：标题区域越界、重叠或顺序错误 boxes=%s @ %dx%d",
                            candidate.boxes, W, H)
            return False
        self.calibration = candidate
        # 定位框变更后不能用旧条带的近似指纹命中旧坐标。
        self._last_fp = self._last_result = self._last_window = None
        self._cells = [None] * 3
        self._low_match_reads = 0
        self._save_calibration()
        log.info("已校准三选一标题位置：%s @ %dx%d", candidate.boxes, W, H)
        return True

    # ---------- 2. 已校准的轻量检查 ----------

    def strip_rect(self, win: Rect) -> Rect | None:
        """三个标题框的外接矩形（屏幕坐标），只截这一条。"""
        if not self.calibrated_for(win.width, win.height):
            return None
        pb = self.calibration.pixel_boxes(win.width, win.height)
        x0, y0 = min(b[0] for b in pb), min(b[1] for b in pb)
        x1, y1 = max(b[2] for b in pb), max(b[3] for b in pb)
        if self.rarities:
            from .cardframe import frame_strip_bounds
            bounds = frame_strip_bounds(pb, win.height)
            if bounds:
                x0, y0, x1, y1 = bounds
                x0, x1 = max(0, x0), min(win.width, x1)
        return Rect(win.left + x0, win.top + y0, x1 - x0, y1 - y0)

    RECHECK_SECONDS = 5.0
    PENDING_SECONDS = 0.9
    LOW_MATCH_READS = 3  # 已稳定后，最多容忍三个真实低识别批次；之后才算卡片消失。

    def check_strip(self, strip: np.ndarray, win: Rect) -> Offer | None:
        """strip 为 strip_rect 截图。画面没变化时直接复用上次结果（确认失败期间除外）。"""
        fp = fingerprint(strip)
        now = time.monotonic()
        active = self._last_result is not None
        confirming = self._stable is not None and 0 < self._low_match_reads < self.LOW_MATCH_READS
        due = any(c is None for c in self._cells) or (active and any(
            now-c["at"] >= self.RECHECK_SECONDS for c in self._cells))
        if (self._last_window == win and not fp_changed(self._last_fp, fp) and not due
                and not any(self._pending) and not confirming):
            log.debug("海克斯OCR source=cache observation=%d", self._observation)
            return replace(self._last_result, source="cache") if self._last_result else None
        if self._last_window != win:
            self._cells = [None] * 3
            self._low_match_reads = 0
        self._last_fp = fp
        self._last_window = win
        t0, c0 = time.perf_counter(), time.thread_time()
        try:
            return self._read_strip(strip, win)
        finally:
            self.cost["strip"] += 1
            self.cost["strip_s"] += time.perf_counter() - t0
            self.cost["strip_cpu"] += time.thread_time() - c0

    def _read_strip(self, strip: np.ndarray, win: Rect) -> Offer | None:
        pb = self.calibration.pixel_boxes(win.width, win.height)
        region = self.strip_rect(win)
        sx, sy = region.left-win.left, region.top-win.top
        rarities = [None]*3
        if self.rarities:
            from .cardframe import classify_card_frames
            rarities = classify_card_frames(strip, pb, strip_origin=(sx, sy), window_height=win.height)
        slots: list[str | None] = []
        texts, scores, boxes, fresh = [], [], [], []
        now = time.monotonic()
        confirming = self._stable is not None and 0 < self._low_match_reads < self.LOW_MATCH_READS
        for i, (x0, y0, x1, y1) in enumerate(pb):
            crop = strip[y0 - sy:y1 - sy, x0 - sx:x1 - sx]
            fp = fingerprint(crop)
            old = self._cells[i]
            # 确认期间绕开像素缓存，只重读上一批没认出来的列；其余列沿用读数。
            read = (old is None or fp_changed(old["fp"], fp) or self._pending[i] is not None
                    or (self._last_result is not None and now-old["at"] >= self.RECHECK_SECONDS)
                    or (confirming and old is not None and old["aid"] is None))
            if read:
                scale = REC_HEIGHT / max(1, crop.shape[0])
                txt, conf = self.ocr.recognize(_resize(crop, scale))
                aid, sc = self.matcher.match(txt)
                if aid and rarities[i] and self.rarities.get(aid) != rarities[i]:
                    log.debug("海克斯颜色冲突 column=%d observed=%s match=%s", i, rarities[i], aid)
                    aid = None
                self._cells[i] = {"fp": fp, "at": now, "text": txt, "conf": conf, "aid": aid, "score": sc}
                self.cost["strip_ocr"] += 1
                log.debug("海克斯OCR source=strip column=%d raw=%r confidence=%.3f match=%r score=%.1f",
                          i, txt, conf, aid, sc)
            else:
                txt, aid, sc = old["text"], old["aid"], old["score"]
            fresh.append(read)
            slots.append(aid)
            texts.append(txt)
            scores.append(sc)
            boxes.append((win.left + x0, win.top + y0, win.left + x1, win.top + y1))
        if any(fresh):
            self._observation += 1
        offer = Offer(slots, texts, scores, boxes, padded=True, source="strip", observation=self._observation)
        self.last_read = {"matched": offer.matched(), "fresh": any(fresh),
                          "source": "strip", "observation": self._observation}
        if self.calibration.guess and offer.matched() == 3:
            self.calibration.guess = False  # 默认位置在本机对上了，存下来
            self._save_calibration()
        if offer.matched() >= 2:
            if self._low_match_reads:
                log.info("三选一跟踪恢复：低命中新观察=%d 本轮重读=%s", self._low_match_reads, fresh)
            self._low_match_reads = 0
            self._last_result = self._stabilize(offer, fresh)
        else:
            self._last_result = None
            for i, read in enumerate(fresh):
                if read:
                    self._pending[i] = None  # 本轮不可靠读数中断此前的“连续新观察”。
            # 暂不发布旧卡，只保留内部连续状态供短暂失败恢复。引擎仍按 3 次 None 关闭。
            # 确认期间绕过空缓存，仅重读失败列，三次 None 来自三个真实 OCR 批次。
            if self._stable is not None and any(fresh):
                self._low_match_reads += 1
                log.info("三选一跟踪待确认：低命中新观察=%d/%d 本轮重读=%s 命中=%d",
                         self._low_match_reads, self.LOW_MATCH_READS, fresh, offer.matched())
            if self._stable is None or self._low_match_reads >= self.LOW_MATCH_READS:
                self._stable = None
                self._pending = [None] * 3
        return self._last_result

    def _stabilize(self, offer: Offer, fresh: list[bool]) -> Offer:
        """单列只采纳连续的新 OCR 观察，短暂读空不重排整组；不无限保留旧卡。"""
        if self._stable is None:
            self._stable = offer
            return offer
        accepted = list(self._stable.slots)
        now = time.monotonic()
        for i, aid in enumerate(offer.slots):
            if not fresh[i]:
                continue
            if aid == accepted[i]:
                self._pending[i] = None
                continue
            prior = self._pending[i]
            first = prior["first"] if prior else now
            count = prior["count"]+1 if prior and prior["aid"] == aid else 1
            if count >= 2:
                accepted[i] = aid
                self._pending[i] = None
            else:
                self._pending[i] = {"aid": aid, "count": count, "first": first}
                if now-first >= self.PENDING_SECONDS:
                    accepted[i] = None
        stable = replace(offer, slots=accepted)
        log.debug("海克斯确认 observation=%d raw_matches=%r published=%r pending=%r",
                  offer.observation, offer.slots, accepted, [p is not None for p in self._pending])
        self._stable = stable
        return stable

    def card_evidence(self, image: np.ndarray, win: Rect, *, full: bool = False,
                      origin: tuple[int, int] | None = None) -> dict:
        """已有像素的保守三卡面板证据；不认字、不截图、不增加捕获或 OCR。

        strip 模式用标题条截图（origin 为它相对客户区的偏移；省略时按尺寸认回）；
        full 模式自己从整帧里截三张标题需要的那一条。几何未知或像素不符时 cards=0，
        调用方必须把 0 当“不确定”，不能当“没有卡”。matched 是最近一次真实读数。
        """
        from .cardframe import card_presence, frame_strip_bounds
        w, h = int(win.width), int(win.height)
        cal = self.calibration if self.calibrated_for(w, h) else Calibration.default(w, h)
        pb = cal.pixel_boxes(w, h)
        result = {"cards": 0, "labels": [None, None, None],
                  "frame": "full" if full else "strip", "width": w, "height": h,
                  "matched": int(self.last_read.get("matched") or 0)}
        if image is None or getattr(image, "ndim", 0) != 3 or image.shape[2] < 3:
            return result
        bounds = frame_strip_bounds(pb, h)
        if bounds is None:
            return result
        if full:
            x0, y0 = max(0, bounds[0]), max(0, bounds[1])
            x1, y1 = min(image.shape[1], bounds[2]), min(image.shape[0], bounds[3])
            if x1 <= x0 or y1 <= y0:
                return result
            strip, oxy = image[y0:y1, x0:x1], (x0, y0)
        else:
            strip = image
            if origin is None:
                # 标题条是 strip_rect 截出来的：按宽高认回它相对客户区的偏移。
                tight = (min(b[0] for b in pb), min(b[1] for b in pb),
                         max(b[2] for b in pb), max(b[3] for b in pb))
                match = next((b for b in (bounds, tight)
                              if (image.shape[1], image.shape[0]) == (b[2]-b[0], b[3]-b[1])), None)
                if match is None:
                    return result
                oxy = (match[0], match[1])
            else:
                oxy = origin
        labels = card_presence(strip, pb, strip_origin=oxy, window_height=h)
        result["labels"] = list(labels)
        result["cards"] = sum(1 for label in labels if label)
        return result

    def column_of(self, x: int, y: int, win: Rect) -> int | None:
        """屏幕坐标 (x, y) 落在哪张卡的竖列上；用于记录玩家点了哪张。"""
        if not self.calibrated_for(win.width, win.height):
            return None
        pb = self.calibration.pixel_boxes(win.width, win.height)
        spacing = (pb[2][0] - pb[0][0]) / 2
        title_y = (pb[0][1] + pb[0][3]) / 2 + win.top
        if abs(y - title_y) > 0.35 * win.height:
            return None
        for i, b in enumerate(pb):
            cx = (b[0] + b[2]) / 2 + win.left
            if abs(x - cx) < spacing / 2:
                return i
        return None
