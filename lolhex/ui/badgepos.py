"""设置里「三选一标签位置」旁边的示意图：一张海克斯卡，标签画在选中的位置。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..messages import tr

# 位置机器码和目录键：机器码不进目录，只有标签走文案表。
_BADGE_POSITION_KEYS = (("top", "settings.badge.top"), ("bottom", "settings.badge.bottom"))


class _BadgePositions:
    """POSITIONS 的惰性视图：遍历时才取标签，所以界面语言换了不用重建下拉框。"""

    def __iter__(self):
        return iter([(code, tr(key)) for code, key in _BADGE_POSITION_KEYS])

    def __len__(self) -> int:
        return len(_BADGE_POSITION_KEYS)


POSITIONS = _BadgePositions()


class BadgePosPreview(QWidget):
    def __init__(self, position: str = "top", parent=None):
        super().__init__(parent)
        self.position = position
        self.setFixedSize(112, 150)

    def set_position(self, position: str) -> None:
        self.position = position
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = QRectF(6, 4, 100, 142)
        p.setPen(QPen(QColor(214, 180, 120), 3))
        p.setBrush(QColor(16, 30, 34))
        p.drawRoundedRect(card, 8, 8)
        p.setPen(QPen(QColor(120, 130, 130), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(36, 18, 40, 40))           # 海克斯图标
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 235, 235))
        p.drawRect(QRectF(30, 66, 52, 6))                # 名字
        p.setBrush(QColor(110, 118, 124))
        for i, w in enumerate((76, 70, 56)):             # 描述
            p.drawRect(QRectF(56 - w / 2, 80 + 8 * i, w, 3))
        box = QRectF(10, 40, 92, 22) if self.position != "bottom" else QRectF(10, 110, 92, 22)
        p.setBrush(QColor(10, 12, 16, 225))
        p.setPen(QPen(QColor(95, 211, 141), 1.5))
        p.drawRoundedRect(box, 4, 4)
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(95, 211, 141))
        p.drawText(box, Qt.AlignCenter, tr("badgepos.preview"))
        p.end()
