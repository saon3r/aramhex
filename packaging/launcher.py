"""打包后的程序入口（PyInstaller）。

启动失败时（文件坏了、更新没装完整等）不弹 Python 的 "Unhandled exception"，改成英文提示，
把错误写进 crash.log 方便排查。这里尽量少依赖程序本身，程序坏了也能弹出来。

不引导去上游官网下载安装包：这是个人分支，上游的安装包装的是另一个程序（带遥测），
所以只说清错误写在哪、设置没丢、以及怎么修（从仓库重新打包，见 docs/DEVELOPMENT.md）。
"""

import os
import sys
import time
import traceback

TITLE = "AramHex ARAM Mayhem Companion"
REPAIR_HINT = "Your settings and cached data are kept. To repair the installation, rebuild it from the project repository (see docs/DEVELOPMENT.md)."


def _crash_log(text: str) -> str:
    base = os.environ.get("ARAMHEX_HOME") or os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "AramHex")
    if os.path.isfile(os.path.join(os.path.dirname(sys.executable), "portable.txt")):
        base = os.path.join(os.path.dirname(sys.executable), "userdata")
    try:
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "crash.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{text}\n")
        return path
    except OSError:
        return ""


def _crash(text: str) -> None:
    path = _crash_log(text)
    msg = "AramHex could not start.\n\n"
    msg += f"The error was written to:\n{path}\n\n" if path else "The error could not be written to crash.log.\n\n"
    msg += REPAIR_HINT
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, TITLE, 0x0 | 0x10)  # 确定 + 错误图标
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from lolhex.__main__ import main
        code = main()
    except SystemExit:
        raise
    except BaseException:
        _crash(traceback.format_exc())
        code = 1
    sys.exit(code)
