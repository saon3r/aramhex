"""清单里的文件名必须限定在数据目录内：绝对路径、盘符、数据流、Windows 保留名都不算相对路径。

压缩包（.pack.xz）本身带着文件字节，逐个文件的 HTTP 地址策略根本不经手；所以写盘之前
只能靠清单校验把名字挡住。这批用例是那次审查发现的越界写盘回归测试。
"""

import hashlib
import json
import lzma
from pathlib import Path

import pytest

from lolhex.data import public
from lolhex.data.public import DatasetError, check_manifest

REQUIRED = ("meta.json", "heroes.json", "hero_augments.json")


def _entry(body: bytes) -> dict:
    return {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}


def _pack(objects: dict) -> bytes:
    """和官网镜像同格式的压缩包：文件名和内容都由调用方给。"""
    raw = json.dumps({"format": public.PACK_FORMAT, "files": objects},
                     ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return lzma.compress(raw.encode("utf-8"))


def _manifest(extra: dict | None = None) -> dict:
    """最小清单：压缩包里还原出的字节就是清单声明的字节。"""
    objects = {name: {} for name in REQUIRED}
    objects.update(extra or {})
    files = {name: _entry(public._dump_json(obj)) for name, obj in objects.items()}
    return {"schema_version": 1, "path": "patches/16.21/normal",
            "snapshot_at": "2026-10-20T00:00:00+08:00", "patch": "16.21", "files": files}


class _PackTransport:
    """只提供压缩包；逐个文件的地址一律失败，证明数据来自压缩包而不是 URL 下载。"""

    def __init__(self, pack: bytes):
        self.pack, self.urls = pack, []

    def fetch(self, url, **kw):
        self.urls.append(url)
        if url.endswith(".pack.xz"):
            return self.pack
        raise AssertionError(f"不该逐个下载：{url}")

    def get(self, url, **kw):
        raise AssertionError(f"测试不该用 GET：{url}")


# 今天的漏洞：盘符开头的名字既没有 ".." 也不是 / 开头，清单放行，unpack 已经有字节，
# 于是 out = tmp / name 直接写到数据目录外面。
ESCAPES = [
    "C:/outside.json",
    "C:\\outside.json",
    "c:outside.json",
    "//server/share/outside.json",
    "/etc/outside.json",
    "..\\..\\evil.json",
    "../outside.json",
    "bands/../../outside.json",
    "bands/./heroes.json",
    "./heroes.json",
    "bands//heroes.json",
    "heroes.json:stream",
    "con.json",
    "NUL.json",
    "com1.json",
    "lpt9.json",
    "heroes.json.",
    "bands/casual /heroes.json",
    "heroes\x00.json",
    "heroes?.json",
    "",
]


@pytest.mark.parametrize("bad", ESCAPES)
def test_check_manifest_rejects_names_outside_the_dataset_dir(bad):
    files = {name: {"sha256": "0" * 64} for name in REQUIRED}
    files[bad] = {"sha256": "0" * 64}
    with pytest.raises(DatasetError):
        check_manifest({"schema_version": 1, "files": files})


@pytest.mark.parametrize("bad", [None, 17, 1.5, b"heroes.json"])
def test_check_manifest_rejects_non_string_names(bad):
    files = {name: {"sha256": "0" * 64} for name in REQUIRED}
    files[bad] = {"sha256": "0" * 64}
    with pytest.raises(DatasetError):
        check_manifest({"schema_version": 1, "files": files})


@pytest.mark.parametrize("good", [
    "meta.json", "heroes.json", "hero_augments.json", "augments.json",
    "hero_spells.json", "hero_items.json", "hero_augment_items.json",
    "bands/casual/heroes.json", "bands/mid/hero_augments.json",
    "bands/high/heroes.json", "bands/top/hero_augments.json",
    # 清单里的名字是相对数据目录的路径，深一层也照收（这是文件名合法性，不是发布的清单格式）
    "patches/16.21/normal/heroes.json",
    "patches/16.21/normal/bands/high/hero_augments.json",
])
def test_check_manifest_keeps_legitimate_nested_band_names(good):
    files = {name: {"sha256": "0" * 64} for name in REQUIRED}
    files[good] = {"sha256": "0" * 64}
    manifest = {"schema_version": 1, "files": files}
    assert check_manifest(manifest) is manifest


def test_shipped_bundled_manifest_still_passes():
    """随程序发布的内置数据用的就是这些名字：不能被新校验挡住。"""
    latest = public.BUNDLED_DIR / "latest.json"
    if not latest.exists():
        pytest.skip("还没有放内置数据（scripts/update_data.py）")
    manifest = json.loads(latest.read_text(encoding="utf-8"))
    assert check_manifest(manifest) is manifest
    assert manifest["files"]


def test_packed_download_cannot_write_outside_the_dataset_dir(tmp_path):
    """压缩包合法、路由合法，但清单文件名指向数据目录外的绝对路径：拒绝，且一个字节都不写。"""
    outside = tmp_path / "outside" / "written.json"
    name = str(outside).replace("\\", "/")
    manifest = _manifest({name: {"leak": True}})
    transport = _PackTransport(_pack({k: {} for k in REQUIRED} | {name: {"leak": True}}))
    dest = tmp_path / "data" / "public"

    with pytest.raises(DatasetError):
        public.download("https://aramhex.com/u/data", manifest, dest, transport=transport)

    assert not outside.exists() and not outside.parent.exists()
    assert not dest.exists() and not dest.with_name("public.new").exists()
    assert transport.urls == []  # 校验在发请求之前


@pytest.mark.parametrize("bad", ["..\\..\\evil.json", "C:/outside.json", "../outside.json"])
def test_packed_download_rejects_escaping_name_before_touching_disk(tmp_path, bad):
    """明确回归：清单键 `..\\..\\evil.json`（以及盘符绝对路径）在发请求、建目录、写盘之前就被拒。"""
    manifest = _manifest({bad: {"leak": True}})
    transport = _PackTransport(_pack({k: {} for k in REQUIRED} | {bad: {"leak": True}}))
    dest = tmp_path / "data" / "public"

    with pytest.raises(DatasetError):
        public.download("https://aramhex.com/u/data", manifest, dest, transport=transport)

    assert transport.urls == []                      # 没有请求：压缩包字节到没到手都无所谓
    assert not dest.exists() and not dest.with_name("public.new").exists()
    assert sorted(p.name for p in tmp_path.rglob("*")) == []  # 临时目录里也没多出任何东西


@pytest.mark.parametrize("bad", ["C:/outside.json", "../outside.json", "con.json"])
def test_unpack_rejects_unsafe_pack_names(bad):
    pack = _pack({k: {} for k in REQUIRED} | {bad: {"leak": True}})
    with pytest.raises(DatasetError):
        public.unpack(pack)


def test_unpack_keeps_legitimate_band_names():
    objects = {k: {} for k in REQUIRED} | {"bands/high/heroes.json": {"17": {}}}
    out = public.unpack(_pack(objects))
    assert set(out) == set(objects) and out["bands/high/heroes.json"] == public._dump_json({"17": {}})


def test_dataset_rejects_a_local_manifest_with_an_escaping_name(tmp_path):
    """本地 latest.json（比如被替换过的缓存）同样要挡住：Dataset 构造时就校验清单。"""
    folder = tmp_path / "ds"
    folder.mkdir()
    body = public._dump_json({})
    for name in REQUIRED:
        (folder / name).write_bytes(body)
    outside = tmp_path / "outside.json"
    outside.write_bytes(public._dump_json({"leak": True}))
    manifest = {"schema_version": 1, "patch": "16.21", "snapshot_at": "2026-10-20T00:00:00+08:00",
                "files": {name: _entry(body) for name in REQUIRED}
                | {str(outside).replace("\\", "/"): _entry(outside.read_bytes())}}
    (folder / "latest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DatasetError):
        public.Dataset(folder, "downloaded")
