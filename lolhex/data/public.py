"""自采统计数据（公开数据仓库 github.com/czgreat/aramhex-data 的格式）。

一份数据 = 一个目录：
    latest.json                      清单：版本、样本时间、文件列表（SHA-256、大小）
    meta.json                        口径、样本时间窗、局限
    heroes.json / hero_augments.json 全体
    bands/<casual|mid|high|top>/heroes.json、hero_augments.json   分段（可选）

两个来源，用样本更新的那份：
- 安装包内置：lolhex/data/bundled/（发版时由 scripts/update_data.py 放进来）；
- 下载的：<app_home>/data/public/（启动时查数据仓库的 latest.json，有新数据就下载，逐个文件校验 SHA-256）。
  先试 aramhex.com 镜像，连不上或校验不过再用 raw.githubusercontent.com 兜底（DATA_SOURCES）。

静态资料（英雄、海克斯字典、装备）仍由父类 DataStore 取；单英雄出装、加点、官方层级已移除，
hero() 只返回自采统计口径的数据。
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import shutil
import threading
import time
from pathlib import Path

from .. import DATA_REPO, MIRROR
from . import http, metadata
from .store import CHERRY_AUGMENTS, DataStore, _rarity, _read

log = logging.getLogger(__name__)


def headers() -> dict[str, str]:
    """统计数据请求的匿名请求头：只有版本号，没有安装编号、Cookie 或账号信息。"""
    return {"User-Agent": http.APP_UA}

# 1.1.1 起只分三档（数据里 high、top 早就合成了「前 5%」，bands/top 和 bands/high 内容相同）
BANDS = {"casual": "娱乐", "mid": "中分", "high": "前 5%"}
BAND_ALIASES = {"top": "high"}  # 老设置文件、查分服务里的 top 当 high


def norm_band(band):
    return BAND_ALIASES.get(band, band) if band else band
BUNDLED_DIR = Path(__file__).with_name("bundled")
RAW_BASE = f"https://raw.githubusercontent.com/{DATA_REPO}/main"
# 先走官网镜像（DMIT 定时从 GitHub 同步），不通再用 raw GitHub。每个文件都按清单校验 SHA-256。
DATA_SOURCES = [f"{MIRROR}/data", RAW_BASE]
SYNC_EVERY_S = 6 * 3600
SCHEMA_VERSION = 1


class DatasetError(ValueError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise DatasetError("数据清单版本不支持")
    files = manifest.get("files")
    if not isinstance(files, dict) or "meta.json" not in files or "heroes.json" not in files \
            or "hero_augments.json" not in files:
        raise DatasetError("数据清单缺文件")
    for name, f in files.items():
        if ".." in name or name.startswith(("/", "\\")) or not name.endswith(".json"):
            raise DatasetError(f"数据清单里有不合法的文件名：{name}")
        if not isinstance(f, dict) or len(str(f.get("sha256", ""))) != 64:
            raise DatasetError(f"数据清单里 {name} 没有 SHA-256")
    return manifest


class Dataset:
    """读进内存的一份数据。构造时逐个文件核对 SHA-256，不对就整份不用。"""

    def __init__(self, folder: Path, origin: str):
        self.folder, self.origin = Path(folder), origin
        manifest = _read(self.folder / "latest.json")
        if manifest is None:
            raise DatasetError(f"{folder} 没有 latest.json")
        # 清单是这份数据的身份：拷一份，调用方/下载流程后续改动不会悄悄改掉已加载数据集的校验依据。
        self.manifest = check_manifest(copy.deepcopy(manifest))
        for name, f in self.manifest["files"].items():
            p = self.folder / name
            if not p.is_file() or _sha256(p) != f["sha256"]:
                raise DatasetError(f"{name} 缺失或校验不对")
        self.meta = _read(self.folder / "meta.json") or {}
        self.patch = str(self.manifest.get("patch") or self.meta.get("patch") or "")
        self.snapshot_at = str(self.manifest.get("snapshot_at") or "")
        self.seq = int(self.manifest.get("seq") or 0)  # 数据更新序号
        self.mode = str(self.manifest.get("mode") or "normal")       # normal / first-prismatic 等
        self.mode_label = str(self.manifest.get("mode_label") or "")
        # 数据版本号：整份清单（全部文件的 SHA-256 + 样本时间）的摘要，任何一个文件变了都会变
        ident = json.dumps([self.patch, self.snapshot_at, self.manifest["files"]], sort_keys=True)
        self.revision = hashlib.sha256(ident.encode("utf-8")).hexdigest()[:12]
        self._tables: dict[str, tuple[dict, dict]] = {}
        self._shrink: dict[str, int] = {}

    def bands_available(self) -> bool:
        return all(f"bands/{b}/heroes.json" in self.manifest["files"] for b in BANDS)

    def band_shrink(self, band: str) -> int:
        if band not in self._shrink:
            self._shrink[band] = _band_shrink(self.table(None), self.table(band))
        return self._shrink[band]

    def optional_table(self, name: str, band: str | None = None) -> dict:
        """可选的数据文件（hero_spells.json、hero_items.json，1.1.1 起读）：清单里有就读，没有返回 {}。
        选了分段且有分段文件时读分段的。老版本客户端不认这些文件，忽略。"""
        for prefix in ((f"bands/{band}/",) if band else ()) + ("",):
            if prefix + name in self.manifest["files"]:
                key = "opt:" + prefix + name
                if key not in self._tables:
                    data = _read(self.folder / (prefix + name))
                    self._tables[key] = data if isinstance(data, dict) else {}
                return self._tables[key]
        return {}

    def table(self, band: str | None) -> tuple[dict, dict]:
        """(heroes, hero_augments)；band=None 为全体。"""
        key = band or ""
        if key not in self._tables:
            prefix = f"bands/{band}/" if band else ""
            self._tables[key] = (_read(self.folder / f"{prefix}heroes.json") or {},
                                 _read(self.folder / f"{prefix}hero_augments.json") or {})
        return self._tables[key]


SHRINK_DEFAULT, SHRINK_MIN, SHRINK_MAX = 3000, 1000, 30000


def _band_shrink(tables_all: tuple[dict, dict], tables_band: tuple[dict, dict]) -> int:
    """分段和全体综合时的 K（局数）：分段里有 K 局时，「这个海克斯比英雄平均高多少」分段和全体各信一半（Gitea #7）。
    按这份数据自己估：同英雄同海克斯，分段的优势减全体的优势，方差扣掉随机误差就是真实差别 τ²，K = 0.25 / τ²。
    16.20 估出来：娱乐、中分约 1.1 万，前 5% 约 3400。格子太少（新版本刚开始）用默认值。"""
    heroes_all, augs_all = tables_all
    heroes_b, augs_b = tables_band
    sq = noise = 0.0
    n = 0
    for hid, augs in augs_b.items():
        hb, ha = heroes_b.get(hid), heroes_all.get(hid)
        if not hb or not ha:
            continue
        for aid, x in augs.items():
            y = (augs_all.get(hid) or {}).get(aid)
            if not y or x.get("games", 0) < 1000 or not y.get("games"):
                continue
            d = (x["win_rate"] - hb["win_rate"]) - (y["win_rate"] - ha["win_rate"])
            p = x["win_rate"]
            sq += d * d
            noise += p * (1 - p) * max(1 / x["games"] - 1 / y["games"], 1 / y["games"])
            n += 1
    if n < 200:
        return SHRINK_DEFAULT
    tau2 = sq / n - noise / n
    if tau2 <= 0:
        return SHRINK_MAX
    return int(min(SHRINK_MAX, max(SHRINK_MIN, 0.25 / tau2)))


def load_best(folders: list[tuple[Path, str]]) -> Dataset | None:
    """在几个候选目录里挑样本最新、校验通过的一份。"""
    best = None
    for folder, origin in folders:
        try:
            ds = Dataset(folder, origin)
        except (DatasetError, OSError, ValueError) as e:
            if (Path(folder) / "latest.json").exists():
                log.warning("统计数据 %s 不能用：%s", folder, e)
            continue
        if best is None or (ds.snapshot_at, ds.patch) > (best.snapshot_at, best.patch):
            best = ds
    return best


PACK_FORMAT = "aramhex-pack-1"


def _dump_json(obj) -> bytes:
    """和数据仓库导出时完全一样的写法，还原出的文件和原文件逐字节一致。"""
    return (json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def make_pack(folder: Path, manifest: dict) -> bytes:
    """一份数据 → 压缩包（官网镜像生成，和 unpack 配对）。"""
    import lzma
    files = {}
    for name in manifest["files"]:
        obj = json.loads((Path(folder) / name).read_text(encoding="utf-8"))
        if name.endswith("hero_augments.json"):
            obj = {h: [[int(a), s["games"], s["wins"], 1 if s.get("low_sample") else 0] for a, s in sorted(d.items())]
                   for h, d in obj.items()}
        files[name] = obj
    raw = json.dumps({"format": PACK_FORMAT, "files": files}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return lzma.compress(raw.encode("utf-8"), preset=9 | lzma.PRESET_EXTREME)


def unpack(blob: bytes) -> dict[str, bytes]:
    """官网镜像上的压缩包（xz）→ {文件名: 原文件字节}。hero_augments 在包里是 [海克斯ID, 局数, 胜场, 样本少]，
    胜率按导出时的算法 round(胜场/局数, 6) 还原。"""
    import lzma
    pack = json.loads(lzma.decompress(blob))
    if pack.get("format") != PACK_FORMAT:
        raise DatasetError("压缩包格式不支持")
    out = {}
    for name, obj in pack["files"].items():
        if name.endswith("hero_augments.json"):
            obj = {h: {str(a): {"games": g, "low_sample": bool(low), "win_rate": round(w / g, 6) if g else 0.0, "wins": w}
                       for a, g, w, low in rows} for h, rows in obj.items()}
        out[name] = _dump_json(obj)
    return out


def download(base_url: str, manifest: dict, dest: Path, timeout: float = 30, progress=None, *,
             transport=None) -> None:
    """按清单下载一份数据到 dest（先写到旁边的临时目录，全部校验通过才换上）。progress(已下载字节, 总字节)。
    先试官网镜像上的压缩包（约小一半），还原后按清单逐个核对 SHA-256；没有或不对就逐个文件下载。"""
    check_manifest(manifest)
    path = str(manifest.get("path") or "").strip("/")
    if not path or ".." in path:
        raise DatasetError("数据清单没有 path")
    tmp = dest.with_name(dest.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    total = sum(int(f.get("size") or 0) for f in manifest["files"].values())
    done = [0]

    def on_bytes(n):
        done[0] += n
        if progress:
            progress(done[0], total)
    files = None
    try:
        files = unpack(http.fetch(f"{base_url}/{path}.pack.xz", timeout=timeout, headers=headers(),
                                  on_bytes=lambda n: progress and progress(0, 0),
                                  transport=transport))
        log.info("统计数据用压缩包下载：%s", base_url)
    except Exception as e:
        log.debug("没有可用的压缩包（%s），逐个文件下载", e)
    try:
        for name, f in manifest["files"].items():
            body = files.get(name) if files else None
            if body is None or hashlib.sha256(body).hexdigest() != f["sha256"]:
                if files:
                    log.info("压缩包里的 %s 对不上，改为逐个文件下载", name)
                    files = None
                body = http.fetch(f"{base_url}/{path}/{name}", timeout=timeout, headers=headers(),
                                  on_bytes=on_bytes, transport=transport)
            if hashlib.sha256(body).hexdigest() != f["sha256"] or ("size" in f and len(body) != f["size"]):
                raise DatasetError(f"{name} 校验不对（下载不完整或文件被改过）")
            out = tmp / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(body)
        (tmp / "latest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        Dataset(tmp, "downloaded")  # 整份再核一遍
        old = dest.with_name(dest.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        if dest.exists():
            dest.rename(old)
        tmp.rename(dest)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


class PublicStore(DataStore):
    def __init__(self, root: Path, refresh_hours: float = 6.0, bundled: Path | None = None,
                 check_updates: bool = True, base_url: str | list[str] | None = None,
                 transport=None):
        super().__init__(root, refresh_hours, transport=transport)
        self.bundled = Path(bundled or BUNDLED_DIR)
        self.downloaded = self.root / "public"
        self.check_updates = check_updates
        if base_url is None:
            urls = DATA_SOURCES
        else:
            urls = [base_url] if isinstance(base_url, str) else base_url
        self.base_urls = [u.rstrip("/") for u in urls]
        self.data_source: str | None = None  # 上次成功取到清单的地址
        self.band: str | None = None
        self.dataset: Dataset | None = None
        self._dataset_seeded = False
        self.data_updated_at: float | None = None
        self.sync_error: str | None = None
        self.sync_progress: dict | None = None  # 下载统计数据时 {done, total}（字节）
        self.sync_every_s = SYNC_EVERY_S  # 多久查一次数据仓库；引擎用固定的本地间隔改
        self.hold = lambda: False  # 返回 True 时（正在对局）不在后台换数据，打完再换，一局里推荐前后一致
        self.data_note: dict | None = None   # 后台换了新数据：{id, text}，界面在游戏外提示一次
        self.data_offer: dict | None = None  # 关了自动更新、发现有新数据：{id, text}，界面在游戏外问一次
        self._last_sync = 0.0
        self._sync_lock = threading.Lock()
        self._views: dict = {}
        self.reload_dataset()

    # ---------- 数据集 ----------

    def reload_dataset(self) -> bool:
        """重新挑选数据；换了一份返回 True。换数据后把已验证的静态表并进本地种子。"""
        ds = load_best([(self.downloaded, "downloaded"), (self.bundled, "bundled")])
        with self._lock:
            changed = ds is not None and (self.dataset is None or ds.revision != self.dataset.revision)
            if changed or ds is None:
                self.dataset = ds
                self._views.clear()
            self._apply_ranks()
        if ds is not None and (changed or not self._dataset_seeded):
            self._seed_from_dataset(ds)
            self._dataset_seeded = True
        return changed

    @staticmethod
    def _dataset_augment_ids(ds: "Dataset") -> set[str]:
        """数据集里真正出现过的海克斯 ID；hero_augments 外层是英雄 ID，必须取内层键。"""
        ids: set[str] = set()
        _, hero_augs = ds.table(None)
        for rows in (hero_augs.values() if isinstance(hero_augs, dict) else ()):
            if isinstance(rows, dict):
                ids.update(str(aid) for aid in rows)
        ids |= {str(aid) for aid in ds.optional_table("augments.json")}
        meta = ds.meta if isinstance(ds.meta, dict) else {}
        for key in ("provisional_augments", "unobserved_augments"):
            rows = meta.get(key)
            if isinstance(rows, dict):
                ids.update(str(aid) for aid in rows)
        return ids

    def _allowed_augment_ids(self) -> set[str]:
        """Mayhem 白名单：已知本地 Mayhem 名字表 + 六张 Cherry 卡 + 数据集里验证过的 ID。

        不从当前缓存里已有键反推：旧版本的 173 条英雄 ID 污染过缓存，不能自我证明合法。
        """
        ids = set(metadata.local_augment_ids()) | set(CHERRY_AUGMENTS)
        if self.dataset is not None:
            ids |= self._dataset_augment_ids(self.dataset)
        return ids

    def _seed_from_dataset(self, ds: "Dataset") -> None:
        """校验通过的数据集里本来就带着英雄中文名、海克斯名字/稀有度和新卡标记：先并进静态表。

        构造函数阶段调用，不发网络。只加白名单里真正有的 ID（Mayhem 统计/232 条字典/新卡），
        不把英文源里 594 条竞技场记录整体放进来，也顺手清掉旧缓存里混进来的英雄 ID。
        """
        heroes, _ = ds.table(None)
        meta = ds.meta if isinstance(ds.meta, dict) else {}
        aug_meta = ds.optional_table("augments.json")
        new_ids = set()
        for key in ("provisional_augments", "unobserved_augments"):
            rows = meta.get(key)
            if isinstance(rows, dict):
                new_ids.update(str(aid) for aid in rows)
        allowed = self._allowed_augment_ids()
        with self._lock:
            cur_heroes = dict(self.heroes)
            for hid, row in (heroes.items() if isinstance(heroes, dict) else ()):
                if not isinstance(row, dict):
                    continue
                hid = str(hid)
                base = dict(cur_heroes.get(hid) or {"id": hid})
                if isinstance(row.get("name"), str) and row["name"].strip():
                    base["name"] = row["name"].strip()
                if isinstance(row.get("title"), str) and row["title"].strip():
                    base["nick"] = row["title"].strip()
                base.setdefault("name_en", metadata.hero_en(hid)[0])
                base.setdefault("nick_en", metadata.hero_en(hid)[1])
                base.setdefault("keywords", ",".join(
                    t for t in (base.get("alias"), base.get("name_en"), base.get("nick_en")) if t))
                cur_heroes[hid] = base

            # 旧 schema 2 缓存可能把 173 个英雄 ID 当成海克斯；只保留白名单里的有效记录。
            cur_augs = {aid: rec for aid, rec in self.augments.items() if aid in allowed}
            for aid in allowed:
                aid = str(aid)
                row = aug_meta.get(aid) if isinstance(aug_meta, dict) else None
                base = dict(cur_augs.get(aid) or {"id": aid})
                if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"].strip():
                    base["name"] = row["name"].strip()
                if not base.get("name"):
                    base["name"] = metadata.augment_zh(aid)
                if not base.get("name_en"):
                    base["name_en"] = metadata.augment_en(aid)
                rarity = _rarity((row or {}).get("rarity")) if isinstance(row, dict) else None
                if rarity:
                    base["rarity"] = rarity
                elif _rarity(base.get("rarity")) is None:
                    base.pop("rarity", None)
                base.setdefault("desc", "")
                base.setdefault("icon", "")
                modes = list(base.get("modes") or [])
                if not any(str(m).startswith("KIWI") for m in modes):
                    modes.append("KIWI")           # 数据集里出现的 ID 已证明是 Mayhem 卡
                base["modes"] = modes
                base["new"] = bool(base.get("new") or aid in new_ids)
                cur_augs[aid] = base
            families = self.static.get("families") or {}
            patch = self.static.get("patch") if families.get("versions") else ds.patch
            self.static = {**self.static, "heroes": cur_heroes, "augments": cur_augs,
                           "patch": patch or self.static.get("patch", "")}
        self._persist()

    def _active_augment_ids(self) -> set[str]:
        # 不回退到 super()：那里的 set(self.augments) 会把旧缓存污染当成合法来源。
        return self._allowed_augment_ids()

    def _new_augment_ids(self) -> set[str]:
        ids = super()._new_augment_ids()
        meta = self.dataset.meta if self.dataset and isinstance(self.dataset.meta, dict) else {}
        for key in ("provisional_augments", "unobserved_augments"):
            rows = meta.get(key)
            if isinstance(rows, dict):
                ids |= {str(aid) for aid in rows}
        return ids

    def sync_data(self, force: bool = False, manual: bool = False) -> bool:
        """查数据仓库有没有更新的统计数据，有就下载并换上。下载了新数据返回 True。
        manual=True：用户同意了统计数据更新提示，关了自动更新、正在对局也查。
        后台查时：正在对局就先不查（打完再查）；关了自动更新只看有没有新的，有就记到 data_offer 等用户点头。"""
        if not manual and self.hold():
            log.debug("对局中，统计数据更新推迟到打完")
            return False
        if not self._sync_lock.acquire(blocking=False):
            return False
        try:
            if not force and time.time() - self._last_sync < self.sync_every_s:
                return False
            self._last_sync = time.time()
            if not self.check_updates and not manual:
                self._look_for_offer()
                return False
            errors = []
            for base in self.base_urls:  # 一个地址连不上、或下载的文件校验不过，就换下一个
                try:
                    changed = self._sync_from(base)
                except Exception as e:
                    errors.append(f"{base.split('/')[2]}：{e}")
                    log.info("从 %s 检查统计数据更新失败：%s", base, e)
                    continue
                self.data_source, self.sync_error = base, None
                return changed
            # 都连不上很常见：用手头的数据，不打扰用户
            self.sync_error = "；".join(errors)[:300]
            return False
        finally:
            self._sync_lock.release()

    def _read_manifest(self, base: str) -> dict:
        """读一份数据仓库的 latest.json（清单只读，不下载）。"""
        remote = http.get_json(f"{base}/latest.json", headers=headers(), timeout=15,
                               transport=self.transport)
        return check_manifest(remote)

    def _newer(self, remote: dict) -> bool:
        cur = self.dataset
        return not cur or (str(remote.get("snapshot_at") or ""), str(remote.get("patch") or "")) > (cur.snapshot_at, cur.patch)

    @staticmethod
    def _describe(remote: dict) -> str:
        """「16.20 版本，截至 10-17，3699 万局」"""
        parts = [f"{remote['patch']} 版本"] if remote.get("patch") else []
        if remote.get("snapshot_at"):
            parts.append("截至 " + str(remote["snapshot_at"])[5:10])
        m = remote.get("matches")
        m = m.get("valid") if isinstance(m, dict) else m
        if isinstance(m, int) and m > 0:
            parts.append(f"{m / 1e4:.0f} 万局" if m >= 1e4 else f"{m} 局")
        return "，".join(parts)

    def _look_for_offer(self) -> None:
        """关了自动更新时：只读清单，看看有没有更新的数据（不下载）。连不上就算了，下次再看。"""
        for base in self.base_urls:
            try:
                remote = self._read_manifest(base)
            except Exception as e:
                log.info("从 %s 查看统计数据失败：%s", base, e)
                continue
            if self._newer(remote):
                log.info("发现新统计数据（%s），自动更新关着，等用户确认", self._describe(remote))
                self.data_offer = {"id": f"{remote.get('patch')}|{remote.get('snapshot_at')}",
                                   "text": self._describe(remote)}
            return

    def _sync_from(self, base: str) -> bool:
        remote = self._read_manifest(base)
        if not self._newer(remote):
            return False
        log.info("统计数据有更新：%s（样本截至 %s），从 %s 下载", remote.get("patch"), remote.get("snapshot_at"), base)
        self.sync_progress = {"done": 0, "total": 0}  # 界面据此显示"统计数据更新中 x / y MB"
        try:
            download(base, remote, self.downloaded, transport=self.transport,
                     progress=lambda d, t: setattr(self, "sync_progress", {"done": d, "total": t}))
        finally:
            self.sync_progress = None
        if self.reload_dataset():
            self.data_updated_at = time.time()
            self.data_offer = None
            self.data_note = {"id": self.dataset.revision, "text": "数据已更新：" + self._describe(remote)}
            return True
        return False

    def refresh(self, force: bool = False) -> None:
        super().refresh(force)
        self.sync_data(force)

    # ---------- 分段 ----------

    def set_band(self, band: str | None) -> None:
        with self._lock:
            band = norm_band(band)
            self.band = band if band in BANDS else None
            self._apply_ranks()

    def bands_available(self) -> bool:
        return bool(self.dataset and self.dataset.bands_available())

    def effective_band(self) -> str | None:
        """实际使用的分数段：数据里没有分段时退回全体。"""
        return self.band if self.band and self.bands_available() else None

    def _apply_ranks(self) -> None:
        """英雄排名、胜率和全英雄海克斯胜率（未识别英雄时的兜底）换成当前分段的。调用方持锁。"""
        if not self.dataset:
            self.ranks = {}
            return
        heroes, hero_augs = self.dataset.table(self.effective_band())
        total = sum(h["games"] for h in heroes.values()) or 1
        order = sorted(heroes, key=lambda h: (-heroes[h]["win_rate"], int(h)))
        agg: dict[str, list[int]] = {}
        for augs in hero_augs.values():
            for aid, a in augs.items():
                s = agg.setdefault(aid, [0, 0])
                s[0] += a["games"]
                s[1] += a["wins"]
        self.ranks = {"source": "public", "patch": self.dataset.patch, "band": self.effective_band(),
                      "heroes": {hid: {"win": heroes[hid]["win_rate"], "games": heroes[hid]["games"],
                                       "pick": heroes[hid]["games"] / total, "rank": i + 1}
                                 for i, hid in enumerate(order)},
                      "augments": {aid: {"win": w / n, "games": n} for aid, (n, w) in agg.items() if n}}

    def excluded_augments(self) -> dict[str, str]:
        """数据集 meta.json 的 excluded_augments：{"1337": {"name": ..., "reason": ...}}。"""
        ex = (self.dataset.meta if self.dataset else {}).get("excluded_augments") or {}
        return {str(aid): str((v or {}).get("reason") or "") if isinstance(v, dict) else str(v or "")
                for aid, v in ex.items()} if isinstance(ex, dict) else {}

    def provisional_augments(self) -> dict[str, dict]:
        """meta.json 的 provisional_augments（scripts/pbe_overlay.py 生成的过渡数据才有）。"""
        pv = (self.dataset.meta if self.dataset else {}).get("provisional_augments") or {}
        return {str(aid): v for aid, v in pv.items() if isinstance(v, dict) and v.get("games")} if isinstance(pv, dict) else {}

    def label(self) -> str:
        if not self.dataset:
            return "暂无统计数据"
        band = self.effective_band()
        return f"自采统计·{self.dataset.patch}版本" + (f"·{BANDS[band]}" if band else "")

    # ---------- 查询（panel / recommend 用） ----------

    def band_shrink(self) -> int | None:
        """当前分段和全体综合用的 K（见 _band_shrink）；没选分段为 None。"""
        band = self.effective_band()
        return self.dataset.band_shrink(band) if band and self.dataset else None

    def win_data_all(self, hero_id: str) -> dict | None:
        """单英雄 × 海克斯胜率（全体，不管选了哪个分段）。"""
        return self.win_data(hero_id, band=None)

    def win_data(self, hero_id: str, allow_network: bool = True, band: str | None = "") -> dict | None:
        """单英雄 × 海克斯胜率（当前分段；band=None 为全体）。"""
        if not self.dataset:
            return None
        band = self.effective_band() if band == "" else band
        heroes, hero_augs = self.dataset.table(band)
        h = heroes.get(str(hero_id))
        if not h:
            return None
        return {"source": "public", "label": self.label(), "patch": self.dataset.patch,
                "sample_games": h["games"], "wins": h["wins"], "sample_win": h["win_rate"],
                "augments": {aid: {"games": a["games"], "wins": a["wins"], "win": a["win_rate"],
                                   "low_sample": a.get("low_sample", False)}
                             for aid, a in (hero_augs.get(str(hero_id)) or {}).items()},
                "band": band, "band_label": BANDS.get(band)}

    def _hero_rows(self, name: str, hero_id: str) -> tuple[list[dict], str]:
        """hero_spells / hero_items 里这个英雄的各行：[{key, games, wins, win}]，按局数从多到少。"""
        if not self.dataset:
            return [], ""
        band = self.effective_band()
        table = self.dataset.optional_table(name, band)
        rows = []
        for key, x in (table.get(str(hero_id)) or {}).items():
            if not isinstance(x, dict):
                continue
            g, w = x.get("games"), x.get("wins")
            if isinstance(g, int) and g > 0 and isinstance(w, int) and 0 <= w <= g:
                rows.append({"key": str(key), "games": g, "wins": w, "win": w / g})
        rows.sort(key=lambda r: -r["games"])
        return rows, self.label()

    def hero_spells(self, hero_id: str) -> tuple[list[dict], str]:
        """自采统计的召唤师技能组合（hero_spells.json：英雄 → "4+32" → 局数/胜场）。没有这个文件返回 []。
        返回 ([{spells: [ID, ID], games, win, pick}], 来源说明)。"""
        rows, label = self._hero_rows("hero_spells.json", hero_id)
        total = sum(r["games"] for r in rows) or 1
        out = [{"spells": [x for x in r["key"].split("+") if x], "games": r["games"], "win": r["win"],
                "pick": r["games"] / total} for r in rows]
        return [r for r in out if len(r["spells"]) == 2], label

    def hero_items(self, hero_id: str) -> tuple[list[dict], str]:
        """自采统计的装备（hero_items.json：英雄 → 装备 ID → 局数/胜场）。没有这个文件返回 []。"""
        rows, label = self._hero_rows("hero_items.json", hero_id)
        return [{"item": r["key"], "games": r["games"], "win": r["win"]} for r in rows], label

    def augment_items(self, hero_id: str, augment_id: str) -> dict | None:
        """按英雄、海克斯配置的装备建议；独立于普通出装统计，保持数据提供的顺序。"""
        if not self.dataset:
            return None
        table = self.dataset.optional_table("hero_augment_items.json")
        hero = table.get(str(hero_id))
        cfg = hero.get(str(augment_id)) if isinstance(hero, dict) else None
        if not isinstance(cfg, dict) or cfg.get("source") not in ("stats", "community", "manual"):
            return None
        raw = cfg.get("items")
        if not isinstance(raw, list):
            return None
        rows, seen = [], set()
        for x in raw:
            if not isinstance(x, dict):
                continue
            iid = str(x.get("item") or "")
            if not iid.isascii() or not iid.isdigit() or len(iid) > 6 or iid in seen:
                continue
            meta = self.items.get(iid) or {}
            name = meta.get("name") or x.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            g, w = x.get("games"), x.get("wins")
            if (g is not None or w is not None) and not (type(g) is int and g > 0 and type(w) is int and 0 <= w <= g):
                continue
            show = cfg.get("show_winrate", True) is True and x.get("show_winrate", True) is True
            rows.append({"item": iid, "name": name[:24], "icon": meta.get("icon"),
                         "games": g, "win": w / g if show and g else None})
            seen.add(iid)
            if len(rows) == 3:  # 卡片另一侧的空位只放三行；人工推荐的先后顺序不重排
                break
        return {"source": cfg["source"], "items": rows} if rows else None

    def hero(self, hero_id: str, allow_network: bool = True) -> dict | None:
        """统计口径的单英雄资料：只有有统计的海克斯，带稀有度和本英雄出场占比。
        官方出装、加点、层级、原画已移除；没有统计返回 None。"""
        stats = self.win_data(hero_id, band=None)  # 列出所有有统计的海克斯，不随当前分段缺行
        if not stats:
            return None
        augments = []
        for aid, a in stats["augments"].items():
            meta = self.augments.get(aid) or {}
            augments.append({"id": aid, "rarity": meta.get("rarity"),
                             "pick": a["games"] / stats["sample_games"] if stats["sample_games"] else None})
        return {"source": "public", "label": stats["label"], "patch": stats["patch"],
                "date": None, "augments": augments}

    def status(self) -> dict:
        s = super().status()
        ds = self.dataset
        meta = ds.meta if ds else {}
        s.update(dataset=bool(ds), dataset_patch=ds.patch if ds else None,
                 dataset_snapshot=ds.snapshot_at if ds else None, dataset_origin=ds.origin if ds else None,
                 dataset_revision=ds.revision if ds else None, dataset_window=meta.get("window"),
                 dataset_matches=(meta.get("matches") or {}).get("valid") if isinstance(meta.get("matches"), dict) else meta.get("matches"),
                 dataset_collected=(meta.get("matches") or {}).get("collected") if isinstance(meta.get("matches"), dict) else None,
                 dataset_regions=meta.get("regions"),
                 dataset_label=self.label(), bands_available=self.bands_available(),
                 band=self.band, band_effective=self.effective_band(),
                 dataset_mode=ds.mode if ds else None,
                 dataset_mode_label=(ds.mode_label or ds.mode) if ds and ds.mode != "normal" else None,
                 data_updated_at=self.data_updated_at, sync_error=self.sync_error,
                 data_progress=self.sync_progress, data_note=self.data_note, data_offer=self.data_offer)
        return s
