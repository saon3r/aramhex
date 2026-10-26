"""单英雄资料面板：胜率与评级、海克斯全表、自采统计的召唤师技能与装备。主窗口和游戏内浮窗共用。
腾讯官方出装、加点、搭档和原画已移除，不再读取官方层级。"""

from __future__ import annotations

from . import recommend
from .messages import tr


# 召唤师技能组合：出场 ≥3% 且至少 1000 局的都放，按胜率排，最多三组（v1.1.5：
# 以前是 ≥10%、最多两组，26 个英雄因此藏掉了胜率更高的一组）。一组都不够格时（极少见）放出场最多的那一组。
SUMMONER_MIN_PICK = 0.03
SUMMONER_MIN_GAMES = 1000
SUMMONER_SHOW = 3


def sort_summoners(rows: list[dict]) -> list[dict]:
    enough = sorted((r for r in rows if r["pick"] >= SUMMONER_MIN_PICK
                     and (r.get("games") or 0) >= SUMMONER_MIN_GAMES), key=lambda r: -r["win"])
    return enough[:SUMMONER_SHOW] or sorted(rows, key=lambda r: -r["games"])[:1]


def hero_panel(store, hero_key, k: int = 300) -> dict | None:
    hid = store.resolve_hero(hero_key)
    if not hid:
        return None
    data = store.hero(hid) or {}
    ag = store.win_data(hid) or {}
    ag_augs = ag.get("augments") or {}
    # 测试服数据的新海克斯：只显示测试服胜率，不算 Δ，不进「推荐海克斯」排行（不是同一个版本的数据）
    provisional = store.provisional_augments() if hasattr(store, "provisional_augments") else {}
    blend = recommend.band_blend(store, hid, ag, k)  # 选了分段：Δ 和三选一一样按分段、全体综合

    augs = []
    for a in data.get("augments", []):
        meta = store.augments.get(a["id"], {})
        x = ag_augs.get(a["id"]) or {}
        d = None
        if a["id"] in provisional:
            pass
        elif blend is not None:
            d = (blend.get(a["id"]) or {}).get("delta")
        elif x.get("win") is not None and x.get("games") and ag.get("sample_win") is not None:
            d = recommend.smoothed_delta(x["win"], x["games"], ag["sample_win"], k)
        augs.append({**a, "name": recommend.augment_label(a["id"], meta), "icon": meta.get("icon"),
                     "desc": meta.get("desc"), "win": x.get("win"), "games": x.get("games"),
                     "source": ("pbe" if a["id"] in provisional else "public") if x else None,
                     "delta": None if d is None else round(d, 2),
                     "sample": recommend.sample_level(((blend or {}).get(a["id"]) or {}).get("games_all")
                                                      or x.get("games"))})

    items = store.items

    def item(i, name=None):
        it = items.get(str(i), {})
        return {"id": str(i), "name": it.get("name") or name or str(i), "icon": it.get("icon")}

    # 自采统计的召唤师技能、装备（数据里有 hero_spells.json / hero_items.json 才有）
    summoners, sum_src, item_stats = [], "", []
    if hasattr(store, "hero_spells"):
        spells = store.spells
        rows, sum_src = store.hero_spells(hid)
        summoners = [{**r, "spells": [{"id": x, "name": (spells.get(x) or {}).get("name") or x,
                                       "icon": (spells.get(x) or {}).get("icon")} for x in r["spells"]]}
                     for r in sort_summoners(rows)]
        rows, _ = store.hero_items(hid)
        item_stats = [{**r, "item": item(r["item"])} for r in rows[:6]]
    rank = (store.ranks.get("heroes") or {}).get(hid, {})
    n_heroes = len(store.ranks.get("heroes") or {}) or None
    return {
        "hero": store.heroes.get(hid),
        "rank": {**rank, "total": n_heroes},
        "augments": augs,
        "date": data.get("date"), "patch": store.static.get("patch"),
        "data_patch": ag.get("patch"), "data_revision": (store.status().get("dataset_revision")),
        "win_source": ag.get("label") or tr("data.no_stats"), "summoners": summoners,
        "summoner_source": sum_src if summoners else "", "summoner_source_date": str(getattr(getattr(store, "dataset", None), "snapshot_at", "") or "")[:10] or None,
        "item_stats": item_stats,
    }
