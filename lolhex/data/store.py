"""静态资料：离线种子、按家族联网刷新、原子落盘、按需查询。

目录：<app_home>/data/
  static.json        英雄、海克斯字典、装备、召唤师技能、版本和每个家族的更新时间

构造函数只读磁盘/随程序的公开表，不发网络请求：没有任何缓存时，用 i18n 名字 +
static_fallback.json 的 id→Data Dragon alias/稀有度先把英雄和海克斯种子建好，引擎据此
立刻能做头像/名字识别。后台刷新（scripts/update_data 之外唯一的静态资料来源）只走
http.py 放行的 Data Dragon 版本化英雄/装备和 CommunityDragon 英文海克斯字典。

腾讯的静态接口（game.gtimg.cn / mlol.qt.qq.com）已移除，不再有 hero/<id>.json，
也不会从旧磁盘缓存复活官方层级或腾讯图标。某个家族刷新失败时保留上一份好数据，
在 status()/last_error 里说明；胜率统计不在这里，见 public.py。
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

from . import http, metadata

log = logging.getLogger(__name__)

# static.json 结构版本：旧缓存没有这个标记，按迁移处理而不是当成完整缓存。
STATIC_SCHEMA = 2
# 需要联网刷新的家族；spells 是本地固定的英文小表，不参与过期判断。
REFRESH_FAMILIES = ("versions", "heroes", "items", "augments")
MAYHEM_MODES = ("KIWI",)
# 六张 Cherry 路径上的海克斯：即使统计/i18n 暂时缺，也留在 Mayhem 识别表里。
CHERRY_AUGMENTS = frozenset({"1332", "1416", "2091", "2116", "2129", "2135"})
_RARITIES = metadata.RARITIES

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
    """先写同目录临时文件再原子替换：写到一半崩溃也不会留下半份缓存。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _table(value) -> dict:
    return value if isinstance(value, dict) else {}


def _records(value) -> dict:
    """只保留 {字符串 ID: 对象} 的表；坏记录整条丢掉，不猜测。"""
    return {str(k): v for k, v in _table(value).items() if isinstance(v, dict)}


def _rarity(value) -> str | None:
    return value if isinstance(value, str) and value in _RARITIES else None


def _keywords(*terms) -> str:
    out, seen = [], set()
    for term in terms:
        for part in str(term or "").split(","):
            part = part.strip()
            if part and part.lower() not in seen:
                seen.add(part.lower())
                out.append(part)
    return ",".join(out)


def _merge_heroes(old: dict, new: dict) -> dict:
    """新抓的官方记录覆盖名字/图标，但保留旧缓存里的搜索关键词/中文名字等补充字段。"""
    out = dict(_records(old))
    for hid, rec in _records(new).items():
        base = dict(out.get(hid) or {})
        merged = {**base, **rec}
        merged["id"] = hid
        merged["keywords"] = _keywords(base.get("keywords"), rec.get("keywords"))
        if not merged.get("name") and base.get("name"):
            merged["name"] = base["name"]
        if not merged.get("nick") and base.get("nick"):
            merged["nick"] = base["nick"]
        out[hid] = merged
    return out


def _merge_augments(old: dict, new: dict) -> dict:
    """英文源不认识的稀有度/空名字不能覆盖已经验证过的兜底记录。"""
    out = dict(_records(old))
    for aid, rec in _records(new).items():
        base = dict(out.get(aid) or {})
        merged = {**base, **rec}
        merged["id"] = aid
        if not merged.get("name") and base.get("name"):
            merged["name"] = base["name"]
        if not merged.get("name_en") and base.get("name_en"):
            merged["name_en"] = base["name_en"]
        rarity = _rarity(rec.get("rarity"))
        if rarity is None:
            rarity = _rarity(base.get("rarity"))
        if rarity:
            merged["rarity"] = rarity
        else:
            merged.pop("rarity", None)
        merged["modes"] = list(rec.get("modes") or base.get("modes") or MAYHEM_MODES[:1])
        merged["new"] = bool(rec.get("new") or base.get("new"))
        out[aid] = merged
    return out


def _usable_records(parsed, family: str) -> dict:
    """整份表解析后为空（空 payload 或每条记录都坏）算这个家族刷新失败。

    解析器对单条坏记录仍然是跳过、不猜；但一份「零条可用记录」的 200 响应不能
    当成成功：它会顶掉上一份好缓存、推进家族时间戳并写进磁盘，源端恢复前一直坏着。
    """
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(f"{family}返回里没有任何可用记录")
    return parsed


_CJK = re.compile("[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]")


def _safe_display_name(value) -> str:
    """旧缓存里的名字能不能直接显示：只接受非空、且不含中日韩文字的字符串。

    兜底表（static_fallback.json）只有英文公开数据；旧腾讯缓存里的装备/召唤师技能名是中文，
    带进英文界面就是漏中文，所以这类名字一律不带走，宁可显示占位符等下一次刷新。
    """
    if not isinstance(value, str):
        return ""
    name = value.strip()
    return "" if not name or _CJK.search(name) else name


def _carry_items(legacy: dict | None) -> dict[str, dict]:
    """旧缓存里的装备表：只带走能安全显示的部分。

    兜底表没有装备，重铺种子时丢掉会让装备名变成数字 ID；但旧版本可能存着腾讯的图标
    地址（game.gtimg.cn）和中文名，两样都不能带进英文界面，图标清空、名字不合规就跳过。
    """
    out: dict[str, dict] = {}
    for iid, rec in _records(_table(legacy).get("items")).items():
        name = _safe_display_name(rec.get("name"))
        if not name:
            continue
        raw_id = rec.get("id")
        key = str(raw_id) if isinstance(raw_id, (str, int)) else str(iid)
        icon = str(rec.get("icon") or "")
        price = rec.get("price")
        out[key] = {
            "id": key,
            "name": name,
            "desc": str(rec.get("desc") or rec.get("plaintext") or ""),
            "price": price if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
            "icon": icon if icon.startswith(metadata.DDRAGON_BASE + "/") else "",
        }
    return out


def _seed_static(legacy: dict | None = None) -> dict:
    """无缓存/坏缓存时的完整种子：随程序的公开表 + i18n；只迁移旧缓存里安全的中文补充。

    装备表是例外：兜底表里没有装备（运行时从 Data Dragon 取），旧缓存里的英文名/图标
    一律原样带走。否则旧版本就地升级后第一次离线启动，装备名会退化成一串数字 ID，
    一直等到下一次元数据刷新才恢复。
    """
    fb = metadata.static_fallback()
    fb_heroes = _table(fb.get("heroes"))
    fb_augs = _table(fb.get("augments"))
    version = metadata.fallback_version()
    legacy = _table(legacy)

    heroes: dict[str, dict] = {}
    for hid in sorted(set(metadata.local_hero_ids()) | set(fb_heroes), key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
        row = _table(fb_heroes.get(hid))
        nick, name = metadata.hero_zh(hid)
        name_en, nick_en = metadata.hero_en(hid)
        old = _table(_table(legacy.get("heroes")).get(hid))
        alias = str(row.get("alias") or old.get("alias") or "")
        heroes[hid] = {
            "id": hid,
            "name": name or str(old.get("name") or ""),
            "nick": nick or str(old.get("nick") or ""),
            "alias": alias,
            "icon": (f"{metadata.DDRAGON_BASE}/{version}/img/champion/{alias}.png" if version and alias else ""),
            "roles": list(row.get("roles") or old.get("roles") or []) if isinstance(row.get("roles") or old.get("roles"), list) else [],
            "name_en": name_en,
            "nick_en": nick_en,
            # 英文搜索词 + 旧缓存里的腾讯关键词（拼音缩写不再重新生成，但已有就保留）
            "keywords": _keywords(alias, name_en, nick_en, old.get("keywords")),
        }

    augments: dict[str, dict] = {}
    for aid in sorted(set(metadata.local_augment_ids()) | set(fb_augs) | CHERRY_AUGMENTS,
                      key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)):
        row = _table(fb_augs.get(aid))
        old = _table(_table(legacy.get("augments")).get(aid))
        rarity = _rarity(row.get("rarity")) or _rarity(old.get("rarity"))
        modes = list(old.get("modes") or [])
        if not any(str(m).startswith("KIWI") for m in modes):
            modes.append(MAYHEM_MODES[0])
        rec = {
            "id": aid,
            "name": metadata.augment_zh(aid) or str(old.get("name") or ""),
            "name_en": metadata.augment_en(aid) or str(old.get("name_en") or old.get("en") or ""),
            "desc": str(old.get("desc") or ""),
            "icon": "",  # 不预取海克斯图标；界面不使用，也不发额外请求
            "modes": modes,
            "new": bool(old.get("new")),
        }
        if rarity:
            rec["rarity"] = rarity
        augments[aid] = rec

    spells = {}
    for sid, name in _table(fb.get("spells")).items():
        if str(name).strip():
            spells[str(sid)] = {"id": str(sid), "name": str(name).strip(), "icon": ""}
    for sid, rec in _records(legacy.get("spells")).items():
        # 兜底表只有 8 个常用召唤师技能；其余 ID 保留旧缓存里的英文名（丢掉就只剩占位符），
        # 但旧腾讯缓存的中文名不带进英文界面。
        spells.setdefault(sid, {"id": sid, "name": _safe_display_name(rec.get("name")) or f"Spell {sid}",
                                "icon": ""})

    items = _carry_items(legacy)

    return {
        "schema": STATIC_SCHEMA,
        "fetched_at": 0,
        "patch": metadata.normalize_patch(version),
        "versions": [{"name": version}] if version else [],
        "heroes": heroes,
        "augments": augments,
        "items": items,
        "spells": spells,
        "families": {},
        # 兜底表缺失时种子只剩 i18n 名字，来源要如实写，不能假装完整的 static_fallback。
        "source": {"seed": "static_fallback" if fb else "i18n", "ddragon": version or None},
    }


# 只有兜底表才提供的字段；大面积缺失说明种子是残缺的（static_fallback.json 缺失/损坏）。
_GAP_NAMES = {"alias": "英雄别名", "rarity": "海克斯稀有度", "spells": "召唤师技能"}


def _seed_gaps(blob: dict) -> list[str]:
    """种子缺了哪些只有兜底表才给的东西。

    判据用「过半缺失」而不是「有一条缺」：后来联网新增的个别记录没有 alias/稀有度是
    正常的，不能因此每次启动都去「修」或拒绝落盘；而兜底表缺失时这三种字段会大面积
    整表为空。
    """
    def mostly_missing(records: dict, present) -> bool:
        total = len(records)
        return not total or sum(1 for rec in records.values() if present(rec)) * 2 < total

    gaps: list[str] = []
    if mostly_missing(_records(blob.get("heroes")),
                      lambda rec: str(rec.get("alias") or "").strip() != ""):
        gaps.append("alias")
    if mostly_missing(_records(blob.get("augments")),
                      lambda rec: _rarity(rec.get("rarity")) is not None):
        gaps.append("rarity")
    if not _records(blob.get("spells")):
        gaps.append("spells")
    return gaps


def _heal_seed(blob: dict) -> tuple[dict, list[str]]:
    """用当前兜底表补齐缓存里缺的 alias/稀有度/召唤师技能，其余内容一律不动。

    只填空字段：刷新来的名字/图标、装备表和家族时间戳都保留原值，所以旧版本落下的
    残缺 schema 2 缓存可以就地治好，不用清缓存、也不发网络请求。兜底表本身仍然缺失
    或为空时原样返回——宁可用旧缓存，也不做删除或覆盖。
    """
    gaps = _seed_gaps(blob)
    if not gaps or not metadata.static_fallback():
        return blob, gaps
    seed = _seed_static()
    out = dict(blob)

    heroes = dict(_records(out.get("heroes")))
    for hid, row in _records(seed.get("heroes")).items():
        cur = dict(heroes.get(hid) or row)
        for key in ("alias", "icon", "name", "nick", "name_en", "nick_en"):
            if not str(cur.get(key) or "").strip():
                cur[key] = row.get(key, "")
        cur["keywords"] = _keywords(cur.get("keywords"), row.get("keywords"))
        cur["id"] = hid
        heroes[hid] = cur

    augments = dict(_records(out.get("augments")))
    for aid, row in _records(seed.get("augments")).items():
        cur = dict(augments.get(aid) or row)
        for key in ("name", "name_en"):
            if not str(cur.get(key) or "").strip():
                cur[key] = row.get(key, "")
        if _rarity(cur.get("rarity")) is None:      # 已经合法的稀有度保持原样
            rarity = _rarity(row.get("rarity"))
            if rarity:
                cur["rarity"] = rarity
            else:
                cur.pop("rarity", None)
        cur.setdefault("desc", "")
        cur.setdefault("icon", "")
        modes = list(cur.get("modes") or [])
        if not any(str(m).startswith("KIWI") for m in modes):
            modes.append(MAYHEM_MODES[0])
        cur["modes"] = modes
        cur["new"] = bool(cur.get("new"))
        cur["id"] = aid
        augments[aid] = cur

    spells = dict(_records(out.get("spells")))
    for sid, rec in _records(seed.get("spells")).items():
        spells.setdefault(sid, dict(rec))

    out.update(heroes=heroes, augments=augments, spells=spells)
    return out, _seed_gaps(out)


def _valid_static(blob) -> bool:
    if not isinstance(blob, dict) or blob.get("schema") != STATIC_SCHEMA:
        return False
    for key in ("heroes", "augments", "items", "spells"):
        if not isinstance(blob.get(key), dict):
            return False
    return isinstance(blob.get("versions"), list)


def _sanitize_static(blob: dict) -> dict:
    out = dict(blob)
    out["heroes"] = _records(blob.get("heroes"))
    out["augments"] = _records(blob.get("augments"))
    out["items"] = _records(blob.get("items"))
    out["spells"] = _records(blob.get("spells"))
    out["families"] = _table(blob.get("families"))
    for aid, rec in out["augments"].items():
        if _rarity(rec.get("rarity")) is None:
            rec.pop("rarity", None)
    return out


class DataStore:
    def __init__(self, root: Path, refresh_hours: float = 6.0, transport=None):
        self.root = Path(root)
        self.refresh_s = refresh_hours * 3600
        self.transport = transport
        self._lock = threading.RLock()
        self.ranks: dict = {}
        self.last_error: str | None = None
        blob = _read(self.root / "static.json")
        if _valid_static(blob):
            # 坏记录逐条丢掉；表和 schema 完整时继续用缓存，启动不等网络。
            cache = _sanitize_static(blob)
            gaps = _seed_gaps(cache)
            if not gaps:
                self.static = cache
            else:
                # 旧版本在兜底表缺失时落下的残缺缓存：能补就就地补齐，补不了照常启动但说明。
                self.static, left = _heal_seed(cache)
                if left:
                    self._incomplete(left)
                else:
                    self._persist()  # 补齐后写回；下次启动不再缺
                    log.info("静态缓存已按兜底表补齐：%s",
                             "、".join(_GAP_NAMES.get(g, g) for g in gaps))
        else:
            self.static = _seed_static(blob if isinstance(blob, dict) else None)
            left = _seed_gaps(self.static)
            if left:
                # 残缺种子绝不写成「正常」缓存：先用 i18n 名字启动，兜底表恢复后重新建完整种子。
                self._incomplete(left)
            else:
                self._persist()  # 坏/旧缓存换成本次的完整种子，下次离线启动一致

    # ---------- 刷新 ----------

    def _family_at(self, name: str) -> float:
        row = _table(_table(self.static.get("families")).get(name))
        try:
            return float(row.get("at") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _stale(self, blob: dict | None = None) -> bool:
        blob = self.static if blob is None else blob
        if not _valid_static(blob):
            return True
        now = time.time()
        return any(not self._family_at(name) or now - self._family_at(name) > self.refresh_s
                   for name in REFRESH_FAMILIES)

    def refresh(self, force: bool = False) -> None:
        self.last_error = None
        if force or self._stale(self.static):
            try:
                self._refresh_static()
            except Exception as e:  # 网络失败：继续用旧缓存
                log.warning("刷新公开资料失败：%s", e)
                self.last_error = f"公开资料：{e}"

    def _ddragon_version(self) -> str:
        versions = self.static.get("versions")
        if isinstance(versions, list) and versions and isinstance(versions[0], dict):
            name = str(versions[0].get("name") or "")
            if metadata.normalize_patch(name):
                return name
        return metadata.fallback_version()

    def _active_augment_ids(self) -> set[str]:
        """Mayhem 识别表的 ID 来源：已验证的统计/字典、本地 Mayhem i18n、六张 Cherry 卡。"""
        return set(metadata.local_augment_ids()) | set(self.augments) | set(CHERRY_AUGMENTS)

    def _new_augment_ids(self) -> set[str]:
        """有 PBE/未观测标记的新海克斯；子类从数据集 meta 补。"""
        return {aid for aid, rec in self.augments.items() if rec.get("new")}

    def _refresh_static(self) -> None:
        now = time.time()
        errors: list[str] = []
        families = dict(_table(self.static.get("families")))
        version = self._ddragon_version()
        patch = metadata.normalize_patch(version)
        versions = list(self.static.get("versions") or [])
        heroes = self.heroes
        items = self.items
        augments = self.augments
        updated = False

        try:
            raw = http.get_json(f"{metadata.DDRAGON_API}/versions.json", timeout=15,
                                transport=self.transport)
            if not isinstance(raw, list) or not raw or not isinstance(raw[0], str):
                raise ValueError("版本列表格式不对")
            version = raw[0].strip()
            patch = metadata.normalize_patch(version)
            if not patch:
                raise ValueError(f"版本号格式不对：{version}")
            versions = [{"name": str(v)} for v in raw[:6] if isinstance(v, str) and v.strip()]
            families["versions"] = {"at": now, "version": version}
            updated = True
        except Exception as e:
            errors.append(f"版本：{e}")
            log.info("版本列表刷新失败，继续用 %s：%s", version or "本地兜底", e)

        # 英雄/装备都依赖版本号；版本抓不到时仍用缓存/兜底版本继续尝试，互不连坐。
        if version:
            try:
                payload = http.get_json(
                    f"{metadata.DDRAGON_BASE}/{version}/data/en_US/champion.json",
                    timeout=30, transport=self.transport)
                heroes = _merge_heroes(
                    heroes, _usable_records(metadata.parse_champions(payload, version), "英雄"))
                families["heroes"] = {"at": now, "version": version}
                updated = True
            except Exception as e:
                errors.append(f"英雄：{e}")
                log.info("英雄资料刷新失败，保留上一份：%s", e)
            try:
                payload = http.get_json(
                    f"{metadata.DDRAGON_BASE}/{version}/data/en_US/item.json",
                    timeout=30, transport=self.transport)
                items = _usable_records(metadata.parse_items(payload, version), "装备")
                families["items"] = {"at": now, "version": version}
                updated = True
            except Exception as e:
                errors.append(f"装备：{e}")
                log.info("装备资料刷新失败，保留上一份：%s", e)
        else:
            errors.append("版本：没有可用的 Data Dragon 版本")

        try:
            payload = http.get_json(metadata.CDRAGON_AUGMENTS, timeout=30,
                                    transport=self.transport)
            parsed = _usable_records(metadata.parse_augments(
                payload, self._active_augment_ids(), modes=MAYHEM_MODES,
                new_ids=self._new_augment_ids()), "海克斯")
            augments = _merge_augments(augments, parsed)
            families["augments"] = {"at": now, "version": version or None}
            updated = True
        except Exception as e:
            errors.append(f"海克斯：{e}")
            log.info("海克斯字典刷新失败，保留上一份：%s", e)

        if errors:
            self.last_error = "；".join(errors)[:500]
        if not updated:
            return  # 一个家族都没刷新成功：保留磁盘上的上一份，绝不写坏
        with self._lock:
            self.static = {
                "schema": STATIC_SCHEMA,
                "fetched_at": now,
                "patch": patch or self.static.get("patch", ""),
                "versions": versions,
                "heroes": heroes,
                "augments": augments,
                "items": items,
                "spells": self.spells,
                "families": families,
                "source": {"ddragon": version or None, "cdragon": "global/default"},
            }
        self._persist()

    def _incomplete(self, gaps: list[str]) -> None:
        """残缺种子/缓存：可见地说明缺了什么，不假装资料完整。"""
        missing = "、".join(_GAP_NAMES.get(g, g) for g in gaps)
        self.last_error = (f"静态资料不完整（缺{missing}）：本地兜底表缺失或损坏，"
                           "恢复后会自动补齐")
        log.warning(self.last_error)

    def _persist(self) -> None:
        with self._lock:
            blob = self.static
        gaps = _seed_gaps(blob)
        if gaps:
            # 残缺缓存绝不落盘：否则日后修好兜底表也只会读到这份看似正常的旧缓存。
            if not self.last_error:
                self._incomplete(gaps)
            return
        try:
            _write(self.root / "static.json", blob)
        except OSError as e:
            log.warning("静态资料落盘失败：%s", e)

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
            if not modes or any(str(m).startswith("KIWI") for m in modes):
                out[aid] = a
        return out

    def hero_terms(self, hid: str) -> list[str]:
        """能搜到这个英雄的所有叫法：名字、称号、英文名/称号、旧缓存关键词、玩家叫法。"""
        h = self.heroes.get(hid) or {}
        raw = [h.get("name"), h.get("nick"), h.get("alias"), h.get("name_en"), h.get("nick_en"),
               *(h.get("keywords") or "").split(","), *hero_aliases().get(hid, [])]
        out, seen = [], set()
        for t in raw:
            t = (t or "").strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out

    def resolve_hero(self, key: str | int | None) -> str | None:
        """按 heroId / 英文 alias / 中文名 / 称号找英雄；
        再按别名（英文关键词、玩家叫法）精确匹配。"""
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
                      (h.get("nick") or "").lower(), (h.get("name_en") or "").lower(),
                      (h.get("nick_en") or "").lower()):
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
            "static_schema": self.static.get("schema"),
            "static_source": self.static.get("source"),
            "static_families": self.static.get("families"),
            # 兜底表缺失时种子只剩 i18n 名字：如实标出，界面/CLI 可以据此提示。
            "static_complete": not _seed_gaps(self.static),
            "augments": len(self.augments),
            "heroes": len(self.heroes),
            "error": self.last_error,
        }
