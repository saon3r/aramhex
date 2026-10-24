"""离线启动：先有本地头像库/匹配器，再后台刷新；不联网、不依赖统计数据。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import cv2
import numpy as np

from lolhex import __main__ as cli
from lolhex.config import Settings
from lolhex.data.public import PublicStore
from lolhex.engine import Engine
from lolhex.vision import portraits


def _crop(body: bytes, size: int = 64) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    assert img is not None
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)


def test_engine_seeds_bank_and_matchers_before_refresh(tmp_path, no_network):
    st = PublicStore(tmp_path / "data", bundled=tmp_path / "missing", check_updates=False,
                     base_url=[])
    assert st.dataset is None and len(st.heroes) >= 173      # 没有统计数据也能认字
    eng = Engine(Settings(), home=tmp_path / "home", store=st)

    assert not (tmp_path / "home" / "data" / "icons").exists()
    eng._load_icons(download=False)
    assert eng._icon_bank is not None and len(eng._icon_bank) == len(st.heroes) == 173
    assert eng._hero_matcher().match("Teemo")[0].split("#")[0] == "17"
    assert eng._hero_matcher().match("the Swift Scout")[0].split("#")[0] == "17"
    assert eng._augment_matcher().match("Titan's Resolve")[0] == "1001"


def test_engine_threads_transport_to_icon_cache_and_downloads(tmp_path, no_network, monkeypatch):
    sentinel = object()
    st = PublicStore(tmp_path / "data", bundled=tmp_path / "missing", check_updates=False,
                     base_url=[])
    eng = Engine(Settings(), home=tmp_path / "home", store=st, transport=sentinel)
    assert eng.icons.transport is sentinel

    seen = {}

    def fake_ensure(folder, heroes, transport=None):
        seen["transport"] = transport
        return 0

    monkeypatch.setattr(portraits, "ensure_icons", fake_ensure)
    eng._load_icons(download=True)
    assert seen["transport"] is sentinel


def test_corrupt_cached_portrait_falls_back_to_bundled_and_client(tmp_path, no_network):
    st = PublicStore(tmp_path / "data", bundled=tmp_path / "missing", check_updates=False,
                     base_url=[])
    folder = tmp_path / "icons"
    folder.mkdir()
    (folder / "Teemo.png").write_bytes(b"not a png")
    bank = portraits.IconBank.from_dir(folder, st.heroes, portraits.client_icons())
    assert len(bank) == 173 and "17" in bank.ids
    client = portraits.client_icons()["17"]
    assert bank.classify(_crop(cv2.imencode(".png", client)[1].tobytes())).hero_id == "17"


def test_ensure_icons_downloads_ddragon_even_for_bundled_alias(tmp_path, monkeypatch):
    from lolhex.data import http

    source = (portraits.HERO_ICONS.parent.parent.parent / "tests" / "fixtures" / "portraits"
              / "source" / "Teemo.png")
    body = source.read_bytes()
    got = []

    def fake_fetch(url, **kw):
        got.append((url, kw.get("transport")))
        return body

    monkeypatch.setattr(http, "fetch", fake_fetch)
    sentinel = object()
    heroes = {"17": {"alias": "Teemo", "icon": "https://ddragon.leagueoflegends.com/cdn/16.21.1/img/champion/Teemo.png"}}
    assert "Teemo" in portraits.hero_icons()                  # 旧内置仍有，但不再阻止运行时更新
    assert portraits.ensure_icons(tmp_path / "icons", heroes, transport=sentinel) == 1
    assert (tmp_path / "icons" / "Teemo.png").read_bytes() == body
    assert got and got[0][1] is sentinel


def test_failed_or_invalid_portrait_download_keeps_cache(tmp_path, monkeypatch):
    from lolhex.data import http

    folder = tmp_path / "icons"
    folder.mkdir()
    monkeypatch.setattr(http, "fetch", lambda *a, **k: b"<html>CDN error</html>")
    heroes = {"17": {"alias": "Teemo", "icon": "https://ddragon.leagueoflegends.com/cdn/16.21.1/img/champion/Teemo.png"}}
    assert portraits.ensure_icons(folder, heroes) == 0
    assert not (folder / "Teemo.png").exists()               # 坏图不落盘
    assert not list(folder.glob("*.tmp"))


def test_spell_and_item_text_fallback_without_metadata(tmp_path, no_network):
    from lolhex.ui import buildview

    st = PublicStore(tmp_path / "data", bundled=tmp_path / "missing", check_updates=False,
                     base_url=[])
    assert st.spells["4"]["name"] == "Flash" and st.spells["4"]["icon"] == ""
    d = {"summoners": [{"spells": [{"id": "4", "name": "Flash"}, {"id": "32", "name": "Mark"}]}],
         "summoner_source": "自采统计"}
    html = "".join(buildview.lines(d, None, True))
    assert "Flash" in html and "Mark" in html
    assert buildview.item(None, {"id": "3115", "name": None}, 24) == "3115"
    assert buildview.item(None, {"id": "3115", "name": "Nashor's Tooth"}, 24) == "Nashor's Tooth"


class _FakeStore:
    def __init__(self, usable):
        self.last_error = "官方资料：断网"
        self.sync_error = "统计数据：断网"
        self.dataset = SimpleNamespace() if usable else None

    def refresh(self, *a, **k):
        pass

    def status(self):
        return {"error": self.last_error, "sync_error": self.sync_error,
                "dataset": self.dataset is not None}


def _fake_engine(monkeypatch, usable):
    class FakeEngine:
        def __init__(self, _settings):
            self.store = _FakeStore(usable)

    monkeypatch.setattr("lolhex.engine.Engine", FakeEngine)


def test_refresh_exit_zero_with_usable_dataset_but_keeps_errors(monkeypatch, capsys):
    _fake_engine(monkeypatch, usable=True)
    assert cli.main(["--refresh"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dataset"] is True
    assert out["error"] and out["sync_error"]            # 返回 0 不代表没错误


def test_refresh_exit_nonzero_without_dataset(monkeypatch, capsys):
    _fake_engine(monkeypatch, usable=False)
    assert cli.main(["--refresh"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["dataset"] is False and out["error"]
