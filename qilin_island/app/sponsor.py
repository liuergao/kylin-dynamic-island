# -*- coding: utf-8 -*-
"""麒麟应用站 · 客户端公共组件：联系我们 / 赞助作者

二维码以 base64 内嵌，不依赖外部文件，离线、PyInstaller 打包、deb 安装都不会丢。

用法（三个应用通用）：
    import sponsor                     # fuyu 包内用 from . import sponsor
    sponsor.open_sponsor(self)         # 弹出赞助二维码
    sponsor.open_contact(self)         # 弹出联系方式（QQ）
    lbl = sponsor.LinkLabel("赞助", self)
    lbl.clicked.connect(lambda: sponsor.open_sponsor(self))
"""
import base64

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                             QLayout, QPushButton, QVBoxLayout)

from ..core import theme as T
from ..core.styles import card_qss
from ..infra.store import Store

QQ = "1849475563"
AUTHOR = "刘*浩"          # 收款实名（部分隐藏），与官网口径一致
SITE = "qilinapp.cn"

_QR_B64 = (
"iVBORw0KGgoAAAANSUhEUgAAASQAAAEkCAMAAACxJ7zeAAADAFBMVEX////a2trQ0NCZmZleXl4yMjINDQ0AAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAADKr86uAAALdElEQVR42u2d64KqOgyFpRd8/zfeJG0BHWlWcBT2sPLjbMdRhM80zWUx53aj0Wg0"
"Go1Go9FoNBqNRqPR3rB7x5DXrp/3fsbza6zPWb9u6/Oez2vPdRISIRHSsZCs560DvQLWg/zqxLc+59VxLVBb7/dcPyEREiEd"
"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"
"NFrH/gHRLqLQOtOenAAAAABJRU5ErkJggg=="
)

_qr_cache = None
QR_WIDTH = 292          # 内嵌图宽度 = 65 个模块 ×4px + 4 模块静区 ×4px


def qr_pixmap(size=None):
    """内嵌二维码 → QPixmap

    图本身是按「每模块 4 像素」出的整数倍位图，**不要再做非整数缩放**：
    65 个模块塞进 200px 时每模块只有 2.6px，四舍五入后有的 2px 有的 3px，
    画出来糊成一团、扫不出来。需要更大就按整数倍放大，用最近邻，模块边缘才干净。
    """
    global _qr_cache
    if _qr_cache is None:
        pm = QPixmap()
        try:
            pm.loadFromData(base64.b64decode(_QR_B64), "PNG")
        except Exception:
            pass
        _qr_cache = pm
    if _qr_cache is None or _qr_cache.isNull():
        return QPixmap()
    if size is None:
        return _qr_cache
    ratio = max(1, int(round(float(size) / _qr_cache.width())))
    w = _qr_cache.width() * ratio
    return _qr_cache.scaled(w, w, Qt.KeepAspectRatio, Qt.FastTransformation)


def skin_for(widget=None):
    """卡片弹窗的皮肤：沿父链问岛体要，问不到（关于框就没父窗）就直接读盘"""
    w = widget
    while w is not None:
        store = getattr(w, "store", None)
        if store is not None:
            return T.skin(store.settings.get("skin", "deep"))
        w = getattr(w, "parentWidget", lambda: None)()
    return T.skin(Store().settings.get("skin", "deep"))



class _Card(QDialog):
    """统一的卡片弹窗基类：配色随皮肤，字号排印固定"""

    def __init__(self, parent, title_text):
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.setStyleSheet(card_qss(skin_for(parent)))
        self.setFixedWidth(366)
        # 宿主本身「总在最前」时（灵动岛胶囊就是这种窗口），普通子对话框会被压在
        # 宿主下面，卡片顶部的标题、副标题正好被遮住。让卡片跟着一起置顶即可。
        if parent is not None and (parent.windowFlags() & Qt.WindowStaysOnTopHint):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(22, 20, 22, 18)
        self.lay.setSpacing(0)
        # 让窗口最小尺寸 = 布局最小尺寸：否则一旦被压小，二维码这种钉死尺寸的
        # 控件会溢出自己的格子、压在下面的文字上
        self.lay.setSizeConstraint(QLayout.SetMinimumSize)

    def add_title(self, text):
        t = QLabel(text)
        t.setObjectName("t1")
        self.lay.addWidget(t)
        return t

    def add_sub(self, text, gap=6):
        s = QLabel(text)
        s.setObjectName("t2")
        s.setWordWrap(True)
        self.lay.addSpacing(gap)
        self.lay.addWidget(s)
        return s

    def add_gap(self, h=12):
        self.lay.addSpacing(h)

    def add_para(self, text, obj_name="word", gap=0):
        """自动换行的段落：固定宽度 + 按 heightForWidth 钉死高度

        wordWrap 的 QLabel 只报「不换行时的」sizeHint，布局先按它排位置，
        等文字真换行了就压到后面的控件上（二维码下面那三行就是这么被压住的）。
        这里自己把高度算出来钉死，一次排对。
        """
        if gap:
            self.lay.addSpacing(gap)
        lbl = QLabel(text)
        lbl.setObjectName(obj_name)
        lbl.setWordWrap(True)
        m = self.lay.contentsMargins()
        w = self.width() - m.left() - m.right()
        lbl.setFixedWidth(w)
        h = lbl.heightForWidth(w)
        if h > 0:
            lbl.setFixedHeight(h)
        self.lay.addWidget(lbl)
        return lbl

    def add_buttons(self, *specs):
        """specs: (文字, 槽函数, 是否主按钮)"""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addStretch(1)
        for text, slot, primary in specs:
            b = QPushButton(text)
            if primary:
                b.setProperty("kind", "primary")
            b.setCursor(Qt.PointingHandCursor)
            if slot is not None:
                b.clicked.connect(slot)
            row.addWidget(b)
        self.add_gap(16)
        self.lay.addLayout(row)


CardDialog = _Card        # 对外别名


class SponsorDialog(_Card):
    """赞助二维码弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent, "赞助作者")
        self.add_title("请作者喝杯咖啡")
        self.add_sub("这些软件，是一个人下班后一点点磨出来的")

        self.add_gap(14)
        pic = QLabel()
        pic.setAlignment(Qt.AlignCenter)
        pm = qr_pixmap()
        if pm.isNull():
            pic.setText("二维码加载失败")
        else:
            pic.setPixmap(pm)
            # QLabel 装不下时会直接把位图裁掉下半截（不会自己把最小高度报给布局），
            # 必须钉死尺寸，否则二维码只显示上面一截 —— 这就是「没显示全」的根因
            pic.setFixedSize(pm.size())
            pic.setToolTip("微信 / 支付宝 扫码")
        self.lay.addWidget(pic)

        self.add_para(
            "· 全部软件免费、无广告、不收集数据，装完就能一直用。\n"
            "· 如果它替你省下了时间，可以扫码请我喝杯咖啡，金额随意，一块也是心意。\n"
            "· 不打赏也照旧用，功能一个都不会少，更新也不会停。",
            "word", gap=14)

        self.add_gap(12)
        ident = QLabel("✓ 收款身份 %s · 本站作者本人" % AUTHOR)
        ident.setObjectName("ident")
        ident.setAlignment(Qt.AlignCenter)
        self.lay.addWidget(ident)

        self.add_para(
            "付款页显示的名字若与此不一致，请立即停止支付并联系作者核对。",
            "note", gap=8)

        self.add_buttons(("关闭", self.accept, False))
        self.adjustSize()


class ContactDialog(_Card):
    """联系我们：QQ"""

    def __init__(self, parent=None):
        super().__init__(parent, "联系我们")
        self.add_title("联系我们")
        self.add_sub("有问题、建议或 bug 反馈，直接找我，能回的都回。")

        self.add_gap(16)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        tag = QLabel("QQ")
        tag.setObjectName("t2")
        num = QLabel(QQ)
        num.setObjectName("qq")
        num.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(tag)
        row.addSpacing(2)
        row.addWidget(num)
        row.addStretch(1)
        self.lay.addLayout(row)

        self.add_gap(10)
        tip = QLabel("加好友时说明一下是哪个软件的用户（文件管理 / 工具箱 / 灵动岛），"
                     "方便我快速定位问题。")
        tip.setObjectName("note")
        tip.setWordWrap(True)
        self.lay.addWidget(tip)

        self.add_gap(14)
        self.hint = QLabel("")
        self.hint.setObjectName("note")
        self.lay.addWidget(self.hint)

        self.add_buttons(("复制 QQ 号", self.copy_qq, True),
                         ("赞助作者", self.open_sponsor, False),
                         ("关闭", self.accept, False))

    def copy_qq(self):
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(QQ)
        self.hint.setText("QQ 号 %s 已复制到剪贴板" % QQ)

    def open_sponsor(self):
        SponsorDialog(self.parent()).exec_()


class LinkLabel(QLabel):
    """可点击的文字（右下角「赞助」用），保留 QLabel 的全部能力"""

    clicked = pyqtSignal()

    def __init__(self, text="赞助", parent=None, color=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("支持一下作者")
        if color:
            self.setStyleSheet("color:%s;" % color)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


def open_sponsor(parent=None):
    return SponsorDialog(parent).exec_()


def open_contact(parent=None):
    return ContactDialog(parent).exec_()
