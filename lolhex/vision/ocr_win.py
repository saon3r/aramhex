"""Windows.Media.Ocr 后端：用系统自带的识别引擎，不再打包 ONNX 模型。

和 RapidOCR 后端（vision/ocr.py）暴露同样的两个方法，`TextLine` 也是同一个结构，所以
检测器和选人界面不用改。差别只在这里：

- 识别是 WinRT 异步 API：用完成回调 + 线程事件等它结束，**不用 asyncio**。
  asyncio 在 Windows 上会给每个事件循环建一个 loopback socketpair，会被「验收测试禁止
  任何 socket 连接」的守卫判成联网，也会让隐私审计多出无谓的疑点；
- 图片直接按 raw BGRA 交给 SoftwareBitmap，不编码 PNG、不落临时文件；
- 系统引擎不返回置信度：识别出文字记 1.0，没识别记 0.0（调用方只用它做日志和展示，
  匹配阈值是另一套模糊匹配分）；
- 行框取该行所有单词框的并集。`words[0]` 只是第一个词的框，直接拿来当行框会让
  `pick_my_hero` 的「字号最大的是自己」判断拿到单个词的高度，可能判反。
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from .ocr import TextLine

log = logging.getLogger(__name__)

# 一次识别最多等这么久；真实耗时：标题条约 1-3ms，整帧 4K 约 130ms。
TIMEOUT_S = 5.0

# 游戏客户端语言 → Windows 识别器语言标签，按顺序试（Windows 按语言包安装）。
LANG_TAGS = {
    "en_US": ("en-US", "en-GB"),
    "zh_CN": ("zh-CN", "zh-Hans-CN", "zh-Hans"),
    "ja_JP": ("ja-JP", "ja"),
    "ko_KR": ("ko-KR", "ko"),
}


class OcrUnavailable(RuntimeError):
    """这台机器没有可用的 Windows OCR 引擎（缺语言包等）。"""


def available_languages() -> list[str]:
    from winrt.windows.media.ocr import OcrEngine

    return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]


class WinOCR:
    """和 vision.ocr.OCR 同接口：detect(图) / recognize(图)。"""

    def __init__(self, game_lang: str = "en_US"):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        engine = None
        tags = LANG_TAGS.get(game_lang or "", ())
        for tag in tags:
            try:
                engine = OcrEngine.try_create_from_language(Language(tag))
            except OSError:      # 语言标签不合法 / 未安装
                engine = None
            if engine is not None:
                break
        if engine is None:
            # 客户端语言的包没装：用系统里已有的那个（至少英文名字还能认）
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise OcrUnavailable(
                f"no Windows OCR recognizer for {game_lang!r}; installed: {available_languages()}")
        self._engine = engine
        self._lock = threading.Lock()
        self.language = engine.recognizer_language.language_tag

    # ---------- WinRT 异步 → 同步 ----------
    @staticmethod
    def _wait(op, timeout: float = TIMEOUT_S):
        """等一次 WinRT 异步操作结束：完成回调置事件，不用事件循环。

        操作可能在设回调之前就已经完成，WinRT 保证此时回调会立即调用；保险起见先看 status。
        """
        done = threading.Event()

        def on_done(operation, status):
            done.set()

        op.completed = on_done
        if op.status != 1 and not done.wait(timeout):   # 1 = Completed
            op.cancel()
            raise TimeoutError(f"Windows OCR did not finish within {timeout:.0f}s")
        return op.get_results()

    @staticmethod
    def _bitmap(img: np.ndarray):
        from winrt.windows.graphics.imaging import (BitmapAlphaMode, BitmapPixelFormat,
                                                    SoftwareBitmap)
        from winrt.windows.security.cryptography import CryptographicBuffer

        img = np.ascontiguousarray(img)
        if img.ndim == 2:
            # 灰度：三个通道同值、alpha 满。直接把灰度值当 alpha 会变成半透明，认不出来
            bgra = np.empty((img.shape[0], img.shape[1], 4), dtype=np.uint8)
            bgra[:, :, 0] = img
            bgra[:, :, 1] = img
            bgra[:, :, 2] = img
            bgra[:, :, 3] = 255
        elif img.shape[2] == 3:
            bgra = np.empty((img.shape[0], img.shape[1], 4), dtype=np.uint8)
            bgra[:, :, :3] = img
            bgra[:, :, 3] = 255
        elif img.shape[2] == 4:
            bgra = img
        else:
            raise ValueError(f"unsupported image shape {img.shape}")
        bgra = np.ascontiguousarray(bgra, dtype=np.uint8)
        return SoftwareBitmap.create_copy_from_buffer(
            CryptographicBuffer.create_from_byte_array(bgra.tobytes()),
            BitmapPixelFormat.BGRA8, bgra.shape[1], bgra.shape[0],
            BitmapAlphaMode.PREMULTIPLIED)

    # ---------- 接口 ----------
    def detect(self, img: np.ndarray) -> list[TextLine]:
        if img is None or getattr(img, "size", 0) == 0:
            return []
        height, width = img.shape[:2]
        if height < 2 or width < 2:
            return []
        with self._lock:
            result = self._wait(self._engine.recognize_async(self._bitmap(img)))
        lines: list[TextLine] = []
        for line in result.lines:
            text = str(line.text or "").strip()
            rects = [w.bounding_rect for w in line.words]
            if not text or not rects:
                continue
            x0 = int(min(r.x for r in rects))
            y0 = int(min(r.y for r in rects))
            x1 = int(max(r.x + r.width for r in rects))
            y1 = int(max(r.y + r.height for r in rects))
            lines.append(TextLine(text, 1.0, (x0, y0, x1, y1)))
        return lines

    def recognize(self, img: np.ndarray) -> tuple[str, float]:
        """一块图里的文字：取字号最大的那一行。

        卡片标题条里除标题还有类别标签（General / Resilience / Utility），标题字号更大，
        所以按行高挑；同样高的取更长的那行。
        """
        lines = self.detect(img)
        if not lines:
            return "", 0.0
        best = max(lines, key=lambda ln: (ln.h, len(ln.text)))
        return best.text, best.score
