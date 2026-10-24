"""（维护脚本）把 Data Dragon 方形头像打成离线兜底文件，可选重生成 lolhex/data/hero_icons.json。

    python scripts/update_hero_icons.py [--out lolhex/data/hero_icons.json]

运行时头像来源已经是 Data Dragon（下载到用户缓存）；这个文件只在内置/离线兜底和回滚时用。
旧文件里的腾讯字节不删；重跑会把同一批 alias 换成 Data Dragon 的公开图（大小写以 Data Dragon
为准，如 Fiddlesticks）。请求都经过 lolhex.data.http 的匿名只读边界，不碰腾讯。
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lolhex.data import http, metadata  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "lolhex" / "data" / "hero_icons.json"))
    args = ap.parse_args()
    versions = http.get_json(f"{metadata.DDRAGON_API}/versions.json", timeout=30)
    version = str(versions[0])
    payload = http.get_json(
        f"{metadata.DDRAGON_BASE}/{version}/data/en_US/champion.json", timeout=60)
    heroes = metadata.parse_champions(payload, version)
    icons = {}
    for hid in sorted(heroes, key=int):
        rec = heroes[hid]
        icons[rec["alias"]] = base64.b64encode(
            http.fetch(rec["icon"], timeout=30)).decode("ascii")
    out = {"source": f"{metadata.DDRAGON_BASE}/{version}/img/champion/{{alias}}.png",
           "fetched": time.strftime("%Y-%m-%d"), "ddragon": version,
           "note": "离线兜底/回滚用；运行时来源仍是 Data Dragon 下载缓存，见 static_fallback.json",
           "icons": icons}
    path = Path(args.out)
    path.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"{len(icons)} 个英雄头像 → {path}（{path.stat().st_size / 1e6:.1f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
