"""静态资料：抓取、落盘、按需刷新。

目录：<app_home>/data/
  static.json        英雄、海克斯字典、装备、召唤师技能、版本

腾讯官方单英雄出装、加点、层级已移除，不再有 hero/<id>.json，也不会从旧磁盘缓存复活官方层级。
网络失败时继续使用旧缓存，并在 status() 里标明，界面据此提示"官方资料可能过期"。
胜率统计不在这里，见 public.py（自采统计数据）。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from . import http, tencent

log = logging.getLogger(__name__)

CDRAGON_AUG = ("https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/"
               "global/zh_cn/v1/cherry-augments.json")
CDRAGON_RARITY = {"kSilver": "silver", "kGold": "gold", "kPrismatic": "prismatic"}

_ALIASES: dict[str, list[str]] | None = None


def hero_aliases() -> dict[str, list[str]]:
    """玩家常用叫法，随安装包带：hero_aliases.json（来源：Hexdata，hexdata.com.cn）
    + hero_nicknames.json（网上常见外号，人工整理）。"""
    global _ALIASES
    if _ALIASES is None:
        _ALIASES = {}
        for name, key in (("hero_aliases.json", "aliases"), ("hero_nicknames.json", "nicknames")):
            try:
                d = json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))[key]
            except (OSError, ValueError, KeyError):
                continue
            for hid, names in d.items():
                _ALIASES.setdefault(hid, []).extend(names)
    return _ALIASES


def _read(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class DataStore:
    def __init__(self, root: Path, refresh_hours: float = 6.0):
        self.root = Path(root)
        self.refresh_s = refresh_hours * 3600
        self._lock = threading.RLock()
        self.static: dict = _read(self.root / "static.json") or {}
        self.ranks: dict = {}
        self.last_error: str | None = None

    # ---------- 刷新 ----------

    def _stale(self, blob: dict) -> bool:
        return not blob or time.time() - blob.get("fetched_at", 0) > self.refresh_s

    def refresh(self, force: bool = False) -> None:
        self.last_error = None
        if force or self._stale(self.static) or not all("roles" in h for h in self.heroes.values()):
            try:
                self._refresh_static()
            except Exception as e:  # 网络失败：继续用旧缓存
                log.warning("刷新官方资料失败：%s", e)
                self.last_error = f"官方资料：{e}"

    def _refresh_static(self) -> None:
        heroes = tencent.parse_hero_list(tencent.fetch_hero_list())
        augments = tencent.parse_kiwi_augments(tencent.fetch_kiwi_augments())
        items = tencent.parse_items(tencent.fetch_items())
        try:
            spells = tencent.parse_summoner_spells(tencent.fetch_summoner_spells())
        except Exception as e:
            log.info("召唤师技能列表获取失败：%s", e)
            spells = self.static.get("spells", {})
        try:
            versions = tencent.fetch_versions()
        except Exception:
            versions = self.static.get("versions", [])
        try:
            self._merge_cdragon(augments)
        except Exception as e:
            log.info("CommunityDragon 补充失败：%s", e)
        patch = versions[0]["name"] if versions else self.static.get("patch", "")
        with self._lock:
            self.static = {"fetched_at": time.time(), "patch": patch, "versions": versions[:6],
                           "heroes": heroes, "augments": augments, "items": items, "spells": spells}
            _write(self.root / "static.json", self.static)

    @staticmethod
    def _merge_cdragon(augments: dict) -> None:
        """腾讯 kiwi 列表偶尔缺条目，用 CommunityDragon 中文数据补名字和稀有度。"""
        raw = http.get_json(CDRAGON_AUG, timeout=30)
        for a in raw:
            aid = str(a.get("id"))
            name_id = str(a.get("augmentNameId", ""))
            icon = str(a.get("augmentSmallIconPath", ""))
            is_mayhem = name_id.startswith("ARAM_") or "kiwi" in icon.lower()
            if aid in augments or not is_mayhem or not a.get("nameTRA"):
                continue
            augments[aid] = {"id": aid, "name": a["nameTRA"].strip(), "en": name_id,
                             "rarity": CDRAGON_RARITY.get(a.get("rarity"), "unknown"),
                             "desc": "", "icon": "", "modes": ["KIWI"], "source": "cdragon"}

    # ---------- 查询 ----------

    @property
    def augments(self) -> dict[str, dict]:
        return self.static.get("augments", {})

    @property
    def heroes(self) -> dict[str, dict]:
        return self.static.get("heroes", {})

    def provisional_augments(self) -> dict[str, dict]:
        """过渡数据里暂用测试服统计的新海克斯 {ID: {games, wins, win_rate, source}}。只有公开数据集有这一项。"""
        return {}

    def excluded_augments(self) -> dict[str, str]:
        """统计里剔除的海克斯 {ID: 原因}（胜率不可信，不打分）。只有公开数据集有这一项。"""
        return {}

    @property
    def items(self) -> dict[str, dict]:
        return self.static.get("items", {})

    @property
    def spells(self) -> dict[str, dict]:
        return self.static.get("spells", {})

    def mayhem_augments(self) -> dict[str, dict]:
        """用于识别匹配的字典：只要大乱斗（KIWI）海克斯，排除纯斗魂竞技场条目。"""
        from ..recommend import HIDDEN_AUGMENTS
        out = {}
        for aid, a in self.augments.items():
            if aid in HIDDEN_AUGMENTS or not a.get("name"):  # 五杀乐队的标记这类没名字的，认不出也不该认
                continue
            modes = a.get("modes") or []
            if not modes or any(m.startswith("KIWI") for m in modes):
                out[aid] = a
        return out

    def hero_terms(self, hid: str) -> list[str]:
        """能搜到这个英雄的所有叫法：名字、称号、英文名、腾讯关键词（含拼音缩写）、玩家叫法。"""
        h = self.heroes.get(hid) or {}
        raw = [h.get("name"), h.get("nick"), h.get("alias"), *(h.get("keywords") or "").split(","),
               *hero_aliases().get(hid, [])]
        out, seen = [], set()
        for t in raw:
            t = (t or "").strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out

    def resolve_hero(self, key: str | int | None) -> str | None:
        """按 heroId / 英文 alias / 中文名 / 称号找英雄；
        再按别名（腾讯关键词、玩家叫法）精确匹配。"""
        if key in (None, "", 0, "0"):
            return None
        k = str(key).strip()
        if k in self.heroes:
            return k
        if k.startswith("game_character_displayname_"):
            k = k[len("game_character_displayname_"):]
        kl = k.lower()
        for hid, h in self.heroes.items():
            if kl in ((h.get("alias") or "").lower(), (h.get("name") or "").lower(),
                      (h.get("nick") or "").lower()):
                return hid
        for hid in self.heroes:
            if kl in (t.lower() for t in self.hero_terms(hid)):
                return hid
        for hid, h in self.heroes.items():
            full = f"{h.get('nick', '')} {h.get('name', '')}".lower()
            if kl and kl in full:
                return hid
        if not kl.isascii():  # 中文外号的一部分，如"风男"→快乐风男
            for hid in self.heroes:
                if any(kl in t for t in self.hero_terms(hid) if not t.isascii()):
                    return hid
        return None

    # 统计数据由子类（PublicStore）提供；这里保留统计接口，没有统计时返回 None。
    def hero(self, hero_id: str, allow_network: bool = True) -> dict | None:
        return self.win_data(hero_id, allow_network)

    def win_data(self, hero_id: str, allow_network: bool = True) -> dict | None:
        return None

    def status(self) -> dict:
        return {
            "patch": self.static.get("patch"),
            "static_at": self.static.get("fetched_at"),
            "augments": len(self.augments),
            "heroes": len(self.heroes),
            "error": self.last_error,
        }
