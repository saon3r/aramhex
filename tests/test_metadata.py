"""公开元数据：Data Dragon 英雄/装备、CommunityDragon 海克斯、英文显示名。

只用随包的中文/英文名字表和内联的小样本，不联网、不读 fixtures。
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from lolhex.data import metadata

DATA = Path(metadata.__file__).parent
I18N = json.loads((DATA / "i18n.json").read_text(encoding="utf-8"))
BUNDLED_AUGMENTS = json.loads((DATA / "bundled" / "augments.json").read_text(encoding="utf-8"))
BUNDLED_HEROES = json.loads((DATA / "bundled" / "heroes.json").read_text(encoding="utf-8"))
DD = "https://ddragon.leagueoflegends.com/cdn"
CD = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default"
CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")


# ---------- 版本 ----------

@pytest.mark.parametrize("raw,expected", [
    ("16.21.1", "16.21"),
    ("16.21", "16.21"),
    (" 16.21.1 ", "16.21"),
    ("16.21.1.2", "16.21"),
    ("", ""),
    ("   ", ""),
    ("abc", ""),
    ("16", ""),
    ("16.x", ""),
    ("16.21.1-beta", ""),
    (None, ""),
])
def test_normalize_patch_exact_cases(raw, expected):
    assert metadata.normalize_patch(raw) == expected


# ---------- Data Dragon 英雄 ----------

def _champion(alias="Ahri", key="103", name="Ahri", title="the Nine-Tailed Fox",
              tags=("Mage", "Assassin"), image=None):
    return {"id": alias, "key": key, "name": name, "title": title, "tags": list(tags),
            "image": {"full": f"{alias}.png" if image is None else image}}


def test_parse_champions_normalized_and_rejects_bad_records():
    payload = {"type": "champion", "data": {
        "Ahri": _champion(),
        "Teemo": _champion("Teemo", "17", "Teemo", "the Swift Scout", ("Marksman", "Assassin")),
        "../Evil": _champion("../Evil", "999"),
        "NoKey": _champion("NoKey", "abc"),
        "Absolute": _champion("Absolute", "998", image="https://evil.example/Absolute.png"),
        "Traversal": _champion("Traversal", "997", image="../Ahri.png"),
        "BadAlias": _champion("Bad/Alias", "996"),
    }}
    before = copy.deepcopy(payload)

    out = metadata.parse_champions(payload, "16.21.1")

    assert set(out) == {"103", "17"}          # 结果按数字英雄 ID 索引，不是 alias
    a = out["103"]
    assert a["id"] == "103" and a["alias"] == "Ahri"
    assert "Ahri" not in out
    assert a["icon"] == f"{DD}/16.21.1/img/champion/Ahri.png"
    assert a["roles"] == ["Mage", "Assassin"]
    assert a["name_en"] == "Ahri" and a["nick_en"] == "the Nine-Tailed Fox"
    # 中文识别名来自 i18n 的 zh_CN 表：[称号, 名字]；英文另存，不覆盖引擎用的字段
    zh = I18N["heroes"]["103"]["zh_CN"]
    assert a["name"] == zh[1] == "阿狸" and a["nick"] == zh[0] == "九尾妖狐"
    assert a["name"] != a["name_en"]
    # 搜索关键词：英文 alias/名/称号都在，中文名字另有字段
    assert "Ahri" in a["keywords"] and "the Nine-Tailed Fox" in a["keywords"]
    assert payload == before


def test_parse_champions_keyed_by_numeric_hero_id_not_alias():
    payload = {"data": {"Ahri": _champion()}}
    out = metadata.parse_champions(payload, "16.21.1")
    assert set(out) == {"103"}
    assert out["103"]["alias"] == "Ahri" and out["103"]["id"] == "103"
    assert "Ahri" not in out


def test_parse_champions_keeps_alias_image_and_english_name_distinct():
    payload = {"data": {
        "Nunu": _champion("Nunu", "20", "Nunu & Willump", "the Boy and His Yeti"),
        "MonkeyKing": _champion("MonkeyKing", "62", "Wukong", "the Monkey King"),
        "Renata": _champion("Renata", "888", "Renata Glasc", "the Chem-Baroness"),
    }}
    out = metadata.parse_champions(payload, "16.21.1")
    assert set(out) == {"20", "62", "888"}
    assert out["20"]["alias"] == "Nunu" and out["20"]["name_en"] == "Nunu & Willump"
    assert out["20"]["icon"].endswith("/Nunu.png")
    assert out["62"]["alias"] == "MonkeyKing" and out["62"]["name_en"] == "Wukong"
    assert out["62"]["icon"].endswith("/MonkeyKing.png")
    assert out["888"]["alias"] == "Renata" and out["888"]["name_en"] == "Renata Glasc"
    assert out["888"]["icon"].endswith("/Renata.png")


def test_parse_champions_rejects_schema_and_bad_version():
    for bad in (None, [], {}, {"data": []}, {"data": None}):
        with pytest.raises(ValueError):
            metadata.parse_champions(bad, "16.21.1")
    with pytest.raises(ValueError):
        metadata.parse_champions({"data": {}}, "16.21.1/../../x")
    with pytest.raises(ValueError):
        metadata.parse_champions({"data": {}}, "")


def test_parse_champions_does_not_paste_english_into_chinese_fields():
    payload = {"data": {"NewChamp": _champion("NewChamp", "999999", "New Champ", "the New")}}
    rec = metadata.parse_champions(payload, "16.21.1")["999999"]
    assert rec["alias"] == "NewChamp"
    assert rec["name"] == "" and rec["nick"] == ""      # 中文表没有就留空，不退回英文
    assert rec["name_en"] == "New Champ" and rec["nick_en"] == "the New"


# ---------- Data Dragon 装备 ----------

def test_parse_items_english_name_and_fixed_icon():
    payload = {"type": "item", "data": {
        "1001": {"name": "Boots", "plaintext": "Slightly increases Movement Speed.",
                 "gold": {"total": 300}, "image": {"full": "1001.png"}},
        "abc": {"name": "Bad", "image": {"full": "abc.png"}},
        "1002": {"name": "Bad", "image": {"full": "https://evil.example/1002.png"}},
        "1003": {"name": "Bad", "image": {"full": "../1003.png"}},
        "1004": {"name": "", "image": {"full": "1004.png"}},
    }}
    before = copy.deepcopy(payload)

    out = metadata.parse_items(payload, "16.21.1")

    assert set(out) == {"1001"}
    boots = out["1001"]
    assert boots == {"id": "1001", "name": "Boots", "icon": f"{DD}/16.21.1/img/item/1001.png",
                     "desc": "Slightly increases Movement Speed.", "price": 300}
    assert payload == before
    with pytest.raises(ValueError):
        metadata.parse_items({"data": {}}, "16.21.1/../x")
    with pytest.raises(ValueError):
        metadata.parse_items([], "16.21.1")


# ---------- CommunityDragon 海克斯 ----------

def _augment(aid, name="Titan's Resolve", rarity="kPrismatic",
             icon="ASSETS/UX/Cherry/Augments/Icons/Titan.png"):
    return {"id": aid, "nameTRA": name, "augmentNameId": "ARAM_Augment_Titan",
            "rarity": rarity, "description": "<p>Gain <b>power</b>.</p>",
            "simpleDescription": "Gain power.", "augmentSmallIconPath": icon}


def test_parse_augments_normalizes_and_keeps_english_separate():
    payload = [
        _augment(1001),
        _augment(1002, "Apex Inventor", "kGold", "ASSETS/UX/Cherry/Augments/Icons/Apex.PNG"),
        _augment(999999, "Mystery", "kBogus", None),
    ]
    before = copy.deepcopy(payload)

    out = metadata.parse_augments(payload)

    assert set(out) == {"1001", "1002", "999999"}
    titan = out["1001"]
    assert titan["name"] == I18N["augments"]["1001"]["zh_CN"] == "泰坦的坚决"
    assert titan["name_en"] == "Titan's Resolve" and titan["name"] != titan["name_en"]
    assert titan["rarity"] == "prismatic"
    assert titan["icon"] == f"{CD}/assets/ux/cherry/augments/icons/titan.png"
    assert out["1002"]["rarity"] == "gold"
    assert out["1002"]["icon"].endswith("/apex.png")
    assert out["999999"] == {"id": "999999", "name": "", "name_en": "Mystery", "rarity": "unknown",
                             "desc": "Gain power.", "icon": "", "modes": [], "new": False}
    assert payload == before


def test_parse_augments_can_pin_modes_and_new_flags_for_the_store():
    out = metadata.parse_augments([_augment(1001), _augment(1002)], {"1001", "1002"},
                                 modes=("KIWI",), new_ids={"1002"})
    assert out["1001"]["modes"] == ["KIWI"] and out["1001"]["new"] is False
    assert out["1002"]["modes"] == ["KIWI"] and out["1002"]["new"] is True


def test_parse_augments_selects_by_active_id_not_aram_or_kiwi_heuristic():
    active = set(BUNDLED_AUGMENTS)
    cherry = ["1332", "1416", "2091", "2116", "2129", "2135"]
    payload = [{"id": int(aid), "nameTRA": "ARAM_Augment_Internal",
                "augmentNameId": "ARAM_Augment_Internal", "rarity": "kGold",
                "augmentSmallIconPath": "ASSETS/UX/Cherry/Augments/Icons/Cherry.png"}
               for aid in cherry]
    payload.append({"id": 999999, "nameTRA": "ARAM_Augment_NotActive",
                    "augmentSmallIconPath": "ASSETS/UX/Kiwi/Icons/Kiwi.png"})

    out = metadata.parse_augments(payload, active)

    assert set(out) == set(cherry)
    for aid in cherry:
        assert out[aid]["name_en"] == I18N["augments"][aid]["en_US"]
        assert out[aid]["name"] == I18N["augments"][aid]["zh_CN"]
    # 不带 active_ids 时按自身 ID 收，证明没有靠 ARAM_/kiwi 路径筛
    assert "999999" in metadata.parse_augments(payload)


def test_parse_augments_covers_all_232_bundled_active_ids():
    payload = [{"id": int(aid), "nameTRA": I18N["augments"][aid]["en_US"],
                "rarity": "kSilver", "augmentSmallIconPath": "ASSETS/UX/Cherry/Augments/Icons/X.png"}
               for aid in BUNDLED_AUGMENTS]
    payload.append({"id": 999999, "nameTRA": "Not Bundled", "rarity": "kGold"})

    out = metadata.parse_augments(payload, set(BUNDLED_AUGMENTS))

    assert set(out) == set(BUNDLED_AUGMENTS) and len(out) == 232
    for aid in BUNDLED_AUGMENTS:
        assert out[aid]["name"] == I18N["augments"][aid]["zh_CN"]
        assert out[aid]["name_en"] == I18N["augments"][aid]["en_US"]


def test_parse_augments_rejects_schema_and_unsafe_icons():
    with pytest.raises(ValueError):
        metadata.parse_augments({"id": 1})

    payload = [
        _augment(1001, icon="https://evil.example/x.png"),
        _augment(1002, "Apex Inventor", "kGold", "ASSETS/../../evil.png"),
        _augment(1003, "Back To Basics", "kSilver", "ASSETS/x.png?token=1"),
        {"id": 1004, "nameTRA": "ARAM_Augment_Internal", "rarity": "kSilver",
         "augmentSmallIconPath": "/lol-game-data/assets/UX/Cherry/Augments/Icons/Back.png"},
        {"id": "abc", "nameTRA": "Bad"},
        {"id": True, "nameTRA": "Bad"},
        "not-a-record",
    ]
    out = metadata.parse_augments(payload)

    assert set(out) == {"1001", "1002", "1003", "1004"}
    assert all(out[aid]["icon"] == "" for aid in ("1001", "1002", "1003"))
    assert out["1004"]["icon"] == f"{CD}/assets/ux/cherry/augments/icons/back.png"
    assert out["1004"]["name_en"] == I18N["augments"]["1004"]["en_US"]
    assert "ARAM_" not in out["1004"]["name_en"]


def test_parse_augments_unknown_english_falls_back_without_internal_names():
    out = metadata.parse_augments([
        {"id": 999999, "nameTRA": "", "rarity": "kSilver"},
        {"id": 999998, "nameTRA": "泰坦的坚决", "rarity": "kSilver"},
    ])
    assert out["999999"]["name_en"] == "Augment 999999" and out["999999"]["name"] == ""
    assert out["999998"]["name_en"] == "Augment 999998"
    assert not CJK.search(out["999998"]["name_en"])


# ---------- 英文显示名 ----------

def test_all_232_bundled_augments_have_english_display_names():
    assert len(BUNDLED_AUGMENTS) == 232
    for aid, meta in BUNDLED_AUGMENTS.items():
        expected = I18N["augments"][aid]["en_US"]
        name = metadata.display_augment_name(aid)
        assert name == expected and not name.startswith("Augment ")
        assert metadata.display_augment_name(int(aid)) == expected
        assert "ARAM_" not in name and not CJK.search(name)


def test_all_173_bundled_heroes_have_english_display_names():
    assert len(BUNDLED_HEROES) == 173
    for hid in BUNDLED_HEROES:
        name, title = I18N["heroes"][hid]["en_US"]
        assert metadata.display_hero_name(hid) == name and not CJK.search(name)
        assert metadata.display_hero_title(hid) == title and not CJK.search(title)
        assert metadata.display_hero_name(int(hid)) == name


def test_display_fallbacks_are_neutral_and_never_chinese():
    assert metadata.display_hero_name(999999) == "Champion 999999"
    assert metadata.display_augment_name("999999") == "Augment 999999"
    assert metadata.display_hero_name(None) == "Champion"
    assert metadata.display_augment_name("") == "Augment"
    assert metadata.display_hero_title(999999) == ""
    assert not CJK.search(metadata.display_hero_name("abc"))
    assert not CJK.search(metadata.display_augment_name("abc"))


def test_rarity_labels_live_in_the_neutral_metadata_module():
    """临时中文显示标签留在数据层，推荐/界面不再 import 已删除的 tencent。"""
    assert metadata.RARITY_CN == {"silver": "白银", "gold": "黄金", "prismatic": "棱彩"}
    from lolhex import recommend
    assert recommend.RARITY_CN is metadata.RARITY_CN


def test_display_accessors_do_not_touch_recognition_tables():
    from lolhex import i18n

    assert i18n.augment_names("zh_CN") == {} and i18n.hero_names("zh_CN") == {}
    metadata.display_augment_name("1001")
    metadata.display_hero_name("103")
    assert i18n.augment_names("zh_CN") == {} and i18n.hero_names("zh_CN") == {}
