from conftest import fixture

from lolhex.data import tencent


def test_static_parsers():
    heroes = tencent.parse_hero_list(fixture("tencent_hero_list.json"))
    assert heroes["17"]["name"] == "提莫" and heroes["17"]["nick"] == "迅捷斥候" and heroes["17"]["alias"] == "Teemo"
    augs = tencent.parse_kiwi_augments(fixture("tencent_kiwi_augments.json"))
    assert augs["1001"]["name"] == "泰坦的坚决" and augs["1001"]["rarity"] == "prismatic"
    assert "<" not in augs["1001"]["desc"]
    arena = tencent.parse_kiwi_augments([{"augmentID": 9, "name_cn": "x", "mode": "CHERRY, KIWI", "level": "kGold"}])
    assert arena["9"]["modes"] == ["CHERRY", "KIWI"]
    spells = tencent.parse_hero_spells(fixture("tencent_hero17_spells.json"))
    assert spells["Q"]["name"] == "致盲吹箭"
