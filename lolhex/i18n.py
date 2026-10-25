"""外服：游戏客户端是别的语言时，海克斯名、英雄名、选英雄界面上的字按那种语言认。

名字表 data/i18n.json 由 scripts/update_i18n.py 从拳头公开数据生成，ID 和腾讯同一套，
所以统计数据、界面显示（中文名）都不用改，只是认字时多一套名字。
日文用内置识别模型就能认；韩文要单独的模型，模型下载已移除，所以没有韩服选项。
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

PATH = Path(__file__).resolve().parent / "data" / "i18n.json"
# 设置里的选项：(代码, 显示名)。中文是 zh_CN：简体名字用腾讯的（和拳头简中一致），
# 繁中（台服等）的名字也一起认——繁中是另一套译名，台服玩家多半不会去改设置。
# 以前单独有过繁中选项（zh_TW），存着这个值的当中文
LANGS = [("zh_CN", "中文 简-繁（国服、台服）"), ("en_US", "English（美服、欧服等）"),
         ("ja_JP", "日本語（日服）")]
# 1.1.1 起没有韩服选项：认韩文要单独的识别模型，模型下载已移除，选了也认不出。
# 老设置文件里留着 ko_KR 的，按英文客户端处理（本工具的目标客户端），不要再当中文。
RETIRED = {"ko_KR"}
# 英国英语客户端识别上就是英语：本 fork 的目标客户端是 en_GB，老设置文件里也可能存着它。
# 内部统一用 en_US（名字表、识别器按 en-US/en-GB 顺序找），不能落到「未知语言 → 中文」。
ENGLISH_ALIASES = {"en_GB": "en_US"}
LANG_CODES = {code for code, _ in LANGS}
TW = "zh_TW"
# 国服客户端选英雄界面上的字（i18n.json 里也有，这里写死，名字表缺失时国服照常能用）
UI_CN = {"bench": "可用", "pick": "选择你的英雄"}


def normalize_lang(lang: str | None) -> str:
    if lang in RETIRED:
        return "en_US"
    if lang in ENGLISH_ALIASES:
        return ENGLISH_ALIASES[lang]
    return lang if lang in LANG_CODES else "zh_CN"


@lru_cache(maxsize=1)
def _table() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("外服名字表读不到：%s", PATH)
        return {}


def _augments(lang: str) -> dict[str, str]:
    return {aid: names[lang] for aid, names in (_table().get("augments") or {}).items() if names.get(lang)}


def _heroes(lang: str) -> dict[str, list[str]]:
    return {hid: [n for n in names[lang] if n] for hid, names in (_table().get("heroes") or {}).items()
            if names.get(lang)}


def augment_names(lang: str) -> dict[str, str]:
    """{海克斯 ID: 这种语言的名字}；中文返回空（用腾讯的名字，繁中另见 traditional_augment_names）。"""
    lang = normalize_lang(lang)
    return {} if lang == "zh_CN" else _augments(lang)


def hero_names(lang: str) -> dict[str, list[str]]:
    """{英雄 ID: [名字, 称号]}；中文返回空。"""
    lang = normalize_lang(lang)
    return {} if lang == "zh_CN" else _heroes(lang)


def traditional_augment_names() -> dict[str, str]:
    """中文模式下额外认的繁中海克斯名。"""
    return _augments(TW)


def traditional_hero_names() -> dict[str, list[str]]:
    """中文模式下额外认的繁中英雄名和称号。"""
    return _heroes(TW)


def ui_text(key: str, lang: str) -> str:
    """选英雄界面上的字：bench=预选栏左边的「可用」，pick=开局选卡的「选择你的英雄」。"""
    lang = normalize_lang(lang)
    if lang == "zh_CN":
        return UI_CN[key]
    return ((_table().get("ui") or {}).get(key) or {}).get(lang) or UI_CN[key]


def ui_texts(key: str, lang: str) -> list[str]:
    """同上，中文模式是 [简体, 繁中] 两种写法，先试简体。"""
    out = [ui_text(key, lang)]
    if normalize_lang(lang) == "zh_CN":
        tw = ((_table().get("ui") or {}).get(key) or {}).get(TW)
        if tw and tw not in out:
            out.append(tw)
    return out
