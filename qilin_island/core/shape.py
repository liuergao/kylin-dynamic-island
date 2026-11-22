# -*- coding: utf-8 -*-
"""交互层 · M2 窗口与形状

有无合成器决定走透明图层还是 1-bit 遮罩；两种收起形态的绘制都在本模块，
窗口尺寸变化后必须同步重算遮罩，否则圆角外会残留上一帧。"""
import math
import time
from PyQt5.QtCore import QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import (QFontMetricsF, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRegion)
from ..platform import x11
from .consts import NOTCH_RADIUS, PANEL_RADIUS
from . import brand
from . import theme as T


def rounded_region(rect, radius, round_top=True, round_bottom=True):
    """逐行算圆角内缩，生成像素级 QRegion。

    1.2.8 用 QPainterPath.toFillPolygon() 出遮罩，弧线只按角度容差采样几个点，
    无合成器时圆角就是一圈白色锯齿。这里一行一个矩形，边界精确到像素。"""
    w, h = rect.width(), rect.height()
    r = min(float(radius), w / 2.0, h / 2.0)
    region = QRegion()
    run_inset = None
    run_y0 = 0
    for y in range(h):
        inset = 0
        if r > 0:
            if round_top and y < r:
                dy = r - 0.5 - y
            elif round_bottom and y > h - 1 - r:
                dy = y - (h - 1 - r) - 0.5
            else:
                dy = 0.0
            if dy > 0:
                dy = min(dy, r)
                inset = int(math.ceil(r - math.sqrt(max(0.0, r * r - dy * dy))))
        if inset != run_inset:
            if run_inset is not None:
                region += _run_rect(rect, run_y0, y - 1, run_inset)
            run_inset = inset
            run_y0 = y
    if run_inset is not None:
        region += _run_rect(rect, run_y0, h - 1, run_inset)
    return region


def _run_rect(rect, y0, y1, inset):
    x = rect.left() + inset
    w = rect.width() - 2 * inset
    if w <= 0:
        return QRegion()
    return QRect(x, rect.top() + y0, w, y1 - y0 + 1)


class ShapeMixin:
    def shape_init(self):
        """M2 初始状态：先定绘制路径——有合成器走透明图层，没有走 1-bit 遮罩"""
        self.comp = self.composited()

    @staticmethod
    def composited():
        """有无合成器：没有就退化为不透明方角，避免黑边/不可见"""
        return x11.has_compositor()

    def _logo_pm(self, size=18):
        """按设备像素比渲染 logo。

        原来固定 18px 位图，在 2× 屏上被放大一倍绘制：边缘那圈半透明像素被
        插值摊平，在深色胶囊上看起来就是一小块灰白矩形雾。改成按 DPR 出图再
        标回逻辑尺寸，像素一对一，边缘干净。
        """
        scr = QGuiApplication.primaryScreen()
        dpr = float(scr.devicePixelRatio()) if scr is not None else 1.0
        dpr = max(1.0, min(4.0, dpr))
        pm = brand.logo_pixmap(int(round(size * dpr)), simple=True)
        pm.setDevicePixelRatio(dpr)
        return pm

    def _refresh_comp(self):
        """合成器可能中途被打开：开着才走抗锯齿圆角 + 半透明，关着走 1bit 遮罩"""
        if self.comp:
            return
        if not self.composited():
            return
        self.comp = True
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._apply_mask()      # comp=True 时这里会 clearMask
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        sk = self.sk()
        # 收起形态分派：细线（一条渐变指示条）/ 刘海（贴顶、只圆下两角）/ 常规胶囊
        if not self.expanded and self._style_now() == "line":
            self._paint_line(p, sk)
            return
        if not self.expanded and self.dock == "top" and self._style_now() == "notch":
            self._paint_notch(p, sk)
            return
        # 有合成器：抗锯齿圆角；无合成器：用窗口遮罩剪出同样的圆角，
        # 不再退化成方角。
        rect = self.rect()
        # border 去掉：comp 下窗口透明、面板画满，外圈不再有描边/露底；
        # 无合成器时先把整块矩形铺成同一渐变，遮罩边缘的抗锯齿像素才不会
        # 混到窗口默认的浅色底上（就是用户反馈的「周边白色锯齿」）。
        # alpha 一律 255：以前 comp 走 246 是想做"半透明玻璃"，实测合成器一开
        # 就是 4% 透底——面板压在文档窗口上，正文笔画会从深色底里浮出来，
        # 小字号对比度也跟着掉。平滑边缘来自圆角路径自身的像素覆盖率，
        # 与整体 alpha 无关，所以这里两者都要：轮廓抗锯齿、内容不透底。
        T.paint_panel(p, rect, sk, radius=PANEL_RADIUS,
                      alpha=255, border=False, opaque=not self.comp)
        if not self.expanded:
            self._paint_rim(p, sk)
        if not self.expanded and self.dock in ("left", "right"):
            self._paint_vertical(p, sk)

    def _paint_rim(self, p, sk):
        """收起态外圈 1px 轮廓线。

        面板态有内容撑边界，胶囊态就是一块纯色贴在桌面上——没有描边时浅色壁纸
        和深色岛之间只有硬切的一刀，看着像块没抠干净的贴纸。描边取 line_strong
        （线色往文本色推 30%，两套底色都看得见）。
        无合成器时窗口靠遮罩剪形，笔宽居中会有一半被剪掉只剩半像素淡线，
        所以整条线要画在遮罩内侧。"""
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        pen = QPen(T.c(T.states(sk), "line_strong"))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(T.rounded_path(rect, PANEL_RADIUS - 0.75))

    def _paint_line(self, p, sk):
        """隐藏态指示线：2~6px 宽的渐变圆角条，顶部停靠是横线、侧停靠是竖线"""
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        a = T.c(sk, "accent")
        b = T.c(sk, "accent2")
        p.setPen(Qt.NoPen)
        if not self.comp:
            p.fillRect(self.rect(), a)     # 先铺满，遮罩边缘的 AA 像素才不会露白
        grad = QLinearGradient(r.topLeft(), r.topRight() if r.width() >= r.height()
                               else r.bottomLeft())
        grad.setColorAt(0.0, a)
        grad.setColorAt(1.0, b)
        p.setBrush(grad)
        p.drawRoundedRect(r, min(r.width(), r.height()) / 2.0,
                          min(r.width(), r.height()) / 2.0)

    def _notch_path(self, rect):
        """刘海：顶部两角为直角、底部两角圆角"""
        w, h = rect.width(), rect.height()
        rad = min(NOTCH_RADIUS, h / 2.0)
        path = QPainterPath()
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right(), rect.bottom() - rad)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - rad, rect.bottom())
        path.lineTo(rect.left() + rad, rect.bottom())
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - rad)
        path.closeSubpath()
        return path

    def _paint_notch(self, p, sk):
        p.setRenderHint(QPainter.Antialiasing, True)
        grad = QLinearGradient(QRectF(self.rect()).topLeft(),
                               QRectF(self.rect()).bottomLeft())
        grad.setColorAt(0.0, T.c(sk, "bg2"))
        grad.setColorAt(1.0, T.c(sk, "bg1"))
        p.setPen(Qt.NoPen)
        if not self.comp:
            p.fillRect(self.rect(), T.c(sk, "bg2"))
        p.setBrush(grad)
        p.fillPath(self._notch_path(QRectF(self.rect())), p.brush())
        if self.comp:
            # 只描底部与两侧，顶部与屏幕边融合
            pen = QPen(T.c(sk, "line"))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = self._notch_path(QRectF(self.rect()).adjusted(0.5, 0, -0.5, -0.5))
            p.drawPath(path)

    def _paint_vertical(self, p, sk):
        """侧边竖版收起态：logo 在上，时间**逐字竖排**（每字正立、自上而下），
        专注中显示剩余时间。整串旋转 -90° 是错的做法——那样得歪头才看得懂。"""
        w, h = self.width(), self.height()
        pm = self._logo_pm(15)
        p.drawPixmap(int((w - 15) / 2), 9, pm)

        fp = self._focus_running()
        if fp is not None:
            text = T.fmt_duration(fp.remaining)
        else:
            text = self.clock.text() or time.strftime("%H:%M")

        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        chars = [c for c in text if not c.isspace()]
        n = max(1, len(chars))
        top, bottom = 26.0, h - 10.0
        avail = max(1.0, bottom - top)
        pitch = min(20.0, avail / n)                 # 每字占的高度
        size = int(max(9, min(15, pitch * 0.86)))
        f = T.font(size, True)
        p.setFont(f)
        fm = QFontMetricsF(f)
        ink_c = T.c(sk, "text")
        block = pitch * n
        y0 = top + (avail - block) / 2.0

        for i, ch in enumerate(chars):
            cy = y0 + pitch * (i + 0.5)
            if ch in ":：":                            # 冒号改成两个小圆点，竖排里更清爽
                p.setPen(Qt.NoPen)
                p.setBrush(ink_c)
                p.drawEllipse(QPointF(w / 2.0, cy - size * 0.22), 1.2, 1.2)
                p.drawEllipse(QPointF(w / 2.0, cy + size * 0.22), 1.2, 1.2)
                continue
            ink = fm.tightBoundingRect(ch)
            p.setPen(ink_c)
            p.setBrush(Qt.NoBrush)
            p.drawText(QPointF(w / 2.0 - ink.center().x(), cy - ink.center().y()), ch)

    def resizeEvent(self, e):
        self.body.setGeometry(self.rect())
        self._apply_mask()
        super().resizeEvent(e)

    def _apply_mask(self):
        """无合成器时用 1bit 窗口遮罩剪出圆角：逐行像素区域，不用粗折线"""
        if self.comp:
            if not self.mask().isEmpty():
                self.clearMask()
            return
        rect = self.rect()
        if not self.expanded and self._style_now() == "line":
            self.setMask(rounded_region(rect, min(rect.width(), rect.height()) / 2.0))
            return
        if not self.expanded and self.dock == "top" and self._style_now() == "notch":
            # 刘海：顶部两角贴屏幕边是直角，只剪下面两个角
            self.setMask(rounded_region(rect, NOTCH_RADIUS,
                                        round_top=False, round_bottom=True))
            return
        self.setMask(rounded_region(rect, PANEL_RADIUS))
