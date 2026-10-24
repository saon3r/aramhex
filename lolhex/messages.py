"""界面文案：默认英文（en_GB），中文原文保留在 data/messages.json 的 zh_CN 里。

- 键名语义化（area.component.item），值里只有 {named} 占位符；数字、日期先在代码里格式化好再传进来。
- 不认识的界面语言、或某条键在英文表里缺失，都退回英文；键本身完全缺失时返回键名并记一条警告。
- 不自动转义：要拼 HTML 的调用方先把不可信的值 escape() 再传进 tr()，目录里的固定标记原样输出。
- quantity / short_date 是给数量和日期的两个格式化工具：单位写法也在目录里（format.*），代码里只有阈值。
- 识别用的语言（Settings.game_lang，en_US）和这里的界面语言是两回事，互不影响。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from importlib import resources

DEFAULT_UI_LANG = "en_GB"
FALLBACK_UI_LANG = "en_GB"
CATALOG_PACKAGE = "lolhex.data"
CATALOG_NAME = "messages.json"

# 数量单位：阈值、除数、目录里的写法。只有数字在这里，单位文字（M / 万）都在目录里。
# 中文按「万」分档（3699 万），英文按 M / K 分档（37M / 9.5K）。
_QUANTITY_UNITS = {
    "en_GB": ((1_000_000, 1_000_000.0, "format.quantity.millions"),
              (1_000, 1_000.0, "format.quantity.thousands")),
    "zh_CN": ((10_000, 10_000.0, "format.quantity.myriad"),),
}

log = logging.getLogger(__name__)
_language = DEFAULT_UI_LANG
_catalog: dict[str, dict[str, str]] | None = None


def _load() -> dict[str, dict[str, str]]:
    """读目录（按包资源找，源码运行和打包后同一套）。读不到就当空表，界面显示键名。"""
    global _catalog
    if _catalog is None:
        try:
            raw = resources.files(CATALOG_PACKAGE).joinpath(CATALOG_NAME).read_bytes()
            data = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError) as e:
            log.warning("Message catalog unavailable (%s): %s", CATALOG_NAME, e)
            data = {}
        _catalog = {str(lang): {str(k): str(v) for k, v in table.items()}
                    for lang, table in (data.items() if isinstance(data, dict) else ())
                    if isinstance(table, dict)}
    return _catalog


def _resolve_language() -> str:
    """当前界面语言：目录里没有就退回英文（未知语言一律英文）。"""
    return _language if _language in _load() else FALLBACK_UI_LANG


def set_language(language: str) -> None:
    """切换界面语言（只有目录里有的语言才生效，其余一律英文）。"""
    global _language
    wanted = (language or "").strip()
    _language = wanted if wanted in _load() else FALLBACK_UI_LANG


def tr(key: str, /, **values: object) -> str:
    """取一条文案并填占位符。键缺失返回键名（记警告）；占位符对不上直接抛错（调用方的 bug）。"""
    catalog = _load()
    template = (catalog.get(_resolve_language()) or {}).get(key)
    if template is None:
        template = (catalog.get(FALLBACK_UI_LANG) or {}).get(key)
    if template is None:
        log.warning("Missing message key: %s", key)
        return key
    return template.format(**values)


def _number(value: object) -> float | None:
    """数量转数字；bool、空值、非数字返回 None（调用方按原样显示）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _trim(number: float) -> str:
    """一位小数，整数就省掉 .0（5.1M、37M）。"""
    text = f"{number:.1f}"
    return text[:-2] if text.endswith(".0") else text


def quantity(value: object) -> str:
    """局数之类的紧凑写法：英文 5.1M / 9.5K，中文 510 万；太小或不是数字就原样。"""
    number = _number(value)
    if number is None:
        return "" if value is None else str(value)
    for threshold, scale, key in _QUANTITY_UNITS.get(_resolve_language(),
                                                     _QUANTITY_UNITS[DEFAULT_UI_LANG]):
        if abs(number) >= threshold:
            return tr(key, value=_trim(number / scale))
    return str(int(round(number)))


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def short_date(value: object) -> str:
    """短日期：英文 17 Oct，中文 10-17（和以前一样的写法）。解析不了返回空串。"""
    day = _as_date(value)
    if day is None:
        return ""
    return tr("format.date.day_month", day=day.day, month=day.month,
              month_name=tr(f"format.month.{day.month}"))
