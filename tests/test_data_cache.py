"""静态资料缓存：离线种子、坏缓存兜底、按家族保留旧数据、原子落盘、传输注入。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from conftest import make_dataset
from lolhex.data import store as store_mod
from lolhex.data.public import Dataset, PublicStore
from lolhex.data.store import DataStore

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHERRY_URL = ("https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/"
              "global/default/v1/cherry-augments.json")


class _Response:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self.content = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")


class FakeTransport:
    """只回应元数据地址；fail 里列的地址抛错，其余记录后正常返回。"""

    def __init__(self, version="16.21.1", fail=(), champion_name="Ahri", item_name="Boots",
                 augment_rarity="kGold"):
        self.version = version
        self.fail = set(fail)
        self.champion_name = champion_name
        self.item_name = item_name
        self.augment_rarity = augment_rarity
        self.urls: list[str] = []

    def get(self, url, *, timeout=20, headers=None):
        self.urls.append(url)
        if any(f in url for f in self.fail):
            raise RuntimeError("模拟失败：" + url)
        if url.endswith("/api/versions.json"):
            return _Response([self.version, "16.20.1"])
        if "/data/en_US/champion.json" in url:
            return _Response({"data": {"Ahri": {
                "key": "103", "name": self.champion_name, "title": "the Nine-Tailed Fox",
                "tags": ["Mage"], "image": {"full": "Ahri.png"}}}})
        if "/data/en_US/item.json" in url:
            return _Response({"data": {"1001": {
                "name": self.item_name, "plaintext": "Slightly increases Movement Speed.",
                "gold": {"total": 300}, "image": {"full": "1001.png"}}}})
        if url == CHERRY_URL:
            return _Response([
                {"id": 1001, "nameTRA": "Titan's Resolve", "rarity": self.augment_rarity},
                {"id": 999999, "nameTRA": "Arena Only", "rarity": "kGold"},
            ])
        raise AssertionError("未预期的地址：" + url)


def test_tencent_static_source_is_fully_removed():
    import importlib.util

    assert importlib.util.find_spec("lolhex.data.tencent") is None
    import inspect

    from lolhex import recommend

    assert "tencent" not in inspect.getsource(recommend)  # 推荐不再引用腾讯模块
    assert recommend.RARITY_CN["gold"] == "黄金"


def test_offline_constructor_seeds_recognition_without_network(tmp_path, no_network):
    st = DataStore(tmp_path / "data")

    assert len(st.heroes) >= 173 and len(st.augments) >= 232
    teemo = st.heroes["17"]
    assert teemo["name"] == "提莫" and teemo["nick"] == "迅捷斥候"   # 认字用的中文字段
    assert teemo["alias"] == "Teemo"
    assert teemo["name_en"] == "Teemo" and teemo["nick_en"]        # 英文显示单独存放
    assert "Teemo" in (teemo["keywords"] or "") and "Swift Scout" in teemo["keywords"]
    assert st.resolve_hero("Teemo") == "17"
    assert st.resolve_hero("the Swift Scout") == "17"               # 英文称号也能搜到
    # 海克斯：中文识别名 + 英文名 + 合法稀有度 + Mayhem 模式
    aug = st.augments["1001"]
    assert aug["name"] == "泰坦的坚决" and aug["name_en"] == "Titan's Resolve"
    assert aug["rarity"] in {"silver", "gold", "prismatic"}
    assert aug["modes"] == ["KIWI"]
    for aid in ("1332", "1416", "2091", "2116", "2129", "2135"):
        assert st.augments[aid]["name"] and st.augments[aid]["modes"] == ["KIWI"]
    assert "unknown" not in {a.get("rarity") for a in st.augments.values()}
    # 召唤师技能只用本地英文名，没有腾讯图标/地址
    assert st.spells["4"]["name"] == "Flash" and st.spells["4"]["icon"] == ""
    assert st.spells["32"]["name"] == "Mark"
    assert st.items == {}                                          # 没有联网就不编造装备


@pytest.mark.parametrize("bad", [
    "{not json",
    json.dumps({"schema": 99, "heroes": {}, "augments": {}, "items": {}, "spells": {}, "versions": []}),
    json.dumps({"schema": 2, "heroes": {}, "augments": {}, "items": {}}),   # 截断：缺表
    json.dumps({"heroes": {"17": {"name": "x"}}, "augments": {}, "items": {}, "spells": {}}),
])
def test_corrupt_or_wrong_schema_cache_cannot_block_startup(tmp_path, no_network, bad):
    root = tmp_path / "data"
    root.mkdir()
    (root / "static.json").write_text(bad, encoding="utf-8")

    st = DataStore(root)
    assert len(st.heroes) >= 173 and len(st.augments) >= 232
    assert st.augments["1001"]["name"] == "泰坦的坚决"
    # 坏缓存被替换成完整的原子缓存，下次离线启动仍有数据
    assert json.loads((root / "static.json").read_text(encoding="utf-8"))["schema"] == store_mod.STATIC_SCHEMA
    assert not list(root.glob("*.tmp"))


def test_legacy_tencent_cache_keeps_keywords_but_never_tencent_icons(tmp_path, no_network):
    root = tmp_path / "data"
    root.mkdir()
    legacy = {
        "fetched_at": time.time(), "patch": "16.20", "versions": [{"name": "16.20"}],
        "heroes": {"17": {"id": "17", "name": "提莫", "nick": "迅捷斥候", "alias": "Teemo",
                          "icon": "https://game.gtimg.cn/images/lol/act/img/champion/Teemo.png",
                          "keywords": "tm,xjch,提莫队长"}},
        "augments": {"1001": {"id": "1001", "name": "泰坦的坚决", "rarity": "prismatic",
                              "icon": "https://game.gtimg.cn/x.png", "modes": ["KIWI"]}},
        "items": {"1001": {"id": "1001", "name": "鞋子", "icon": "https://game.gtimg.cn/i.png"}},
        "spells": {"4": {"id": "4", "name": "闪现", "icon": "https://game.gtimg.cn/s.png"}},
    }
    (root / "static.json").write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    st = DataStore(root)
    assert "tm" in st.hero_terms("17") and "xjch" in st.hero_terms("17")   # 旧拼音关键词保留
    assert "gtimg" not in json.dumps(st.static, ensure_ascii=False)        # 腾讯图标/地址一律不复活
    assert st.spells["4"]["name"] == "Flash" and st.spells["4"]["icon"] == ""
    assert st.items == {}


def test_family_failure_keeps_last_good_family_and_records_error(tmp_path):
    root = tmp_path / "data"
    first = FakeTransport(version="16.21.1")
    st = DataStore(root, refresh_hours=0, transport=first)
    st.refresh(force=True)
    items_before = json.loads(json.dumps(st.items))
    heroes_at = st.static["families"]["heroes"]["at"]
    items_at = st.static["families"]["items"]["at"]
    assert st.items["1001"]["name"] == "Boots" and st.heroes["103"]["name_en"] == "Ahri"
    assert not st.last_error

    second = FakeTransport(version="16.22.1", fail=("/img/item", "/item.json"),
                           champion_name="Ahri Prime")
    st.transport = second
    st.refresh(force=True)

    assert st.heroes["103"]["name_en"] == "Ahri Prime"
    assert "16.22.1" in st.heroes["103"]["icon"]
    assert st.items == items_before                              # 失败的家族保留上一份
    assert st.static["families"]["items"]["at"] == items_at
    assert st.last_error and "item" in st.last_error.lower()
    # 不是一个 roles 哨兵那样每次数据循环都重抓：成功家族的时间戳已更新
    assert st.static["families"]["heroes"]["at"] >= heroes_at


def test_failed_refresh_never_replaces_good_cache(tmp_path):
    root = tmp_path / "data"
    st = DataStore(root, refresh_hours=0, transport=FakeTransport())
    st.refresh(force=True)
    good = (root / "static.json").read_text(encoding="utf-8")

    class Broken(FakeTransport):
        def get(self, url, *, timeout=20, headers=None):
            raise RuntimeError("断网")

    st.transport = Broken()
    st.refresh(force=True)
    assert st.last_error and (root / "static.json").read_text(encoding="utf-8") == good
    assert st.augments["1001"]["name"] == "泰坦的坚决"


def test_unknown_source_rarity_does_not_overwrite_fallback(tmp_path):
    root = tmp_path / "data"
    st = DataStore(root, refresh_hours=0, transport=FakeTransport(augment_rarity="kBogus"))
    st.refresh(force=True)
    assert st.augments["1001"]["rarity"] == "prismatic"          # 内置 fallback 保留
    assert "999999" not in st.augments                           # Arena-only 不因英文源而进识别表


def test_refresh_uses_injected_transport_only(tmp_path):
    fake = FakeTransport()
    st = DataStore(tmp_path / "data", refresh_hours=0, transport=fake)
    st.refresh(force=True)
    assert VERSIONS_URL in fake.urls and CHERRY_URL in fake.urls
    assert any("/data/en_US/champion.json" in u for u in fake.urls)
    assert any("/data/en_US/item.json" in u for u in fake.urls)


def test_icon_cache_rejects_invalid_png_and_keeps_last_good(tmp_path, monkeypatch):
    import os

    import cv2
    import numpy as np

    from lolhex.data import icons

    folder = tmp_path / "img"
    path = folder / "item" / "1001.png"
    path.parent.mkdir(parents=True)
    ok, buf = cv2.imencode(".png", np.full((8, 8, 3), 90, np.uint8))
    assert ok
    good = buf.tobytes()
    path.write_bytes(good)
    os.utime(path, (1, 1))                                   # 过期，触发一次刷新
    monkeypatch.setattr(icons.http, "fetch", lambda *a, **k: b"<html>CDN error</html>")
    cache = icons.IconCache(folder, workers=1)
    assert cache.local("item", "1001", "https://ddragon.leagueoflegends.com/x.png")
    cache._pool.shutdown(wait=True)
    assert path.read_bytes() == good                         # 坏响应不覆盖旧缓存
    assert not list(folder.rglob("*.tmp"))

    cache2 = icons.IconCache(folder, workers=1)
    assert cache2.local("item", "2002", "https://ddragon.leagueoflegends.com/y.png") is None
    cache2._pool.shutdown(wait=True)
    assert not (folder / "item" / "2002.png").exists()


def test_warm_relaunch_reads_cache_without_network(tmp_path):
    root = tmp_path / "data"
    DataStore(root, refresh_hours=0, transport=FakeTransport()).refresh(force=True)
    fresh = DataStore(root)
    assert fresh.items["1001"]["name"] == "Boots"
    assert fresh.heroes["103"]["name_en"] == "Ahri"
    assert fresh.static["families"]["augments"]["at"]


def test_public_store_threads_transport_to_metadata(tmp_path):
    fake = FakeTransport()
    make_dataset(tmp_path / "bundled")
    st = PublicStore(tmp_path / "data", bundled=tmp_path / "bundled", check_updates=False,
                     base_url=[], transport=fake)
    st.refresh(force=True)
    assert VERSIONS_URL in fake.urls


def test_dataset_manifest_is_a_defensive_copy(tmp_path):
    make_dataset(tmp_path / "b")
    ds = Dataset(tmp_path / "b", "bundled")
    caller = json.loads((tmp_path / "b" / "latest.json").read_text(encoding="utf-8"))
    caller["files"]["heroes.json"]["sha256"] = "0" * 64
    caller["files"]["heroes.json"]["size"] = 1
    assert ds.manifest["files"]["heroes.json"]["sha256"] != "0" * 64


def _real_bundled_ids() -> tuple[set[str], set[str]]:
    """真实内置数据集的 (允许的 Mayhem 海克斯 ID, 英雄 ID)；不经过任何缓存。"""
    data = Path(__file__).parent.parent / "lolhex" / "data"
    bundled = data / "bundled"
    flat = json.loads((bundled / "augments.json").read_text(encoding="utf-8"))
    nested = json.loads((bundled / "hero_augments.json").read_text(encoding="utf-8"))
    meta = json.loads((bundled / "meta.json").read_text(encoding="utf-8"))
    i18n = json.loads((data / "i18n.json").read_text(encoding="utf-8"))
    heroes = json.loads((bundled / "heroes.json").read_text(encoding="utf-8"))
    allowed = set(flat) | set(i18n["augments"])
    for rows in nested.values():                 # 嵌套表：外层是英雄 ID，内层才是海克斯 ID
        allowed |= set(rows)
    for key in ("provisional_augments", "unobserved_augments"):
        allowed |= set(meta.get(key) or {})
    allowed |= {"1332", "1416", "2091", "2116", "2129", "2135"}
    return allowed, set(heroes)


def test_real_dataset_seed_never_uses_hero_ids_as_augment_ids(tmp_path, no_network):
    allowed, hero_ids = _real_bundled_ids()
    st = PublicStore(tmp_path / "data", bundled=Path(__file__).parent.parent / "lolhex" / "data" / "bundled",
                     check_updates=False, base_url=[])
    assert set(st.augments) == allowed
    assert not (set(st.augments) & hero_ids)
    assert st._active_augment_ids() == allowed
    assert all(aid in st.augments for aid in ("1332", "1416", "2091", "2116", "2129", "2135"))


def test_polluted_schema2_cache_is_healed_on_restart_without_http(tmp_path, no_network):
    allowed, hero_ids = _real_bundled_ids()
    bundled = Path(__file__).parent.parent / "lolhex" / "data" / "bundled"
    root = tmp_path / "data"
    st = PublicStore(root, bundled=bundled, check_updates=False, base_url=[])
    blob = json.loads((root / "static.json").read_text(encoding="utf-8"))
    for hid in sorted(hero_ids, key=int):         # 复现旧 bug 写进去的 173 条英雄 ID
        blob["augments"][hid] = {"id": hid, "name": "", "name_en": "", "desc": "", "icon": "",
                                 "modes": ["KIWI"], "new": False}
    (root / "static.json").write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")

    again = PublicStore(root, bundled=bundled, check_updates=False, base_url=[])
    assert set(again.augments) == allowed        # 内存愈合
    assert not (set(again.augments) & hero_ids)
    disk = json.loads((root / "static.json").read_text(encoding="utf-8"))
    assert set(disk["augments"]) == allowed      # 落盘愈合，重启后不会复活
    assert again.augments["1001"]["name"] and again.augments["1001"]["rarity"]
    meta = json.loads((bundled / "meta.json").read_text(encoding="utf-8"))
    prov = set(meta["provisional_augments"])
    assert prov <= set(again.augments) and all(again.augments[a]["new"] for a in prov)
    assert "1332" in again.augments and "2128" in again.augments


def test_dataset_seed_adds_metadata_before_refresh(tmp_path, no_network):
    make_dataset(tmp_path / "b")
    st = PublicStore(tmp_path / "data", bundled=tmp_path / "b", check_updates=False, base_url=[])
    assert st.dataset is not None
    assert st.augments["2128"]["rarity"] == "gold"
    assert st.static["patch"] == "16.20"


def test_dataset_new_flags_reach_store_and_scorer(tmp_path, no_network):
    from lolhex import recommend

    make_dataset(tmp_path / "b", meta_extra={
        "unobserved_augments": {"3086": {"name": "小蜜蜂", "status": "未观测"}}})
    st = PublicStore(tmp_path / "data", bundled=tmp_path / "b", check_updates=False, base_url=[])
    rec = st.augments["3086"]
    assert rec["new"] is True and rec["name"] and rec["modes"] == ["KIWI"]
    card = recommend.evaluate(st, "17", ["3086"])["slots"][0]
    assert card["verdict"] == "nodata" and card["basis"] == "new"
    assert recommend.win_text(card) == "?"                 # 没有统计就不编造数字
