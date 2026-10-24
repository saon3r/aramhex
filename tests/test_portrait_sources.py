"""公开头像来源夹具：DataDragon 方形头像 与 随程序内置的拳头客户端头像。

只证明现有 IconBank 的阈值和比对数学在真实素材上成立；不是实机选人/预选栏验证。
夹具的来源、版本和哈希见 tests/fixtures/portraits/README.md 与 manifest.json。
"""

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np

from lolhex.vision import portraits
from lolhex.vision.portraits import IconBank

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "portraits"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
BENCH_SIZES = (64, 56)  # 预选栏头像小块的实际大小
# 英文名和 DataDragon 路径名不一致的三个英雄；其余 170 个把 en_US 名字去掉空格/撇号就对得上内置别名
_ALIAS_OVERRIDES = {"20": "Nunu", "62": "MonkeyKing", "888": "Renata"}


def _read(path: Path) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    assert img is not None, path
    return img


def _decode(body: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    assert img is not None
    return img


def _ddragon_bank() -> IconBank:
    return IconBank({e["hero_id"]: _read(FIXTURES / e["source_file"]) for e in MANIFEST["sources"]})


def _hero_id_alias(tencent: dict[str, bytes]) -> dict[str, str]:
    """英雄 id → 内置腾讯头像的 alias（数据都来自仓库自带文件）。"""
    by_name = {re.sub(r"[^a-z0-9]", "", alias.lower()): alias for alias in tencent}
    i18n = json.loads((portraits.HERO_ICONS.parent / "i18n.json").read_text(encoding="utf-8"))
    out = {}
    for hid, langs in i18n["heroes"].items():
        name = re.sub(r"[^a-z0-9]", "", langs["en_US"][0].lower())
        alias = _ALIAS_OVERRIDES.get(hid) or by_name.get(name)
        if alias is not None:
            out[hid] = alias
    return out


def test_fixture_provenance_is_pinned():
    """五张 DataDragon 原图和五张内置客户端头像都按 manifest 的哈希、URL、来源钉死。"""
    dd = MANIFEST["ddragon"]
    assert dd["version"] == "16.21.1" and dd["host"] == "ddragon.leagueoflegends.com"
    assert len(MANIFEST["sources"]) == 5
    bundled = json.loads(portraits.CLIENT_ICONS.read_text(encoding="utf-8"))["icons"]
    for e in MANIFEST["sources"]:
        assert e["en_US"] == e["alias"]  # DataDragon 路径名就是英文名
        assert e["source_url"] == f"https://{dd['host']}/cdn/{dd['version']}/img/champion/{e['alias']}.png"
        assert hashlib.sha256((FIXTURES / e["source_file"]).read_bytes()).hexdigest() == e["source_sha256"]
        payload = base64.b64decode(bundled[e["hero_id"]])
        assert hashlib.sha256(payload).hexdigest() == e["bundled_png_sha256"]
        client = _read(FIXTURES / e["client_file"])
        assert np.array_equal(client, _decode(payload))  # 客户端头像就是内置 CDragon 字节，不是另画的
        assert hashlib.sha256((FIXTURES / e["client_file"]).read_bytes()).hexdigest() == e["client_file_sha256"]


@pytest.mark.parametrize("size", BENCH_SIZES)
def test_ddragon_reference_matches_real_client_icons(size):
    """只用 DataDragon 原图建库，也要把真实客户端头像认回正确英雄，并超过现有阈值。"""
    bank = _ddragon_bank()
    assert len(bank) == 5
    for e in MANIFEST["sources"]:
        crop = _read(FIXTURES / e["client_file"])
        if crop.shape[0] != size:
            crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
        m = bank.classify(crop)
        assert m.hero_id == e["hero_id"], (e["hero_id"], size, m)
        assert m.score >= portraits.MIN_SCORE
        assert m.score - m.second >= portraits.MIN_MARGIN


def test_flat_slot_abstains_with_source_bank():
    bank = _ddragon_bank()
    for size in BENCH_SIZES:
        assert bank.classify(np.full((size, size, 3), 30, np.uint8)).hero_id is None


def test_bundled_tencent_references_classify_all_client_icons():
    """跨来源回归：内置腾讯头像建库，去认内置拳头客户端头像（两个来源，不是自己认自己）。

    实测 64×64：165 个认对、8 个不认、0 个认错。低于 165 或出现认错就说明比对逻辑退化。
    """
    tencent = portraits.hero_icons()
    client = portraits.client_icons()
    assert len(tencent) == len(client) == 173
    id_alias = _hero_id_alias(tencent)
    assert set(id_alias) == set(client) and len(set(id_alias.values())) == len(id_alias)
    bank = IconBank({alias: _decode(tencent[alias]) for alias in id_alias.values()})
    assert len(bank) == 173
    correct = abstain = wrong = 0
    for hid, crop in client.items():
        m = bank.classify(crop)
        if m.hero_id == id_alias[hid]:
            correct += 1
        elif m.hero_id is None:
            abstain += 1
        else:
            wrong += 1
    assert wrong == 0, f"{wrong} 个认错"
    assert correct >= 165, f"只认对 {correct}/173"
    assert correct + abstain == 173


def test_combined_bank_has_full_fallback_coverage():
    """组合库（腾讯 + 客户端头像）每个英雄都能兜住：173/173。

    注意：探针图本身就是客户端参考图之一，这是自匹配覆盖率，不是独立识别率；
    独立结果看上一个测试。
    """
    tencent = portraits.hero_icons()
    client = portraits.client_icons()
    id_alias = _hero_id_alias(tencent)
    bank = IconBank({hid: [_decode(tencent[id_alias[hid]]), crop] for hid, crop in client.items()})
    assert len(bank) == 173
    correct = wrong = 0
    for hid, crop in client.items():
        m = bank.classify(crop)
        if m.hero_id == hid:
            correct += 1
        elif m.hero_id is not None:
            wrong += 1
    assert wrong == 0 and correct == 173
