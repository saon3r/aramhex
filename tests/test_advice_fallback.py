"""推荐口径：有足够本英雄样本才用本英雄胜率，否则明确标 all champs，再不然只给 ?。"""

from lolhex import recommend
from lolhex.panel import hero_panel


def _set_hero_sample(store, aid, games, win_rate):
    store.dataset.table(None)[1]["17"][aid] = {
        "games": games, "wins": round(games * win_rate), "win_rate": win_rate,
        "low_sample": games < 3000,
    }


def test_champion_rate_precedes_global(store):
    ev = recommend.evaluate(store, "17", ["1029", "2128", "1373"])
    best = ev["slots"][ev["best_index"]]
    assert best["basis"] == "hero_win"
    assert best["score"] is not None and best["augment_id"] == "1029"
    assert "all champs" not in recommend.win_text(best)
    assert "This champion:" in " ".join(best["reasons"])


def test_missing_champion_uses_labelled_global(store):
    # 英雄认识，但这几张海克斯没有本英雄数据：用全英雄合计，明确标 all champs。
    ev = recommend.evaluate(store, "1", ["2128", "1373"])
    for slot in ev["slots"]:
        assert slot["basis"] == "global_win"
        assert slot["score"] is not None
        assert slot["rate_label"] == "all champs"
        assert "all champs" in recommend.win_text(slot)
        assert "%" in recommend.win_text(slot)
    assert ev["best_index"] is not None
    assert "all champs" in ev["advice"]


def test_tiny_champion_uses_labelled_global_or_nodata(store):
    _set_hero_sample(store, "1029", 2, 1.0)
    slot = recommend.evaluate(store, "17", ["1029"])["slots"][0]
    assert slot["basis"] == "global_win" and slot["score"] is not None
    assert "all champs" in recommend.win_text(slot)

    # 全英雄样本也很少：没有数，只有 ?，不给一个自信的百分比。
    store.ranks["augments"]["1029"].update(games=2, win=1.0)
    slot = recommend.evaluate(store, "17", ["1029"])["slots"][0]
    assert slot["verdict"] == "nodata" and slot["score"] is None
    assert slot.get("win") is None
    assert recommend.win_text(slot) == "?"


def test_missing_or_tiny_all_rates_has_no_number(store):
    store.ranks["augments"]["4444"] = {"win": 0.5, "games": 2}
    ev = recommend.evaluate(store, "999", ["4444"])
    slot = ev["slots"][0]
    assert slot["verdict"] == "nodata" and slot["basis"] == "nodata"
    assert slot["score"] is None and slot.get("win") is None
    assert recommend.win_text(slot) == "?"
    assert "%" not in recommend.win_text(slot)
    assert ev["best_index"] is None and "%" not in ev["advice"]

    missing = recommend.evaluate(store, "999", ["5555"])["slots"][0]
    assert missing["verdict"] == "nodata" and missing["score"] is None
    assert missing.get("win") is None and "%" not in recommend.win_text(missing)
    assert recommend.win_text(missing) == "?"


def test_global_mean_ignores_games_without_win(store):
    # 有效汇总行：只有 win 不是 None 的局数才参与分子和分母。
    valid = [v for v in store.ranks["augments"].values() if v.get("win") is not None]
    valid_mean = sum(v["win"] * v["games"] for v in valid) / sum(v["games"] for v in valid)
    store.ranks["augments"]["9999"] = {"games": 10**7, "win": None}
    slot = recommend.evaluate(store, "1", ["2128"])["slots"][0]
    assert slot["basis"] == "global_win"
    assert abs(slot["score"] - (0.52 - valid_mean) * 100) < 0.01


def test_no_official_tier_dependency(store, monkeypatch):
    panel = hero_panel(store, "17")
    assert panel and all("tier" not in a for a in panel["augments"])
    assert not {"builds", "skills", "partners", "splash", "spells"} & panel.keys()

    def boom(*_a, **_k):
        raise AssertionError("evaluate must not read the removed official hero source")

    with monkeypatch.context() as m:
        m.setattr(store, "hero", boom)
        ev = recommend.evaluate(store, "17", ["1029", "2128", "1373"])
    for slot in ev["slots"]:
        assert "tier" not in slot and "pick" not in slot
        assert slot["basis"] in {"hero_win", "global_win", "pbe", "excluded", "new", "nodata"}
        assert slot["basis"] != "tier_only"
    assert "tencent_date" not in ev["sources"]
