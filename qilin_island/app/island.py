# -*- coding: utf-8 -*-
"""应用层 · 岛体宿主（M1–M5 的装配点）

Island 只做三件事：把各模块装配成一个窗口、持有跨模块共享的根状态、
对外提供页面所用的 host 门面。绘制、几何、输入、让位、内容各自的实现
都在同名 Mixin 里，改行为请进对应模块，不要在这里加分支。

host 门面（页面可用的全部对外能力）：
    store / settings      配置与数据（M14）
    sk() / skin_name()    当前皮肤（M2）
    notify(t, b, ms)      通知（M5：托盘可用走托盘，否则岛内 Toast，都没有才改标题）
    refresh_badge()       胶囊徽标重算（M1）
    set_clipboard(text)   写剪贴板（M9）
    ext_drag(bool)        拖出文件期间冻结自动收起（M3）
    provider(name)        取某个能力的提供者（M6–M12 注册表）
"""
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QLabel,
                             QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ..core.content import ContentMixin
from ..core.dock import DockMixin
from ..core.form import FormMixin
from ..core.input import InputMixin
from ..core.pill import CarWidget, EqWidget, LogoLabel
from ..core.shape import ShapeMixin
from ..core.toast import Toast
from ..infra.store import Store
from ..modules import PAGE_CLASSES
from ..modules.widgets import PinGlyphButton
from ..core import theme as T
from .shell import ShellMixin
from .tray import TrayMixin


class Island(FormMixin, ShapeMixin, InputMixin, DockMixin, ContentMixin,
             TrayMixin, ShellMixin, QWidget):
    """胶囊 + 面板：唯一的顶层窗口"""

    def __init__(self, store=None):
        super().__init__(None)
        self.store = store or Store()
        # 各模块自己声明初始状态，顺序与依赖一致：先绘制路径，再形态、输入、让位
        self.shape_init()
        self.form_init()
        self.input_init()
        self.content_init()
        self.tray_init()
        self.shell_init()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool |
                            Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        if self.comp:
            self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowTitle(T.APP_NAME)
        self.toast = Toast(self)          # 通知兜底：托盘不可用时在胶囊下方提示

        self._build()
        self.apply_skin()
        self._place(collapsed=True)
        self._update_chips()      # 启动即填充轮播（否则前 2 秒空白，时间不显示）

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self._build_tray()
        self._update_header()
        self._watch_screen()
        QApplication.instance().installEventFilter(self)

    def _build(self):
        # 顶层不挂布局：布局的 sizeHint 会反过来 resize 窗口，把收起形态的
        # 精确尺寸（刘海 34 / 细线 6）顶掉。所有控件装进内层 body，岛体
        # 尺寸完全由 _place 控制，body 只负责跟随窗口大小。
        self.body = QWidget(self)
        self.body.setObjectName("body")
        root = QVBoxLayout(self.body)
        root.setContentsMargins(12, 7, 12, 10)
        root.setSpacing(4)

        head = QWidget()
        head.setObjectName("head")
        h = QHBoxLayout(head)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.logo = LogoLabel(self)
        self.clock = QLabel("--:--")
        self.clock.setObjectName("clock")
        self.chips = CarWidget(self, lead=h.spacing())
        self._car_pages = []              # [(segs, text)]
        self._car_pages_text = []         # 纯文本（测试/调试）
        self._car_idx = 0
        self._car_at = time.time()
        self._water_show_until = 0        # 「该喝水了」轮播展示截止
        self.chips.setObjectName("chips")
        self.eq = EqWidget(self)
        self.badge = QLabel("")
        self.badge.setObjectName("badge")
        self.focus_badge = QLabel("")
        self.focus_badge.setObjectName("focuspill")
        self.focus_badge.setVisible(False)
        self.btn_pin = PinGlyphButton(self.sk, self)   # 1.4.11：「钉」字换成小钉子图案
        self.btn_pin.setProperty("nav", "true")
        self.btn_pin.setToolTip("常驻展开")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(bool(self.store.settings.get("pinned")))
        # 图标固定在最左、按钮固定在右，中间整段留给轮播：
        # 文字由 CarWidget 自己按岛体中轴摆位，图标不参与居中、切页不跟着挪
        h.addWidget(self.logo)
        h.addWidget(self.clock)
        h.addWidget(self.chips, 1)
        h.addWidget(self.eq)
        h.addStretch(0)
        h.addWidget(self.badge)
        h.addWidget(self.focus_badge)
        h.addWidget(self.btn_pin)
        root.addWidget(head)
        self.head = head

        nav = QWidget()
        nav.setObjectName("nav")
        self.nav_row = QHBoxLayout(nav)
        self.nav_row.setContentsMargins(T.SP["s"], T.SP["s"],
                                        T.SP["s"], T.SP["s"])
        self.nav_row.setSpacing(T.SP["xs"])
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.stack = QStackedWidget()
        self.pages = []
        names = [c.title for c in PAGE_CLASSES]
        self.nav_row.addStretch(1)      # 左右等分：页签组整体落在面板中轴上
        for i in range(len(PAGE_CLASSES)):
            b = QPushButton(names[i])
            b.setProperty("nav", "true")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(b, i)
            self.nav_row.addWidget(b)
        self.nav_row.addStretch(1)
        root.addWidget(nav)
        self.nav = nav

        root.addWidget(self.stack, 1)
        self._build_pages()
        self.nav_group.buttonClicked[int].connect(self.goto)
        self.btn_pin.clicked.connect(self.toggle_pin)

    def _build_pages(self):
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        self.pages = []
        self.providers = {}
        for cls in PAGE_CLASSES:
            p = cls(self)
            self.stack.addWidget(p)
            self.pages.append(p)
            for cap in p.capabilities:          # 能力注册：胶囊与页面靠名字对接
                self.providers[cap] = p
        idx = min(int(self.store.settings.get("page", 0)), len(self.pages) - 1)
        self.goto(max(0, idx))

    def reload_pages(self):
        cur = self.current_index()
        self._build_pages()
        self.goto(cur)

    def current_index(self):
        return self.stack.currentIndex()

    def current_page(self):
        return self.stack.currentWidget()

    def provider(self, name):
        """按能力名取提供者；该页被关掉时返回 None，调用方须容忍"""
        return self.providers.get(name)

    def goto(self, idx):
        if not self.pages:
            return
        idx = max(0, min(idx, len(self.pages) - 1))
        old = self.stack.currentWidget()
        if old is not None and old is not self.pages[idx]:
            old.on_hide()
        self.stack.setCurrentIndex(idx)
        btn = self.nav_group.button(idx)
        if btn:
            btn.setChecked(True)
        self.store.settings["page"] = idx
        self.store.save()
        self.pages[idx].on_show()

    @property
    def settings(self):
        return self.store.settings

    def ext_drag(self, on):
        """文件中转站拖出文件期间冻结自动收起，松手后恢复"""
        self._ext_drag = bool(on)
