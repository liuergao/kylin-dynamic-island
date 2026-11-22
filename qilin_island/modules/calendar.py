# -*- coding: utf-8 -*-
"""应用层 · 日历与日程（M10）"""
from calendar import monthrange
from datetime import date, datetime, timedelta
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QPainter, QPen
from PyQt5.QtWidgets import (QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)
from ..app import sponsor
from ..core.styles import card_qss
from ..infra.timeutil import (EV_REPEAT_OPTIONS, ev_occurrence, next_occurrence,
                              parse_dt)
from .base import Page
from ..core.consts import CONTENT_PAD_X
from .widgets import ChoiceButton
from ..core import theme as T

# 1.4.15 日历页的纵向账本（面板 348，页面容器 267，页面上下边距 2/8 → 可用 257）：
#   月份行 22 + 间距 4 + 网格 G + 间距 4 + 底部按钮行 31 + 间距 4 + 日程列表 L = 257
#   ⇒ G + L = 192。
# 以前网格 minimumHeight 写 160、列表 minimumHeight 写 40，两个下限加起来 200 > 192，
# 布局压不下去就在网格与按钮行之间重叠了 4px（就是 1.3.3 遗留的那条「日历页纵向
# 挤压」）。同时列表当天没日程时仍占 40px 透明高度，用户看到的「下面一块空白」
# 就是它。现在两个数都按这本账重定：
GRID_MIN_H = 144   # 有日程时的网格下限：192 − 48，正好等于分配值，不会再挤
EV_LIST_H = 48     # 当天有日程时列表的固定高（约两行，更多走滚动条）


class EventDialog(QDialog):
    """新建日程：与设置/赞助弹窗同一套卡片观感（配色随皮肤）+ 中文按钮。

    原来 inheriting 岛体深色 QSS、按钮又是英文 OK/Cancel，标题栏浅色内容深色
    两者割裂；这里显式套卡片样式表并跟随置顶宿主。"""

    def __init__(self, parent=None, day=None, sk_getter=None):
        super().__init__(parent)
        self.setWindowTitle("新建日程")
        # 输入框的配色也在 card_qss 里：不套自带样式就会继承到岛体那套深色控件，
        # 浅标题栏配深内容（就是 B 机看到的割裂）
        self.setStyleSheet(card_qss(sponsor.skin_for(parent)))
        # 岛体是置顶窗口，弹窗不置顶会被压住（1.0.11 同款修复）
        w = parent
        while w is not None and not (w.windowFlags() & Qt.WindowStaysOnTopHint):
            w = w.parentWidget() if hasattr(w, "parentWidget") else None
        if w is not None:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(300)
        f = QFormLayout(self)
        self.title = QLineEdit()
        self.title.setPlaceholderText("会议主题或事项…")
        self.title.setAccessibleName("日程内容")
        self.date = QDateEdit(calendarPopup=True)
        from PyQt5.QtCore import QDate
        d = day or date.today()
        self.date.setDate(QDate(d.year, d.month, d.day))
        self.date.setAccessibleName("日程日期")
        self.time = QTimeEdit()
        self.time.setTime(datetime.now().replace(minute=0, second=0, microsecond=0).time())
        self.time.setAccessibleName("日程时间")
        self.remind = QSpinBox()
        self.remind.setRange(0, 120)
        self.remind.setValue(10)
        self.remind.setSuffix(" 分钟前")
        self.remind.setAccessibleName("提前提醒分钟")
        # 1.4.4：重复从待办迁到日历（待办只管「写什么、做没做」）
        self.repeat = ChoiceButton(EV_REPEAT_OPTIONS, value=0,
                                   sk_getter=sk_getter, tooltip="重复规则")
        self.repeat.setAccessibleName("日程重复规则")
        f.addRow("内容", self.title)
        f.addRow("日期", self.date)
        f.addRow("时间", self.time)
        f.addRow("提醒", self.remind)
        f.addRow("重复", self.repeat)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("确定")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        f.addRow(box)

    def value(self):
        from PyQt5.QtCore import QDateTime
        d = self.date.date().toPyDate()
        t = self.time.time().toPyTime()
        start = datetime.combine(d, t)
        return self.title.text().strip(), start, self.remind.value(), int(
            self.repeat.currentData() or 0)


class MonthGrid(QWidget):
    """自绘月历：6 行 × 7 列，完全跟随主题，无系统控件默认底色

    行高不写死：cell_h = (可用高 − 星期表头) / 6，页面把多出来的高度全给它，
    格子就自己长高（1.4.15 空日程日 196px → 每行 29.7px，有日程 144px → 21.0px）。
    """
    WEEK = ["一", "二", "三", "四", "五", "六", "日"]

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        today = date.today()
        self.year, self.month = today.year, today.month
        self.selected = today
        self.on_change = None
        self.setMinimumHeight(GRID_MIN_H)
        self.setMouseTracking(True)
        self._cells = []

    def _first(self):
        return date(self.year, self.month, 1)

    def shift(self, delta):
        y, m = self.year, self.month + delta
        if m < 1:
            y, m = y - 1, 12
        elif m > 12:
            y, m = y + 1, 1
        self.year, self.month = y, m
        self.update()

    def select(self, day):
        self.selected = day
        self.year, self.month = day.year, day.month
        if self.on_change:
            self.on_change(day)
        self.update()

    def _layout_cells(self):
        first = self._first()
        start = first - timedelta(days=first.weekday())
        cells = []
        for i in range(42):
            cells.append(start + timedelta(days=i))
        return cells

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        sk = self.parent().host.sk() if hasattr(self.parent(), "host") else T.skin("deep")
        w = self.width() / 7.0
        head_h = 18.0
        cell_h = (self.height() - head_h) / 6.0

        p.setFont(T.font(9))
        p.setPen(T.c(sk, "text3"))
        for i, name in enumerate(self.WEEK):
            p.drawText(QRectF(i * w, 0, w, head_h), Qt.AlignCenter, name)

        cells = self._layout_cells()
        self._cells = []
        today = date.today()
        ev_days = {}
        rep_evs = []
        for ev in self.store.events():
            st = parse_dt(ev["start"])
            if st is None:
                continue
            rep = int(ev.get("repeat") or 0)
            if rep:
                rep_evs.append((st, rep))
            else:
                d = st.date()
                ev_days[d] = ev_days.get(d, 0) + 1

        def _n_on(d):
            n = ev_days.get(d, 0)
            for st, rep in rep_evs:
                if ev_occurrence(st, rep, d) is not None:
                    n += 1
            return n

        for idx, d in enumerate(cells):
            r, c = divmod(idx, 7)
            rect = QRectF(c * w + 1.5, head_h + r * cell_h + 1.5, w - 3, cell_h - 3)
            self._cells.append((rect, d))
            in_month = (d.month == self.month)
            if d == self.selected:
                p.setBrush(QBrush(T.c(sk, "accent")))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, 7, 7)
                p.setPen(T.ink_over(T.c(sk, "accent"), sk))
            else:
                p.setPen(T.c(sk, "text") if in_month else T.c(sk, "text3"))
                if d == today:
                    pen = QPen(T.c(sk, "accent"))
                    pen.setWidthF(1.2)
                    p.setBrush(Qt.NoBrush)
                    p.setPen(pen)
                    p.drawRoundedRect(rect, 7, 7)
                    p.setPen(T.c(sk, "accent"))
            # 1.4.15：行高从 23.7 抬到 29.7 后，10px 的日期在格子里显小，跟着抬到 11px
            p.setFont(T.font(11, d == today))
            p.drawText(rect.adjusted(0, -3, 0, 0), Qt.AlignCenter, str(d.day))
            if _n_on(d):
                dot = 2.6
                cy = rect.bottom() - 4.5
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(T.ink_over(T.c(sk, "accent"), sk)
                                  if d == self.selected else T.c(sk, "accent2")))
                p.drawEllipse(QPointF(rect.center().x(), cy), dot, dot)

    def mousePressEvent(self, e):
        pos = e.pos()
        for rect, d in self._cells:
            if rect.contains(QPointF(pos)):
                self.select(d)
                return
        super().mousePressEvent(e)


class CalendarPage(Page):
    capabilities = ("calendar",)
    title = "日历"

    def __init__(self, host):
        super().__init__(host)
        v = QVBoxLayout(self)
        # 1.4.14：水平边距 10→CONTENT_PAD_X(=0)，与页签卡同一条列缘
        v.setContentsMargins(CONTENT_PAD_X, 2, CONTENT_PAD_X, 8)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(4)
        self.btn_prev = QPushButton("‹")
        self.btn_next = QPushButton("›")
        for b in (self.btn_prev, self.btn_next):
            b.setFixedWidth(26)
            b.setFixedHeight(22)
            b.setProperty("nav", "true")
        self.lbl_month = QLabel("")
        self.lbl_month.setAlignment(Qt.AlignCenter)
        head.addWidget(self.btn_prev)
        head.addWidget(self.lbl_month, 1)
        head.addWidget(self.btn_next)
        v.addLayout(head)

        self.grid = MonthGrid(self.store, self)
        self.grid.on_change = lambda d: self.refresh()
        # 1.4.15：stretch 3→1，页面剩下的纵向空间全部给网格（列表定高、不参与抢）
        v.addWidget(self.grid, 1)

        row = QHBoxLayout()
        self.lbl = QLabel("")
        self.lbl.setObjectName("muted")
        row.addWidget(self.lbl, 1)
        self.btn_add = QPushButton("新建")
        self.btn_imp = QPushButton("导入 ics")
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_imp)
        v.addLayout(row)

        self.list = QListWidget()
        self.list.setAccessibleName("当天日程列表")
        # 1.4.15：以前 min40 / max88 再叠 stretch 2，会和网格抢那 192px——两个下限
        # 加起来 200 > 192，压不下去就在网格与按钮行之间重叠 4px（1.3.3 遗留的纵向
        # 挤压）。现在定高 48（约两行，更多走滚动条），当天没日程整条收起：那 40px
        # 的透明列表就是用户截图里「下面还有空白」的那一块。
        self.list.setFixedHeight(EV_LIST_H)
        v.addWidget(self.list, 0)

        self.btn_add.clicked.connect(self.new_event)
        self.btn_imp.clicked.connect(self.import_ics)
        self.btn_prev.clicked.connect(lambda: self._shift(-1))
        self.btn_next.clicked.connect(lambda: self._shift(1))
        self.refresh()

    def _shift(self, delta):
        self.grid.shift(delta)
        # 选中日跟随当前展示的月份：翻月后底部日期/日程列表不再是上个月的
        last = monthrange(self.grid.year, self.grid.month)[1]
        self.grid.select(date(self.grid.year, self.grid.month,
                              min(self.grid.selected.day, last)))
        self.refresh()

    def apply_skin(self, sk):
        self.grid.update()

    def selected_day(self):
        return self.grid.selected

    def new_event(self):
        dlg = EventDialog(self, self.selected_day(),
                          sk_getter=getattr(self.host, "sk", None))
        if dlg.exec_() == QDialog.Accepted:
            title, start, remind, repeat = dlg.value()
            if title:
                self.store.add_event(title, start, remind, repeat=repeat)
                self.refresh()

    def import_ics(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 ics 文件", "", "日历 (*.ics)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                n = self.store.import_ics(f.read())
            self.refresh()
            self.notify("导入完成", "%d 条日程" % n, 3000)
        except Exception as e:
            self.notify("导入失败", str(e), 4000)

    def next_meeting(self, now=None):
        """→ (datetime, event) 下一场会议（含进行中；重复项按规则推进），无则 None"""
        now = now or datetime.now()
        best = None
        for e in self.store.events():
            st = parse_dt(e["start"])
            if st is None:
                continue
            occ = next_occurrence(st, int(e.get("repeat") or 0), now)
            if occ is None or occ > now + timedelta(days=1):
                continue
            if best is None or occ < best[0]:
                best = (occ, e)
        return best

    def refresh(self):
        day = self.selected_day()
        evs = self.store.events_on(day)
        self.lbl_month.setText("%d 年 %d 月" % (self.grid.year, self.grid.month))
        txt = "%d 月 %d 日 · %d 个日程" % (day.month, day.day, len(evs))
        nxt = self.next_meeting()
        if nxt is not None:
            st, ev = nxt
            name = (ev["title"] or "").replace(" ", "")[:6] or "会议"
            mark = "进行中" if st <= datetime.now() else st.strftime("%H:%M")
            txt += "  ·  下一场 %s %s" % (mark, name)
        self.lbl.setText(txt)
        self.list.clear()
        for e in evs:
            st = parse_dt(e["start"])
            txt = "%s  %s" % (st.strftime("%H:%M") if st else "--:--", e["title"])
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, e["id"])
            self.list.addItem(it)
        # 当天没日程就整条收起：隐藏件在 QVBoxLayout 里不占高、也不占那一格间距，
        # 省出来的 52px（48 + 4）全部落进网格行高
        self.list.setVisible(self.list.count() > 0)
        self.grid.update()

    def tick(self, now):
        if now - getattr(self, "_check", 0) < 20:
            return
        self._check = now
        for e in self.store.due_events(now):
            st = parse_dt(e["start"])
            self.notify("日程提醒", "%s  %s" % (st.strftime("%H:%M") if st else "", e["title"]))
            self.store.mark_event_reminded(e, now)
