# -*- coding: utf-8 -*-
"""应用层 · M5 托盘与可见性

托盘菜单、隐藏横线、任务栏规避。托盘不可用时（无系统托盘）仍能靠快捷键和二次启动唤起。"""
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu, QSystemTrayIcon
from ..core import brand
from ..platform import x11
from ..core import theme as T


class TrayMixin:
    def tray_init(self):
        self.tray = None

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(brand.logo_pixmap(32, simple=True)), self)
        self.tray.setToolTip("%s · 后台运行中" % T.APP_NAME)
        m = QMenu()
        # 1.2.9：隐藏不再是「面板不见」，而是收成一条横线，右键这里就是那个开关
        self.m_hide = m.addAction("隐藏成横线")
        self.m_hide.triggered.connect(self.toggle_hidden)
        a_reveal = m.addAction("显示面板")
        a_reveal.triggered.connect(self.reveal)
        a_settings = m.addAction("设置…")
        a_settings.triggered.connect(self.open_settings)
        a_about = m.addAction("关于")
        a_about.triggered.connect(self.open_about)
        a_contact = m.addAction("联系我们…")
        a_contact.triggered.connect(self.open_contact)
        a_sponsor = m.addAction("赞助作者…")
        a_sponsor.triggered.connect(self.open_sponsor)
        a_recenter = m.addAction("回到屏幕正中")
        a_recenter.triggered.connect(self.recenter)
        m.addSeparator()
        a_quit = m.addAction("退出")
        a_quit.triggered.connect(self.quit)
        m.aboutToShow.connect(self._sync_tray_menu)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(
            lambda r: self.reveal()
            if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()

    def _sync_tray_menu(self):
        if hasattr(self, "m_hide"):
            self.m_hide.setText("取消隐藏" if self._hidden else "隐藏成横线")

    def toggle_hidden(self):
        """托盘右键的隐藏开关：折叠胶囊 ↔ 隐藏横线"""
        self.set_hidden(not self._hidden)

    def skip_taskbar(self):
        """让窗口不出现在底栏/任务栏：用 WM 的 skip_taskbar 状态，失败静默"""
        try:
            wid = int(self.winId())
        except Exception:
            return
        x11.skip_taskbar(wid)

    def prepare_taskbar(self):
        """必须在 show() 之前调用：把窗口类型改成只保留 UTILITY，UKUI 底栏才不占位"""
        try:
            wid = int(self.winId())      # 建原生窗口，但还不 map
        except Exception:
            return False
        return x11.set_utility_type(wid)
