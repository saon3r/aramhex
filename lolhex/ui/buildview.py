"""自采统计的召唤师技能、装备富文本（主窗口和浮窗共用）：都只放图标。
图标还没下载好时先显示名字，下载完 IconCache.version 变化后界面重新渲染。
腾讯官方出装、加点已移除；lines 只保留统计口径的召唤师技能和常出装备。
文案走 messages 目录（默认英文）；不可信的值先 escape() 再交给 tr()，目录里只放固定文字。
"""

from __future__ import annotations
from html import escape

from ..messages import tr

GRAY = "#8b93a7"
# 富文本里的间距用 &nbsp;：普通空格在 QLabel 里会被折叠，全角空格是中文排版痕迹。
GAP = "&nbsp;&nbsp;"


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _text(value) -> str:
    """外部文字（图标没下载好时的名字）：先转义再拼进 HTML。"""
    return escape(str(value or ""), quote=False)


def _img(path: str, size: int) -> str:
    return f'<img src="{path}" width="{size}" height="{size}" align="middle">'


def item(icons, it: dict, size: int) -> str:
    """装备：只放图标（还没下载好时临时用名字）。"""
    p = icons.local("item", it.get("id"), it.get("icon")) if icons else None
    return _img(p, size) if p else _text(it.get("name") or it.get("id"))


def spell_pair(icons, row: dict, size: int) -> str:
    """召唤师技能组合：只放图标（没下载好时临时用名字）。"""
    out = []
    for s in row.get("spells") or []:
        p = icons.local("spell", s.get("id"), s.get("icon")) if icons and s.get("id") else None
        out.append(_img(p, size) if p else _text(s.get("name")))
    return "&nbsp;".join(out)


def lines(d: dict, icons, show_win: bool, size: int = 24, compact: bool = False) -> list[str]:
    """统计口径的几行：召唤师技能（有数据时）、常出装备。compact=浮窗（图标小一号、行更紧凑）。"""
    wr = (lambda x: f" <span style='color:{GRAY}'>{_pct(x)}</span>") if show_win else (lambda x: "")
    out = []
    sums = d.get("summoners") or []  # panel.sort_summoners 已经筛好（出场 ≥3% 且 ≥1000 局、按胜率、最多三组）
    if sums and d.get("summoner_source"):
        date = d.get("summoner_source_date") or tr("build.date_unknown")
        out.append("<span style='color:" + GRAY + "'>"
                   + tr("build.summoner_source", source=escape(str(d["summoner_source"])),
                        date=escape(str(date)))
                   + "</span>")
    def stat(s):  # 胜率在前（按胜率排的），排得下就带上出场；关了显示胜率只写出场
        pick = _pct(s.get("pick"))
        return tr("build.stat", win=_pct(s.get("win")), pick=pick) if show_win else tr("build.stat_pick", pick=pick)
    title = "<b>" + tr("build.summoner_title") + "</b>"
    if sums and compact:  # 浮窗：一组一行，第一行带标题，第二行对齐
        for i, s in enumerate(sums):
            head = title + GAP if i == 0 else "<span style='color:transparent'>" + title + "</span>" + GAP
            out.append(head + spell_pair(icons, s, size) + f" <span style='color:{GRAY}'>{stat(s)}</span>")
    elif sums:
        out.append(title)
        out.extend(GAP + f"{spell_pair(icons, s, size)} <span style='color:{GRAY}'>{stat(s)}</span>" for s in sums)

    its = (d.get("item_stats") or [])[: 4 if compact else 6]
    if its:  # 自采统计的装备（数据里有 hero_items.json 才有）
        out.append("<b>" + tr("build.items_title") + "</b>" + GAP
                   + tr("common.list_separator").join(item(icons, x["item"], size) + wr(x.get("win")) for x in its))
    return out
