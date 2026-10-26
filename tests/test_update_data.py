"""发版时取最新统计数据：内置数据更新（例如过渡数据）时不能被覆盖。"""
import hashlib
import importlib.util
import json
from pathlib import Path

from conftest import make_dataset

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("update_data", ROOT / "scripts" / "update_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _src(tmp_path, snapshot_at):
    src = tmp_path / "src"
    src.mkdir()
    (src / "latest.json").write_text(json.dumps({"snapshot_at": snapshot_at, "path": "x", "files": {}}), encoding="utf-8")
    return src


def test_manifest_is_deterministic_utf8_lf_and_payloads_untouched(tmp_path, monkeypatch):
    """latest.json 写成 UTF-8 + LF，数据文件字节原样保留。

    bundled/** 在 .gitattributes 里是 -text（保住发布过的 SHA-256），所以用 write_text 写清单会在
    Windows 上生成 CRLF，git diff --check 把每一行都当成行尾空白。清单只能是 LF，且不能顺手改
    数据文件：它们的哈希就是发布出去的那份。
    """
    from lolhex.data.public import Dataset

    mod = _load()
    src = tmp_path / "src"
    src.mkdir()
    source = make_dataset(src)                      # 数据文件用 write_bytes 写，LF
    payload_dir = src / source["path"]
    for name in source["files"]:
        target = payload_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        (src / name).replace(target)

    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(mod, "BUNDLED", bundled)
    assert mod.main(["--from", str(src)]) == 0

    raw = (bundled / "latest.json").read_bytes()
    assert b"\r\n" not in raw, "latest.json must not contain CRLF"
    assert raw.endswith(b"\n")
    for line in raw.split(b"\n")[:-1]:
        assert line == line.rstrip(), f"trailing whitespace in latest.json: {line!r}"
    text = raw.decode("utf-8")                      # 同一份内容的可重现写法
    assert raw == (json.dumps(json.loads(text), ensure_ascii=False, indent=1, sort_keys=True)
                   + "\n").encode("utf-8")

    written = json.loads(text)
    assert sorted(written["files"]) == sorted(source["files"])
    for name, entry in source["files"].items():
        body = (bundled / name).read_bytes()
        assert body == (payload_dir / name).read_bytes(), f"{name} bytes changed"
        assert hashlib.sha256(body).hexdigest() == entry["sha256"], f"{name} hash changed"
        assert written["files"][name]["sha256"] == entry["sha256"]
    assert Dataset(bundled, "bundled").revision    # 换行修好之后仍是一份能校验的数据


def test_keeps_newer_bundled(tmp_path, monkeypatch, capsys):
    mod = _load()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "latest.json").write_text(json.dumps({"snapshot_at": "2026-10-21T12:00:00+08:00"}), encoding="utf-8")
    monkeypatch.setattr(mod, "BUNDLED", bundled)
    monkeypatch.setattr(mod, "check_manifest", lambda m: m)
    assert mod.main(["--from", str(_src(tmp_path, "2026-10-17T18:51:45+08:00"))]) == 0
    assert "不换" in capsys.readouterr().out
    assert json.loads((bundled / "latest.json").read_text(encoding="utf-8"))["snapshot_at"].startswith("2026-10-21")


def test_replaces_older_bundled(tmp_path, monkeypatch):
    mod = _load()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "latest.json").write_text(json.dumps({"snapshot_at": "2026-10-16T09:15:50+08:00"}), encoding="utf-8")
    monkeypatch.setattr(mod, "BUNDLED", bundled)
    monkeypatch.setattr(mod, "check_manifest", lambda m: m)
    monkeypatch.setattr(mod, "Dataset", lambda path, name: type("D", (), {"patch": "16.20", "snapshot_at": "x"})())
    assert mod.main(["--from", str(_src(tmp_path, "2026-10-17T18:51:45+08:00"))]) == 0
    assert json.loads((bundled / "latest.json").read_text(encoding="utf-8"))["snapshot_at"].startswith("2026-10-17")
