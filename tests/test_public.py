"""自采统计数据：内置 / 下载两份里挑样本新的；逐文件校验；分段切换；从数据仓库下载更新。"""

import functools
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import make_dataset

CJK = re.compile("[\u3000\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\uff00-\uffef]")
from httpfixtures import LocalTransport
from lolhex.data import public
from lolhex.data.public import Dataset, DatasetError, PublicStore, check_manifest


def _serve(root: Path):
    """本地 HTTP 服务，模拟数据仓库的目录（latest.json 在根，文件在 patches/<版本>/<模式>/）。"""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "remote"
    root.mkdir()
    httpd, base = _serve(root)
    yield root, base
    httpd.shutdown()


def _publish(root, snapshot_at, patch="16.20"):
    """按数据仓库的真实目录结构放一份：latest.json 在根，文件在 patches/<版本>/normal/。"""
    folder = root / "patches" / patch / "normal"
    manifest = make_dataset(folder, snapshot_at=snapshot_at, patch=patch)
    (folder / "latest.json").unlink()
    (root / "latest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_bundled_dataset_loads_and_ranks(store):
    st = store.status()
    assert st["dataset"] and st["dataset_patch"] == "16.20" and st["dataset_origin"] == "bundled"
    assert st["bands_available"] and st["dataset_label"] == "Self-collected stats · patch 16.20"
    assert st["dataset_matches"] == 70000 and st["dataset_collected"] == 72000
    assert store.ranks["heroes"]["17"]["rank"] == 1 and store.ranks["heroes"]["17"]["games"] == 400000
    assert store.ranks["augments"]["1029"]["games"] == 45000  # 所有英雄合计


def test_band_switch_and_fallback(store):
    store.set_band("casual")
    assert store.win_data("17")["band_label"] == "Casual"
    store.set_band("high")
    assert store.effective_band() == "high" and store.ranks["heroes"]["17"]["games"] == 2000
    assert store.win_data("17")["band_label"] == "Top 5%"
    store.set_band("top")  # 1.1.0 以前的「顶尖」：当前 5%（high）
    assert store.effective_band() == "high"
    store.set_band("bogus")
    assert store.effective_band() is None and store.ranks["heroes"]["17"]["games"] == 400000


def test_dataset_without_bands_falls_back_to_all(tmp_path):
    make_dataset(tmp_path / "b", bands=False)
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", check_updates=False)
    s.set_band("high")
    assert s.band == "high" and s.effective_band() is None and not s.bands_available()


def test_tampered_file_is_rejected(tmp_path):
    make_dataset(tmp_path / "b")
    (tmp_path / "b" / "heroes.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DatasetError):
        Dataset(tmp_path / "b", "bundled")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", check_updates=False)
    assert s.dataset is None and s.win_data("17") is None and "No stats" in s.label()


@pytest.mark.parametrize("bad", ["../evil.json", "/abs.json", "x.exe"])
def test_manifest_rejects_unsafe_names(bad):
    with pytest.raises(DatasetError):
        check_manifest({"schema_version": 1, "files": {"meta.json": {"sha256": "0" * 64},
                                                       "heroes.json": {"sha256": "0" * 64},
                                                       "hero_augments.json": {"sha256": "0" * 64},
                                                       bad: {"sha256": "0" * 64}}})


def test_newer_download_wins_over_bundled(tmp_path):
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    make_dataset(tmp_path / "data" / "public", snapshot_at="2026-10-20T00:00:00+08:00", patch="16.21")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", check_updates=False)
    assert s.dataset.origin == "downloaded" and s.dataset.patch == "16.21"


def test_sync_downloads_newer_data(tmp_path, server):
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    _publish(root, "2026-10-13T00:00:00+08:00")
    assert s.sync_data(force=True) is False  # 和内置的一样新：不下载
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    assert s.sync_data(force=True) is True
    assert s.dataset.origin == "downloaded" and s.dataset.patch == "16.21" and s.data_updated_at
    assert (tmp_path / "data" / "public" / "bands" / "top" / "heroes.json").exists()
    assert s.sync_data() is False  # 6 小时内不重复查


def test_sync_rejects_tampered_download(tmp_path, server):
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    (root / "patches" / "16.21" / "normal" / "heroes.json").write_text("{}", encoding="utf-8")
    assert s.sync_data(force=True) is False
    assert s.dataset.origin == "bundled" and "校验" in s.sync_error
    assert not (tmp_path / "data" / "public").exists() and not (tmp_path / "data" / "public.new").exists()


def test_sync_failure_is_quiet(tmp_path):
    make_dataset(tmp_path / "b")
    dead = "http://127.0.0.1:9"
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=dead,
                    transport=LocalTransport(dead))
    assert s.sync_data(force=True) is False and s.sync_error and s.dataset.origin == "bundled"


def test_default_transport_rejects_an_arbitrary_base_url(tmp_path, monkeypatch):
    """没显式注入传输时，本地/任意 base_url 在发请求之前就被拒；统计数据保持内置那份。"""
    make_dataset(tmp_path / "b")
    sent = []
    monkeypatch.setattr("requests.sessions.Session.send",
                        lambda self, request, **kw: sent.append((request, kw)))
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url="http://127.0.0.1:9")
    assert s.sync_data(force=True) is False
    assert s.sync_error and s.dataset.origin == "bundled"
    assert sent == []


def test_sync_disabled_only_offers(tmp_path, server):
    # 关了自动更新：只看清单，有新的就记到 data_offer 等用户点头，不下载；点头（manual）才下载
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    check_updates=False, transport=LocalTransport(base))
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    assert s.sync_data(force=True) is False
    assert s.dataset.origin == "bundled" and not (tmp_path / "data" / "public").exists()
    assert s.data_offer and "patch 16.21" in s.data_offer["text"] and "as of 20 Oct" in s.data_offer["text"]
    assert s.status()["data_offer"] == s.data_offer
    assert s.sync_data(force=True, manual=True) is True
    assert s.dataset.patch == "16.21" and s.data_offer is None


def test_sync_waits_until_game_ends(tmp_path, server):
    # 对局中后台不换数据（一局里推荐前后一致），打完再换，换完记一条提示
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    in_game = [True]
    s.hold = lambda: in_game[0]
    assert s.sync_data() is False and s.dataset.origin == "bundled" and s._last_sync == 0
    in_game[0] = False
    assert s.sync_data() is True and s.dataset.patch == "16.21"
    assert s.data_note and s.data_note["text"].startswith("Stats updated: patch 16.21, as of 20 Oct")
    assert s.status()["data_note"]["id"] == s.dataset.revision


def test_real_bundled_data_is_valid():
    """仓库里随程序发布的内置数据：清单、校验完整；分段有没有和清单声明一致（4.0 首版只有全体，bands=false）。"""
    if not (public.BUNDLED_DIR / "latest.json").exists():
        pytest.skip("还没有放内置数据（scripts/update_data.py）")
    ds = Dataset(public.BUNDLED_DIR, "bundled")
    heroes, augs = ds.table(None)
    assert len(heroes) > 150 and ds.bands_available() == bool(ds.manifest.get("bands"))
    assert all(0 < h["win_rate"] < 1 for h in heroes.values())


def test_sync_falls_back_to_mirror(tmp_path, server):
    """第一个地址不可用（这里被策略拒绝）：换下一个地址下载。"""
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b",
                    base_url=["http://127.0.0.1:9", base], transport=LocalTransport(base))
    assert s.sync_data(force=True) is True
    assert s.data_source == base and s.dataset.patch == "16.21"


def test_sync_skips_tampered_mirror(tmp_path, server):
    """第一个镜像的数据被改过：换下一个镜像。两个镜像都是真实路径形状。"""
    root, base = server
    bad = tmp_path / "bad_remote"
    bad.mkdir()
    bad_httpd, bad_base = _serve(bad)
    try:
        make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
        _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
        _publish(bad, "2026-10-20T00:00:00+08:00", patch="16.21")
        (bad / "patches" / "16.21" / "normal" / "heroes.json").write_text("{}", encoding="utf-8")
        s = PublicStore(tmp_path / "data", bundled=tmp_path / "b",
                        base_url=[bad_base, base], transport=LocalTransport(bad_base, base))
        assert s.sync_data(force=True) is True and s.data_source == base
    finally:
        bad_httpd.shutdown()


def test_data_download_reports_progress(tmp_path, server):
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    manifest = _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    seen = []
    public.download(base, manifest, tmp_path / "dl", progress=lambda d, t: seen.append((d, t)),
                    transport=LocalTransport(base))
    total = sum(f["size"] for f in manifest["files"].values())
    assert seen[-1] == (total, total)
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    assert s.status()["data_progress"] is None  # 不在下载时没有进度


def _normalize(root, patch):
    """把发布目录里的文件按数据仓库导出的写法重写一遍（胜率 = round(胜场/局数, 6)），重算清单。"""
    folder = root / "patches" / patch / "normal"
    manifest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
    for name in manifest["files"]:
        obj = json.loads((folder / name).read_text(encoding="utf-8"))
        if name.endswith("hero_augments.json"):
            for d in obj.values():
                for s in d.values():
                    s["win_rate"] = round(s["wins"] / s["games"], 6) if s["games"] else 0.0
                    s["low_sample"] = bool(s.get("low_sample"))
        body = public._dump_json(obj)
        (folder / name).write_bytes(body)
        manifest["files"][name] = {"sha256": public.hashlib.sha256(body).hexdigest(), "size": len(body)}
    (root / "latest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder, manifest


def test_pack_download_restores_exact_files(tmp_path, server):
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    folder, manifest = _normalize(root, "16.21")
    pack = public.make_pack(folder, manifest)
    (root / "patches" / "16.21" / "normal.pack.xz").write_bytes(pack)
    # 压缩包可用时，逐个文件的地址都删掉：证明数据确实来自压缩包
    for name in manifest["files"]:
        (folder / name).rename(folder / (name + ".bak"))
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    assert s.sync_data(force=True) is True and s.dataset.patch == "16.21"
    assert len(pack) < sum(f["size"] for f in manifest["files"].values())


def test_bad_pack_falls_back_to_files(tmp_path, server):
    root, base = server
    make_dataset(tmp_path / "b", snapshot_at="2026-10-13T00:00:00+08:00")
    _publish(root, "2026-10-20T00:00:00+08:00", patch="16.21")
    (root / "patches" / "16.21" / "normal.pack.xz").write_bytes(b"not xz")
    s = PublicStore(tmp_path / "data", bundled=tmp_path / "b", base_url=base,
                    transport=LocalTransport(base))
    assert s.sync_data(force=True) is True and s.dataset.patch == "16.21"


def test_old_top_band_setting_becomes_high(tmp_path):
    # 1.1.1 去掉「顶尖」：老设置文件 data_band=top 读成 high
    import json
    from lolhex.config import Settings
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"data_band": "top", "install_id": "0123456789abcdef"}), encoding="utf-8")
    assert Settings.load(p).data_band == "high"


def _add_file(folder, name, obj):
    import hashlib
    import json as _json
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    m = _json.loads((folder / "latest.json").read_text(encoding="utf-8"))
    m["files"][name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size}
    (folder / "latest.json").write_text(_json.dumps(m), encoding="utf-8")


def test_optional_spells_and_items_files(store):
    # 1.1.1（A12）：数据里有 hero_spells.json / hero_items.json 就显示，没有就跳过
    from lolhex.data.public import Dataset
    from lolhex.panel import hero_panel
    assert store.hero_spells("17") == ([], store.label()) and hero_panel(store, "17")["summoners"] == []
    folder = store.dataset.folder
    _add_file(folder, "hero_spells.json", {"17": {"4+32": {"games": 9000, "wins": 4800}, "4+7": {"games": 1000, "wins": 400},
                                                  "坏": {"games": "x"}, "4+14": {"games": 10, "wins": 11}}})
    _add_file(folder, "hero_items.json", {"17": {"3115": {"games": 500, "wins": 270}}})
    store.dataset = Dataset(folder, store.dataset.origin)
    rows, label = store.hero_spells("17")
    assert [r["spells"] for r in rows] == [["4", "32"], ["4", "7"]] and abs(rows[0]["pick"] - 0.9) < 1e-9
    d = hero_panel(store, "17")
    assert len(d["summoners"]) == 2 and d["summoner_source"] and d["summoners"][0]["spells"][0]["id"] == "4"
    assert d["item_stats"][0]["item"]["id"] == "3115" and abs(d["item_stats"][0]["win"] - 0.54) < 1e-9
    from lolhex.ui import buildview
    html = "<br>".join(buildview.lines(d, None, True))
    assert "Summoner spells" in html and "Common items" in html


def test_summoners_3pct_and_1000_games_sorted_by_win_top3():
    """召唤师技能：出场 ≥3% 且 ≥1000 局的都放，按胜率排，最多三组；一组都不够时放出场最多的一组。"""
    from lolhex.panel import sort_summoners
    rows = [{"spells": ["4", "32"], "games": 5530, "win": 0.456, "pick": 0.553},
            {"spells": ["4", "21"], "games": 3480, "win": 0.433, "pick": 0.348},
            {"spells": ["4", "6"], "games": 1200, "win": 0.47, "pick": 0.12},
            {"spells": ["4", "7"], "games": 440, "win": 0.60, "pick": 0.044},
            {"spells": ["4", "14"], "games": 2000, "win": 0.55, "pick": 0.02}]
    # 440 局（不够 1000 局）和 2% 出场都不够格，哪怕胜率更高；剩下三组按胜率排
    assert [r["spells"][1] for r in sort_summoners(rows)] == ["6", "32", "21"]
    few = [{"spells": ["4", "x"], "games": 900, "win": 0.5, "pick": 0.09},
           {"spells": ["4", "y"], "games": 80, "win": 0.7, "pick": 0.08}]
    assert [r["spells"][1] for r in sort_summoners(few)] == ["x"]


def test_overlay_summoners_show_win_rate():
    """浮窗和主界面：胜率在前、带出场，一组一行；关了「显示胜率」只写出场。"""
    from lolhex.ui import buildview
    d = {"summoners": [{"spells": [{"id": "4", "name": "闪现"}, {"id": "32", "name": "雪球"}], "games": 900, "win": 0.534, "pick": 0.9},
                       {"spells": [{"id": "4", "name": "闪现"}, {"id": "6", "name": "疾跑"}], "games": 100, "win": 0.51, "pick": 0.1}],
         "summoner_source": "自采统计"}
    compact = buildview.lines(d, None, True, compact=True)
    rows = [x for x in compact if "闪现" in x]
    assert len(rows) == 2 and "Win rate 53.4% · Pick rate 90.0%" in rows[0] and "Win rate 51.0% · Pick rate 10.0%" in rows[1]
    off = "".join(buildview.lines(d, None, False, compact=True))
    assert "Win rate" not in off and "Pick rate 90.0%" in off
    full = "".join(buildview.lines(d, None, True))
    assert "Win rate 53.4% · Pick rate 90.0%" in full

def test_non_normal_mode_label_is_english():
    """数据集给的 mode_label 是中文；非普通模式的显示名不能漏中文到状态栏。"""
    from lolhex.data.public import _mode_label

    class D:
        mode = "first-prismatic"
        mode_label = "\u9996\u6b21\u68f1\u5f69"   # 首次棱彩

    label = _mode_label(D())
    assert label == "First Prismatic" and not CJK.search(label)
    assert _mode_label(None) is None
    D.mode, D.mode_label = "normal", "\u5e38\u89c4"
    assert _mode_label(D()) is None

