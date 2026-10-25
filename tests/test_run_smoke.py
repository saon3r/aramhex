"""启动冒烟测试：overlay.run 能走到事件循环（1.0.8/1.0.9 曾因变量名冲突一启动就崩）。"""
import re

import pytest

pytest.importorskip("PySide6")

CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")


def test_run_starts(tmp_path, monkeypatch):
    monkeypatch.setenv("ARAMHEX_HOME", str(tmp_path))
    from PySide6.QtWidgets import QApplication

    from lolhex.config import Settings
    from lolhex.engine import Engine
    from lolhex.ui import overlay

    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(Engine, "start", lambda self: None)
    s = Settings.load(tmp_path / "config.json")
    s.check_data_updates = False
    assert overlay.run(lambda: Engine(s), minimized=True) == 0


def test_version_notice_once(tmp_path, monkeypatch):
    monkeypatch.setenv("ARAMHEX_HOME", str(tmp_path))
    from lolhex import __version__
    from lolhex.config import Settings
    from lolhex.ui.overlay import version_notice
    s = Settings.load(tmp_path / "config.json")
    assert version_notice(s) is None            # 第一次安装：不提示
    assert version_notice(s) is None            # 同一个版本再开：不提示
    s.last_version = "0.0.1"                    # 模拟刚从旧版本更新上来
    assert version_notice(s) == f"Updated to {__version__}"
    assert version_notice(s) is None            # 只提示一次
    old = tmp_path / "old.json"                 # 老版本留下的设置文件（没有 last_version）
    old.write_text('{"show_winrate": true}', encoding="utf-8")
    assert version_notice(Settings.load(old)) == f"Updated to {__version__}"


def test_launcher_shows_friendly_error(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    import ctypes
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location("launcher", Path(__file__).parent.parent / "packaging" / "launcher.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setenv("ARAMHEX_HOME", str(tmp_path))
    path = launcher._crash_log("Traceback: 测试")
    assert path and "测试" in Path(path).read_text(encoding="utf-8")

    # 崩溃提示只说英文：打包后的窗口不属于 lolhex/ui/*.py，界面闸门管不到它
    seen = {}

    class FakeUser32:
        def MessageBoxW(self, hwnd, msg, title, flags):
            seen.update(msg=msg, title=title, flags=flags)
            return 1

    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=FakeUser32()), raising=False)
    launcher._crash("Traceback: boom")
    assert not CJK.search(seen["msg"]) and not CJK.search(seen["title"])
    assert str(tmp_path) in seen["msg"] and "crash.log" in seen["msg"]   # 说清日志写在哪
    assert "aramhex.com" not in seen["msg"].lower()   # 不引导去上游装另一个程序


def test_blank_capture_warns_once():
    from types import SimpleNamespace
    from lolhex.ui import overlay
    said = []
    ov = SimpleNamespace(visible=True, notify=said.append,
                         engine=SimpleNamespace(snapshot=lambda: {"vision": {"blank": True}}))
    for _ in range(3):
        try:
            overlay.Overlay._tick(ov)
        except AttributeError:
            pass  # 后面画浮窗的部分在这个替身上没有，提醒已经发了
    assert len(said) == 1 and "Borderless" in said[0]
