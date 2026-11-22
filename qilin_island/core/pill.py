# -*- coding: utf-8 -*-
"""核心层 · 胶囊内的自绘控件（M1 4.2 内容显示）

logo、信息轮播、音乐跳动条；只做显示，不判断该显示什么。

1.4.3 对齐口径（用户验收标准）：
  ① 图标墨迹贴住左内边距，且**不随轮播页移动**；
  ② 图标墨迹中线与文字墨迹中线严格重合（±1px）；
  ③ 静止页文字在「图标右侧剩余区」内居中 —— 不是整个胶囊的中轴居中。"""
import math
from PyQt5.QtCore import QPointF, QRectF, QSize, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PyQt5.QtWidgets import QSizePolicy, QWidget
from .consts import CAR_MAX
from . import theme as T


class LogoLabel(QWidget):
    """收起态左侧图标。

    QLabel 摆 pixmap 只能靠对齐/外边距粗调，而这张图的墨迹只占上 80%（底部
    留白），直接居中会比时间文字高出 4px 左右，看着就是"图标飘在上面"。
    这里自绘，`dy` 精确控制落下多少像素，和文字的视觉中线对齐。

    1.4.3：pixmap 自身四周还有 1px 透明边，照 (0, dy) 画的话墨迹离左内边距
    还差 1px，"贴左"就不实。这里先量出墨迹的左上偏移，画时抵消掉。"""

    def __init__(self, island, size=18, height=24, dy=6):
        super().__init__()
        self._island = island
        self._size = size
        self._dy = dy
        self._ix = 0              # pixmap 墨迹相对左沿的透明边，画时抵消
        self._measured = False
        self.setFixedSize(size, height)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setToolTip("麒麟灵动岛")

    def _pixmap(self):
        pm = self._island._logo_pm(self._size)
        if not self._measured:
            img = pm.toImage()
            for x in range(img.width()):
                if any(img.pixelColor(x, y).alpha() > 8
                       for y in range(img.height())):
                    self._ix = x
                    break
            self._measured = True
        return pm

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawPixmap(-self._ix, self._dy, self._pixmap())
        p.end()


class CarWidget(QWidget):
    """收起态信息轮播条：逐段着色文本；内容超宽自动横向滚动（不用省略号）；
    切页时 alpha 淡入（QPainter.setOpacity，纯绘制层实现，任何环境稳定）"""

    FPIX = 12                      # 与 QSS QLabel#chips 同字号；10px 在 1080p 胶囊里偏小
    PAD = 8.0                      # 左右各留的余量：跑马灯首尾停留 + 切页滑入
    VDY = 2.5                      # 文字光学中线比基线算法算出的位置低 2.5px，与图标墨迹中线严格重合

    def __init__(self, island, lead=6.0):
        super().__init__(island)
        self.island = island
        self.LEAD = float(lead)   # 本控件左缘到图标右沿的间距（= 头部布局 spacing）
        self._pages = []          # [(segs, text)]
        self._idx = 0             # 当前页
        self._segs = []           # 当前页段落
        self._off = 0.0           # 滚动偏移
        self._off_max = 0.0
        self._fade = 1.0          # 切页淡入
        self._anim = None         # 淡入动画句柄
        self._scrolling = False
        self._axis = 0.0          # 静止页的居中基准：本控件即「图标右侧剩余区」，按它的中心居中
        self._ink = (0.0, 0.0)    # 本页墨迹相对绘制原点的左右边界，居中按墨迹不按字宽
        # 度量/绘制用固定字体：QSS 的 QWidget 字号会覆盖 setFont，绕开它
        self._mfont = QFont()
        self._mfont.setPixelSize(self.FPIX)
        self.setFixedHeight(18)
        # 横向吃满图标~右缘之间的空间：文字位置由 paintEvent 按**本控件中轴**摆，
        # 也就是「去掉图标之后那块地」的中心；图标固定在左侧不参与居中
        # （用户要求：图标不能随轮播页左右跳）
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._on_frame)
        self._timer.start()

    def set_pages(self, pages, idx):
        """pages=[(segs, text)]；idx 变化→淡入切页，同页→静默刷新数据"""
        self._pages = pages
        idx = idx % len(pages) if pages else 0
        segs = pages[idx][0] if pages else []
        moved = (idx != self._idx) or (not self._segs and bool(segs))
        self._idx = idx
        self._segs = segs
        if moved:
            self._fade_in()
            self._off = -24.0            # 头部短暂停留
        fm = QFontMetricsF(self._mfont)
        # 墨迹边界：字宽含首尾空格的推进量，按字宽居中会让肉眼看到的字偏右几 px
        acc, lo, hi = 0.0, 0.0, 0.0
        for t, _c in segs:
            r = fm.boundingRect(t)
            lo = acc + r.x() if not acc else min(lo, acc + r.x())
            hi = max(hi, acc + r.x() + r.width())
            acc += fm.horizontalAdvance(t)
        self._ink = (lo, hi)
        cw = acc
        # 跑不跑看本控件能占多宽（Expanding 下这就是图标右侧的全部空间），
        # 只留一个 PAD 给切页滑入
        avail = max(1.0, self.width() - self.PAD)
        self._off_max = max(0.0, cw - avail)
        self._scrolling = cw > avail
        if not self._scrolling:
            self._off = 0.0
        # 居中基准：自由区 =「图标右沿 → 本控件右缘」，LEAD 这段间距也算自由区，
        # 所以中线要往左让半个 LEAD
        self._axis = self.width() / 2.0 - self.LEAD / 2.0
        if self.max_w() != self.width():     # 预算宽变了才动布局，避免抖动
            self.updateGeometry()
        self.update()

    def current_text(self):
        return self._pages[self._idx][1] if self._pages else ""

    def _fade_in(self):
        """切页淡入：用 token 的时长与入场曲线，滑入位移跟着 alpha 一起缓动"""
        if self._anim is not None:
            self._anim.stop()
        self._fade = 0.0
        self._anim = T.animate(self, "_fade", 0.0, 1.0, T.DUR["slow"], "enter", self)
        self._anim.finished.connect(lambda: setattr(self, "_anim", None))
        self.update()

    def max_w(self):
        """全部轮播页中的最大预算宽（截到 CAR_MAX）——布局预算用，
        保证切页与数据刷新时本控件宽度稳定；budget_w=None 的页按实际内容宽算"""
        if not self._pages:
            return 0
        fm = QFontMetricsF(self._mfont)
        m = 0.0
        for segs, _text, bw in self._pages:
            w = bw if bw is not None else sum(fm.horizontalAdvance(t) for t, _ in segs)
            m = max(m, w)
        return int(min(m, CAR_MAX)) + 2 * int(self.PAD)

    def resizeEvent(self, e):
        """控件宽度变了就刷新居中基准：文字永远落在「图标右侧剩余区」的正中，
        不因窗口尺寸/右侧控件显隐而偏到岛体中轴上"""
        self._axis = self.width() / 2.0 - self.LEAD / 2.0
        super().resizeEvent(e)

    def _on_frame(self):
        dirty = False
        # 淡入不再按帧手加：时长与曲线归 token（见 _fade_in），这里只管跑马灯
        if self._scrolling:
            self._off += 0.7              # ~14px/s
            if self._off > self._off_max + 48:
                self._off = -24.0         # 首尾各停留约 1.5s
            dirty = True
        if dirty:
            self.update()

    def paintEvent(self, e):
        if not self._segs:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setOpacity(self._fade)
        fm = QFontMetricsF(self._mfont)
        cw = sum(fm.horizontalAdvance(t) for t, _ in self._segs)
        if self._scrolling:
            x = self.PAD - max(0.0, self._off)      # 跑马灯：从左余量处滚入
        else:
            # 静止页：墨迹中线落在「图标右侧剩余区」的中轴上（用户要求：内容占没有
            # 图标的那块地的中心，而不是整个胶囊的中心）。左侧贴到控件原点即是
            # 图标右沿+间距，天然压不到图标；右侧超出时收到右边缘内。
            lo, hi = self._ink
            x = self._axis - (lo + hi) / 2.0
            x = min(max(x, 0.0), max(0.0, self.width() - hi))
        x += (1.0 - self._fade) * 8.0            # 切页时轻微右→左滑入
        base = (self.height() + fm.ascent() - fm.descent()) / 2.0 + self.VDY
        p.setClipRect(self.rect())
        for text, color in self._segs:
            w = fm.horizontalAdvance(text)
            if x + w > 0 and x < self.width():
                p.setPen(QColor(color))
                p.drawText(QPointF(x, base), text)
            x += w
        p.end()

    def sizeHint(self):
        return QSize(max(10, self.max_w()), 18)


class EqWidget(QWidget):
    """收起态迷你均衡条：播放中随节拍跳动，暂停时静止。

    不采集音频流（离线优先），用相位错开的正弦叠加模拟频谱起伏，
    视觉上「在动」就够了；等以后接 PulseAudio 采样再换真数据。
    """

    def __init__(self, island):
        super().__init__()
        self._island = island
        self._t = 0.0
        self._on = False
        self.setFixedSize(16, 22)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setToolTip("正在播放")

    def set_playing(self, on):
        on = bool(on)
        if on != self._on:
            self._on = on
            self.update()

    def advance(self):
        """每秒推一帧相位；没在播放就不重绘（省电）"""
        if self._on and self.isVisible():
            self._t += 0.9
            self.update()

    def paintEvent(self, e):
        if not self.isVisible():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        sk = self._island.sk()
        n, w = 4, 2.4
        gap = (self.width() - n * w) / (n - 1) if n > 1 else 0
        base = self.height() - 2.0
        color = T.c(sk, "accent")
        color.setAlpha(210)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        for i in range(n):
            if self._on:
                v = (0.32 + 0.60 * abs(math.sin(self._t * 1.7 + i * 0.9))
                     * (0.55 + 0.45 * math.sin(self._t * 0.63 + i * 1.7)))
            else:
                v = 0.22
            h = max(3.0, base * min(1.0, v))
            p.drawRoundedRect(QRectF(i * (w + gap), base - h, w, h), 1.2, 1.2)
        p.end()
