"""腾讯国服公开数据（101.qq.com / 掌盟同源）。

静态资料 game.gtimg.cn：英雄、海克斯（kiwi）、装备、召唤师技能；版本号仍从 mlol 取。
统计相关的网络入口和解析（英雄榜、海克斯榜、单英雄的出装/加点/官方层级）已移除，
Task 4 换静态元数据时连同本文件一起删除。

这些接口没有公开文档，字段含义按 101.qq.com 前端的用法与数值核对得出；
解析函数都是纯函数，接口变了只需改这里和对应测试。
"""

from __future__ import annotations

import re

from . import http

GTIMG = "https://game.gtimg.cn/images/lol/act/img"
MLOL = "https://mlol.qt.qq.com/go"
REFERER = "https://101.qq.com/"

RARITY = {"kSilver": "silver", "kGold": "gold", "kPrismatic": "prismatic"}
RARITY_CN = {"silver": "白银", "gold": "黄金", "prismatic": "棱彩"}


# ---------- 抓取 ----------

def fetch_versions() -> list[dict]:
    return http.get_json(f"{MLOL}/database/versionlist?zone=lol&from=h5", referer=REFERER)["data"]


def fetch_hero_list() -> dict:
    return http.get_json(f"{GTIMG}/js/heroList/hero_list.js")


def fetch_kiwi_augments() -> list:
    return http.get_json(f"{GTIMG}/js/kiwi/kiwi_augments.json")


def fetch_items() -> dict:
    return http.get_json(f"{GTIMG}/js/items/items.js")


def fetch_summoner_spells() -> dict:
    return http.get_json(f"{GTIMG}/js/summonerskillList/summonerskill_list.js")


# ---------- 解析 ----------

# 单英雄出装/加点/官方层级、英雄榜、海克斯榜的网络入口和解析都已移除；
# 下面只保留静态资料的纯解析函数。Task 4 换静态元数据时连同 tencent.py 一起删除。

def _i(x) -> int | None:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def parse_hero_list(raw: dict) -> dict[str, dict]:
    heroes = {}
    for h in raw.get("hero", []):
        hid = str(h["heroId"])
        heroes[hid] = {
            "id": hid,
            # 腾讯的 name 是称号（迅捷斥候），title 是英雄名（提莫）；这里反过来存更直观。
            "name": h.get("title") or h.get("name"),
            "nick": h.get("name"),
            "alias": h.get("alias"),
            "icon": f"{GTIMG}/champion/{h.get('alias')}.png",
            "keywords": h.get("keywords", ""),
            # 定位：fighter 战士 / mage 法师 / assassin 刺客 / tank 坦克 / marksman 射手 / support 辅助，主定位在前
            "roles": list(h.get("roles") or []),
        }
    return heroes


_TAG = re.compile(r"<[^>]+>")


def parse_kiwi_augments(raw: list) -> dict[str, dict]:
    out = {}
    for a in raw:
        aid = str(a["augmentID"])
        modes = [m.strip() for m in str(a.get("mode", "")).split(",") if m.strip()]
        out[aid] = {
            "id": aid,
            "name": a.get("name_cn", "").strip(),
            "en": a.get("name_en", ""),
            "rarity": RARITY.get(a.get("level", ""), "unknown"),
            "desc": _TAG.sub("", a.get("tooltip") or a.get("desc") or "").strip(),
            "icon": a.get("small_Icon") or a.get("large_Icon") or "",
            "modes": modes,
            "new": bool(a.get("isPBE") or a.get("isNew")),  # 测试服 / 刚上线的新海克斯：统计里还没有它
        }
    return out


def parse_summoner_spells(raw: dict) -> dict[str, dict]:
    """召唤师技能：id 与 Riot 一致（4 闪现、14 引燃、32 标记…），带官方图标。"""
    out = {}
    for sid, s in (raw.get("summonerskill") or {}).items():
        if s.get("name") and s.get("icon"):
            out[str(sid)] = {"id": str(sid), "name": s["name"], "icon": s["icon"]}
    return out


def parse_items(raw: dict) -> dict[str, dict]:
    out = {}
    for it in raw.get("items", []):
        iid = str(it["itemId"])
        out[iid] = {
            "id": iid,
            "name": it.get("name", ""),
            "icon": it.get("iconPath", ""),
            "desc": it.get("plaintext") or "",
            "price": _i(it.get("total")),
        }
    return out


def parse_hero_spells(raw: dict) -> dict[str, dict]:
    spells = {}
    for s in raw.get("spells", []):
        key = str(s.get("spellKey", "")).upper()
        if key in ("Q", "W", "E", "R", "PASSIVE"):
            spells[key] = {"name": s.get("name", ""), "icon": s.get("abilityIconPath", "")}
    return spells
