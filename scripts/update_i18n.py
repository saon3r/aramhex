"""外服用的名字表：海克斯名、英雄名和选英雄界面上的字，英文、韩文、日文、繁中（外加简中用来核对）。

    python scripts/update_i18n.py [--out lolhex/data/i18n.json]

来源都是拳头公开数据（维护脚本，不随程序运行）：
- 海克斯：CommunityDragon 的 kiwi.bin.json（AugmentPlatformId 就是游戏里的海克斯 ID）+ 各语言 lol.stringtable.json。
  正式服（latest）和测试服（pbe）都取，正式服优先；测试服补上还没上线的新海克斯。
  stringtable 里新加的键是哈希：小写键名的 xxh3_64 取低 38 位，写成 {%010x}（要装 xxhash，只有这个脚本用）。
- 英雄：Data Dragon 各语言 champion.json 的 name 和 title（按 key 即英雄数字 ID）。
- 选英雄界面：rcp-fe-lol-champ-select 的 trans.json（预选栏左边的「可用」、开局选卡的「选择你的英雄」）。
不再下载/核对任何腾讯接口。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CD = "https://raw.communitydragon.org"
DD = "https://ddragon.leagueoflegends.com"
# 程序里的语言代码 → CommunityDragon 目录名
# ko_KR 不生成：韩服选项和韩文识别模型都已移除，名字表里留着也永远选不到
LANGS = {"zh_CN": "zh_cn", "zh_TW": "zh_tw", "en_US": "en_us", "ja_JP": "ja_jp"}
UI_KEYS = {"bench": "champion_bench_label", "pick": "subset-champions-grid-header"}


def get_json(url: str):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.json()


def lookup(table: dict, key: str) -> str | None:
    k = key.lower()
    if k in table:
        return table[k]
    import xxhash
    for fn in (xxhash.xxh3_64_intdigest, xxhash.xxh64_intdigest):
        for bits in (38, 40):
            h = "{%010x}" % (fn(k.encode()) & ((1 << bits) - 1))
            if h in table:
                return table[h]
    return None


def augments(branch: str) -> dict[str, dict[str, str]]:
    kiwi = get_json(f"{CD}/{branch}/game/maps/modespecificdata/kiwi.bin.json")
    tra = {str(v["AugmentPlatformId"]): v["NameTra"] for v in kiwi.values()
           if isinstance(v, dict) and v.get("__type") == "AugmentData" and v.get("AugmentPlatformId") and v.get("NameTra")}
    out: dict[str, dict[str, str]] = {}
    for lang, d in LANGS.items():
        table = get_json(f"{CD}/{branch}/game/{d}/data/menu/en_us/lol.stringtable.json")["entries"]
        for aid, key in tra.items():
            name = lookup(table, key)
            if name and name.strip():
                out.setdefault(aid, {})[lang] = name.strip()
    print(f"{branch}: {len(tra)} 个海克斯，有名字的 {len(out)} 个")
    return out


def heroes() -> tuple[str, dict[str, dict[str, list[str]]]]:
    ver = get_json(f"{DD}/api/versions.json")[0]
    out: dict[str, dict[str, list[str]]] = {}
    for lang in LANGS:
        for c in get_json(f"{DD}/cdn/{ver}/data/{lang}/champion.json")["data"].values():
            out.setdefault(str(c["key"]), {})[lang] = [c["name"], c["title"]]
    return ver, out


def ui_texts() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {k: {} for k in UI_KEYS}
    for lang, d in LANGS.items():
        t = get_json(f"{CD}/latest/plugins/rcp-fe-lol-champ-select/global/{d}/trans.json")
        for k, key in UI_KEYS.items():
            if t.get(key):
                out[k][lang] = t[key]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="外服名字表")
    ap.add_argument("--out", type=Path, default=ROOT / "lolhex" / "data" / "i18n.json")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    aug = augments("pbe")
    aug.update(augments("latest"))  # 正式服的名字优先
    ver, hero = heroes()
    ui = ui_texts()

    print("选英雄界面：", json.dumps(ui, ensure_ascii=False))

    out = {"_说明": "外服名字表，scripts/update_i18n.py 生成。augments/heroes 用游戏同一套数字 ID；heroes 每种语言是 [名字, 称号]。",
           "ddragon": ver, "augments": dict(sorted(aug.items(), key=lambda kv: int(kv[0]))),
           "heroes": dict(sorted(hero.items(), key=lambda kv: int(kv[0]))), "ui": ui}
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=False) + "\n", encoding="utf-8")
    print(f"写入 {a.out}：海克斯 {len(aug)} 个、英雄 {len(hero)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
