# -*- coding: utf-8 -*-
"""交互层 · 岛内 Toast（临时提示条）

托盘的 showMessage 依赖系统通知进程；麒麟 UKUI 上没这个进程时它会抛异常，
调用方只能降级成"改窗口标题"，用户等于什么都没收到。这一层用岛体自己的绘制
口径补一条短暂提示：贴在胶囊下沿、置顶、不抢焦点、圆角沿用 rounded_region
的像素级遮罩，淡入淡出走 theme.animate——所以设置页的「动效」总开关关掉时，
它是直接出现/消失，不闪也不拖尾。"""
from PyQt5.QtCore import QRect, QTimer, Qt
from PyQt5.QtGui import QColor, QFontMetricsF, QPainter
from PyQt5.QtWidgets import QWidget
from . import shape
from . import theme as T

H = 32                       # 高度：4px 格点（8 的倍数）
PAD_X = 12                   # 左右留白（格点值）
GAP = 8                      # 与胶囊的间距
BAR_W = 4                    # 左侧主色条，正好一个格点
MAX_W = 480                  # 再宽就成了横幅，长句交给省略号
MIN_W = 120


class Toast(QWidget):
    def __init__(self, island):
        super().__init__(None)
        self._island = island
        self._text = ""
        self._a = 0.0                       # 整条的不透明度，动画驱动这个值
        self._anim = None
        self._action = None                 # (label, callback)，右侧可点区域
        self._act_rect = QRect()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.fade_out)
        # Tool：不进任务栏也不进 Alt+Tab；不接焦点 + 显示不激活：
        # 弹提示时绝不把焦点从用户正在打字的窗口上抢走
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # 跟岛体同规则：有合成器才走透明图层，没有就靠遮罩裁，
        # 否则非合成 X11 上整块底会变成黑色
        if getattr(island, "comp", False):
            self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedHeight(H)
        self.setAccessibleName("提示")

    # ── 对外 ──────────────────────────────────────────────────────────────
    def show_text(self, text, ms=4000, action=None):
        """action=(label, callback)：右侧多一块可点区域（删除撤销等短动作用）"""
        self._text = (text or "").strip()
        if not self._text:
            return
        self._action = action if (action and callable(action[1])) else None
        was_hidden = not self.isVisible()
        self.resize(self._need_w(), H)
        self._place()
        self.show()
        self._apply_mask()
        if was_hidden:
            self._a = 0.0
        self._fade(1.0, "enter")
        self._timer.start(max(600, int(ms)))

    def mousePressEvent(self, e):
        if self._action is not None and self._act_rect.contains(e.pos()):
            label, cb = self._action
            self._action = None
            self._timer.stop()
            self.hide()
            cb()
            return
        super().mousePressEvent(e)

    def fade_out(self):
        if self.isVisible():
            self._fade(0.0, "exit")

    def sync(self):
        """岛体移动或形变之后重贴一次位置：只在显示时算，不显示就什么都不做"""
        if self.isVisible():
            self._place()

    # ── 尺寸与位置 ────────────────────────────────────────────────────────
    def _need_w(self):
        fm = QFontMetricsF(self.font())
        w = int(fm.boundingRect(self._text).width()) + 2 * PAD_X + BAR_W + 4
        if self._action:
            w += int(fm.boundingRect(self._action[0]).width()) + 2 * PAD_X
        return max(MIN_W, min(MAX_W, w))

    def _place(self):
        """默认贴在胶囊下沿；下面放不下（贴屏幕底）就翻到上沿"""
        g = self._island.geometry()
        area = self._island._screen()
        x = g.left() + (g.width() - self.width()) // 2
        x = max(area.left(), min(x, area.right() - self.width() + 1))
        y = g.bottom() + GAP + 1
        if y + H > area.bottom():
            y = max(area.top(), g.top() - GAP - H)
        self.move(x, y)

    def _apply_mask(self):
        """无合成器才用 1-bit 遮罩裁圆角，和岛体同一个函数。

        有合成器时必须 clearMask：遮罩是 1-bit 的，压在抗锯齿绘制上等于把已经
        画顺的圆弧重新切成台阶——正是这次要修的锯齿。
        """
        if getattr(self._island, "comp", False):
            if not self.mask().isEmpty():
                self.clearMask()
            return
        r = T.clamp_r(T.R["overlay"], self.height(), self.width())
        self.setMask(shape.rounded_region(self.rect(), r))

    # ── 淡入淡出 ──────────────────────────────────────────────────────────
    def _fade(self, to, ease):
        if self._anim is not None:
            self._anim.stop()
            self._anim = None

        def _done():
            # 一个连接干完收尾：清句柄会把 _Eased 的引用放掉，若此时还有第二个
            # 连接排在后面，槽就丢了。hide 也必须在放引用之前做。
            if to < 0.5:
                self.hide()
            self._anim = None

        self._anim = T.animate(self, "_a", self._a, to, T.DUR["fast"], ease, self)
        self._anim.finished.connect(_done)

    # ── 绘制 ──────────────────────────────────────────────────────────────
    def paintEvent(self, e):
        sk = T.states(self._island.sk())
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        alpha = int(250 * max(0.0, min(1.0, self._a)))
        if alpha <= 0:
            p.end()
            return
        r = T.clamp_r(T.R["overlay"], rect.height(), rect.width())
        base = QColor(T.c(sk, "card"))
        base.setAlpha(alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(base)
        p.drawRoundedRect(rect, r, r)
        # 左边一根主色条：形状之外再多一路"这是灵动岛说的话"的标识
        bar = QColor(T.c(sk, "accent"))
        bar.setAlpha(alpha)
        p.setBrush(bar)
        p.drawRect(0, 0, BAR_W, rect.height())
        ink = QColor(T.c(sk, "text"))
        ink.setAlpha(alpha)
        p.setPen(ink)
        p.setFont(T.font(11))
        fm = QFontMetricsF(p.font())
        body_w = rect.width() - BAR_W - 2 * PAD_X
        act_w = 0
        if self._action:
            act_w = int(fm.boundingRect(self._action[0]).width()) + 4
            body_w -= act_w + PAD_X
        txt = fm.elidedText(self._text, Qt.ElideRight, body_w)
        p.drawText(QRect(BAR_W + PAD_X, 0, body_w, rect.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, txt)
        self._act_rect = QRect()
        if self._action:
            ax = rect.right() - PAD_X - act_w
            self._act_rect = QRect(ax - 4, 0, act_w + 8, rect.height())
            p.setPen(QColor(T.c(sk, "accent")))
            p.drawText(QRect(ax, 0, act_w, rect.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self._action[0])
        p.end()

    def text(self):
        """自检用：当前正在提示的内容（已按宽度省略的就是看到的）"""
        return self._text
