"""文案目录与 tr 助手：默认英文、中文原文、未知语言回退、缺键诊断、占位符一致性、数量/日期格式。

目录是冻结的：这里既测助手的契约，也测目录本身（键集合一致、占位符一致、英文里没有中文）。
改代码的人如果用了目录里没有的键，test_converted_modules_only_use_catalog_keys 会红。
"""

from __future__ import annotations

import ast
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from lolhex import messages
from lolhex.messages import DEFAULT_UI_LANG, quantity, set_language, short_date, tr
from lolhex.ui.data_status import data_status_html

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{([a-z_0-9]+)(?::[^}]*)?\}")
CJK = re.compile("[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")

# 必须一直在目录里的键：单测把「已知键」钉住，删掉就是回归。
REQUIRED_KEYS = (
    # 共用词
    "app.name", "app.name_version", "common.help", "common.rescan", "common.clear", "common.confirm",
    "common.quit", "common.settings", "common.not_detected", "hero.candidates", "common.list_separator",
    "rarity.silver", "rarity.gold", "rarity.prismatic",
    "verdict.best", "verdict.ok", "verdict.reroll", "verdict.unknown", "verdict.nodata",
    "phase.none", "phase.client", "phase.ingame",
    "vision.idle", "vision.paused", "vision.scanning",
    "band.all", "band.casual", "band.mid", "band.high",
    "warning.fullscreen", "hero.none_selected", "sample.few",
    # 数据状态（本次转换的 pilot）
    "data.status.none", "data.status.patch", "data.status.games", "data.status.as_of",
    "data.status.stale_patch", "data.status.event_fallback", "data.status.official_failed",
    "data.about_label", "data.progress_label", "data.progress_format",
    # 格式工具（quantity / short_date）
    "format.quantity.millions", "format.quantity.thousands", "format.quantity.myriad",
    "format.date.day_month", "format.month.1", "format.month.10", "format.month.12",
    # 设置下拉框标签（后面 UI 按 code 取，生产者文件本轮不改）
    "settings.speed.standard", "settings.speed.saver", "settings.speed.low",
    "settings.lang.zh_cn", "settings.lang.en_us", "settings.lang.ja_jp", "settings.lang.ko_kr",
    "settings.badge.top", "settings.badge.bottom", "settings.badge_position",
    # 署名（About 现在是英文写死，键先放进目录，UI 转换时按 code 取）
    "about.product", "about.portable", "about.upstream", "about.stats", "about.disclaimer",
)


@pytest.fixture(autouse=True)
def _english_default():
    set_language(DEFAULT_UI_LANG)
    yield
    set_language(DEFAULT_UI_LANG)


def catalog() -> dict[str, dict[str, str]]:
    return messages._load()


def placeholder_mismatches(table: dict[str, dict[str, str]]) -> list[str]:
    """返回占位符对不上的键（两个语言里 {name} 集合必须一样，忽略 :02d 这类格式）。"""
    english, chinese = table.get("en_GB") or {}, table.get("zh_CN") or {}
    bad = []
    for key in sorted(set(english) | set(chinese)):
        if key not in english or key not in chinese:
            bad.append(key)
        elif set(PLACEHOLDER.findall(english[key])) != set(PLACEHOLDER.findall(chinese[key])):
            bad.append(key)
    return bad


def literal_tr_keys(path: Path) -> list[str]:
    """模块里 tr('字面键', ...) 的键（f-string 拼出来的不算，月份键由 REQUIRED_KEYS 钉住）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if name == "tr" and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            out.append(node.args[0].value)
    return out


# ---------- 助手契约 ----------

def test_default_ui_language_is_british_english():
    assert DEFAULT_UI_LANG == "en_GB"
    assert tr("common.rescan") == "Rescan"
    assert tr("app.name") == "AramHex ARAM Mayhem Companion"


def test_set_language_switches_to_chinese_originals():
    set_language("zh_CN")
    assert tr("common.rescan") == "重新识别"
    assert tr("data.status.official_failed") == "官方资料获取失败"


def test_unknown_or_empty_language_falls_back_to_english():
    for lang in ("fr_FR", "de", "", "en_US"):
        set_language(lang)
        assert tr("common.rescan") == "Rescan", lang


def test_missing_key_returns_key_and_warns(caplog):
    with caplog.at_level("WARNING", logger="lolhex.messages"):
        assert tr("totally.missing.key") == "totally.missing.key"
    assert "Missing message key: totally.missing.key" in caplog.text


def test_bad_placeholder_is_a_loud_error():
    with pytest.raises(KeyError):
        tr("stats.winrate")
    with pytest.raises(KeyError):
        tr("stats.winrate", wrong="51.2%")


def test_placeholder_checker_catches_mismatch():
    good = {"en_GB": {"k": "{a} of {b}"}, "zh_CN": {"k": "{a}/{b}"}}
    assert placeholder_mismatches(good) == []
    bad = {"en_GB": {"k": "{a} of {b}"}, "zh_CN": {"k": "{a} of {c}"}}
    assert placeholder_mismatches(bad) == ["k"]
    missing = {"en_GB": {"k": "{a}"}, "zh_CN": {}}
    assert placeholder_mismatches(missing) == ["k"]


# ---------- 目录本体（冻结的契约） ----------

def test_catalog_loads_both_locales_from_package_resources():
    table = catalog()
    assert set(table) == {"en_GB", "zh_CN"}
    assert len(table["en_GB"]) >= 200


def test_catalog_locales_have_identical_key_sets():
    table = catalog()
    assert set(table["en_GB"]) == set(table["zh_CN"])


def test_catalog_placeholders_are_identical_across_locales():
    assert placeholder_mismatches(catalog()) == []


def test_english_catalog_values_contain_no_cjk():
    bad = {k: v for k, v in catalog()["en_GB"].items() if CJK.search(v)}
    assert bad == {}


def test_catalog_contains_every_required_key():
    english = catalog()["en_GB"]
    missing = [k for k in REQUIRED_KEYS if k not in english]
    assert missing == []


def test_catalog_is_valid_json_on_disk():
    path = ROOT / "lolhex" / "data" / "messages.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(raw) == ["en_GB", "zh_CN"]


def test_converted_modules_only_use_catalog_keys():
    english = catalog()["en_GB"]
    unused = []
    for rel in ("lolhex/messages.py", "lolhex/ui/data_status.py"):
        keys = literal_tr_keys(ROOT / rel)
        assert keys, rel
        unused += [f"{rel}:{k}" for k in keys if k not in english]
    assert unused == []


# ---------- quantity / short_date ----------

def test_quantity_unit_tables_use_the_expected_locale_formats():
    """英文只走 M/K，中文只走「万」；用错表会渲染出量级不对的数字。"""
    from lolhex.messages import _QUANTITY_UNITS

    assert [key for _, _, key in _QUANTITY_UNITS["en_GB"]] == [
        "format.quantity.millions", "format.quantity.thousands"]
    assert [key for _, _, key in _QUANTITY_UNITS["zh_CN"]] == ["format.quantity.myriad"]


@pytest.mark.parametrize("value,expected", [
    (5_100_000, "5.1M"), (36_990_000, "37M"), (9_500, "9.5K"), (950, "950"), (0, "0"),
    (-1_200, "-1.2K"), ("12100", "12.1K"), (None, ""), ("n/a", "n/a"), (True, "True"),
])
def test_quantity_english(value, expected):
    assert quantity(value) == expected


@pytest.mark.parametrize("value,expected", [
    (36_990_000, "3699 万"), (5_100_000, "510 万"), (9_500, "9500"), (None, ""), ("n/a", "n/a"),
])
def test_quantity_chinese(value, expected):
    set_language("zh_CN")
    assert quantity(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("2026-10-17", "17 Oct"), ("2026-10-17T11:56:47+08:00", "17 Oct"),
    (date(2026, 5, 3), "3 May"),
    (datetime(2026, 10, 23, 23, 30, tzinfo=timezone.utc), "23 Oct"),
    ("garbage", ""), (None, ""), ("", ""),
])
def test_short_date_english(value, expected):
    assert short_date(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("2026-10-17", "10-17"), (date(2026, 5, 3), "05-03"), ("garbage", ""), (None, ""),
])
def test_short_date_chinese(value, expected):
    set_language("zh_CN")
    assert short_date(value) == expected


# ---------- pilot：data_status_html ----------

FULL = {"dataset": True, "dataset_patch": "16.20", "dataset_matches": 36_990_000,
        "dataset_snapshot": "2026-10-13T11:56:47+08:00", "patch": "16.20"}


def test_status_without_dataset_is_english():
    assert data_status_html({}) == "No stats data"


def test_status_line_is_english_by_default():
    text = data_status_html(FULL)
    assert text == "Patch 16.20 · 37M games · as of 13 Oct"


def test_status_line_keeps_chinese_when_asked():
    set_language("zh_CN")
    text = data_status_html(FULL)
    assert text == "16.20 版本 · 3699 万局 · 截至 10-13"


def test_status_mode_label_and_stale_patch():
    text = data_status_html({**FULL, "dataset_mode_label": "常规", "patch": "16.21"})
    assert text.startswith("常规 · Patch 16.20 · ")
    assert "Game updated to 16.21; stats not updated yet" in text


def test_status_event_fallback_and_error():
    text = data_status_html({**FULL, "event_fallback": True, "event_label": "竞技场", "error": "boom"})
    assert "No 竞技场 stats yet - using general data" in text
    assert text.endswith("Official data fetch failed")


def test_status_escapes_untrusted_values_before_tr():
    text = data_status_html({**FULL, "dataset_patch": "<script>alert(1)</script>",
                             "dataset_mode_label": "<img src=x>", "patch": ""})
    assert "<script>" not in text and "<img" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "&lt;img src=x&gt;" in text


def test_status_escapes_event_label():
    text = data_status_html({**FULL, "event_fallback": True, "event_label": "<b>x</b>"})
    assert "<b>x</b>" not in text and "&lt;b&gt;x&lt;/b&gt;" in text
