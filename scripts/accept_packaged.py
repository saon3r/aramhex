r"""Packaged-app acceptance: run the frozen build with no Python on PATH.

用法（仓库根目录，先跑 `packaging/build.ps1 -PortableOnly`）：

    .venv\Scripts\python.exe scripts\accept_packaged.py

默认用 %%TEMP%%\opencode\aramhex-m2-acceptance\warm-home 当暖缓存；可用环境变量
ARAMHEX_ACCEPT_HOME 指到别的目录。

Checks, in order:
  1. the self-test inside the frozen app (Qt, OCR, English chrome, fixture -> 3 badges,
     and that every loaded lolhex module came from the install directory, not the repo);
  2. a warmed-cache start with updates disabled: stays up, opens no TCP connections;
  3. a start that is meant to fail: the English crash dialog appears, then is closed;
  4. a start with a client language whose recognizer pack is missing: the log says so.

The app is launched with PATH reduced to System32/Windows so nothing can silently fall back
to the venv or the source tree.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "build" / "dist" / "AramHex"
EXE = DIST / "AramHex.exe"
FIXTURE = REPO / "tests" / "fixtures" / "real-mayhem-augment-screen.png"
WORK = Path(os.environ["TEMP"]) / "opencode" / "packaged-accept" / time.strftime("%Y%m%d-%H%M%S")
SOURCE_HOME = Path(os.environ.get("ARAMHEX_ACCEPT_HOME") or (Path(os.environ["TEMP"]) / "opencode" / "aramhex-m2-acceptance" / "warm-home"))

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def clean_env(home: Path) -> dict:
    return {
        "PATH": r"C:\Windows\System32;C:\Windows",
        "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
        "TEMP": os.environ.get("TEMP", r"C:\Windows\Temp"),
        "TMP": os.environ.get("TMP", r"C:\Windows\Temp"),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        # 真实启动环境一定有这些；缺了 getpass.getuser() 会抛（应用现在也能兜住，但验收要贴近现实）
        "USERNAME": os.environ.get("USERNAME", ""),
        "USERDOMAIN": os.environ.get("USERDOMAIN", ""),
        "COMPUTERNAME": os.environ.get("COMPUTERNAME", ""),
        "PROCESSOR_ARCHITECTURE": os.environ.get("PROCESSOR_ARCHITECTURE", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "ARAMHEX_HOME": str(home),
        "LANG": "en_GB.UTF-8",
    }


def warmed_home(name: str, *, disable_updates: bool = True, game_lang: str | None = None) -> Path:
    home = WORK / name
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    if SOURCE_HOME.exists():
        for item in ("config.json", "data"):
            src = SOURCE_HOME / item
            if src.is_dir():
                shutil.copytree(src, home / item)
            elif src.exists():
                shutil.copy2(src, home / item)
    cfg_path = home / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    if disable_updates:
        cfg["check_data_updates"] = False
        cfg["refresh_hours"] = 999.0
    if game_lang:
        cfg["game_lang"] = game_lang
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return home


def tcp_connections(pid: int) -> list:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-NetTCPConnection -OwningProcess {pid} -ErrorAction SilentlyContinue "
                          f"| Select-Object -ExpandProperty State"],
                         capture_output=True, text=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def run_and_wait(exe: Path, args: list[str], env: dict, seconds: float) -> subprocess.Popen:
    proc = subprocess.Popen([str(exe), *args], env=env, cwd=str(exe.parent),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(seconds)
    return proc


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def find_dialog(timeout: float = 20.0) -> tuple[int, str, str] | None:
    """找 AramHex 的模态对话框，返回 (hwnd, title, text)。"""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value
        if "AramHex" not in title:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        text = ""
        # 对话框里的正文是子 STATIC 控件
        child = user32.GetWindow(hwnd, 5)  # GW_CHILD
        while child:
            cbuf = ctypes.create_unicode_buffer(2048)
            user32.GetWindowTextW(child, cbuf, 2048)
            if len(cbuf.value) > len(text):
                text = cbuf.value
            child = user32.GetWindow(child, 2)  # GW_HWNDNEXT
        found.append((hwnd, title, text or cls.value))
        return True

    deadline = time.time() + timeout
    while time.time() < deadline and not found:
        user32.EnumWindows(cb, 0)
        if not found:
            time.sleep(0.5)
    return found[0] if found else None


def main() -> int:
    print(f"build: {EXE}", flush=True)
    if not EXE.is_file():
        record("frozen build exists", False, str(EXE))
        return 1
    size_mb = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1e6
    record("frozen build exists", True, f"{size_mb:.0f} MB one-folder at {DIST}")

    # ---- 1. self-test inside the frozen app, with the fixture ----
    home = warmed_home("selftest")
    report_path = WORK / "selftest.json"
    env = clean_env(home)
    proc = subprocess.run([str(EXE), "--self-test-gui", str(report_path), "--self-test-fixture", str(FIXTURE)],
                          env=env, cwd=str(EXE.parent), capture_output=True, text=True, timeout=300)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    (WORK / "selftest-exit.txt").write_text(f"exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}", encoding="utf-8")
    ok = proc.returncode == 0 and report.get("success") is True
    record("self-test passes in the frozen app", ok, f"exit {proc.returncode}")
    record("runs frozen", report.get("frozen") is True, repr(report.get("frozen")))
    record("package lives inside the install dir", report.get("package_inside_install") is True,
           report.get("package_dir", ""))
    outside = report.get("modules_outside_install") or []
    record("no module loaded from outside the install", outside == [], str(outside[:4]))
    record("no python.exe on PATH", report.get("path_has_python") is False, repr(report.get("path_has_python")))
    record("interpreter is the packaged exe", Path(str(report.get("python_exe", ""))).name.lower() == "aramhex.exe",
           str(report.get("python_exe")))
    record("OCR works", report.get("ocr_ok") is True, str(report.get("ocr_text")))
    record("UI chrome is English", report.get("chrome_ok") is True and not report.get("chrome_cjk"),
           str(report.get("chrome_texts")))
    record("fixture reads three cards", report.get("ids") == ["2016", "2138", "2088"], str(report.get("ids")))
    record("three badges render", report.get("badges") == 3 and report.get("fixture_ok") is True,
           f"badges={report.get('badges')} inside={report.get('badges_inside')} ordered={report.get('badges_ordered')}")

    # ---- 2. warmed-cache start, updates disabled: no network use ----
    home = warmed_home("warm")
    proc = run_and_wait(EXE, [], clean_env(home), 18)
    alive = proc.poll() is None
    connections = tcp_connections(proc.pid) if alive else []
    log = home / "aramhex.log"
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    record("warmed start stays up", alive, f"pid {proc.pid}")
    record("warmed start opens no TCP connections", connections == [], str(connections))
    record("warmed start logs the OCR engine", "Windows.Media.Ocr" in log_text)
    # 英雄头像库是从缓存的 static.json 建的：173 个就说明缓存数据集读到了（应用不打印 dataset= 行）
    record("warmed start reads the cached dataset", "173" in log_text, "icon bank from cached static.json")
    if alive:
        (WORK / "warm-log.txt").write_text(log_text[-4000:], encoding="utf-8")
    stop(proc)

    # ---- 3. a start that must fail: English crash dialog ----
    broken = WORK / "not-a-directory"
    broken.write_text("x", encoding="utf-8")          # ARAMHEX_HOME 指向文件：启动必然抛
    proc = run_and_wait(EXE, [], clean_env(broken), 6)
    dialog = find_dialog(20)
    if dialog:
        hwnd, title, text = dialog
        record("crash dialog appears", True, f"title={title!r}")
        english = not any("\u4e00" <= ch <= "\u9fff" for ch in (title + text))
        record("crash dialog is English", english, text.replace("\r\n", " ")[:160])
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
        time.sleep(1)
    else:
        record("crash dialog appears", False, "no dialog window found")
    stop(proc)

    # ---- 4. missing recognizer pack ----
    home = warmed_home("zh-without-pack", game_lang="zh_CN")
    proc = run_and_wait(EXE, [], clean_env(home), 15)
    log = home / "aramhex.log"
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    said = "no Windows OCR recognizer" in log_text or "Windows OCR 用不了" in log_text
    record("missing recognizer is reported", said,
           next((ln for ln in log_text.splitlines() if "recognizer" in ln or "用不了" in ln), "no log line"))
    stop(proc)

    print("\n=== summary ===", flush=True)
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{len(results) - len(failed)}/{len(results)} passed; artefacts in {WORK}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
