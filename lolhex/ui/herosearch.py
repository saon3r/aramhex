"""手动选英雄的搜索补全：名字、称号之外，别名和拼音缩写也能搜到（提百万、快乐风男、tm）。

界面语言是英文时，下拉里只显示英文名、英文称号和英文别名；中文名/称号/外号仍然留在
匹配用的关键字里（store.hero_terms 不动），所以按中文叫法照样能搜到对应英雄。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QCompleter

from ..data.metadata import display_hero_name, display_hero_title
from ..messages import tr


def hero_completer(store, parent=None) -> tuple[QCompleter, dict[str, str]]:
    """返回补全器和 {补全文字: 英雄 id}。下拉里显示"Teemo the Swift Scout"，
    有英文别名时显示"Twisted Fate the Card Master (TwistedFate, TF)"；按包含关系匹配
    名字、称号、英文/拼音关键词，以及中文别名（中文只在匹配里，不显示）。"""
    rows, names = [], {}
    for hid in store.heroes:
        base = " ".join(t for t in (display_hero_name(hid), display_hero_title(hid)) if t)
        extra = [t for t in store.hero_terms(hid) if t.lower() not in base.lower()]
        english = [t for t in extra if t.isascii()]
        key = " ".join([base, *extra])
        names[key] = hid
        rows.append((tr("hero.completer.aliases", base=base,
                        aliases=tr("common.list_separator").join(english)) if english else base,
                     key))
    comp = QCompleter(parent)
    model = QStandardItemModel(comp)  # 挂在补全器上，免得函数返回后被回收
    for display, key in sorted(rows):
        item = QStandardItem(display)
        item.setData(key, Qt.UserRole)
        model.appendRow(item)
    comp.setModel(model)
    comp.setCompletionRole(Qt.UserRole)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    comp.setFilterMode(Qt.MatchContains)
    return comp, names
