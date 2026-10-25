"""RapidOCR（PaddleOCR 模型的 ONNX 版）封装，离线运行。

两种用法：
- detect(img)：检测+识别，找出画面中所有文字行（单线程约 1 秒，只在少数时候用）；
- recognize(img)：已知文字区域时只做识别（每块约 20ms）。
模型首次使用时加载（约 0.5s），之后常驻。
韩服识别模型下载已移除（use_rec_model 仍保留接口，默认用内置模型）。
Det/Rec/Cls 三个模型固定用安装包内的本地文件（见 _MODEL_FILES）：缺文件/空文件直接报错，
损坏文件由 onnxruntime 拒绝；任何情况下都不会去 modelscope.cn 下载模型。
只用一个线程：onnxruntime 默认把所有核都拉来算，对局中每次认字都会和游戏抢 CPU，玩家会掉帧、卡顿。
单线程总 CPU 少一半，慢一点（标题条约 70ms、整块扫描约 1 秒）不影响使用。

这个模块同时是 OCR 后端的入口：`get_ocr()` 默认用 Windows.Media.Ocr（系统自带，更快更小），
Windows 引擎用不了时退回这里的 RapidOCR。接口只有 detect / recognize 两个方法。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# rapidocr 自带（随安装包发布）的三个 ONNX 模型。名字写死是有意的：升级换代改了默认
# 模型名时，这里找不到文件就本地报错停下，绝不让 rapidocr 去 modelscope.cn 下载。
# PyInstaller 用 collect_data_files("rapidocr") 把它们放在同一个相对路径下。
_MODEL_FILES = {
    "Det": "PP-OCRv6_det_small.onnx",
    "Rec": "PP-OCRv6_rec_small.onnx",
    "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
}


class ModelUnavailableError(RuntimeError):
    """本地 OCR 模型缺失或为空：宁可失败也不联网下载。"""


def _bundled_model_dir() -> Path:
    """rapidocr 包内的 models 目录（从包实际位置解析，不写死 .venv 路径）。"""
    import rapidocr

    return Path(rapidocr.__file__).resolve().parent / "models"


def _bundled_model_paths() -> dict[str, Path]:
    """三个本地模型路径；缺失/空文件在创建引擎之前就报错。"""
    root = _bundled_model_dir()
    paths = {part: root / name for part, name in _MODEL_FILES.items()}
    for part, path in paths.items():
        if not path.is_file():
            raise ModelUnavailableError(f"{part} 模型缺失：{path}（不联网下载，请检查 rapidocr 安装）")
        if path.stat().st_size <= 0:
            raise ModelUnavailableError(f"{part} 模型是空文件：{path}（不联网下载，请检查 rapidocr 安装）")
    return paths


@dataclass
class TextLine:
    text: str
    score: float
    box: tuple[int, int, int, int]  # x0, y0, x1, y1（相对输入图）

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    @property
    def h(self) -> int:
        return self.box[3] - self.box[1]


THREADS = {"EngineConfig.onnxruntime.intra_op_num_threads": 1, "EngineConfig.onnxruntime.inter_op_num_threads": 1}


class OCR:
    _inst = None
    _inst_lock = threading.Lock()
    _rec_model: str | None = None  # 换用的识别模型（韩文）；None 为内置

    def __init__(self, rec_model: str | None = None):
        from rapidocr import RapidOCR
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        params = dict(THREADS)
        # 固定本地模型路径：model_path 非空时 rapidocr 不会走下载分支，缺模型只是报错。
        # 非空但损坏的文件交给 onnxruntime 拒绝（SDK 的 SHA 校验在本地路径下不生效）。
        for part, path in _bundled_model_paths().items():
            params[f"{part}.model_path"] = str(path)
        if rec_model:
            from rapidocr.utils.typings import LangRec, ModelType, OCRVersion
            params.update({"Rec.lang_type": LangRec.KOREAN, "Rec.model_type": ModelType.MOBILE,
                           "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_path": rec_model})
        self._engine = RapidOCR(params=params)
        self.rec_model = rec_model
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "OCR":
        with cls._inst_lock:
            if cls._inst is None or cls._inst.rec_model != cls._rec_model:
                cls._inst = cls(cls._rec_model)
            return cls._inst

    @classmethod
    def use_rec_model(cls, path: str | None) -> None:
        """换识别模型（None 换回内置）；下次 get() 时重新加载。"""
        with cls._inst_lock:
            cls._rec_model = str(path) if path else None

    def detect(self, img: np.ndarray) -> list[TextLine]:
        with self._lock:
            r = self._engine(img, use_det=True, use_cls=False, use_rec=True)
        lines = []
        if r is None or getattr(r, "boxes", None) is None or getattr(r, "txts", None) is None:
            return lines
        for box, txt, sc in zip(r.boxes, r.txts, r.scores):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append(TextLine(str(txt), float(sc), (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))))
        return lines

    def recognize(self, img: np.ndarray) -> tuple[str, float]:
        if img.size == 0:
            return "", 0.0
        with self._lock:
            r = self._engine(img, use_det=False, use_cls=False, use_rec=True)
        if r is None or not getattr(r, "txts", None):
            return "", 0.0
        return str(r.txts[0]), float(r.scores[0])


# ---------- OCR 后端选择 ----------

# 默认用系统自带的 Windows.Media.Ocr；ARAMHEX_OCR=rapid 可以强制退回 RapidOCR（对比、排查用）。
ENGINE_ENV = "ARAMHEX_OCR"
_engines: dict[tuple[str, str], object] = {}
_engines_lock = threading.Lock()


def _build_engine(wanted: str, game_lang: str):
    if not wanted.startswith("rapid"):
        try:
            from .ocr_win import WinOCR

            inst = WinOCR(game_lang)
            log.info("OCR 引擎：Windows.Media.Ocr（%s）", inst.language)
            return inst
        except (ImportError, OSError, RuntimeError) as e:
            # OcrUnavailable / 没装 winrt：退回内置模型。其他异常（代码 bug）照常抛出。
            log.warning("Windows OCR 用不了（%s），这次用 RapidOCR", e)
    return OCR.get()


def get_ocr(game_lang: str = "en_US", engine: str | None = None):
    """当前 OCR 后端（同一个语言复用同一个引擎）。

    后端只有两个方法：detect(图) → 文字行列表，recognize(图) → (文字, 分数)。
    """
    wanted = (engine or os.environ.get(ENGINE_ENV) or "win").strip().lower()
    key = (wanted, game_lang or "en_US")
    with _engines_lock:
        inst = _engines.get(key)
        if inst is None:
            inst = _build_engine(wanted, key[1])
            _engines[key] = inst
        return inst


def reset_engines() -> None:
    """丢掉缓存的引擎（换语言、测试换后端时用）。"""
    with _engines_lock:
        _engines.clear()
