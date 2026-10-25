"""便携版目录里的 portable.txt 是给玩家看的英文说明：本 fork 的发布页、手动替换、没有自动更新。

build.ps1 用单引号 here-string 写这个文件，测试直接从脚本里取出来读，避免另抄一份文案。
"""

import re
from pathlib import Path

BUILD = Path(__file__).resolve().parent.parent / "packaging" / "build.ps1"
FORK_RELEASES = "https://github.com/saon3r/aramhex/releases"
CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")


def _portable_text() -> str:
    src = BUILD.read_text(encoding="utf-8-sig")
    m = re.search(r"Set-Content -LiteralPath \(Join-Path \$stage 'portable\.txt'\)"
                  r".*?-Value @'\r?\n(.*?)\r?\n'@", src, re.S)
    assert m, "build.ps1 里找不到写 portable.txt 的那段"
    return m.group(1)


def test_portable_text_is_english_ascii():
    text = _portable_text()
    assert text.strip() and not CJK.search(text)
    assert text.isascii()  # PowerShell 5.1 的编码坑：非 ASCII 会变问号
    assert "$" not in text  # 单引号 here-string 不展开变量，别让人以为会


def test_portable_text_points_at_this_fork_releases():
    text = _portable_text()
    assert FORK_RELEASES in text
    assert "czgreat" not in text  # 上游仓库地址：这里下载不到这次的便携版


def test_portable_text_says_updates_are_manual():
    low = _portable_text().lower()
    assert "no automatic update" in low or "no auto-update" in low
    assert "download" in low and "replace" in low
    assert "userdata" in low and "uninstall" in low


def test_build_script_keeps_its_utf8_bom():
    """PowerShell 5.1 读没有 BOM 的脚本会用 ANSI 解码，中文注释直接解析失败。"""
    assert BUILD.read_bytes().startswith(b"\xef\xbb\xbf")
