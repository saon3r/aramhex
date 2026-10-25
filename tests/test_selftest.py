"""打包自检本身要有测试：它一旦坏了，安装包会带着「自检通过」的假象出厂。

跑的是源码里的同一条路径（Qt + OCR + 主界面英文 + 夹具三张标签）；打包后的差异只在
PyInstaller 的收集，另有安装包验收补上。
"""

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "real-mayhem-augment-screen.png"


def test_self_test_reports_gui_ocr_chrome_and_three_badges(store, tmp_path):
    from lolhex import gui_selftest

    report_path = tmp_path / "report.json"
    code = gui_selftest.run(str(report_path), str(FIXTURE))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert code == 0, report
    assert report["success"] is True
    assert report["gui_ok"] and report["ocr_ok"]
    assert report["chrome_ok"] and not report["chrome_cjk"]
    assert not any(CJK.search(text) for text in report["chrome_texts"])
    assert report["ids"] == ["2016", "2138", "2088"]
    assert report["badges"] == 3 and report["badges_inside"] and report["badges_ordered"]
    assert report["fixture_ok"] is True
    assert not CJK.search(report["advice"])


def test_self_test_fails_loudly_without_a_fixture(store, tmp_path):
    from lolhex import gui_selftest

    report_path = tmp_path / "report.json"
    code = gui_selftest.run(str(report_path), str(tmp_path / "missing.png"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 1 and report["success"] is False, report
    assert report.get("fixture_ok") is False, report
    assert report.get("fixture_error") == "fixture not found", report
