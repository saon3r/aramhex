"""公开元数据：Data Dragon 英雄/装备、CommunityDragon 海克斯，以及英文显示名。

这里只解析已经拿到的 JSON（纯函数），不联网、不碰腾讯，也不导入 store/tencent，
避免和正在改造的数据层互相依赖。ID 和现有腾讯/统计是同一套数值；中文识别名从
data/i18n.json 的 zh_CN 表取，英文另存在 name_en/nick_en，显示用 display_*，
不覆盖引擎认字用的中文字段。

约定：整份 payload 结构不对（不是 dict/list、缺 data、版本字符串带路径）抛
ValueError；单条记录坏掉（ID/别名/图片路径不合法）跳过，不拿它拼任意 URL。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DDRAGON_BASE = "https://ddragon.leagueoflegends.com/cdn"
DDRAGON_API = "https://ddragon.leagueoflegends.com/api"
CDRAGON_BASE = ("https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/"
                "global/default")
CDRAGON_AUGMENTS = f"{CDRAGON_BASE}/v1/cherry-augments.json"

# 稀有度机器码；和自采数据/界面用的是同一套。
_RARITY = {"kSilver": "silver", "kGold": "gold", "kPrismatic": "prismatic"}
# 临时中文显示标签（Task 8 换英文/繁中）；推荐和界面从这里取，不再 import 已删除的腾讯模块。
RARITY_CN = {"silver": "白银", "gold": "黄金", "prismatic": "棱彩"}
RARITIES = frozenset(RARITY_CN)

_I18N = Path(__file__).with_name("i18n.json")
_FALLBACK = Path(__file__).with_name("static_fallback.json")
_DD_VERSION = re.compile(r"\d+\.\d+(?:\.\d+)*")
_PATCH = re.compile(r"\s*(\d+)\.(\d+)(?:\.\d+)*\s*")
_ALIAS = re.compile(r"[A-Za-z0-9]+")
_ASSET = re.compile(r"[a-z0-9._/-]+")
_TAG = re.compile(r"<[^>]+>")
_INTERNAL = re.compile(r"^(?:ARAM_|game_|lol_|kiwi_)", re.IGNORECASE)
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")


# ---------- 本地名字表 ----------

@lru_cache(maxsize=1)
def _names() -> dict:
    try:
        raw = json.loads(_I18N.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _row(section: str, key: str) -> dict:
    rows = _names().get(section)
    row = rows.get(key) if isinstance(rows, dict) else None
    return row if isinstance(row, dict) else {}


@lru_cache(maxsize=1)
def static_fallback() -> dict:
    """随程序钉住的离线兜底表（id→Data Dragon alias、海克斯稀有度、召唤师技能英文名）。

    生成来源、版本和 payload SHA-256 记在文件里的 sources；不含胜率/统计清单，
    联网刷新后以磁盘缓存为准。文件缺失或坏了返回空表，调用方照常退化为只有 i18n 名字。
    """
    try:
        raw = json.loads(_FALLBACK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def fallback_version() -> str:
    """兜底表对应的 Data Dragon 版本（例如 16.21.1）；没有就空串。"""
    return _text(static_fallback().get("ddragon"))


def local_hero_ids() -> frozenset[str]:
    rows = _names().get("heroes")
    return frozenset(str(k) for k in rows) if isinstance(rows, dict) else frozenset()


def local_augment_ids() -> frozenset[str]:
    """本地 i18n 里已知的海克斯 ID（Mayhem 平台来源），用于选择英文源里的记录。"""
    rows = _names().get("augments")
    return frozenset(str(k) for k in rows) if isinstance(rows, dict) else frozenset()


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _english(value) -> str:
    """英文名字：空、内部 stringtable key、误混进来的中文都不算。"""
    text = _text(value)
    if not text or _INTERNAL.match(text) or _CJK.search(text):
        return ""
    return text


def hero_zh(hero_id: str | int) -> tuple[str, str]:
    """本地 i18n 里的 (中文称号, 中文名)；没有返回两个空串。"""
    return _zh_hero(_display_key(hero_id))


def hero_en(hero_id: str | int) -> tuple[str, str]:
    """本地 i18n 里的 (英文名, 英文称号)；没有返回两个空串。"""
    names = _row("heroes", _display_key(hero_id)).get("en_US")
    if not isinstance(names, list):
        return "", ""
    return (_english(names[0]) if names else "",
            _english(names[1]) if len(names) > 1 else "")


def augment_zh(augment_id: str | int) -> str:
    return _text(_row("augments", _display_key(augment_id)).get("zh_CN"))


def augment_en(augment_id: str | int) -> str:
    return _english(_row("augments", _display_key(augment_id)).get("en_US"))


def _zh_hero(hid: str) -> tuple[str, str]:
    """i18n 的 zh_CN 是 [称号, 名字]；返回 (称号, 名字)。"""
    names = _row("heroes", hid).get("zh_CN")
    if not isinstance(names, list):
        return "", ""
    return (_text(names[0]) if len(names) > 0 else "",
            _text(names[1]) if len(names) > 1 else "")


# ---------- 小工具 ----------

def _int_id(value) -> str | None:
    """稳定数字 ID -> 十进制字符串；bool、负数、非数字返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return str(int(value.strip()))
    return None


def _int_or_none(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _version(version: str) -> str:
    v = _text(version)
    if not v or not _DD_VERSION.fullmatch(v):
        raise ValueError("Data Dragon 版本格式不对")
    return v


def _data(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("元数据 payload 不是对象")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("元数据 payload 缺 data 对象")
    return data


def _cdragon_icon(path) -> str:
    """CommunityDragon 相对资源路径 -> 固定 host 的 URL；不合法返回空串。

    只接受 png 相对路径：拒绝绝对 URL、查询串/锚点、反斜杠、空段、`.`/`..`。
    路径统一转小写，CommunityDragon 的 default 资源就是小写。
    """
    p = _text(path)
    if not p or "://" in p or p.startswith("//") or "\\" in p:
        return ""
    if "?" in p or "#" in p:
        return ""
    low = p.lower()
    if low.startswith("/lol-game-data/"):
        p = p[len("/lol-game-data/"):]
    elif low.startswith("lol-game-data/"):
        p = p[len("lol-game-data/"):]
    p = p.lstrip("/")
    low = p.lower()
    if not low.endswith(".png"):
        return ""
    parts = low.split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        return ""
    if not _ASSET.fullmatch(low):
        return ""
    return f"{CDRAGON_BASE}/{low}"


def normalize_patch(version: str) -> str:
    """补丁号：'16.21.1' -> '16.21'；'16.21' 原样；缺失/畸形返回 ''。"""
    if not isinstance(version, str):
        return ""
    m = _PATCH.fullmatch(version)
    return f"{m.group(1)}.{m.group(2)}" if m else ""


# ---------- 解析 ----------

def parse_champions(payload: dict, version: str) -> dict[str, dict]:
    """Data Dragon champion.json -> {数字英雄 ID: 记录}；alias 只放在记录里。"""
    ver = _version(version)
    data = _data(payload)
    out: dict[str, dict] = {}
    for alias, rec in data.items():
        if not isinstance(alias, str) or not _ALIAS.fullmatch(alias) or not isinstance(rec, dict):
            continue
        hid = _int_id(rec.get("key"))
        name = _text(rec.get("name"))
        if hid is None or not name:
            continue
        image = rec.get("image")
        full = image.get("full") if isinstance(image, dict) else None
        if full != f"{alias}.png":
            continue
        tags = rec.get("tags")
        roles = ([t.strip() for t in tags if isinstance(t, str) and t.strip()]
                 if isinstance(tags, list) else [])
        nick, cn_name = _zh_hero(hid)
        nick_en = _text(rec.get("title"))
        out[hid] = {
            "id": hid,
            "name": cn_name,       # 引擎认字用的中文英雄名
            "nick": nick,          # 引擎认字用的中文称号
            "alias": alias,
            "icon": f"{DDRAGON_BASE}/{ver}/img/champion/{alias}.png",
            "roles": roles,
            "name_en": name,
            "nick_en": nick_en,
            # 搜索/补全：英文 alias、名字、称号；中文名字/称号和本地别名表另有字段
            "keywords": ",".join(t for t in (alias, name, nick_en) if t),
        }
    return out


def parse_items(payload: dict, version: str) -> dict[str, dict]:
    """Data Dragon item.json -> {数字装备 ID: 英文名/固定图标/描述/总价}。"""
    ver = _version(version)
    data = _data(payload)
    out: dict[str, dict] = {}
    for raw_id, rec in data.items():
        iid = _int_id(raw_id)
        if iid is None or not isinstance(rec, dict):
            continue
        name = _text(rec.get("name"))
        if not name:
            continue
        image = rec.get("image")
        full = image.get("full") if isinstance(image, dict) else None
        if full != f"{iid}.png":
            continue
        gold = rec.get("gold")
        out[iid] = {
            "id": iid,
            "name": name,
            "icon": f"{DDRAGON_BASE}/{ver}/img/item/{iid}.png",
            "desc": _text(rec.get("plaintext")),
            "price": _int_or_none(gold.get("total")) if isinstance(gold, dict) else None,
        }
    return out


def parse_augments(payload: list[dict], active_ids: set[str] | None = None, *,
                   modes=(), new_ids: set[str] | None = None) -> dict[str, dict]:
    """CommunityDragon 英文 cherry-augments.json -> {数字 ID: 记录}。

    active_ids 给了就只收这些 ID（大小兼容 str/int），不再看 ARAM_ 前缀或 kiwi 图标路径；
    为 None 时收所有合法记录。图标只从合法相对路径拼固定 host，缺/坏就留空，不丢记录。
    modes/new_ids 由调用方按已验证的数据集/本地表给出，落在记录里供 store 过滤和推荐使用。
    """
    if not isinstance(payload, list):
        raise ValueError("海克斯 payload 不是列表")
    keep = None if active_ids is None else {_int_id(x) for x in active_ids}
    mode_list = [str(m) for m in modes if str(m).strip()]
    fresh = {_int_id(x) for x in (new_ids or ())}
    out: dict[str, dict] = {}
    for rec in payload:
        if not isinstance(rec, dict):
            continue
        aid = _int_id(rec.get("id"))
        if aid is None or (keep is not None and aid not in keep):
            continue
        names = _row("augments", aid)
        icon = ""
        for key in ("augmentSmallIconPath", "iconSmall", "iconLarge"):
            icon = _cdragon_icon(rec.get(key))
            if icon:
                break
        desc = rec.get("simpleDescription") or rec.get("description")
        out[aid] = {
            "id": aid,
            "name": augment_zh(aid),       # 中文识别名；没有就空着
            "name_en": (_english(rec.get("nameTRA")) or _english(names.get("en_US"))
                        or f"Augment {aid}"),
            "rarity": _RARITY.get(rec.get("rarity"), "unknown")
            if isinstance(rec.get("rarity"), str) else "unknown",
            "desc": _TAG.sub("", desc).strip() if isinstance(desc, str) else "",
            "icon": icon,
            "modes": list(mode_list),
            "new": aid in fresh,
        }
    return out


# ---------- 英文显示 ----------

def _display_key(value) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def display_hero_name(hero_id: str | int) -> str:
    """英文英雄名；未知 ID 返回 'Champion <id>'，绝不返回中文或内部 key。"""
    key = _display_key(hero_id)
    names = _row("heroes", key).get("en_US")
    if isinstance(names, list) and names:
        return _english(names[0]) or (f"Champion {key}" if key else "Champion")
    return f"Champion {key}" if key else "Champion"


def display_hero_title(hero_id: str | int) -> str:
    """英文称号（'the Dark Child'）；未知 ID 返回空串（不重复占位名）。"""
    key = _display_key(hero_id)
    names = _row("heroes", key).get("en_US")
    if isinstance(names, list) and len(names) > 1:
        return _english(names[1])
    return ""


def display_augment_name(augment_id: str | int) -> str:
    """英文海克斯名；未知 ID 返回 'Augment <id>'，绝不返回中文或内部 key。"""
    key = _display_key(augment_id)
    return (_english(_row("augments", key).get("en_US"))
            or (f"Augment {key}" if key else "Augment"))
