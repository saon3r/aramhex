"""OCR 模型策略：只用安装包里自带的本地模型，缺失/为空/损坏都本地报错，绝不联网下载。

rapidocr 的默认配置把 Det/Rec/Cls.model_path 留空，引擎发现模型不存在或哈希不对会直接
用 requests 去 ModelScope 下载，绕开 lolhex 的 HTTP 白名单。这里固定三个模型路径，
把“下载模型”这条路彻底关掉。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from lolhex.vision import ocr as ocr_mod

MODEL_NAMES = {
    "Det": "PP-OCRv6_det_small.onnx",
    "Rec": "PP-OCRv6_rec_small.onnx",
    "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
}


def forbid_downloads(monkeypatch) -> list:
    """记录任何下载/HTTP 尝试；真被调用时还会直接炸掉，测试不会静默通过。"""
    from rapidocr.utils import download_file

    calls: list = []

    def boom(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("模型缺失时不允许联网下载")

    monkeypatch.setattr(download_file.DownloadFile, "run", classmethod(lambda cls, *a, **k: boom(*a, **k)))
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests.Session, "request", boom)
    return calls


def use_model_dir(monkeypatch, path: Path) -> None:
    """把包内模型目录换成临时目录，只动 getter，不给生产构造函数加测试参数。"""
    monkeypatch.setattr(ocr_mod, "_bundled_model_dir", lambda: path)


def test_engine_params_pin_three_local_bundled_models(monkeypatch):
    """引擎拿到的是三个明确的本地文件路径，而不是靠 rapidocr 自己解析/下载。"""
    import rapidocr

    seen = []
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda params=None: seen.append(params) or object())

    ocr_mod.OCR()

    params = seen[0]
    model_root = ocr_mod._bundled_model_dir().resolve()
    assert model_root.is_relative_to(Path(rapidocr.__file__).resolve().parent)
    for part, name in MODEL_NAMES.items():
        path = Path(params[f"{part}.model_path"]).resolve()
        assert path == model_root / name
        assert path.is_file() and path.stat().st_size > 0


def test_rec_model_override_only_replaces_rec_path(monkeypatch):
    """保留现有 use_rec_model/rec_model 接口：只换识别模型，检测/方向模型仍是本地自带。"""
    import rapidocr

    seen = []
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda params=None: seen.append(params) or object())

    ocr_mod.OCR(rec_model="custom.onnx")

    params = seen[0]
    assert params["Rec.model_path"] == "custom.onnx"
    assert Path(params["Det.model_path"]).name == MODEL_NAMES["Det"]
    assert Path(params["Cls.model_path"]).name == MODEL_NAMES["Cls"]


def test_missing_bundled_model_fails_locally_without_download(monkeypatch, tmp_path):
    calls = forbid_downloads(monkeypatch)
    use_model_dir(monkeypatch, tmp_path)
    with pytest.raises(ocr_mod.ModelUnavailableError, match="PP-OCRv6_det_small"):
        ocr_mod.OCR()
    assert calls == []


def test_zero_byte_bundled_model_fails_locally_without_download(monkeypatch, tmp_path):
    for name in MODEL_NAMES.values():
        (tmp_path / name).write_bytes(b"")
    calls = forbid_downloads(monkeypatch)
    use_model_dir(monkeypatch, tmp_path)
    with pytest.raises(ocr_mod.ModelUnavailableError, match="PP-OCRv6_det_small"):
        ocr_mod.OCR()
    assert calls == []


def test_corrupt_local_model_raises_from_runtime_without_download(monkeypatch, tmp_path):
    """非空但内容坏了：本地路径绕过 SDK 的 SHA 校验，交给 onnxruntime 拒绝，也不许下载。"""
    for name in MODEL_NAMES.values():
        (tmp_path / name).write_bytes(b"not an onnx model")

    calls = forbid_downloads(monkeypatch)
    use_model_dir(monkeypatch, tmp_path)

    with pytest.raises(Exception) as caught:
        ocr_mod.OCR()
    assert not isinstance(caught.value, TypeError)  # 确实由 onnxruntime 拒绝，而不是接口参数错误
    assert calls == []


def test_loadable_rec_model_with_damaged_character_metadata_cannot_download(monkeypatch, tmp_path):
    import shutil
    import onnxruntime

    root = ocr_mod._bundled_model_dir()
    for name in MODEL_NAMES.values():
        shutil.copyfile(root / name, tmp_path / name)
    rec = tmp_path / MODEL_NAMES["Rec"]
    original = rec.read_bytes()
    assert b"character" in original
    rec.write_bytes(original.replace(b"character", b"characteX"))
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = onnxruntime.InferenceSession(str(rec), sess_options=options,
                                          providers=["CPUExecutionProvider"])
    assert "character" not in session.get_modelmeta().custom_metadata_map
    use_model_dir(monkeypatch, tmp_path)
    calls = forbid_downloads(monkeypatch)
    # PP-OCRv6 has no fallback dict_url: damaged metadata must fail locally too.
    with pytest.raises(Exception) as caught:
        ocr_mod.OCR()
    assert not isinstance(caught.value, TypeError)
    assert calls == []
