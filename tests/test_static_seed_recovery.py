"""C5：兜底表缺失/损坏时的种子完整性与自愈。

旧版本在 static_fallback.json 缺失时会把「没有 alias/稀有度/召唤师技能」的种子当成
schema 2 正常缓存落盘，之后即使修好兜底表也只会读到这份残缺缓存。这里钉住三件事：

1. 残缺种子必须可见（warning + last_error + status.static_complete），且绝不落盘成
   看似正常的缓存；
2. 兜底表恢复后，旧残缺 schema 2 缓存就地补齐，装备/家族时间戳/刷新过的记录都保留；
3. 兜底表不可用但缓存本身是完整的，照常启动，不覆盖、不删除。

资源缺失/损坏用进程内 monkeypatch 模拟，绝不改名或删除随程序的真实文件。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from conftest import make_dataset
from lolhex.data import metadata
from lolhex.data import store as store_mod
from lolhex.data.public import PublicStore
from lolhex.data.store import DataStore

# static_fallback.json 缺失和「文件在但内容是坏壳」是同一类降级。
BAD_FALLBACKS = ({}, {"schema": 99, "heroes": {}, "augments": {}, "spells": {}})


def _degraded_cache(root: Path, monkeypatch) -> dict:
    """造一份旧版本在兜底表缺失时落盘的 schema 2 残缺缓存，但带上好装备表和家族时间戳。"""
    with monkeypatch.context() as patch:
        patch.setattr(metadata, "static_fallback", lambda: {})
        blob = store_mod._seed_static()
    blob["schema"] = store_mod.STATIC_SCHEMA
    blob["fetched_at"] = 1782000000.0
    blob["items"] = {"1001": {"id": "1001", "name": "Boots", "plaintext": "Slightly faster."}}
    blob["families"] = {"heroes": {"at": 1782000100.0, "version": "16.20"},
                        "items": {"at": 1782000200.0, "version": "16.20"}}
    # 刷新过的记录：合法名字/图标/稀有度不许被兜底表覆盖
    blob["heroes"]["103"] = {"id": "103", "name": "阿狸", "nick": "九尾妖狐", "alias": "Ahri",
                            "icon": "https://ddragon.leagueoflegends.com/cdn/16.25.1/img/champion/Ahri.png",
                            "name_en": "Ahri Prime", "nick_en": "the Nine-Tailed Fox",
                            "keywords": "Ahri Prime"}
    blob["augments"]["2128"]["rarity"] = "prismatic"
    root.mkdir(parents=True, exist_ok=True)
    (root / "static.json").write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    return blob


@pytest.mark.parametrize("payload", BAD_FALLBACKS)
def test_missing_or_corrupt_fallback_is_visible_and_never_persisted(
        tmp_path, no_network, monkeypatch, caplog, payload):
    caplog.set_level(logging.WARNING, logger="lolhex.data.store")
    monkeypatch.setattr(metadata, "static_fallback", lambda: dict(payload))
    root = tmp_path / "data"

    st = DataStore(root)

    assert len(st.heroes) >= 173 and len(st.augments) >= 232      # i18n 名字仍能离线识别
    assert st.last_error and "静态资料不完整" in st.last_error
    assert st.status()["static_complete"] is False
    assert any("静态资料不完整" in rec.getMessage() for rec in caplog.records)
    disk = root / "static.json"
    assert not disk.exists() or not store_mod._valid_static(
        json.loads(disk.read_text(encoding="utf-8")))


def test_fixed_fallback_heals_degraded_schema2_cache_without_http(tmp_path, no_network,
                                                                 monkeypatch):
    root = tmp_path / "data"
    degraded = _degraded_cache(root, monkeypatch)
    assert store_mod._seed_gaps(degraded) == ["alias", "rarity", "spells"]
    before = (root / "static.json").read_text(encoding="utf-8")

    st = DataStore(root)                       # 兜底表已恢复；no_network 保证全程不发请求

    assert st.last_error is None and st.status()["static_complete"] is True
    assert all(h["alias"] for h in st.heroes.values())
    assert all(a.get("rarity") for a in st.augments.values())
    assert st.spells["4"]["name"] == "Flash" and st.spells["32"]["name"] == "Mark"
    assert st.resolve_hero("Teemo") == "17"
    # 好数据原样保留：装备、家族时间戳、抓取时间、刷新过的英雄/稀有度
    assert st.items == degraded["items"]
    assert st.static["families"] == degraded["families"]
    assert st.static["fetched_at"] == degraded["fetched_at"]
    assert st.static["patch"] == degraded["patch"]
    assert st.augments["2128"]["rarity"] == "prismatic"
    assert st.heroes["103"]["icon"].endswith("/16.25.1/img/champion/Ahri.png")
    assert st.heroes["103"]["name_en"] == "Ahri Prime"
    # 就地修好并落盘，重启不再缺
    disk = json.loads((root / "static.json").read_text(encoding="utf-8"))
    assert store_mod._seed_gaps(disk) == []
    assert disk["items"] == degraded["items"] and disk["families"] == degraded["families"]
    assert disk["fetched_at"] == degraded["fetched_at"]
    assert (root / "static.json").read_text(encoding="utf-8") != before


def test_healthy_cache_stays_usable_when_fallback_is_unavailable(tmp_path, no_network,
                                                                 monkeypatch):
    root = tmp_path / "data"
    healthy = DataStore(root)
    assert store_mod._seed_gaps(healthy.static) == []
    good = (root / "static.json").read_bytes()

    with monkeypatch.context() as patch:
        patch.setattr(metadata, "static_fallback", lambda: {})
        again = DataStore(root)

    assert again.heroes["17"]["alias"] == "Teemo"
    assert again.spells["4"]["name"] == "Flash"
    assert again.last_error is None and again.status()["static_complete"] is True
    assert (root / "static.json").read_bytes() == good           # 完整缓存没被降级种子顶掉


def test_degraded_cache_is_kept_but_flagged_while_fallback_is_unavailable(
        tmp_path, no_network, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="lolhex.data.store")
    root = tmp_path / "data"
    degraded = _degraded_cache(root, monkeypatch)
    before = (root / "static.json").read_bytes()

    with monkeypatch.context() as patch:
        patch.setattr(metadata, "static_fallback", lambda: {})
        st = DataStore(root)

    assert st.heroes["17"]["name"] == "提莫" and st.items == degraded["items"]
    assert st.last_error and "静态资料不完整" in st.last_error
    assert st.status()["static_complete"] is False
    assert any("静态资料不完整" in rec.getMessage() for rec in caplog.records)
    assert (root / "static.json").read_bytes() == before         # 不覆盖、不删除、不写坏


def test_public_store_cannot_persist_an_incomplete_seed(tmp_path, no_network, monkeypatch):
    bundled = tmp_path / "bundled"
    make_dataset(bundled)
    root = tmp_path / "data"

    with monkeypatch.context() as patch:
        patch.setattr(metadata, "static_fallback", lambda: {})
        st = PublicStore(root, bundled=bundled, check_updates=False, base_url=[])

    assert len(st.heroes) >= 173 and st.last_error        # 有数据集也能启动，但要说明缺什么
    assert st.status()["static_complete"] is False
    disk = root / "static.json"
    assert not disk.exists() or not store_mod._valid_static(
        json.loads(disk.read_text(encoding="utf-8")))
