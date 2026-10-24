"""C2：任何一个必需家族返回空表/全是坏记录时，整份响应按失败处理。

解析器对单条坏记录一直是「跳过、不猜」；但整份表解析为空说明源端给了空或全坏的
数据，不能当成刷新成功去顶掉上一份好缓存、推进家族时间戳或写进磁盘。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lolhex.data.store import DataStore

CHAMPION_URL = "/data/en_US/champion.json"
ITEM_URL = "/data/en_US/item.json"
AUGMENT_URL = "/v1/cherry-augments.json"


class _Response:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")


AHRI = {"key": "103", "name": "Ahri", "title": "the Nine-Tailed Fox",
        "tags": ["Mage"], "image": {"full": "Ahri.png"}}
BOOTS = {"name": "Boots", "plaintext": "Slightly increases Movement Speed.",
         "gold": {"total": 300}, "image": {"full": "1001.png"}}


class FakeMetadataTransport:
    """只回答 Data Dragon / CommunityDragon 的元数据；测试可以随时改写某个家族的表。"""

    def __init__(self):
        self.version = "16.21.1"
        self.champions = {"data": {"Ahri": dict(AHRI)}}
        self.items = {"data": {"1001": dict(BOOTS)}}
        self.augments = [{"id": 1001, "nameTRA": "Titan's Resolve", "rarity": "kGold"}]
        self.urls: list[str] = []

    def get(self, url, *, timeout=20, headers=None):
        self.urls.append(url)
        if url.endswith("/api/versions.json"):
            return _Response([self.version, "16.20.1"])
        if url.endswith(CHAMPION_URL):
            return _Response(self.champions)
        if url.endswith(ITEM_URL):
            return _Response(self.items)
        if url.endswith(AUGMENT_URL):
            return _Response(self.augments)
        raise AssertionError("未预期的地址：" + url)


def _disk(root: Path) -> dict:
    return json.loads((Path(root) / "static.json").read_text(encoding="utf-8"))


def _snapshot(value):
    return json.loads(json.dumps(value))


@pytest.fixture
def refreshed(tmp_path):
    """先成功刷新一次，拿到一份好的缓存和它的家族时间戳。"""
    root = tmp_path / "data"
    transport = FakeMetadataTransport()
    store = DataStore(root, refresh_hours=0, transport=transport)
    store.refresh(force=True)
    assert store.items["1001"]["name"] == "Boots"
    assert store.heroes["103"]["name_en"] == "Ahri"
    assert store.augments["1001"]["name_en"] == "Titan's Resolve"
    assert not store.last_error
    return root, store, transport


def test_empty_item_payload_keeps_good_cache_and_surfaces_the_error(refreshed):
    root, store, transport = refreshed
    good_items = _snapshot(store.items)
    items_at = store.static["families"]["items"]["at"]
    heroes_at = store.static["families"]["heroes"]["at"]

    # 源端升级了版本、给了新的英雄表，但装备表是 200 + 空 data。
    transport.version = "16.22.1"
    transport.champions = {"data": {"Ahri": {**AHRI, "name": "Ahri Prime"}}}
    transport.items = {"data": {}}
    store.refresh(force=True)

    # 装备：上一份好数据、家族时间戳、磁盘缓存都原样保留，错误可见。
    assert store.items == good_items
    assert store.static["families"]["items"]["at"] == items_at
    assert store.last_error and "装备" in store.last_error
    disk = _disk(root)
    assert disk["items"] == good_items
    assert disk["families"]["items"]["at"] == items_at
    # 其他家族照常刷新：没有被这一家族的失败连坐，失败也没有被成功掩盖。
    assert store.heroes["103"]["name_en"] == "Ahri Prime"
    assert store.static["families"]["heroes"]["at"] >= heroes_at
    assert disk["versions"][0]["name"] == "16.22.1"
    assert not list((Path(root)).glob("*.tmp"))


@pytest.mark.parametrize("payload", [
    {"data": {}},                                                    # 空表
    {"data": {"1001": {"name": "", "image": {"full": "1001.png"}}}},  # 名字为空
    {"data": {"1002": {"name": "Boots", "image": {"full": "x.png"}},  # 图标路径对不上
              "bad": {"name": "Boots", "image": {"full": "bad.png"}}}},
])
def test_item_family_rejects_payloads_with_no_usable_records(refreshed, payload):
    root, store, transport = refreshed
    good_items = _snapshot(store.items)
    items_at = store.static["families"]["items"]["at"]

    transport.items = payload
    store.refresh(force=True)

    assert store.items == good_items
    assert store.static["families"]["items"]["at"] == items_at
    assert store.last_error and "装备" in store.last_error
    assert _disk(root)["items"] == good_items


@pytest.mark.parametrize("family, payload, marker", [
    ("champions", {"data": {}}, "英雄"),
    ("champions", {"data": {"Ahri": {**AHRI, "name": ""}}}, "英雄"),
    ("augments", [], "海克斯"),
    ("augments", [{"id": None, "nameTRA": "Broken"}, {"id": 999999, "nameTRA": "Arena Only"}], "海克斯"),
])
def test_hero_and_augment_families_reject_empty_or_all_invalid_results(
        refreshed, family, payload, marker):
    root, store, transport = refreshed
    heroes = _snapshot(store.heroes)
    augments = _snapshot(store.augments)
    heroes_at = store.static["families"]["heroes"]["at"]
    augments_at = store.static["families"]["augments"]["at"]

    setattr(transport, family, payload)
    store.refresh(force=True)

    assert store.heroes == heroes and store.augments == augments
    assert store.last_error and marker in store.last_error
    disk = _disk(root)
    assert disk["heroes"] == heroes and disk["augments"] == augments
    # 失败家族的「已刷新」时间戳不推进；另一个家族不受牵连、也不掩盖这个错误。
    if family == "champions":
        assert store.static["families"]["heroes"]["at"] == heroes_at
        assert disk["families"]["heroes"]["at"] == heroes_at
        assert store.static["families"]["augments"]["at"] >= augments_at
    else:
        assert store.static["families"]["augments"]["at"] == augments_at
        assert disk["families"]["augments"]["at"] == augments_at
        assert store.static["families"]["heroes"]["at"] >= heroes_at


def test_family_error_clears_on_the_next_good_refresh(refreshed):
    root, store, transport = refreshed
    transport.items = {"data": {}}
    store.refresh(force=True)
    assert store.last_error

    transport.version = "16.22.1"
    transport.items = {"data": {"1003": {**BOOTS, "name": "Boots Mk II",
                                         "image": {"full": "1003.png"}}}}
    store.refresh(force=True)

    assert not store.last_error
    assert store.items["1003"]["name"] == "Boots Mk II"
    assert _disk(root)["items"]["1003"]["name"] == "Boots Mk II"
