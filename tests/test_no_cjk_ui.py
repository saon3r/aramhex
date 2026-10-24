"""界面里的中文字面量闸门：lolhex/ui/*.py 里除了真正的文档字符串，不许出现中文常量。

只跳过模块/类/函数真正的 docstring（按节点身份判断）；注释本来就不是常量，自然不算。
日志调用、整个文件都不豁免；全绿之前不许 xfail/skip —— 每个模块一份真实红。

后面按模块转换的人可以只跑自己那个模块：

    $env:QT_QPA_PLATFORM = 'offscreen'
    .venv\\Scripts\\python.exe -m pytest tests/test_no_cjk_ui.py -k mainwindow
    .venv\\Scripts\\python.exe -m pytest tests/test_no_cjk_ui.py -k overlay

`-k <模块名>` 选中该模块的用例；不带 -k 就是整个界面的闸门（要等所有 UI 模块转换完才绿）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import lolhex.ui

UI_DIR = Path(lolhex.ui.__file__).resolve().parent
UI_FILES = sorted(UI_DIR.glob("*.py"))
MODULE_IDS = [p.stem for p in UI_FILES]

# 常见的 CJK 区段，外加全角标点（，；：（）「」、）和表意空格 U+3000：
# 这些同样是「中文界面」的痕迹，不能只盯汉字。
CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")


def docstring_ids(tree: ast.AST) -> set[int]:
    """真正的模块/类/函数 docstring 的字符串常量节点 id。"""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            found.add(id(first.value))
    return found


def cjk_literals(source: str, filename: str = "<test>") -> list[tuple[int, str]]:
    """源码里带中文的字符串常量：[(行号, 值)]。f-string 的每段字面量都算。"""
    tree = ast.parse(source, filename=filename)
    skip = docstring_ids(tree)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in skip and CJK.search(node.value)):
            hits.append((node.lineno, node.value))
    return sorted(hits)


# ---------- 扫描器自己的单测：先证明它不瞎也不乱咬 ----------

def test_scanner_ignores_module_class_and_function_docstrings():
    source = (
        '"""模块说明：中文。"""\n'
        "class A:\n"
        '    """类说明：中文。"""\n'
        "    def f(self):\n"
        '        """函数说明：中文。"""\n'
        "        return 1\n"
    )
    assert cjk_literals(source) == []


def test_scanner_ignores_comments():
    assert cjk_literals("# 中文注释\nx = 'ok'\n") == []


def test_scanner_catches_plain_and_fstring_fragments():
    source = (
        'a = "首选"\n'
        'b = f"胜率 {1}%"\n'
        'c = "abc" "候选："\n'
    )
    hits = cjk_literals(source)
    values = [v for _, v in hits]
    assert "首选" in values
    assert any("胜率" in v for v in values)          # f-string 里的字面量段
    assert any(v.endswith("候选：") for v in values)  # 隐式拼接：编译期已合成一个常量
    assert len(hits) == 3


def test_scanner_catches_nested_functions_and_fullwidth_punctuation():
    source = (
        "def outer():\n"
        "    def inner():\n"
        '        return "（你：）"\n'
        "    return inner\n"
    )
    assert [v for _, v in cjk_literals(source)] == ["（你：）"]


def test_scanner_allows_ascii_and_non_cjk_unicode():
    source = 'a = "—"\nb = "café"\nc = "首选"\n'
    assert [v for _, v in cjk_literals(source)] == ["首选"]


def test_scanner_ignores_bytes_constants():
    assert cjk_literals('a = b"\\xe4\\xb8\\xad"\nb = 1\n') == []


# ---------- 真闸门 ----------

def test_gate_covers_every_ui_module():
    assert len(UI_FILES) >= 10
    assert {"__init__", "autoshot", "badgepos", "buildview", "data_status", "herosearch",
            "mainwindow", "overlay"} <= set(MODULE_IDS)


@pytest.mark.parametrize("path", UI_FILES, ids=MODULE_IDS)
def test_ui_module_has_no_cjk_string_literals(path: Path):
    hits = cjk_literals(path.read_text(encoding="utf-8"), str(path))
    if hits:
        detail = "; ".join(f"line {line}: {value!r}" for line, value in hits)
        pytest.fail(f"{path.name}: {len(hits)} CJK string literal(s) left -> {detail}")
