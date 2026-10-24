"""发布流程不再依赖已删除的自动更新模块，但正常的打包/发布步骤仍在。"""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_has_no_removed_updater_or_patch_step():
    text = _text()
    for token in ("lolhex.patch", "lolhex.update", "python -m lolhex.patch",
                  "build/updates", "updates-v", "purge.jsdelivr.net"):
        assert token not in text, token


def test_release_workflow_keeps_normal_packaging_and_release():
    text = _text()
    for token in ("python -m pytest -q", "packaging/build.ps1",
                  "scripts/release_notes.py", "gh release create"):
        assert token in text, token
    assert "python scripts/update_data.py" in text  # 发布时更新内置统计数据是保留的发布步骤
