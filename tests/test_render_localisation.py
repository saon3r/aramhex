"""玩家能看到的每一段建议文字都是英文。

这些句子由生产者拼好（recommend / public / panel）再交给界面，绕过 `lolhex/ui/*.py`
的 AST 闸门——Task 8 延后的正是它们。这里按「真正会显示出来的字符串」断言：海克斯名、
胜率文本、理由、建议、五杀乐队、数据来源标签、面板里的海克斯全表。

只断言英文，不改打分、样本分档或建议规则。
"""

import re

from lolhex import recommend
from lolhex.panel import hero_panel

CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")
OFFER = ["2128", "1029", "1373"]  # 与 test_recommend.py 同一组卡
PENTAKILL = ["3170", "3171", "3172"]  # 五杀乐队那组：显示时要带强化技能


def _offer_strings(ev):
    out = [ev["advice"], (ev.get("sources") or {}).get("win_source") or ""]
    for slot in ev["slots"]:
        out += [slot.get("name") or "", slot.get("note") or "", recommend.win_text(slot)]
        out += list(slot.get("reasons") or [])
    return [text for text in out if text]


def _cjk(strings):
    return [text for text in strings if CJK.search(text)]


def test_offer_badges_and_advice_are_english(store):
    ev = recommend.evaluate(store, "17", OFFER)
    assert ev["slots"][1]["verdict"] == "best"  # 前提没变：结论仍是同一张卡
    assert not _cjk(_offer_strings(ev)), _cjk(_offer_strings(ev))


def test_advice_without_champion_is_english(store):
    ev = recommend.evaluate(store, None, OFFER)
    assert not _cjk(_offer_strings(ev)), _cjk(_offer_strings(ev))


def test_unrecognised_and_thin_sample_reasons_are_english(store):
    store.ranks["augments"]["1001"] = {"win": 0.5, "games": 5000}
    heroes, augs = store.dataset.table(None)
    base = heroes["17"]["win_rate"]
    augs["17"]["2128"] = {"games": 385, "wins": round(385 * (base + 0.03)), "win_rate": base + 0.03}
    ev = recommend.evaluate(store, "17", ["1029", None, "2128", "1001"])
    assert ev["slots"][1]["verdict"] == "unknown"
    assert not _cjk(_offer_strings(ev)), _cjk(_offer_strings(ev))


def test_pentakill_text_is_english(store):
    heroes, augs = store.dataset.table(None)
    wins = heroes["17"]["win_rate"]
    for aid in PENTAKILL:
        augs["17"][aid] = {"games": 3200, "wins": round(3200 * wins), "win_rate": wins}
    ev = recommend.evaluate(store, "17", PENTAKILL)
    text = recommend.pentakill_text(recommend.pentakill_rates(store, "17"))
    assert text, "五杀乐队那组应该有文字"
    assert not _cjk([text, *[s.get("name") or "" for s in ev["slots"]]]), text


def test_source_label_is_english_with_and_without_band(store):
    store.set_band(None)
    assert not CJK.search(store.label())
    for band in ("casual", "mid", "high"):
        store.set_band(band)
        assert not CJK.search(store.label()), store.label()
        assert not CJK.search((store.status() or {}).get("band_label") or "")
    store.set_band(None)


def test_augment_names_in_panel_are_english(store):
    panel = hero_panel(store, "17")
    assert panel and panel["augments"]
    names = [a["name"] for a in panel["augments"]]
    assert not _cjk(names), _cjk(names)
    assert not _cjk([panel["win_source"]]), panel["win_source"]


def test_panel_display_fields_are_english(store):
    panel = hero_panel(store, "17")
    checks = [panel.get("win_source") or "", panel.get("summoner_source") or ""]
    for aug in panel["augments"]:
        checks += [aug.get("name") or "", aug.get("desc") or ""]
    for row in panel.get("summoners") or []:
        checks += [s.get("name") or "" for s in row.get("spells") or []]
    for row in panel.get("item_stats") or []:
        checks.append((row.get("item") or {}).get("name") or "")
    assert not _cjk([c for c in checks if c]), _cjk([c for c in checks if c])
