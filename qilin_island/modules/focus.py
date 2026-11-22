# -*- coding: utf-8 -*-
"""应用层 · 专注计时（M7）"""
from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QFontMetricsF, QPainter
from PyQt5.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .base import Page
from ..core.consts import CONTENT_PAD_X
from ..core import theme as T


class Ring(QWidget):
    """专注进度环：秒级推进只有千分之几的跨度，直接落值；开始/重置/换段这种
    肉眼看得见的大跨度才用 token 缓动补中间帧，不然圆环是"跳"过去的。"""

    JUMP = 0.02

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ratio = 0.0
        self.text = "25:00"
        self.sub = "准备开始"
        self._anim = None
        self.setMinimumHeight(150)

    def set_state(self, ratio, text, sub):
        self.text = text
        self.sub = sub
        self.goto(ratio)

    def goto(self, ratio):
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        if abs(ratio - self.ratio) > self.JUMP:
            self._anim = T.animate(self, "ratio", self.ratio, ratio,
                                   T.DUR["normal"], "inout", self)
            self._anim.finished.connect(lambda: setattr(self, "_anim", None))
        else:
            self.ratio = ratio
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        sk = T.skin(self.parent().host.skin_name())
        d = min(self.width(), self.height()) - 30
        rect = QRectF((self.width() - d) / 2.0, (self.height() - d) / 2.0, d, d)
        T.paint_ring(p, rect, self.ratio, sk, width=7)

        # 倒计时数字严格压在圆心，副标题（专注中/休息中）紧贴数字下方。
        # 用 tightBoundingRect（字形真实墨迹框）而不是 ascent/descent 计算基线，
        # 否则中文字体的行距会让数字看起来偏离圆心。
        f_num = T.font(20, True)
        f_sub = T.font(9)
        fm_n = QFontMetricsF(f_num)
        fm_s = QFontMetricsF(f_sub)
        ink_n = fm_n.tightBoundingRect(self.text)
        ink_s = fm_s.tightBoundingRect(self.sub) if self.sub else None
        gap = 3.0
        cy = rect.center().y()

        def draw_ink(font, ink, text, color, center_y):
            p.setFont(font)
            p.setPen(color)
            x = self.width() / 2.0 - ink.width() / 2.0 - ink.left()
            baseline = center_y - (ink.top() + ink.height() / 2.0)
            p.drawText(QPointF(x, baseline), text)

        draw_ink(f_num, ink_n, self.text, T.c(sk, "text"), cy)
        if ink_s is not None:
            sub_cy = cy + ink_n.height() / 2.0 + gap + ink_s.height() / 2.0
            draw_ink(f_sub, ink_s, self.sub, T.c(sk, "text2"), sub_cy)


class FocusPage(Page):
    capabilities = ("focus",)
    title = "专注"

    def __init__(self, host):
        super().__init__(host)
        self._started = False   # 区分「没开始」与「暂停在半路」
        v = QVBoxLayout(self)
        # 1.4.14：水平边距 CONTENT_PAD_X(=0)，与页签卡同一条列缘
        v.setContentsMargins(CONTENT_PAD_X, 6, CONTENT_PAD_X, 10)
        v.setSpacing(6)
        self.ring = Ring(self)
        v.addWidget(self.ring, 1)

        # 底行三列：左列放开始/暂停，右列放重置，两列等宽把统计小字夹在正中
        # （原来 暂停|重置 挤左上、统计贴右上，用户口径：重置要靠右，统计要居中）
        row = QGridLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setHorizontalSpacing(6)
        row.setVerticalSpacing(0)
        self.btn = QPushButton("开始")
        self.btn.setProperty("kind", "primary")
        self.btn_reset = QPushButton("重置")
        self.stat = QLabel("")
        self.stat.setObjectName("muted")
        self.stat.setAlignment(Qt.AlignCenter)
        self.btn.setAccessibleName("开始或暂停专注")
        self.btn_reset.setAccessibleName("重置专注计时")
        self.stat.setAccessibleName("今日专注统计")
        row.addWidget(self.btn, 0, 0, Qt.AlignLeft)
        row.addWidget(self.stat, 0, 1)
        row.addWidget(self.btn_reset, 0, 2, Qt.AlignRight)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 0)
        row.setColumnStretch(2, 1)
        v.addLayout(row)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick_second)
        self.running = False
        self.mode = "work"
        self.total = 25 * 60
        self.remaining = self.total
        self.btn.clicked.connect(self.toggle)
        self.btn_reset.clicked.connect(self.reset)
        self.refresh_stat()

    def cfg(self):
        c = self.store.settings.get("focus") or {}
        return int(c.get("work", 25)), int(c.get("rest", 5))

    def shell_skin(self):
        return self.host.skin_name()

    def refresh_stat(self):
        f = self.store.focus_today()
        self.stat.setText("今日 %d 个 · %d 分钟" % (f.get("done", 0), int(f.get("seconds", 0)) // 60))
        self.paint_state()

    def paint_state(self):
        ratio = 0.0 if not self.total else 1.0 - self.remaining / float(self.total)
        sub = {"work": "专注中", "rest": "休息中"}.get(self.mode, "")
        if not self.running:
            # 用显式标志区分“还没开始”和“暂停在半路”，后者只剩 remaining==total 时会误判
            sub = "准备开始" if not self._started else "已暂停"
        self.ring.set_state(ratio, T.fmt_duration(self.remaining), sub)

    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def start(self):
        if self.remaining <= 0:
            self.reset()
        self.running = True
        self._started = True
        self.timer.start()
        self.btn.setText("暂停")
        self.paint_state()
        self.host.refresh_badge()

    def pause(self):
        self.running = False
        self.timer.stop()
        self.btn.setText("继续")
        self.paint_state()
        self.host.refresh_badge()

    def reset(self, mode=None):
        self.running = False
        self._started = False
        self.timer.stop()
        work, rest = self.cfg()
        self.mode = mode or "work"
        self.total = (work if self.mode == "work" else rest) * 60
        self.remaining = self.total
        self.btn.setText("开始")
        self.paint_state()
        self.host.refresh_badge()

    def _tick_second(self):
        self.step(1)

    def step(self, sec=1):
        """供测试直接推进秒数"""
        if self.remaining > 0:
            self.remaining -= sec
        if self.remaining <= 0:
            self.finish()
        else:
            self.paint_state()

    def finish(self):
        self.running = False
        self.timer.stop()
        if self.mode == "work":
            work, rest = self.cfg()
            self.store.focus_add(work * 60)
            self.notify("专注结束", "%d 分钟到，休息 %d 分钟吧" % (work, rest))
            self.reset("rest")
            self.start()
        else:
            self.notify("休息结束", "回到专注吧")
            self.reset("work")
        self.refresh_stat()

    def tick(self, now):
        pass
