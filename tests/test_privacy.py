"""隐私回归：不再生成/保存安装编号，不再上报使用情况，统计数据匿名下载，关于页静态署名。"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import make_dataset
from httpfixtures import LocalTransport
from lolhex import __version__, config
from lolhex.config import Settings

RETIRED_MODULES = ("cloud", "cloudsettings", "logupload", "rank", "update", "patch", "langpack")
RETIRED_KEYS = ("install_id", "send_usage", "user_set", "seen_notice", "riot_id", "my_rank",
                "logs_sent", "logs_tries")


def _no_identifier(monkeypatch):
    import secrets

    def boom(*a, **k):
        raise AssertionError("设置加载不能生成安装编号")
    monkeypatch.setattr(secrets, "token_hex", boom)


def test_retired_feature_modules_are_gone():
    for name in RETIRED_MODULES:
        assert importlib.util.find_spec(f"lolhex.{name}") is None, name


def test_settings_load_never_generates_an_install_id(tmp_path, monkeypatch):
    _no_identifier(monkeypatch)
    p = tmp_path / "config.json"
    s = Settings.load(p)
    assert s.game_lang == "en_US"
    p.write_text(json.dumps({"speed": "low"}), encoding="utf-8")
    assert Settings.load(p).speed == "low"


def test_install_identity_and_remote_control_keys_are_explicitly_removed():
    assert {"install_id", "send_usage", "user_set", "seen_notice", "riot_id", "my_rank",
            "logs_sent", "logs_tries"} <= config.REMOVED


def test_old_config_cannot_resurrect_identity_or_rank(tmp_path, monkeypatch):
    _no_identifier(monkeypatch)
    p = tmp_path / "config.json"
    old = {
        "install_id": "0123456789abcdef", "send_usage": False,
        "user_set": ["speed"], "seen_notice": "5",
        "riot_id": "Someone#1234", "my_rank": {"results": [{"band": "mid"}]},
        "logs_sent": ["0123456789abcdef"], "logs_tries": {"0123456789abcdef": 3},
        "speed": "low", "made_up": {"keep": True},
    }
    p.write_text(json.dumps(old), encoding="utf-8")
    s = Settings.load(p)
    for key in RETIRED_KEYS:
        assert not hasattr(s, key), key
        assert key not in s.extra, key
    assert s.extra == {"made_up": {"keep": True}}      # 真正未知的键照旧保留
    assert s.speed == "low"

    assert s.save(p)
    saved = json.loads(p.read_text(encoding="utf-8"))
    for key in RETIRED_KEYS:
        assert key not in saved, key
    assert saved["made_up"] == {"keep": True}

    again = Settings.load(p)                            # 再读一次也不会复活
    for key in RETIRED_KEYS:
        assert not hasattr(again, key) and key not in again.extra, key


def test_game_lang_defaults_to_english_recognition(tmp_path):
    assert Settings().game_lang == "en_US"
    p = tmp_path / "config.json"
    assert Settings.load(p).game_lang == "en_US"
    p.write_text(json.dumps({"speed": "low"}), encoding="utf-8")   # 老设置文件没有 game_lang
    assert Settings.load(p).game_lang == "en_US"
    for explicit in ("zh_CN", "ko_KR", "ja_JP", "en_US"):
        p.write_text(json.dumps({"game_lang": explicit}), encoding="utf-8")
        assert Settings.load(p).game_lang == explicit


def _publish(root: Path, snapshot_at: str, patch: str = "16.20") -> dict:
    folder = root / "patches" / patch / "normal"
    manifest = make_dataset(folder, snapshot_at=snapshot_at, patch=patch)
    (folder / "latest.json").unlink()
    (root / "latest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


@pytest.fixture
def recording_server(tmp_path):
    root = tmp_path / "remote"
    root.mkdir()
    seen: list[dict] = []

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
            super().do_GET()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield root, f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def _assert_anonymous(seen: list[dict]) -> None:
    """统计数据的所有请求只带版本号 User-Agent：没有安装编号、Cookie、账号或来源头。"""
    assert seen
    for req in seen:
        assert req["headers"].get("user-agent") == f"aramhex/{__version__}"
        for name in ("cookie", "authorization", "proxy-authorization", "referer", "x-aramhex-id"):
            assert name not in req["headers"], name


def test_stats_download_requests_carry_no_identity(recording_server, tmp_path):
    from lolhex.data.public import PublicStore

    root, base, seen = recording_server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    assert s.sync_data(force=True) is True and s.dataset.patch == "16.21"
    paths = [x["path"] for x in seen]
    assert "/latest.json" in paths and "/patches/16.21/normal/heroes.json" in paths  # 清单 + 逐个文件
    _assert_anonymous(seen)


def _make_pack(root: Path, patch: str = "16.21") -> bytes:
    """把发布目录按导出写法归一化后压成 pack，和 unpack 逐字节一致。"""
    from lolhex.data import public

    folder = root / "patches" / patch / "normal"
    manifest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    for name in manifest["files"]:
        obj = json.loads((folder / name).read_text(encoding="utf-8"))
        if name.endswith("hero_augments.json"):
            for d in obj.values():
                for s in d.values():
                    s["win_rate"] = round(s["wins"] / s["games"], 6) if s["games"] else 0.0
                    s["low_sample"] = bool(s.get("low_sample"))
        body = public._dump_json(obj)
        (folder / name).write_bytes(body)
        manifest["files"][name] = {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}
    (root / "latest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pack = public.make_pack(folder, manifest)
    (root / "patches" / patch / "normal.pack.xz").write_bytes(pack)
    return pack


def test_stats_pack_request_carries_no_identity(recording_server, tmp_path):
    from lolhex.data.public import PublicStore

    root, base, seen = recording_server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    _make_pack(root)
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    assert s.sync_data(force=True) is True and s.dataset.patch == "16.21"
    assert any(x["path"].endswith(".pack.xz") for x in seen)
    _assert_anonymous(seen)


def test_stats_per_file_fallback_carries_no_identity(recording_server, tmp_path):
    from lolhex.data.public import PublicStore

    root, base, seen = recording_server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    (root / "patches" / "16.21" / "normal.pack.xz").write_bytes(b"not xz")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    assert s.sync_data(force=True) is True and s.dataset.patch == "16.21"
    assert any(x["path"] == "/patches/16.21/normal/hero_augments.json" for x in seen)
    _assert_anonymous(seen)


def test_stats_offer_request_carries_no_identity(recording_server, tmp_path):
    from lolhex.data.public import PublicStore

    root, base, seen = recording_server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    check_updates=False, transport=LocalTransport(base))
    assert s.sync_data(force=True) is False
    assert [x["path"] for x in seen] == ["/latest.json"]
    _assert_anonymous(seen)


def test_public_store_has_no_cloud_event_configuration():
    import inspect
    from lolhex.data.public import PublicStore
    params = inspect.signature(PublicStore.__init__).parameters
    assert "event_source" not in params
    assert not hasattr(PublicStore, "_sync_event")


def test_engine_uses_fixed_local_stats_schedule(monkeypatch):
    import lolhex.engine as engine
    assert not hasattr(engine, "cloud")
    assert engine.DATA_SYNC_SECONDS == 6 * 3600      # 原云控 data_minutes 默认值 360 分钟
    calls = []

    class Store:
        heroes: dict = {}
        sync_every_s = 0.0

        def refresh(self):
            pass

        def status(self):
            return {}

    eng = engine.Engine(Settings(), home=Path("."), store=Store())
    monkeypatch.setattr(eng, "_warm_up", lambda: None)
    monkeypatch.setattr(eng._data_wake, "wait", lambda s: calls.append(s) or eng._stop.set())
    eng._data_loop()
    every = eng.store.sync_every_s
    assert 0.9 * engine.DATA_SYNC_SECONDS <= every <= 1.1 * engine.DATA_SYNC_SECONDS
    assert calls == [5400.0]      # 原 refresh_hours 6 小时的四分之一，且不超过固定间隔的一半


def test_cli_does_not_import_retired_features():
    import inspect
    from lolhex import __main__ as entry
    assert not hasattr(entry, "cloud")
    source = inspect.getsource(entry)
    assert "cloud" not in source and "cloudsettings" not in source
    assert "install_id" not in source and "send_usage" not in source


def test_update_rank_and_usage_ui_surface_is_gone():
    pytest.importorskip("PySide6")
    from lolhex.ui import mainwindow
    for name in ("RankWorker", "UpdateWorker"):
        assert not hasattr(mainwindow, name), name
    for name in ("check_update", "refresh_rank_if_stale", "recheck_rank_if_newer",
                 "_apply_cloud", "_apply_cloud_settings", "_cloud_popups",
                 "_update_lang_hint", "_download_langpack"):
        assert not hasattr(mainwindow.MainWindow, name), name


def test_about_is_static_attribution_with_cn_stats_label():
    pytest.importorskip("PySide6")
    from lolhex.ui.mainwindow import about_html
    html = about_html()
    assert "github.com/czgreat/aramhex" in html and "MIT" in html
    assert "github.com/czgreat/aramhex-data" in html and "CC BY-NC 4.0" in html
    assert "CN" in html      # 统计数据来自国服
