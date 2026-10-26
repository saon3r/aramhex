"""三选一评分：以自采统计为准，官方层级已移除。

数据来源（依次）：
1. 自采统计：本英雄 × 这个海克斯的胜率（样本足够才单独成立；可按分段）；
2. 本英雄没有数据或样本太少：自采统计里这个海克斯在所有英雄上的合计胜率，明确标 all champs；
3. 全英雄样本也不足：只显示「?」，不给数字，标无数据。

分数 = 相对该英雄基准胜率的Δ胜率（百分点）：
1. 贝叶斯平滑：smoothed = (胜率×场次 + 基准×k) / (场次 + k)，k 默认 300，小样本的高胜率会被拉回基准附近。
2. Δ = smoothed − 该英雄基准胜率。
3. 样本分档：<250 局仅参考、250–999 中等、≥1000 充足，显示在界面上。
4. 首选只在样本充足（≥1000 局）的海克斯里挑：冷门海克斯偶尔胜率高，多半是局数少碰巧打出来的。
   比同屏其他海克斯少一个数量级以上（<1/10）的，标"样本太少"并提示刷新，不管胜率多高；
   只是不足 1000 局的，不当首选、标"样本偏少"。三张都不足时仍正常比较，但明确标仅供参考：
   每张都带 sample_warning（分数、名次、首选不变），建议里写明三张（或首选那张）样本偏少。
选取率只展示，不进分数：常拿不代表强。
选了分段时（Gitea #7，10-21）：「这个海克斯比英雄平均高多少」按分段局数把分段和全体综合，
Δ = w·Δ分段 + (1−w)·Δ全体，w = 分段局数 / (分段局数 + K)，K 由数据自己估（public._band_shrink）。
分段对英雄强弱影响大，对同一英雄几个海克斯谁好影响小得多（16.20：前 5% 和娱乐局比，海克斯优势真实差别约 1 个点），
所以分段里几十局的海克斯基本按全体数据算，局数多了才按分段；样本分档和首选门槛按全体局数。显示的胜率、局数仍是分段的原始数。
过渡数据里暂用测试服统计的新海克斯（数据集 provisional_augments）：先用它在测试服所有英雄上的合计胜率打底
（底 = 英雄基准 + 合计胜率相对 50% 的差，按合计局数平滑），再用本英雄在测试服的局数微调；
不参与上面的样本分档和"样本太少"判断，也不参与同稀有度胜率排名（不是同一个版本的数据），理由里写明测试服数据。
统计里剔除的海克斯（数据集 excluded_augments，如尊我为王：完成任务后被替换，局末数据不准）标「无数据」，
不打分、不用官方层级兜底、不参与首选比较。新海克斯（腾讯列表 isPBE/isNew，或整份统计里一局都没有）也标「无数据」。
"""

from __future__ import annotations

from .data.metadata import RARITY_CN, RARITIES, augment_en  # RARITY_CN 由调用方/测试继续引用
from .messages import tr

REROLL_BELOW = -0.5  # 低于英雄基准 0.5pp 以上：可考虑刷新
REROLL_GAP = 2.0     # 比首选低 2pp 以上：可考虑刷新
RELIABLE_GAMES = 1000  # 本英雄局数达到这个数才能当首选
TOO_FEW_RATIO = 0.1    # 局数不到同屏最多那张的 1/10：样本太少，提示刷新
# 显示用的说明文字都从目录取（玩家看到的是英文）；这里只留键名，方便测试和调用方引用。
NODATA_KEY = "augment.note.nodata"
NEW_KEY = "augment.note.new"
PBE_KEY = "augment.note.pbe"
# 五杀乐队（海斗 4.0）：三选一里的「重型 / 力量 / 鞭挞」三张卡分别强化 Q / W / E，「厄运」强化 R。
# 卡面标题是技能图标，只看名字不知道强化哪个技能，所以显示时补上
PENTAKILL = {"3170": "Q", "3171": "W", "3172": "E", "3173": "R"}
HIDDEN_AUGMENTS = {"3176"}  # 五杀乐队的内部标记，没有名字，不当海克斯显示
WEAPON_OF_DESTINY = "3081"
PBE_DISPLAY_MIN_GAMES = 30


def win_text(row: dict) -> str:
    """显示口径独立于打分：全英雄口径明确写 all champs；没有可靠数据只显示 ?。"""
    if row.get("basis") == "global_win":
        if row.get("win") is None:
            return "?"
        text = tr("stats.win_text.all_champs", win=f"{row['win'] * 100:.1f}")
        if row.get("hero_games"):
            text = tr("stats.win_text.all_champs_hero_games", win=f"{row['win'] * 100:.1f}",
                      games=row["hero_games"])
        return text
    if row.get("display_win_scope") == "global" and row.get("display_win") is not None:
        return tr("stats.win_text.all_champs_hero_games", win=f"{row['display_win'] * 100:.1f}",
                  games=row.get("games") or 0)
    if row.get("basis") == "pbe" and (row.get("games") or 0) < PBE_DISPLAY_MIN_GAMES:
        return tr("stats.win_text.all_champs_hero_games", win=f"{row['pbe_win'] * 100:.1f}",
                  games=row.get("games") or 0)
    if row.get("win") is not None:
        return tr("stats.win_text.hero", win=f"{row['win'] * 100:.1f}")
    if row.get("verdict") == "nodata" or row.get("basis") in ("nodata", "excluded", "new"):
        return "?"
    return ""


def display_name(aid: str, name: str) -> str:
    """「重型」→「Heavy (empowers Q)」；其他海克斯原样。"""
    return (tr("augment.display.skill_name", name=name, key=PENTAKILL[aid])
            if aid in PENTAKILL and name else name)


def augment_label(aid: str, meta: dict | None) -> str:
    """玩家看到的英文名：优先数据集里的英文名，缺了用公开元数据的英文名。

    绝不回退到中文的 `name`——那是认字用的识别名，显示出来就又漏中文了。
    """
    meta = meta or {}
    return meta.get("name_en") or augment_en(aid) or aid


def pentakill_rates(store, hero_id: str | None) -> dict | None:
    """本英雄（没认出英雄时用全英雄）选五杀乐队 Q / W / E / R 的局数和胜率。一项数据都没有返回 None。
    用全体数据（不分分段）：这几张卡局数本来就少，再分段更不可信。"""
    if hero_id:
        get_all = getattr(store, "win_data_all", None)
        ag = (get_all(hero_id) if get_all else None) or store.win_data(hero_id) or {}
        augs = ag.get("augments") or {}
    else:
        augs = store.ranks.get("augments") or {}
    provisional = store.provisional_augments() if hasattr(store, "provisional_augments") else {}
    rows = []
    for aid, key in PENTAKILL.items():
        a = augs.get(aid) or {}
        if a.get("games") and a.get("win") is not None:
            meta = store.augments.get(aid) or {}
            rows.append({"augment_id": aid, "key": key, "name": augment_label(aid, meta) or key,
                         "games": a["games"], "win": a["win"]})
    if not rows:
        return None
    return {"hero": bool(hero_id), "pbe": any(r["augment_id"] in provisional for r in rows), "rows": rows}


def pentakill_text(pk: dict | None) -> str:
    """「Pentakill (this champion): Q 51.2% (3200 games)　W …」，界面直接用。"""
    if not pk:
        return ""
    parts = [tr("augment.pentakill.row", key=r["key"], win=f"{r['win'] * 100:.1f}", games=r["games"])
             for r in pk["rows"]]
    who = tr("augment.pentakill.who_hero" if pk["hero"] else "augment.pentakill.who_all")
    pbe = tr("augment.pentakill.pbe_suffix") if pk["pbe"] else ""
    return tr("augment.pentakill.title", who=who, pbe=pbe,
              rates=tr("common.list_separator").join(parts))


def sample_level(games: int | None) -> str:
    if not games:
        return "none"
    if games < 250:
        return "low"
    if games < 1000:
        return "medium"
    return "high"


SAMPLE_KEYS = {"none": "sample.none", "low": "sample.low",
               "medium": "sample.medium", "high": "sample.high"}


def sample_text(level: str) -> str:
    """样本分档的显示文字（英文在目录里）。"""
    return tr(SAMPLE_KEYS.get(level, "sample.none"))


def _supported(games: int | None) -> bool:
    """沿用 sample_level 的既有样本门槛：low（<250 局）不单独成立。"""
    return sample_level(games) in ("medium", "high")


def smoothed_delta(win: float | None, games: int | None, base: float | None, k: int) -> float | None:
    """贝叶斯平滑后的Δ胜率（百分点）。"""
    if win is None or base is None or not games:
        return None
    s = (win * games + base * k) / (games + k)
    return (s - base) * 100


def win_ranks(augments: dict, static: dict) -> dict:
    """本英雄同稀有度里按原始胜率排名；胜率相同名次相同。"""
    groups = {}
    for aid, stats in augments.items():
        win = stats.get("win")
        rarity = (static.get(aid) or {}).get("rarity")
        # 只认三档；unknown/缺失不另立第四组，避免界面冒出没有名字的排名。
        if rarity in RARITIES and type(win) in (int, float) and 0 <= win <= 1 and stats.get("games", 0) > 0:
            groups.setdefault(rarity, []).append((aid, win))
    ranks = {}
    for rows in groups.values():
        rows.sort(key=lambda row: (-row[1], row[0]))
        previous = None
        rank = 0
        for position, (aid, win) in enumerate(rows, 1):
            if previous is None or win != previous:
                rank = position
            ranks[aid] = {"rank": rank, "rank_total": len(rows), "rank_basis": "hero_rarity_win_rate"}
            previous = win
    return ranks


def band_blend(store, hero_id: str | None, ag: dict | None, k: int) -> dict | None:
    """选了分段时，本英雄每个海克斯的综合Δ（见文件开头）；没选分段或数据不全返回 None。"""
    if not hero_id or not ag or not ag.get("band") or ag.get("sample_win") is None or not hasattr(store, "win_data_all"):
        return None
    allw = store.win_data_all(hero_id)
    K = store.band_shrink()
    if not allw or not K or allw.get("sample_win") is None:
        return None
    band_augs = ag.get("augments") or {}
    out = {}
    for aid, x in (allw.get("augments") or {}).items():
        d_all = smoothed_delta(x.get("win"), x.get("games"), allw["sample_win"], k)
        if d_all is None:
            continue
        b = band_augs.get(aid) or {}
        nb = b.get("games") or 0
        if nb and b.get("win") is not None:
            w = nb / (nb + K)
            d = w * (b["win"] - ag["sample_win"]) * 100 + (1 - w) * d_all
        else:
            w, d = 0.0, d_all
        out[aid] = {"delta": d, "weight": w, "games": nb or None, "win": b.get("win") if nb else None,
                    "games_all": x["games"], "win_all": x["win"]}
    return out


def _provisional(r: dict, p: dict, mine: dict | None, base: float | None, k: int) -> dict:
    """暂用测试服统计的新海克斯：合计胜率打底，本英雄测试服局数微调。"""
    n_all, w_all = p["games"], p["win_rate"]
    lift = (w_all - 0.5) * n_all / (n_all + k)   # 合计胜率相对 50% 的差，局数少时往 0 收
    ref = 0.5 if base is None else base
    prior = ref + lift
    n = (mine or {}).get("games") or 0
    win = (mine or {}).get("win")
    smoothed = (win * n + prior * k) / (n + k) if n and win is not None else prior
    d = (smoothed - ref) * 100
    r.update(score=round(d, 2), basis="pbe", source="pbe", sample="low", games=n or None, win=win,
             pbe_games=n_all, pbe_win=w_all)
    hero_part = (tr("reason.pbe_hero", games=n, win=f"{win * 100:.1f}")
                 if n and win is not None else tr("reason.pbe_no_hero"))
    r["reasons"].append(tr("reason.pbe", n_all=n_all, w_all=f"{w_all * 100:.1f}",
                           hero_part=hero_part, delta=f"{d:+.1f}", pbe_note=tr(PBE_KEY)))
    return r


def evaluate(store, hero_id: str | None, slots: list[str | None], k: int = 300) -> dict:
    ag = store.win_data(hero_id) if hero_id else None
    source_label = getattr(store, "label", None)
    label = (source_label() if callable(source_label) else "") or tr("data.label_default")
    ag_augs = (ag or {}).get("augments") or {}
    excluded = store.excluded_augments()
    provisional = store.provisional_augments() if hasattr(store, "provisional_augments") else {}
    # 排名只在正式服统计、样本足够的海克斯之间排：测试服的新海克斯不是同一个版本的数据，只显示测试服胜率、不排名；
    # 剔除的和样本太少的都不参与。4.0 删掉的海克斯过渡数据里已经去掉，名次的分母跟着变
    blend = band_blend(store, hero_id, ag, k)
    rank_src = ({aid: {"win": (ag["sample_win"] + v["delta"] / 100), "games": v["games_all"]} for aid, v in blend.items()}
                if blend is not None else ag_augs)
    ranks_by_win = win_ranks({aid: s for aid, s in rank_src.items()
                              if aid not in provisional and aid not in excluded and _supported(s.get("games"))},
                             store.augments)
    base = (ag or {}).get("sample_win")
    if base is None and hero_id:
        base = ((store.ranks.get("heroes") or {}).get(str(hero_id)) or {}).get("win")
    global_augs = store.ranks.get("augments") or {}
    # 分子和分母只用同一批有效行（有局数且胜率不是 None），否则 win=None 的行会把均值压低。
    valid_global = [g for g in global_augs.values() if g.get("games") and g.get("win") is not None]
    total_games = sum(g["games"] for g in valid_global)
    global_mean = (sum(g["win"] * g["games"] for g in valid_global) / total_games
                   if total_games else None)

    results = []
    for idx, aid in enumerate(slots):
        r: dict = {"index": idx, "augment_id": aid, "score": None, "basis": None,
                   "verdict": "unknown", "reasons": []}
        if not aid:
            r["reasons"].append(tr("reason.unrecognised"))
            results.append(r)
            continue
        meta = store.augments.get(aid, {})
        r.update(name=display_name(aid, augment_label(aid, meta)), rarity=meta.get("rarity"),
                 icon=meta.get("icon"), desc=meta.get("desc", ""))
        if aid == WEAPON_OF_DESTINY and hero_id and hasattr(store, "augment_items"):
            hint = store.augment_items(hero_id, aid)
            if hint:
                r["item_hint"] = hint
        if aid in excluded:
            r.update(verdict="nodata", basis="excluded")
            r["reasons"].append(tr(NODATA_KEY))
            results.append(r)
            continue
        if aid in provisional:
            results.append(_provisional(r, provisional[aid], ag_augs.get(aid), base, k))
            continue
        if aid in ranks_by_win:
            r.update(ranks_by_win[aid])
            rarity = r.get("rarity")
            r["reasons"].append(tr("reason.hero_rarity_rank",
                                   rarity=tr(f"rarity.{rarity}") if rarity in RARITIES else "",
                                   rank=r["rank"], total=r["rank_total"]))

        # 1) 本英雄胜率（选了分段：分段和全体按局数综合）；样本太少不单独成立
        a = ag_augs.get(aid)
        bl = (blend or {}).get(aid)
        slot_hero_games = (bl or {}).get("games") or (a or {}).get("games")
        if bl and base is not None and _supported(bl["games_all"]):
            d = bl["delta"]
            r.update(win=bl["win"], games=bl["games"], games_all=bl["games_all"], win_all=bl["win_all"],
                     sample=sample_level(bl["games_all"]), source="public", band_weight=round(bl["weight"], 3))
            band_part = (tr("reason.band_blend",
                            label=label, games=bl["games"], win=f"{bl['win'] * 100:.1f}",
                            games_all=bl["games_all"], win_all=f"{bl['win_all'] * 100:.1f}",
                            delta=f"{d:+.1f}")
                         if bl["games"] else tr("reason.band_blend_no_band", label=label,
                                                games_all=bl["games_all"],
                                                win_all=f"{bl['win_all'] * 100:.1f}",
                                                delta=f"{d:+.1f}"))
            r["reasons"].append(band_part)
            r["score"] = round(d, 2)
            r["basis"] = "hero_win"
        elif a and a.get("win") is not None and _supported(a.get("games")) and base is not None:
            d = smoothed_delta(a["win"], a["games"], base, k)
            r.update(win=a["win"], games=a["games"], sample=sample_level(a["games"]), source="public")
            r["reasons"].append(tr("reason.hero_win", win=f"{a['win'] * 100:.1f}", games=a["games"],
                                   sample=sample_text(r["sample"]), label=label, delta=f"{d:+.1f}"))
            r["score"] = round(d, 2)
            r["basis"] = "hero_win"
        # 2) 本英雄没有数据或样本太少：全英雄合计胜率，明确标 all champs；全英雄也很少就不给数字
        if r["score"] is None and global_mean is not None:
            g = global_augs.get(aid)
            if g and g.get("win") is not None and _supported(g.get("games")):
                d = (g["win"] - global_mean) * 100
                r.update(win=g["win"], games=g.get("games"), score=round(d, 2), basis="global_win",
                         rate_label="all champs", hero_games=slot_hero_games,
                         sample=sample_level(g.get("games")), source="public")
                why = tr("reason.why_insufficient_hero" if hero_id else "reason.why_no_hero")
                r["reasons"].append(tr("reason.all_champs", why=why, win=f"{g['win'] * 100:.1f}",
                                       games=g.get("games"), delta=f"{d:+.1f}"))
            elif g and g.get("win") is not None:
                r["reasons"].append(tr("reason.all_champs_too_small"))
        # 3) 新海克斯（测试服 / 刚上线）：统计里还没有，不当成「几乎不选」去扣分。
        #    腾讯上线后可能去掉 isPBE 标记，所以整份统计里一局都没有的也算新的
        if r["score"] is None and (meta.get("new") or (global_augs and aid not in global_augs)):
            r.update(verdict="nodata", basis="new")
            r["reasons"].append(tr(NEW_KEY))
            results.append(r)
            continue
        if r["score"] is None:
            r.update(verdict="nodata", basis="nodata")
            r["reasons"].append(tr("reason.no_data"))
        results.append(r)

    # 正式服的新海克斯也沿用明确的显示口径；不改原始 win、局数、打分和首选规则。
    for r in results:
        aid = r.get("augment_id")
        g = global_augs.get(aid) or {}
        if ((store.augments.get(aid) or {}).get("new") and r.get("basis") == "hero_win"
                and (r.get("games") or 0) < PBE_DISPLAY_MIN_GAMES and _supported(g.get("games"))
                and g.get("win") is not None):
            r.update(display_win_scope="global", display_win=g["win"])
    scored = [r for r in results if r["score"] is not None]
    # 样本够不够按全体局数（选了分段时分数主要来自全体数据），没选分段就是本身的局数
    hero_sample_counts = [r.get("games_all") or r.get("games") or 0 for r in scored if r.get("basis") == "hero_win"]
    most = max(hero_sample_counts, default=0)
    for r in scored:
        if r.get("basis") != "hero_win":
            continue
        g = r.get("games_all") or r.get("games") or 0
        if most >= RELIABLE_GAMES and g < most * TOO_FEW_RATIO:
            r["thin"] = "too_few"
            r["reasons"].append(tr("reason.too_few_vs_screen", games=g))
        elif most >= RELIABLE_GAMES and g < RELIABLE_GAMES:
            r["thin"] = "few"
            r["reasons"].append(tr("reason.few_games", games=g))
        if g < RELIABLE_GAMES:
            # 可信度提示独立于同屏比较：三张都不足 1000 局也不能一声不吭。局数用全体（选了分段时的
            # games_all），分数、首选池和分段综合都仍按原规则；「样本太少」已有更重的提醒，只加一句。
            r["sample_warning"] = True
            if not r.get("thin"):
                r["reasons"].append(tr("reason.sample_reference"))

    pool = [r for r in scored if not r.get("thin")] or scored
    best = max(pool, key=lambda r: r["score"]) if pool else None
    passed = [r for r in scored if r is not best and r.get("thin") and best is not None and r["score"] > best["score"]]
    for r in scored:
        if r is best:
            r["verdict"] = "best"
        elif r.get("thin") == "too_few":
            r["verdict"] = "reroll"
        elif r.get("thin"):
            r["verdict"] = "ok"
        elif r["score"] < REROLL_BELOW or r["score"] <= best["score"] - REROLL_GAP:
            r["verdict"] = "reroll"
        else:
            r["verdict"] = "ok"

    if best is None:
        advice = tr("advice.none")
    elif len(slots) == 3 and len(scored) == 3 and all(r.get("sample_warning") for r in scored):
        # 三张都不到 1000 局：结论仍是最高分那张，但明确说只是仅供参考，不写成「首选」
        advice = tr("advice.sample_all", name=best.get("name"))
    elif best.get("sample_warning"):
        advice = tr("advice.sample_best", name=best.get("name"))
    elif len(scored) == len(slots) and all(r["score"] < REROLL_BELOW for r in scored):
        advice = tr("advice.all_bad", name=best.get("name"))
    else:
        advice = tr("advice.best", name=best.get("name"))
        if passed:
            advice += "".join(tr("advice.passed", name=r.get("name"),
                                 reason=tr("advice.reason_too_few" if r["thin"] == "too_few"
                                           else "advice.reason_few"))
                              for r in passed)
    if best is not None and best.get("basis") == "pbe":
        advice += tr("advice.pbe_suffix")
    if best is not None and best.get("basis") == "global_win" and hero_id:
        advice += tr("advice.hero_insufficient_suffix")
    if not hero_id:
        advice += tr("advice.no_hero_suffix")

    pentakill = pentakill_rates(store, hero_id) if any(a in PENTAKILL for a in slots if a) else None
    return {
        "hero_id": hero_id,
        "base_win": base,
        "slots": results,
        "pentakill": pentakill,
        "best_index": best["index"] if best else None,
        "advice": advice,
        "sources": {"win_source": label,
                    "data_patch": (ag or {}).get("patch"), "patch": store.static.get("patch")},
    }
