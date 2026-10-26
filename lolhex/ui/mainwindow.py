"""主界面与系统托盘。

- 主窗口：数据状态、当前英雄（识别结果/候选/搜索手动选）、英雄评级与出装加点、当前三选一推荐、设置。
- 关闭主窗口只是隐藏到托盘；退出要在托盘菜单里点「退出」。
- 托盘：双击打开主界面；右键菜单。
"""

from __future__ import annotations

import logging
import os
import threading
import webbrowser
from html import escape
from importlib import resources

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QScrollArea,
                               QPushButton, QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget)

from .. import DATA_HOMEPAGE, HELP_PAGE, HOMEPAGE, __version__, i18n, recommend
from ..config import SPEEDS, is_portable
from ..data.metadata import display_augment_name, display_hero_name, display_hero_title
from ..data.public import BANDS
from ..messages import tr
from . import autostart
from .badgepos import POSITIONS as BADGE_POSITIONS, BadgePosPreview
from . import buildview
from .data_status import data_status_html
from .herosearch import hero_completer

VERDICT_COLORS = {"best": "#2e9d5b", "ok": "#3b7dd8", "reroll": "#d0533f",
                  "unknown": "#888", "nodata": "#888"}
RARITIES = ("silver", "gold", "prismatic")
PHASES = ("client", "ingame")
VISION_STATUSES = ("idle", "paused", "scanning")


def verdict_label(code) -> tuple[str, str]:
    """机器码 -> (目录里的标签, 颜色)；不认识的码按 unknown 处理。"""
    code = code if code in VERDICT_COLORS else "unknown"
    return tr(f"verdict.{code}"), VERDICT_COLORS[code]


def rarity_label(code) -> str:
    return tr(f"rarity.{code}") if code in RARITIES else ""


def augment_name(aid) -> str:
    """海克斯英文名（按 ID 查 metadata）；五杀乐队那四个保持「强化 Q/W/E/R」附注。"""
    key = "" if aid is None else str(aid)
    if not key:
        return tr("common.not_detected")
    name = display_augment_name(key)
    if key in recommend.PENTAKILL:
        return tr("augment.display.skill_name", name=name, key=recommend.PENTAKILL[key])
    return name


def phase_label(phase) -> str:
    return tr(f"phase.{phase if phase in PHASES else 'none'}")


def vision_label(status) -> str:
    return tr(f"vision.{status if status in VISION_STATUSES else 'idle'}")


def band_label(band) -> str:
    return tr(f"band.{band}") if band in BANDS else tr("band.all")


def app_icon() -> QIcon:
    data = resources.files("lolhex.ui").joinpath("icon.png").read_bytes()
    pm = QPixmap()
    pm.loadFromData(data)
    return QIcon(pm)


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _progress_bar() -> QProgressBar:
    bar = QProgressBar()
    bar.setTextVisible(True)
    bar.setMaximumHeight(18)
    bar.hide()
    return bar


def show_progress(bar: QProgressBar, label: str, done: int | None = None, total: int | None = None) -> None:
    """进度条上写"<在做什么> 已下载 / 总共 MB"；不知道总量时只写文字。"""
    if total:
        bar.setRange(0, 1000)
        bar.setValue(int(1000 * min(done or 0, total) / total))
        bar.setFormat(tr("data.progress_format", label=label,
                         done=f"{(done or 0) / 1e6:.1f}", total=f"{total / 1e6:.1f}"))
    else:
        bar.setRange(0, 1)
        bar.setValue(0)
        bar.setFormat(label)
    bar.show()


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet("QFrame#card{border:1px solid #d7dbe3;border-radius:6px;background:#fbfcfe}")
    return f


def hard_exit_later(seconds: float = 5.0,
                    reason: str = "Exit timed out; forcing the process to end so the update can proceed") -> None:
    """更新要替换文件：正常退出卡住（后台线程、网络请求没结束）时，几秒后强制结束本进程。
    1.0.9 之前在 172 上出现过：旧助手没退出，文件被占用，更新被还原。"""
    import threading

    def go():
        logging.getLogger(__name__).warning(reason)
        logging.shutdown()
        os._exit(0)
    t = threading.Timer(seconds, go)
    t.daemon = True
    t.start()


QUIT_TIMEOUT_S = 3.0


def quit_app(engine) -> None:
    """托盘「退出」和浮窗「退出」：停后台线程、结束事件循环；几秒内没退干净就强制结束进程。
    1.0.91 在 172 上出现过：点了退出，后台线程都停了，界面事件循环却没结束，进程一直留着、文件删不掉。"""
    logging.getLogger(__name__).info("Quit")
    app = QApplication.instance()
    if app is not None:
        app.setProperty("quitting", True)  # 主窗口的关闭不再改成缩到托盘
    engine.stop()
    hard_exit_later(QUIT_TIMEOUT_S, "Exit timed out; forcing the process to end")
    QApplication.exit(0)


BAND_CHOICES = [("", tr("band.all"))] + [(c, tr(f"band.{c}")) for c in BANDS]


def about_html() -> str:
    """静态署名（不联网）：上游代码 MIT，统计数据 CC BY-NC 4.0，并注明数据来自国服。"""
    upstream = f"<a href='{HOMEPAGE}'>czgreat/aramhex</a>"
    stats = f"<a href='{DATA_HOMEPAGE}'>czgreat/aramhex-data</a>"
    portable = tr("about.portable") if is_portable() else ""
    return (
        f"<b>{tr('about.product')}</b> {__version__}{portable}<br>"
        f"{tr('about.upstream', link=upstream)}<br>"
        f"{tr('about.stats', link=stats)}<br>"
        f"<span style='color:#777'>{tr('about.disclaimer')}</span>"
    )


class MainWindow(QMainWindow):
    def __init__(self, engine, overlay):
        super().__init__()
        self.engine = engine
        self.overlay = overlay
        self._names: dict[str, str] = {}
        self._cand_ids: list = []
        self._panel_hero = None
        self._hint_shown = False
        self.setWindowTitle(tr("app.name_version", version=__version__))
        self.setWindowIcon(app_icon())
        self.resize(700, 820)
        self.setMinimumSize(360, 260)

        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # 顶部状态
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(40, 40))
        title = QLabel(f"<b style='font-size:17px'>{tr('app.name')}</b> "
                       f"<span style='font-size:13px;color:#555'>{__version__}</span>")
        head.addWidget(logo)
        head.addWidget(title, 1)
        self.btn_dash = QPushButton(tr("common.help"))
        self.btn_dash.clicked.connect(lambda: webbrowser.open(HELP_PAGE))
        head.addWidget(self.btn_dash)
        lay.addLayout(head)

        # 提示和弹窗都不在对局中出现（会抢游戏的焦点）：回到游戏外再出
        self._popup_open = False  # 有提醒类弹窗开着（不叠第二个）
        self._shown_note = None
        self._asked_offers: set = set()
        self._notify_timer = QTimer(self)
        self._notify_timer.timeout.connect(self._notify_tick)
        self._notify_timer.start(3000)

        self.status = QLabel()
        self.status.setWordWrap(False)  # 内容自带 <br> 换行；自动换行会让高度算不准被压扁
        self.status.setTextFormat(Qt.RichText)
        sc = _card()
        scl = QVBoxLayout(sc)
        scl.addWidget(self.status)
        self.data_progress = _progress_bar()  # 下载统计数据时显示
        scl.addWidget(self.data_progress)
        lay.addWidget(sc)

        # 英雄
        hc = _card()
        hl = QVBoxLayout(hc)
        self.hero_label = QLabel()
        self.hero_label.setTextFormat(Qt.RichText)
        hl.addWidget(self.hero_label)
        self.cs_label = QLabel()  # 选人界面：待选栏按胜率排序的汇总
        self.cs_label.setTextFormat(Qt.RichText)
        self.cs_label.setWordWrap(True)
        self.cs_label.hide()
        hl.addWidget(self.cs_label)
        self.cands = QHBoxLayout()
        hl.addLayout(self.cands)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("hero.search.placeholder"))
        self.search.returnPressed.connect(self._search_pick)
        btn_clear = QPushButton(tr("common.clear"))
        btn_clear.clicked.connect(lambda: self.engine.set_hero(None))
        row.addWidget(self.search, 1)
        row.addWidget(btn_clear)
        hl.addLayout(row)
        brow = QHBoxLayout()
        brow.addWidget(QLabel(tr("settings.band.label")))
        self.band_box = QComboBox()
        for code, label in BAND_CHOICES:
            self.band_box.addItem(label, code)
        self.band_box.setCurrentIndex(max(0, self.band_box.findData(engine.settings.data_band or "")))
        self.band_box.currentIndexChanged.connect(lambda i: self.engine.set_band(self.band_box.itemData(i) or None))
        brow.addWidget(self.band_box)
        brow.addStretch(1)
        hl.addLayout(brow)
        lay.addWidget(hc)

        # 标签页
        self.tabs = QTabWidget()
        self.tab_hero = QLabel()
        self.tab_hero.setTextFormat(Qt.RichText)
        self.tab_hero.setWordWrap(True)
        self.tab_hero.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.tab_hero.setTextInteractionFlags(Qt.TextSelectableByMouse)
        w1 = QWidget()
        QVBoxLayout(w1).addWidget(self.tab_hero)
        self.tabs.addTab(w1, tr("tab.build"))

        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        self.offer_advice = QLabel(tr("offer.none"))
        self.offer_advice.setWordWrap(True)
        l2.addWidget(self.offer_advice)
        grid = QGridLayout()
        self.offer_cards = []
        for i in range(3):
            lab = QLabel()
            lab.setTextFormat(Qt.RichText)
            lab.setWordWrap(True)
            lab.setAlignment(Qt.AlignTop)
            lab.setMinimumWidth(170)
            fr = _card()
            QVBoxLayout(fr).addWidget(lab)
            grid.addWidget(fr, 0, i)
            self.offer_cards.append(lab)
        l2.addLayout(grid)
        btns = QHBoxLayout()
        b1 = QPushButton(tr("common.rescan"))
        b1.clicked.connect(self.engine.rescan)
        b2 = QPushButton(tr("settings.recalibrate_button"))
        b2.clicked.connect(self._recalibrate)
        btns.addWidget(b1)
        btns.addWidget(b2)
        btns.addStretch(1)
        l2.addLayout(btns)
        l2.addStretch(1)
        self.tabs.addTab(w2, tr("tab.offer"))

        self.tabs.addTab(self._settings_tab(), tr("common.settings"))
        lay.addWidget(self.tabs, 1)
        # 小屏或高缩放时保留完整内容，允许滚动，不让底部操作落到屏幕外。
        root.setMinimumSize(640, 700)
        viewport = QScrollArea()
        viewport.setWidgetResizable(True)
        viewport.setFrameShape(QScrollArea.NoFrame)
        viewport.setWidget(root)
        self.setCentralWidget(viewport)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    # ---------- 设置 ----------

    def _settings_tab(self) -> QWidget:
        s = self.engine.settings
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setSpacing(14)
        f = QFormLayout()
        f.setVerticalSpacing(10)
        outer.addLayout(f)
        self.set_corner = QComboBox()
        self.set_corner.addItems([tr("settings.corner.top_right"), tr("settings.corner.top_left")])
        self.set_corner.setCurrentIndex(0 if s.overlay_corner == "top-right" else 1)
        # 三选一标签放卡片上方还是下方，旁边的示意图跟着选项变
        self.set_badge = QComboBox()
        for code, label in BADGE_POSITIONS:
            self.set_badge.addItem(label, code)
        self.set_badge.setCurrentIndex(max(0, self.set_badge.findData(s.badge_position)))
        self.badge_preview = BadgePosPreview(s.badge_position)
        self.set_badge.currentIndexChanged.connect(
            lambda i: self.badge_preview.set_position(self.set_badge.itemData(i)))
        # 示意图比下拉框高：右边放示意图，左边下拉框下面接着放后面几项，不留空白
        badge_row = QHBoxLayout()
        badge_left = QVBoxLayout()
        badge_left.setSpacing(10)
        badge_row.addLayout(badge_left, 1)
        badge_row.addWidget(self.badge_preview, 0, Qt.AlignTop)
        self.set_speed = QComboBox()
        for key in SPEEDS:
            self.set_speed.addItem(tr(f"settings.speed.{key}"), key)
        self.set_speed.setCurrentIndex(max(0, self.set_speed.findData(s.speed)))
        self.set_auto = QCheckBox(tr("settings.autostart"))
        self.set_auto.setChecked(autostart.is_enabled())
        self.set_data = QCheckBox(tr("settings.data_updates"))
        self.set_data.setChecked(s.check_data_updates)
        # 外服：游戏客户端的语言（识别用的名字表；识别模型只用内置的）
        self.set_lang = QComboBox()
        for code, _label in i18n.LANGS:
            self.set_lang.addItem(tr(f"settings.lang.{code.lower()}"), code)
        self.set_lang.setCurrentIndex(max(0, self.set_lang.findData(i18n.normalize_lang(s.game_lang))))
        f.addRow(tr("settings.game_lang"), self.set_lang)
        f.addRow(tr("settings.scan_rate"), self.set_speed)
        f.addRow(tr("settings.overlay_corner"), self.set_corner)
        badge_left.addWidget(self.set_badge)
        badge_left.addWidget(self.set_auto)
        badge_left.addWidget(self.set_data)
        save = QPushButton(tr("settings.save"))
        save.clicked.connect(self._save_settings)
        badge_left.addStretch(1)
        badge_left.addWidget(save)  # 放在示意图左边、和示意图底边对齐，不留空白
        f.addRow(tr("settings.badge_position"), badge_row)

        outer.addStretch(1)
        card = _card()
        cv = QVBoxLayout(card)
        cv.setContentsMargins(18, 16, 18, 16)
        cv.setSpacing(8)
        about = QLabel(about_html())
        about.setTextFormat(Qt.RichText)
        about.setWordWrap(True)
        about.setOpenExternalLinks(True)
        self.about_label = about
        cv.addWidget(about)
        self.about_data = QLabel()
        self.about_data.setStyleSheet("color:#555")
        cv.addWidget(self.about_data)
        outer.addWidget(card)
        # 设置项越来越多：放进可滚动区域，窗口矮的时候不会被压扁
        scroll = QScrollArea()
        scroll.setWidget(w)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    # ---------- 数据更新提示 ----------

    def _in_game(self) -> bool:
        return self.engine.snapshot().get("phase") == "ingame"

    def _busy(self) -> bool:
        """对局中或正在选英雄：这时不弹窗（会抢游戏或客户端的焦点）。"""
        snap = self.engine.snapshot()
        return snap.get("phase") == "ingame" or bool(snap.get("champ_select"))

    def _modal_open(self) -> bool:
        """有提醒类弹窗开着（不叠第二个）。"""
        return self._popup_open or QApplication.activeModalWidget() is not None

    def _toast(self, text: str) -> None:
        tray = getattr(self, "tray", None)
        if tray:
            tray.showMessage(tr("app.name"), text, app_icon(), 6000)

    def _notify_tick(self):
        """游戏外才出：数据已更新的提示、关了自动更新时的「是否更新」。
        弹窗还要避开选英雄；已经有弹窗开着时不再叠一个（计时器在弹窗打开期间也会跑）。"""
        if self._in_game() or self._modal_open():
            return
        dd = self.engine.snapshot().get("data") or {}
        note = dd.get("data_note")
        if note and note.get("id") != self._shown_note:
            self._shown_note = note["id"]
            logging.getLogger(__name__).info("Toast: %s", note["text"])
            self._toast(note["text"])
        offer = dd.get("data_offer")
        if offer and offer.get("id") not in self._asked_offers and not self._busy() and not self._modal_open():
            self._asked_offers.add(offer["id"])  # 每份新数据只问一次；点了「稍后」下次启动再问
            self._popup_open = True
            try:
                ask = QMessageBox.question(
                    self, tr("dialog.stats.title"),
                    tr("dialog.stats.new_offer", summary=escape(str(offer['text']))))
            finally:
                self._popup_open = False
            if ask == QMessageBox.Yes:
                st = self.engine.store
                threading.Thread(target=lambda: st.sync_data(force=True, manual=True), daemon=True).start()

    def _save_settings(self):
        s = self.engine.settings
        s.check_data_updates = self.set_data.isChecked()
        if hasattr(self.engine.store, "check_updates"):
            self.engine.store.check_updates = s.check_data_updates  # 马上生效，不用重开
        s.speed = self.set_speed.currentData() or "standard"
        s.overlay_corner = "top-right" if self.set_corner.currentIndex() == 0 else "top-left"
        s.badge_position = self.set_badge.currentData() or "top"
        lang = self.set_lang.currentData() or "en_US"
        if lang != s.game_lang:
            self.engine.set_game_lang(lang)
        saved = s.save()
        self.overlay.set_visible(s.overlay)
        self.overlay.panel.corner = s.overlay_corner
        try:
            autostart.set_enabled(self.set_auto.isChecked())
        except OSError as e:
            QMessageBox.warning(self, tr("dialog.autostart.title"),
                                tr("dialog.autostart.failed", error=escape(str(e))))
        if saved:
            QMessageBox.information(self, tr("common.settings"), tr("dialog.save.ok"))
        else:
            QMessageBox.warning(self, tr("common.settings"), tr("dialog.save.failed"))

    def _recalibrate(self):
        self.engine.reset_calibration()
        QMessageBox.information(self, tr("dialog.recalibrate.title"), tr("dialog.recalibrate.done"))

    def _ensure_completer(self):
        heroes = self.engine.store.heroes
        if self._names or not heroes:
            return
        comp, self._names = hero_completer(self.engine.store, self)
        comp.activated.connect(lambda text: (self.engine.set_hero(self._names.get(text, text)), self.search.clear()))
        self.search.setCompleter(comp)

    def _search_pick(self):
        t = self.search.text().strip()
        if t:
            self.engine.set_hero(self._names.get(t, t))
            self.search.clear()

    def _set_candidates(self, cands):
        ids = [c.get("id") for c in cands]
        if ids == self._cand_ids:
            return
        self._cand_ids = ids
        while self.cands.count():
            it = self.cands.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if cands:
            self.cands.addWidget(QLabel(tr("hero.candidates")))
        for c in cands[:6]:
            b = QPushButton(display_hero_name(c.get("id")))
            b.clicked.connect(lambda _=False, hid=c.get("id"): self.engine.set_hero(hid))
            self.cands.addWidget(b)
        self.cands.addStretch(1)

    # ---------- 刷新 ----------

    def refresh(self):
        if not self.isVisible():
            return
        snap = self.engine.snapshot()
        self._ensure_completer()
        dd = snap.get("data", {})
        v = snap.get("vision", {})
        err = v.get("error") or {}
        warnings = []
        if err.get("code") == "ocr_unavailable":
            warnings.append(i18n.ocr_unavailable_notice(err.get("language")))
        if v.get("blank"):
            warnings.append(tr("warning.fullscreen"))
        warn = "".join(f" · <span style=\"color:#d0533f\">{text}</span>" for text in warnings)
        self.status.setText(
            f"<b>{tr('main.status.label')}</b>{phase_label(snap.get('phase'))}<br>"
            f"<b>{tr('main.status.vision')}</b>{vision_label(v.get('status'))}{warn}<br>"
            f"<b>{tr('main.status.data')}</b>{band_label(dd.get('band_effective'))} · {data_status_html(dd)}")
        if hasattr(self, "about_data"):
            self.about_data.setText(tr("data.about_label") + data_status_html(dd))
        dp = dd.get("data_progress")
        if dp:
            show_progress(self.data_progress, tr("data.progress_label"), dp.get("done"), dp.get("total"))
        else:
            self.data_progress.hide()

        h, hid = snap.get("hero"), snap.get("hero_id")
        show_win = snap.get("settings", {}).get("show_winrate", True)
        d = self.engine.hero_panel(hid) if hid else None
        if h:
            r = (d or {}).get("rank") or {}
            b = self.engine.hero_brief(hid)
            rating = []
            if b.get("grade"):
                rating.append(tr("stats.grade", grade=escape(str(b['grade']))))
            if b.get("rank"):
                rating.append(tr("stats.win_rank", rank=b['rank'], total=b.get('total') or '?'))
            if show_win and r.get("win") is not None:
                rating.append(tr("stats.winrate", pct=_pct(r['win'])))
            if r.get("pick") is not None:
                rating.append(tr("stats.pickrate", pct=_pct(r['pick'])))
            self.hero_label.setText(
                f"<span style='font-size:18px'><b>{escape(display_hero_name(hid))}</b></span> "
                f"{escape(display_hero_title(hid))}<br>"
                f"{' · '.join(rating)}")
        else:
            self.hero_label.setText(f"<b>{tr('hero.none_selected')}</b>")
        cs = snap.get("champ_select")
        if cs and (cs.get("bench") or cs.get("cards")):
            from .overlay import champ_select_summary
            self.cs_label.setText(champ_select_summary(cs, show_win))
            self.cs_label.show()
        else:
            self.cs_label.hide()
        self._set_candidates(snap.get("candidates") or [])

        key = (hid, d.get("date"), d.get("data_revision"), self.engine.icons.version, dd.get("band_effective")) if d else None
        if d and self._panel_hero != key:
            self._panel_hero = key
            self.tab_hero.setText(self._hero_html(d, show_win))
        elif not d:
            self._panel_hero = None
            self.tab_hero.setText(f"<span style='color:#777'>{tr('hero.no_champion_yet')}</span>")
        self._render_offer(snap.get("evaluation"), show_win)

    def _hero_html(self, d, show_win) -> str:
        out = buildview.lines(d, self.engine.icons, show_win, size=28)
        top = [a for a in d.get("augments", []) if a.get("delta") is not None and a.get("sample") != "low"]
        top.sort(key=lambda a: -a["delta"])
        if top:
            out.append(f"<b>{tr('augment.recommended_header')}</b>")
            for a in top[:8]:
                out.append(f"&nbsp;&nbsp;{escape(augment_name(a.get('id')))} "
                           f"<span style='color:#777'>{rarity_label(a.get('rarity'))}"
                           f"</span> <b style='color:#2e9d5b'>{a['delta']:+.1f}</b>")
        return "<br>".join(out)

    def _render_offer(self, ev, show_win):
        if not ev:
            self.offer_advice.setText(f"<span style='color:#777'>{tr('offer.none')}</span>")
            for lab in self.offer_cards:
                lab.setText("")
            return
        pk = recommend.pentakill_text(ev.get("pentakill"))
        self.offer_advice.setText(f"<b style='font-size:15px'>{ev['advice']}</b>"
                                  + (f"<br><span style='color:#c9a0ff'>{escape(pk)}</span>" if pk else ""))
        for lab, r in zip(self.offer_cards, ev["slots"]):
            v, col = verdict_label(r.get("verdict"))
            if r.get("verdict") == "best" and r.get("sample_warning"):
                v = tr("sample.best_reference")
            lines = [f"<b style='color:{col}'>{v}</b>",
                     f"<b>{escape(augment_name(r.get('augment_id')))}</b>"]
            meta = [rarity_label(r.get("rarity"))]
            lines.append("<span style='color:#777'>" + " ".join(m for m in meta if m) + "</span>")
            if r["verdict"] == "nodata":
                note = tr("augment.note.new" if r.get("basis") == "new" else "augment.note.nodata")
                lines.append(f"<span style='color:#777'>{note}</span>")
                wt = recommend.win_text(r)
                if wt:
                    lines.append(wt)
            if r.get("basis") == "pbe":
                pbe = (tr("augment.pbe_games", games=r['pbe_games'], win=_pct(r['pbe_win']))
                       if r.get("pbe_games") else "")
                lines.append(f"<span style='color:#777'>{pbe}{tr('augment.note.pbe')}</span>")
            if r.get("score") is not None:
                s = f"{r['score']:+.1f}"
                if show_win and recommend.win_text(r):
                    s += " · " + recommend.win_text(r)
                if r.get("thin") or r.get("sample_warning"):
                    warn = tr("sample.too_few_warn") if r.get("thin") == "too_few" else tr("sample.few")
                    s += f" · <span style='color:#ff7a6b'>{warn}</span>"
                lines.append(s)
            lab.setText("<br>".join(lines))

    # ---------- 窗口行为 ----------

    def show_and_raise(self):
        screen = self.screen()
        if screen:
            available = screen.availableGeometry()
            self.resize(min(self.width(), max(360, available.width() - 16)),
                        min(self.height(), max(260, available.height() - 48)))
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.refresh()

    def closeEvent(self, e):
        if QApplication.instance().property("quitting"):
            e.accept()
            return
        e.ignore()
        self.hide()
        if not self._hint_shown and QSystemTrayIcon.isSystemTrayAvailable():
            self._hint_shown = True
            tray = getattr(self, "tray", None)
            if tray:
                tray.showMessage(tr("app.name"), tr("tray.background_hint"), app_icon(), 4000)


class Tray(QSystemTrayIcon):
    def __init__(self, engine, window: MainWindow, overlay):
        super().__init__(app_icon())
        self.engine, self.window, self.overlay = engine, window, overlay
        self.setToolTip(tr("app.name_version", version=__version__))
        m = QMenu()
        m.addAction(tr("tray.open_main"), window.show_and_raise)
        self.act_overlay = QAction(tr("tray.toggle_overlay"), m, checkable=True)
        self.act_overlay.setChecked(engine.settings.overlay)
        self.act_overlay.toggled.connect(self._toggle_overlay)
        m.addAction(self.act_overlay)
        m.addAction(tr("common.rescan"), engine.rescan)
        self.messageClicked.connect(window.show_and_raise)
        self.act_auto = QAction(tr("settings.autostart"), m, checkable=True)
        self.act_auto.setChecked(autostart.is_enabled())
        self.act_auto.toggled.connect(self._toggle_auto)
        m.addAction(self.act_auto)
        m.addSeparator()
        m.addAction(tr("common.quit"), self.quit)
        self.setContextMenu(m)
        self._menu = m
        self.activated.connect(self._activated)
        self.timer = QTimer()
        self.timer.timeout.connect(self._tooltip)
        self.timer.start(3000)

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.window.show_and_raise()

    def _toggle_overlay(self, on: bool):
        s = self.engine.settings
        s.set_by_user("overlay", on)
        s.save()
        self.overlay.set_visible(s.overlay)

    def _toggle_auto(self, on: bool):
        try:
            autostart.set_enabled(on)
        except OSError:
            pass

    def _tooltip(self):
        s = self.engine.snapshot()
        h = s.get("hero")
        self.setToolTip(tr("app.name_version", version=__version__) + "\n" + phase_label(s.get("phase")) +
                        (tr("tray.tooltip_champion", name=display_hero_name(s.get("hero_id"))) if h else ""))

    def quit(self):
        self.hide()
        quit_app(self.engine)
