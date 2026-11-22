# -*- coding: utf-8 -*-
"""应用层 · 页面共用控件（选择菜单/按钮、待办委托、勾选图标）"""
from PyQt5.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap)
from PyQt5.QtWidgets import (QApplication, QFrame, QMenu, QPushButton, QSizePolicy, QStyle, QStyleOptionViewItem, QStyledItemDelegate, QWidget)
from ..infra.timeutil import REPEAT_ALL
from ..infra.svgpath import load_asset, scaled_into
from ..core import theme as T


CHECK_SIZE = 16          # 待办勾选框边长
ROW_PAD = 0              # 行内容贴卡片内缘（卡片 1px 框 + 2px padding 已把整行推到输入框同一轴上）
PIN_HIT_W = 26           # 剪贴板行尾钉子热区宽（比图案宽，好点）
PIN_GLYPH = 14.0         # 图钉最长边（1.4.13 换成 SVG 图标后从 12 提到 14，
                          # 图标本身比原来那三笔细，12px 上实心只有 21 个像素）
PIN_ROLE = Qt.UserRole + 1   # 行是否已固定（委托只读这个位，不读文案里的符号）
PIN_ASSET = "pushpin.svg"    # 用户给的图钉素材（斜 30°），顶栏与剪贴板行尾共用
PIN_STROKE = 1.3             # 未固定态描边粗细（12px 图标上 1.3px 刚好不断线）


def flatten_card_frame(view):
    """卡片列表统一压掉原生 5px 框+阴影，边框只由 QSS 画 1px。
    配合 styles.py 的 #card padding:2px，行内容与同页输入框左右对齐。"""
    view.setFrameShape(QFrame.NoFrame)
    view.setFrameShadow(QFrame.Plain)
    return view


def tick_pixmap(color, size=14, width=None):
    """用 QPainter 画一个对号图标：位图缩放会发虚，矢量在任意 DPR 下都干净"""
    pm = QPixmap(int(size), int(size))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(width if width else max(1.6, size * 0.155))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(size * 0.17, size * 0.525)
    path.lineTo(size * 0.415, size * 0.765)
    path.lineTo(size * 0.835, size * 0.255)
    p.drawPath(path)
    p.end()
    return pm


class ChoiceMenu(QMenu):
    """替代 QComboBox 的选项菜单

    QComboBox 的弹出层宽度会被 QStyle 与屏幕边界二次收窄，麒麟 UKUI 上
    「不重复 / 工作日 / 每周一」这类长项一律被裁。QMenu 的尺寸由 sizeHint
    决定，自己按字体度量算最小宽度最稳，也不受 style 影响。
    """

    def __init__(self, items, current=None, sk=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        sk = sk or T.skin("deep")
        self._tick = QIcon(tick_pixmap(sk["accent"], 13, 1.9))
        blank = QPixmap(13, 13)
        blank.fill(Qt.transparent)
        self._blank = QIcon(blank)
        self._need_w = 0
        fm = self.fontMetrics()
        for label, data in items:
            a = self.addAction(label)
            a.setData(data)
            a.setIcon(self._tick if data == current else self._blank)
            self._need_w = max(self._need_w, fm.boundingRect(label).width())

    def mark(self, current):
        for a in self.actions():
            a.setIcon(self._tick if a.data() == current else self._blank)

    def sizeHint(self):
        s = super().sizeHint()
        # 文本宽 + 对号列 + 左右内边距（与 QSS 的 padding 对齐）
        return QSize(max(s.width(), self._need_w + 62), s.height())


class ChoiceButton(QPushButton):
    """一个显示当前值、点开 ChoiceMenu 的按钮（对外接口保持 currentData/setCurrentData）"""

    changed = pyqtSignal(object)

    def __init__(self, items=(), value=None, sk_getter=None, parent=None, tooltip=""):
        super().__init__(parent)
        self._items = list(items)
        self._value = self._items[0][1] if (self._items and value is None) else value
        self._sk_getter = sk_getter or (lambda: T.skin("deep"))
        self.setProperty("kind", "choice")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if tooltip:
            self.setToolTip(tooltip)
        self.clicked.connect(self.popup)
        self._fit()

    def currentData(self):
        return self._value

    def setCurrentData(self, value):
        self._value = value
        self._fit()

    def set_items(self, items):
        self._items = list(items)
        self._fit()

    def label_of(self, value):
        for label, data in self._items:
            if data == value:
                return label
        return self._items[0][0] if self._items else ""

    def _fit(self):
        fm = self.fontMetrics()
        w = max([fm.boundingRect(l).width() for l, _ in self._items] or [18])
        self.setText("%s  ▾" % self.label_of(self._value))
        self.setMinimumWidth(w + 40)
        self.updateGeometry()

    def popup(self):
        if not self._items:
            return
        m = ChoiceMenu(self._items, self._value, self._sk_getter(), self)
        act = m.exec_(self.mapToGlobal(QPoint(0, self.height() + 3)))
        if act is None:
            return
        value = act.data()
        if value != self._value:
            self._value = value
            self._fit()
            self.changed.emit(value)


META_ROLE = Qt.UserRole + 1


def repeat_options():
    """重复规则选项（掩码与 store.REPEAT_ALL 的位定义一致）"""
    opts = [("不重复", 0), ("每天", REPEAT_ALL), ("工作日", 0b0011111)]
    for i, name in enumerate(["周一", "周二", "周三", "周四", "周五", "周六", "周日"]):
        opts.append(("每" + name, 1 << i))
    return opts


class TodoDelegate(QStyledItemDelegate):
    """待办行：勾选框与文字全部自绘

    1.0.3 之前靠 QSS 画 indicator、delegate 再补一层对号，两套逻辑叠在一起，
    对号位置跟着 style 的 indicator 矩形走，出现歪斜、压边框；日期矩形的宽度
    `meta_w - 8` 也比实际文本窄，长日期被裁掉尾巴。这里一律自绘：
    勾选框固定在行首 16×16，日期按墨迹宽度精确右对齐，正文优先省略。
    """

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        s.setWidth(0)  # 不让长文本把列表撑出横向滚动条
        s.setHeight(max(26, s.height()))
        return s

    def editorEvent(self, event, model, option, index):
        """勾选热区按自绘方框判定（style 的指示器矩形与自绘框错位约 12px）"""
        if (event.type() == QEvent.MouseButtonRelease
                and index.flags() & Qt.ItemIsUserCheckable):
            r = option.rect
            box = QRectF(r.left() + ROW_PAD, r.center().y() - CHECK_SIZE / 2.0,
                         CHECK_SIZE, CHECK_SIZE)
            if box.contains(QPointF(event.pos())):
                checked = index.data(Qt.CheckStateRole) == Qt.Checked
                model.setData(index, Qt.Unchecked if checked else Qt.Checked,
                              Qt.CheckStateRole)
                return True
        return super().editorEvent(event, model, option, index)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text or ""
        meta = index.data(META_ROLE) or ""
        checked = index.data(Qt.CheckStateRole) == Qt.Checked
        opt.text = ""
        # 关掉 style 自带的勾选指示器，避免和自绘的方框重影
        opt.features &= ~QStyleOptionViewItem.HasCheckIndicator
        opt.state &= ~QStyle.State_HasFocus

        w = opt.widget
        style = w.style() if w is not None else QApplication.style()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        if checked:
            painter.setOpacity(0.6)      # 已完成沉底行整行降透明度（1.4.4）
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, w)   # 只画底色/选中态
        painter.setClipRect(opt.rect)

        sk = self.host.sk()
        r = QRectF(opt.rect)
        box = QRectF(r.left() + ROW_PAD, r.center().y() - CHECK_SIZE / 2.0,
                     CHECK_SIZE, CHECK_SIZE)
        self._checkbox(painter, box, checked, sk)

        f = QFont(opt.font)
        f.setStrikeOut(checked)
        painter.setFont(f)
        fm = QFontMetrics(f)

        right = r.right() - ROW_PAD
        body_left = box.right() + 8.0
        meta_w = fm.boundingRect(meta).width() if meta else 0
        if meta:
            painter.setPen(T.c(sk, "text3"))
            painter.drawText(QRectF(right - meta_w, r.top(), meta_w, r.height()),
                             int(Qt.AlignRight | Qt.AlignVCenter), meta)
            body_right = right - meta_w - 9.0
        else:
            body_right = right

        if opt.state & QStyle.State_Selected:
            color = T.c(sk, "accent")
        elif checked:
            color = T.c(sk, "text3")
        else:
            color = T.c(sk, "text")
        painter.setPen(color)
        body = QRectF(body_left, r.top(), max(0.0, body_right - body_left), r.height())
        if body.width() > 4:
            painter.drawText(body, int(Qt.AlignLeft | Qt.AlignVCenter),
                             fm.elidedText(text, Qt.ElideRight, int(body.width())))
        painter.restore()

    @staticmethod
    def _checkbox(p, box, checked, sk):
        """圆角方块 + 圆头折线对号，尺寸固定不受 style 影响"""
        if checked:
            p.setPen(Qt.NoPen)
            p.setBrush(T.c(sk, "accent"))
            p.drawRoundedRect(box, 4.5, 4.5)
            pen = QPen(T.ink_over(T.c(sk, "accent"), sk))
            pen.setWidthF(1.75)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(box.left() + box.width() * 0.195, box.top() + box.height() * 0.510)
            path.lineTo(box.left() + box.width() * 0.405, box.top() + box.height() * 0.725)
            path.lineTo(box.left() + box.width() * 0.780, box.top() + box.height() * 0.255)
            p.drawPath(path)
        else:
            pen = QPen(T.c(T.states(sk), "line_strong"))
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.setBrush(T.c(sk, "card"))
            p.drawRoundedRect(box.adjusted(0.6, 0.6, -0.6, -0.6), 4.5, 4.5)


class ClipPinDelegate(QStyledItemDelegate):
    """剪贴板行尾的小钉子（1.4.10）

    正文和钉子都在 paint 里按 option.rect 现算——不能在 refresh 里预先 elide：
    那时视口宽可能还没落定（岛刚展开、皮肤刚换、offscreen 自检里都撞到过），
    按旧宽切出来的字符串会一路带到下一次 refresh，长文案就会压在钉子上面。
    1.4.10 之前正是这个坑：refresh 里 `avail - (14 if pinned else 0)` 只有固定行
    才留 14px，未固定行本来就会被钉子压住尾字。

    钉子是用户给的图钉图标（assets/pushpin.svg，1.4.13 起走 infra/svgpath 解析成
    矢量路径），墨色 T.pin_ink：深色皮肤纯白、浅色皮肤正文墨。固定态实心、未固定
    描边——状态靠填充区分，不往文案里塞符号，读屏取到的仍是原文。

    点钉子＝切固定，且不能和「点行复制」撞车：委托比视图先收到事件，命中热区
    后返回 True 把事件吃掉，itemClicked 就不会再发。
    """

    pinToggled = pyqtSignal(int)      # 参数：clip 行 id
    TEXT_PAD_L = 6.0                  # 正文左内缘（与待办行同一口径）
    TEXT_PAD_R = 6.0                  # 正文与钉子热区之间的间隙

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        s.setWidth(0)                 # 长文本不许把列表撑出横向滚动条
        s.setHeight(max(26, s.height()))
        return s

    @staticmethod
    def pin_rect(row_rect):
        """热区取整行高、右侧 PIN_HIT_W 宽——图案只有 12px，但别指望人瞄 12px"""
        return QRectF(float(row_rect.right()) - ROW_PAD - PIN_HIT_W,
                      float(row_rect.top()), float(PIN_HIT_W),
                      float(row_rect.height()))

    @classmethod
    def text_rect(cls, row_rect):
        """正文可用宽 = 行宽 − 左内缘 − 热区 − 间隙（每行都扣，不再看固定与否）"""
        r = QRectF(row_rect)
        w = r.width() - cls.TEXT_PAD_L - PIN_HIT_W - cls.TEXT_PAD_R
        return QRectF(r.left() + cls.TEXT_PAD_L, r.top(), max(0.0, w), r.height())

    def elided(self, text, fm, row_rect):
        """给自检用的同一套 elide（paint 里也走它，避免两处口径分叉）"""
        return fm.elidedText(text, Qt.ElideRight, int(self.text_rect(row_rect).width()))

    def editorEvent(self, event, model, option, index):
        if (event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.LeftButton
                and self.pin_rect(option.rect).contains(QPointF(event.pos()))):
            payload = index.data(Qt.UserRole)
            if payload:
                self.pinToggled.emit(int(payload[0]))
                return True
        return super().editorEvent(event, model, option, index)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = (opt.text or "").replace("\n", " ")
        opt.text = ""
        opt.state &= ~QStyle.State_HasFocus
        w = opt.widget
        style = w.style() if w is not None else QApplication.style()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, w)   # 只画底色/选中态
        painter.setClipRect(opt.rect)
        sk = self.host.sk()
        f = QFont(opt.font)
        painter.setFont(f)
        fm = QFontMetrics(f)
        body = self.text_rect(opt.rect)
        painter.setPen(T.c(sk, "accent") if (opt.state & QStyle.State_Selected)
                       else T.c(sk, "text"))
        if body.width() > 4:
            painter.drawText(body, int(Qt.AlignLeft | Qt.AlignVCenter),
                             fm.elidedText(text, Qt.ElideRight, int(body.width())))
        self._pin(painter, self.pin_rect(opt.rect), bool(index.data(PIN_ROLE)), sk)
        painter.restore()

    def _pin(self, painter, box, pinned, sk):
        # 1.4.13：用户给的图钉图标 + 白墨（原来未固定用 line 描边，在 card 上对比
        # 只有 1.1，等于看不见）。状态仍靠填充区分：固定实心、未固定描边。
        paint_pin(painter, box, pinned, T.pin_ink(sk))


def paint_pin(painter, box, filled, ink, size=PIN_GLYPH):
    """画用户给的那枚图钉图标（resources/assets/pushpin.svg，斜 30°、针尖朝左下）。

    1.4.13 起顶栏和剪贴板行尾都换成这枚图标，而且两处必须走同一份路径——图标是用户
    直接给的素材，不能再各画各的。机上的 PyQt5 没有 QtSvg（`import PyQt5.QtSvg`
    直接 ModuleNotFoundError），QIcon 也认不了 .svg，所以由 infra/svgpath.py 把
    `d` 与 `transform` 解析成 QPainterPath：矢量、随 DPR 缩放，颜色完全由调用方给
    的 ink 决定（素材里那句 fill="currentColor" 就是"颜色你说了算"的意思）。

    filled=True 实心（已钉住/已固定），False 描边（未钉住）；两态同形同位，只换填充。
    """
    src, vb = load_asset(PIN_ASSET)
    path = scaled_into(src, vb, box, size)
    if filled:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(ink))
    else:
        pen = QPen(ink)
        pen.setWidthF(PIN_STROKE)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)


class PinGlyphButton(QPushButton):
    """顶栏右上角的「常驻展开」按钮（1.4.11，1.4.13 换图标与配色）。

    原来这里是一个「钉」字，按用户口径换成小钉子图案；图案本身现在直接用用户给的
    pushpin.svg，与剪贴板行尾同一份路径、同一个墨色。
    底色/描边仍归 QSS 画：先 super().paintEvent() 再自绘，状态反馈不用自己重写。
    钉住态的样式加了 [pin="true"] 这条规则——不再铺整块 accent 底（白钉压 accent
    只有 1.94 对比），改成卡片底 + accent 描边环，于是两态都能用同一支白墨。
    """

    GLYPH = 16.0             # 最长边 16：顶栏比行尾大 2px（按钮 26×24 装得下），
                             # 同一枚图标、同一个墨色，只是尺寸一档
                             # 剪贴板行尾仍是 PIN_GLYPH=14，行高只有 26
    W, H = 26, 24            # 26 = PIN_HIT_W，比原来的 21 宽 5px，好点

    def __init__(self, sk_provider, parent=None):
        super().__init__("", parent)
        self.sk_provider = sk_provider
        self.setProperty("pin", "true")      # 让 styles.py 那条钉住规则生效
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("常驻展开开关（小钉子）")

    def paintEvent(self, e):
        super().paintEvent(e)                      # QSS 的胶囊底先画
        sk = self.sk_provider()
        on = self.isChecked()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        paint_pin(p, QRectF(0.0, 0.0, float(self.width()), float(self.height())),
                  on, T.pin_ink(sk), self.GLYPH)
        p.end()


class ToggleSwitch(QWidget):
    """自绘开关（设置页的布尔项）。

    第三方开关库（pyqt5Custom 的 ToggleSwitch 等）是 GPL-3.0，且色值写死在
    构造函数里（win10 风格就写死了一组不透明的蓝），换八套皮肤必然糊成一片；
    它的动画还用 time.time() 墙钟 + 固定 speed 在重绘里推，不吃时长 token。
    这里四十行自绘：轨道/滑块颜色全从当前皮肤取，尺寸落在 4px 格点，位移走
    theme.animate，所以设置页的「动效」总开关对它同样有效。"""

    W = 40                     # 4px 格点：轨道 40×20
    H = 20
    PAD = 4                    # 滑块离轨道端的净距
    KNOB = 12                  # 滑块直径 = H - 2*PAD，行程 = W - 2*PAD - KNOB = 20

    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, label="", sk_provider=None, parent=None):
        super().__init__(parent)
        self._on = bool(checked)
        self._p = 1.0 if self._on else 0.0        # 动画驱动的位移比例
        self._anim = None
        self._sk_provider = sk_provider
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setAccessibleName(label or "开关")
        self._sync_accessibility()

    # ── 值 ────────────────────────────────────────────────────────────────
    def skin(self):
        return self._sk_provider() if self._sk_provider else T.skin("deep")

    def isChecked(self):
        return self._on

    def setChecked(self, on):
        """外部设值不触发 toggled，语义与 QCheckBox 一致"""
        if bool(on) != self._on:
            self._flip(bool(on), emit=False)

    def _flip(self, on, emit=True):
        self._on = bool(on)
        self._sync_accessibility()
        if self._anim is not None:
            self._anim.stop()
        self._anim = T.animate(self, "_p", self._p, float(self._on),
                               T.DUR["fast"], "inout", self)
        self._anim.finished.connect(lambda: setattr(self, "_anim", None))
        if emit:
            self.toggled.emit(self._on)

    def _sync_accessibility(self):
        # 读屏念「每日晨报 已开启」就够了，不靠颜色表达状态
        self.setAccessibleDescription("已开启" if self._on else "已关闭")

    # ── 交互 ──────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.setFocus()
            self._flip(not self._on)
            e.accept()
            return
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._flip(not self._on)
            e.accept()
        else:
            super().keyPressEvent(e)

    # ── 绘制 ──────────────────────────────────────────────────────────────
    def _knob_rect(self):
        return QRectF(self.PAD + self._p * (self.W - 2 * self.PAD - self.KNOB),
                      (self.H - self.KNOB) / 2.0, self.KNOB, self.KNOB)

    def paintEvent(self, e):
        sk = T.states(self.skin())
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        inset = 2.0 if self.hasFocus() else 0.0
        if inset:
            # 焦点框只画在外圈：麒麟无合成器，靠 QGraphicsEffect 画不出稳定高亮
            pen = QPen(T.c(sk, "text2"))
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.6, 0.6, self.W - 1.2, self.H - 1.2),
                              T.clamp_r(self.H / 2.0, self.H - 1.2), 
                              T.clamp_r(self.H / 2.0, self.H - 1.2))
        track = QRectF(inset, inset, self.W - 2 * inset, self.H - 2 * inset)
        r = T.clamp_r(self.H / 2.0, track.height())
        p.setPen(Qt.NoPen)
        p.setBrush(T.c(sk, "accent") if self._on else T.c(sk, "line_strong"))
        p.drawRoundedRect(track, r, r)
        # 滑块取轨道上的对比墨色：亮皮走到深、暗皮走到浅，不写死白
        p.setBrush(T.ink_over(T.c(sk, "accent") if self._on
                              else T.c(sk, "line_strong"), sk))
        kr = self._knob_rect()
        p.drawEllipse(kr)
        p.end()
