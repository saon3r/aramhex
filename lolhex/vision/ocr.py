"""OCR 后端入口：Windows.Media.Ocr（系统自带，离线，不打包任何模型）。

后端只暴露两个方法：

- detect(img) → 文字行列表（每行 text / score / box）；
- recognize(img) → (文字, 分数)，取一块图里字号最大的那一行。

`TextLine` 是调用方共用的数据结构：box 是相对输入图的像素框，`h` 是整行高度
（选人界面靠它判断「名字最大的是自己」）。引擎按界面语言缓存：换语言就是换识别器；
没有对应语言包时抛 `OcrUnavailable`，让调用方记日志并在这一局不显示标签，
而不是拿别的语言的识别器凑出一个错误结果。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


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


_engines: dict[str, object] = {}
_engines_lock = threading.Lock()


def get_ocr(game_lang: str = "en_US"):
    """当前界面语言的 OCR 后端（同一个语言复用同一个引擎）。"""
    key = game_lang or "en_US"
    with _engines_lock:
        inst = _engines.get(key)
        if inst is None:
            from .ocr_win import WinOCR

            inst = WinOCR(key)
            log.info("OCR 引擎：Windows.Media.Ocr（%s）", inst.language)
            _engines[key] = inst
        return inst


def reset_engines() -> None:
    """丢掉缓存的引擎（换语言、或者后来才装上语言包时用）。"""
    with _engines_lock:
        _engines.clear()
