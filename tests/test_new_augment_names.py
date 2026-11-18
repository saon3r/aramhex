"""新统计数据带来的新海克斯：英文名不用等 6 小时的资料刷新周期，下一轮就补上；
英文源确实没有名字时，一小时内不重复去问。"""

from __future__ import annotations

import time

from lolhex.data.store import DataStore
from test_metadata_refresh_failures import AUGMENT_URL, FakeMetadataTransport


def _store(tmp_path, monkeypatch, ids):
    transport = FakeMetadataTransport()
    store = DataStore(tmp_path / "data", refresh_hours=6, transport=transport)
    store.refresh(force=True)
    monkeypatch.setattr(store, "_active_augment_ids", lambda: set(ids))
    # 新数据集刚换上：种子里有这张卡，但英文名是空的（_seed_from_dataset 的样子）
    store.static["augments"]["9060"] = {"id": "9060", "name": "单曲红人", "name_en": "",
                                        "modes": ["KIWI"], "rarity": "gold"}
    transport.urls.clear()
    return store, transport


def _augment_calls(transport):
    return [u for u in transport.urls if u.endswith(AUGMENT_URL)]


def test_new_augment_gets_english_name_without_waiting_for_the_six_hour_refresh(tmp_path, monkeypatch):
    store, transport = _store(tmp_path, monkeypatch, {"1001", "9060"})
    transport.augments.append({"id": 9060, "nameTRA": "One Hit Wonder", "rarity": "kGold"})
    # 资料还算新：只等到期的话要 6 小时
    store.static["families"]["augments"]["at"] = time.time() - 2 * 3600

    store.refresh()

    assert store.augments["9060"]["name_en"] == "One Hit Wonder"
    assert store.augments["9060"]["name"] == "单曲红人"
    assert len(_augment_calls(transport)) == 1
    assert not [u for u in transport.urls if "champion.json" in u]  # 只补海克斯，不重刷别的家族


def test_missing_name_is_not_requested_again_within_the_hour(tmp_path, monkeypatch):
    store, transport = _store(tmp_path, monkeypatch, {"1001", "9060"})
    store.static["families"]["augments"]["at"] = time.time() - 2 * 3600

    store.refresh()          # 英文源也没有 9060：问一次
    store.refresh()          # 一小时内不再问
    store.refresh()

    assert len(_augment_calls(transport)) == 1
    assert store.augments["9060"]["name_en"] in ("", None) or "9060" in store.augments["9060"]["name_en"]


def test_card_seen_after_the_last_fetch_is_asked_at_once_even_right_after_a_refresh(tmp_path, monkeypatch):
    # 首次启动的顺序：6 小时资料刷新刚取完字典，紧接着下载的新统计数据才带来新卡。不能等一小时。
    store, transport = _store(tmp_path, monkeypatch, {"1001", "9060"})
    transport.augments.append({"id": 9060, "nameTRA": "One Hit Wonder", "rarity": "kGold"})
    assert time.time() - store._family_at("augments") < 60

    store.refresh()

    assert store.augments["9060"]["name_en"] == "One Hit Wonder"
    assert len(_augment_calls(transport)) == 1


def test_still_missing_name_is_asked_again_after_an_hour(tmp_path, monkeypatch):
    store, transport = _store(tmp_path, monkeypatch, {"1001", "9060"})
    store.refresh()
    transport.augments.append({"id": 9060, "nameTRA": "One Hit Wonder", "rarity": "kGold"})
    store._names_tried_at -= 3601

    store.refresh()

    assert store.augments["9060"]["name_en"] == "One Hit Wonder"
    assert len(_augment_calls(transport)) == 2
    assert "One Hit Wonder" in (tmp_path / "data" / "static.json").read_text(encoding="utf-8")


def test_named_augments_cause_no_extra_requests(tmp_path, monkeypatch):
    store, transport = _store(tmp_path, monkeypatch, {"1001"})

    store.refresh()

    assert _augment_calls(transport) == []
