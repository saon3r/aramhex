"""数据来源一行字（主窗口和浮窗共用）。文案走 messages 目录（默认英文），中文原文在目录里。

不可信的值先 escape() 再交给 tr()：目录里只放固定文字和 {named} 占位符，不做全局转义，
所以这里每个外部字符串（口径标签、补丁号、赛事名）都自己转义。
"""
from datetime import datetime, timedelta, timezone
from html import escape

from ..messages import quantity, short_date, tr


def _bjt(value, fmt="%Y-%m-%d"):
    try:
        stamp = datetime.fromisoformat(str(value))
        if stamp.tzinfo is not None:
            return stamp.astimezone(timezone(timedelta(hours=8))).strftime(fmt)
    except (TypeError, ValueError):
        pass
    return ""


def data_status_html(d):
    if not d.get("dataset"):
        parts = [tr("data.status.none")]
    else:
        parts = ([escape(str(d["dataset_mode_label"]))] if d.get("dataset_mode_label") else []) + [
            tr("data.status.patch", patch=escape(str(d.get("dataset_patch") or "")))]
        matches = d.get("dataset_matches")
        if isinstance(matches, int):
            parts.append(tr("data.status.games", games=quantity(matches)))
        day = _bjt(d.get("dataset_snapshot"))
        if day:
            parts.append(tr("data.status.as_of", date=short_date(day)))
        if d.get("patch") and d.get("dataset_patch") and d["patch"] != d["dataset_patch"]:
            parts.append(tr("data.status.stale_patch", patch=escape(str(d["patch"]))))
    if d.get("event_fallback") and d.get("event_label"):
        parts.append(tr("data.status.event_fallback", event=escape(str(d["event_label"]))))
    if d.get("error"):
        parts.append(tr("data.status.official_failed"))
    return " · ".join(parts)
