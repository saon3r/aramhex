"""Runtime fallback files must also be available in a frozen build."""

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["static_fallback.json", "messages.json"])
def test_runtime_metadata_resource_is_packaged(name):
    root = Path(__file__).resolve().parents[1]
    spec = root / "packaging" / "lolhex.spec"
    tree = ast.parse(spec.read_text(encoding="utf-8"))
    resources = {
        tuple(item.value for item in node.elts)
        for statement in tree.body
        if isinstance(statement, ast.AugAssign)
        and isinstance(statement.target, ast.Name)
        and statement.target.id == "datas"
        and isinstance(statement.value, ast.List)
        for node in statement.value.elts
        if isinstance(node, ast.Tuple)
        and len(node.elts) == 2
        and all(isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in node.elts)
    }
    resource = (f"../lolhex/data/{name}", "lolhex/data")
    assert (spec.parent / resource[0]).is_file()
    assert resource in resources
