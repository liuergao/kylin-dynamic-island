# -*- coding: utf-8 -*-
"""应用层 · 饮水提醒（M8）"""
from datetime import datetime
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .base import Page
from ..core.consts import CONTENT_PAD_X
from ..core import theme as T


class Cups(QWidget):
    """梯形水杯网格：杯数多时自动折行（每行最多 4 只），整组在杯区居中。

    1.4.7 把杯子按格子铺满，结果 67×65 的近正方形读数就是"桶"；1.4.8 给单杯
    封顶（宽 44px、竖高比例 1.30），行列均分时间隙再封顶，多出来的空间作为对称
    留白——杯子不放大成桶，一排也不会被拉得满屏稀疏。"""

    COLS_MAX = 4
    TAPER = 0.13             # 下底每侧内收比例（梯形腰的斜度）
    CUP_MAX_W = 44           # 单杯最大宽：宁可留白，不把杯子撑大
    CUP_RATIO = 1.30         # 高/宽，杯子是竖的
    EDGE = 2.0               # 杯区内缘留白：描边 1.6px 的一半不能裁掉
    MAX_GAP = 20             # 相邻杯子最大间隙：再空也不把一排杯子拉散

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cups = 0
        self.goal = 8
        self.setMinimumHeight(120)
        self.setAccessibleName("今日水杯进度")

    def set_state(self, cups, goal):
        self.cups, self.goal = cups, max(1, goal)
        self.update()

    def _grid(self):
        cols = min(self.goal, self.COLS_MAX)
        rows = (self.goal + cols - 1) // cols
        return cols, rows

    def cell_rects(self):
        """→ [(QRectF, filled)] 每只杯子的梯形外接矩形，供绘制与自检量尺寸

        尺寸封顶（宽 44），但行列按杯区两端铺齐——杯子不放大成桶，画面也不空。"""
        cols, rows = self._grid()
        cell_w = self.width() / float(cols)
        cell_h = self.height() / float(rows)
        w = min(cell_w * 0.80,
                cell_h * 0.80 / self.CUP_RATIO,
                float(self.CUP_MAX_W))
        h = w * self.CUP_RATIO
        usable_w = self.width() - 2 * self.EDGE
        usable_h = self.height() - 2 * self.EDGE
        # 行列均分，但间隙封顶 MAX_GAP：杯子不放大，也不会被拉得满屏稀疏，
        # 超出部分作为对称留白
        pitch_x = self._pitch(usable_w, w, cols)
        pitch_y = self._pitch(usable_h, h, rows)
        x0 = self.EDGE + (usable_w - ((cols - 1) * pitch_x + w)) / 2.0
        y0 = self.EDGE + (usable_h - ((rows - 1) * pitch_y + h)) / 2.0
        out = []
        for i in range(self.goal):
            r, c = divmod(i, cols)
            out.append((QRectF(x0 + c * pitch_x, y0 + r * pitch_y, w, h),
                        i < self.cups))
        return out

    def _pitch(self, usable, size, n):
        if n <= 1:
            return 0.0
        return min((usable - size) / float(n - 1), size + self.MAX_GAP)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        sk = T.skin(self.parent().host.skin_name())
        for rect, filled in self.cell_rects():
            self._cup(p, rect, filled, sk)

    def _cup(self, p, rect, filled, sk):
        """上宽下窄的梯形杯身 + 只描边的杯口椭圆。

        杯口不能填色：1.4.7 给空杯的椭圆填了 card 色，杯区本身没有背景，
        那块椭圆就成了一枚浮在页面底色上的异色补丁。改成一律 NoBrush，
        只沿轮廓描一笔，杯口是"口"而不是一块斑。"""
        ink = T.c(sk, "accent") if filled else T.c(sk, "line")
        eh = rect.width() * 0.20              # 杯口椭圆高
        body = QRectF(rect.left(), rect.top() + eh / 2.0,
                      rect.width(), rect.height() - eh / 2.0)
        inset = body.width() * self.TAPER     # 下底内收，形成梯形
        path = QPainterPath()
        path.moveTo(body.topLeft())
        path.lineTo(body.topRight())
        path.lineTo(QPointF(body.right() - inset, body.bottom()))
        path.lineTo(QPointF(body.left() + inset, body.bottom()))
        path.closeSubpath()
        pen = QPen(ink)
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.setBrush(QBrush(T.c(sk, "accent")) if filled else Qt.NoBrush)
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)                # 杯口一律不填，避免异色补丁
        p.drawEllipse(QRectF(body.left(), rect.top(), body.width(), eh))


class WaterPage(Page):
    capabilities = ("water",)
    title = "饮水"

    def __init__(self, host):
        super().__init__(host)
        v = QVBoxLayout(self)
        # 1.4.14：水平边距 CONTENT_PAD_X(=0)，与页签卡同一条列缘
        v.setContentsMargins(CONTENT_PAD_X, 8, CONTENT_PAD_X, 10)
        v.setSpacing(8)
        self.big = QLabel("0 / 8 杯")
        # QSS 的 QWidget{font-size:12px} 会压掉 setFont，字号只能写进控件自己的
        # 样式表。1.4.7 定到 20px 用户嫌大，1.4.8 收到 16px（比原来 12px 仍醒目）
        self.big.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.big.setAlignment(Qt.AlignCenter)
        self.big.setAccessibleName("今日饮水量")
        v.addWidget(self.big)
        # 杯区吃掉剩余高度：页面不再上下各留一段空白
        self.cups = Cups(self)
        v.addWidget(self.cups, 1)

        row = QHBoxLayout()
        self.btn_add = QPushButton("喝一杯")
        self.btn_add.setProperty("kind", "primary")
        self.btn_sub = QPushButton("撤销")
        row.addStretch(1)           # 按钮组水平居中，不再左贴
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_sub)
        row.addStretch(1)
        v.addLayout(row)

        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.info.setAlignment(Qt.AlignHCenter)
        self.info.setWordWrap(True)
        self.info.setAccessibleName("饮水提醒设置")
        self.btn_add.setAccessibleName("记录喝一杯水")
        self.btn_sub.setAccessibleName("撤销一杯水")
        v.addWidget(self.info)

        self.btn_add.clicked.connect(lambda: self.add(1))
        self.btn_sub.clicked.connect(lambda: self.add(-1))
        self.btn_sub.setEnabled(False)      # 0 杯时撤销无意义，置灰
        self._remind = 0
        self.refresh()

    def cfg(self):
        return self.store.settings.get("water") or {}

    def add(self, delta):
        cups = self.store.water_add(delta)
        self.refresh()
        return cups

    def refresh(self):
        c = self.cfg()
        goal = int(c.get("goal", 8))
        cups = self.store.water_today()
        self.big.setText("%d / %d 杯   %d ml" % (cups, goal, cups * int(c.get("cup", 250))))
        self.cups.set_state(cups, goal)
        self.btn_sub.setEnabled(cups > 0)
        self.info.setText("提醒：每 %d 分钟，%02d:00–%02d:00 之间" % (
            int(c.get("interval", 45)), int(c.get("from", 9)), int(c.get("to", 21))))

    def water_due(self, now):
        """→ (该喝水?, 已喝杯数, 目标) 供收起态轮播复用"""
        c = self.cfg()
        hour = datetime.fromtimestamp(now).hour
        if not (int(c.get("from", 9)) <= hour < int(c.get("to", 21))):
            return False, self.store.water_today(), int(c.get("goal", 8))
        gap = int(c.get("interval", 45)) * 60
        return (now - self._remind >= gap,
                self.store.water_today(), int(c.get("goal", 8)))

    def tick(self, now):
        due, cups, goal = self.water_due(now)
        if due and cups < goal:
            self._remind = now
            self.notify("该喝水了", "今天 %d / %d 杯，来一杯" % (cups, goal))
