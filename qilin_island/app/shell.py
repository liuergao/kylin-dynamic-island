# -*- coding: utf-8 -*-
"""应用层 · M5/M15 外壳：皮肤、通知、更新、自启、单实例、退出

岛体对外的门面（host）也在这一层：页面只调用这里约定的方法。"""
import re
from PyQt5.QtCore import QTimer, QUrl, Qt
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QSystemTrayIcon
from ..core import brand
from ..core import theme as T
from ..core.styles import global_qss
from ..services import autostart, clipboard, ipc
from . import sponsor
from .settings import SettingsDialog


class ShellMixin:
    def shell_init(self):
        """M5/M15 初始状态：退出标记、唤醒通道、动效总开关"""
        self._quitting = False
        self.server = None
        self.apply_motion()

    def apply_motion(self):
        """动效总开关落到 theme：关掉后 animate 只落终值不补中间帧，
        形变/进度环/轮播淡入都不用各自加分支，改完立刻生效不用重启。"""
        T.set_motion(bool(self.store.settings.get("motion", True)))

    def skin_name(self):
        return self.store.settings.get("skin", "deep")

    def sk(self):
        return T.skin(self.skin_name())

    def apply_skin(self):
        self.setStyleSheet(global_qss(self.sk()))
        for p in self.pages:
            if hasattr(p, "apply_skin"):
                p.apply_skin(self.sk())
        self.logo.update()
        if self.tray:
            self.tray.setIcon(QIcon(brand.logo_pixmap(32, simple=True)))
        self.update()

    def notify(self, title, body, ms=5000, action=None):
        """通知落地：岛体在屏幕上看得见，就用胶囊下方的 Toast（一定看得见）；
        隐藏态/不在屏上才交给系统托盘；托盘也没起来才改窗口标题，绝不静默丢弃。
        action=(label, callback) 只有 Toast 这条路支持（托盘消息点不了）。"""
        text = ("%s · %s" % (title, body)) if body else title
        tst = getattr(self, "toast", None)
        if tst is not None and self.isVisible() and not self._hidden:
            tst.show_text(text, ms, action)
            return
        if self.tray and self.tray.isVisible():
            try:
                self.tray.showMessage(title, body, QSystemTrayIcon.Information, ms)
                return
            except Exception:
                pass
        self.setWindowTitle("%s · %s" % (T.APP_NAME, title))

    def set_clipboard(self, text):
        text = clipboard.normalize(text)
        self._last_clip = text
        clipboard.write_text(text)

    def open_settings(self):
        self._settle_before_dialog()
        dlg = SettingsDialog(self)
        dlg.exec_()

    # 检查更新：点击才联网，失败静默降级
    UPDATE_URL = "https://qilinapp.cn/fuyu/version.json"

    @staticmethod
    def _ver_tuple(v):
        return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)

    def check_update(self, on_done):
        """on_done(text, url)：url 非空表示有新版本，可直接打开官网"""
        try:
            from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
        except Exception:
            on_done("当前环境不支持联网检查", None)
            return
        if getattr(self, "_upd_nm", None) is None:
            self._upd_nm = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(self.UPDATE_URL))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        reply = self._upd_nm.get(req)

        def _abort():
            try:
                reply.abort()
            except Exception:
                pass

        QTimer.singleShot(6000, _abort)           # 弱网超时兜底

        def done():
            raw = ""
            try:
                raw = bytes(reply.readAll()).decode("utf-8", "ignore").strip()
            except Exception:
                raw = ""
            self._apply_version_json(raw, on_done)
            reply.deleteLater()

        reply.finished.connect(done)

    def _apply_version_json(self, raw, on_done):
        """解析 version.json 文本并回调结果（纯逻辑，可单测）"""
        text, url = "检查失败：当前网络不可用", None
        try:
            info = {}
            if raw and raw.strip():
                import json as _json
                info = _json.loads(raw)
            remote = str(info.get("version") or "")
            url = str(info.get("url") or "https://qilinapp.cn")
            if remote:
                if self._ver_tuple(remote) > self._ver_tuple(T.VERSION):
                    text = "发现新版本 %s（当前 %s）" % (remote, T.VERSION)
                else:
                    text = "已是最新版本（%s）" % T.VERSION
                    url = None
            else:
                text, url = "检查失败：服务器无响应", None
        except Exception:
            text, url = "检查失败：更新信息格式错误", None
        try:
            on_done(text, url)
        except Exception:
            pass

    def open_contact(self):
        self._settle_before_dialog()
        sponsor.open_contact(self)

    def open_sponsor(self):
        self._settle_before_dialog()
        sponsor.open_sponsor(self)

    def open_about(self):
        self._settle_before_dialog()
        # 注意：不能用 QMessageBox —— 它会继承岛体的深色 QSS，出现"白底浅字"
        # 看不清。这里用自带配色、无父窗口的卡片弹窗，任何皮肤下都清晰。
        dlg = sponsor.CardDialog(None, "关于 %s" % T.APP_NAME)
        # 与设置、赞助卡片一致：跟着置顶，展开态下也不会被岛体压住
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dlg.add_title("%s %s" % (T.APP_NAME, T.VERSION))
        dlg.add_sub("麒麟 / 飞腾单机版桌面信息岛", gap=4)
        body = QLabel(
            "功能设计参考开源项目 Daozai（MIT License，© 2026 小唐的 Token and "
            "Daozai contributors）。本项目为独立实现，界面、标识与代码均为原创，"
            "未使用其任何素材。\n\n"
            "许可：本项目代码 MIT；内置 PyQt5 采用 GPLv3，对外分发需遵守其条款。\n\n"
            "运行环境：Python 3.8 + PyQt5 + Qt 5.12，完全离线，不依赖网络。")
        body.setObjectName("word")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # wordWrap 的 QLabel 不会自己把高度算给父布局，先钉死可用宽度，
        # 否则最后一行会被截掉半句
        _m = dlg.lay.contentsMargins()
        body.setFixedWidth(dlg.width() - _m.left() - _m.right())
        dlg.add_gap(12)
        dlg.lay.addWidget(body)

        upd_holder = {}

        def do_check():
            b = upd_holder.get("btn")
            if b is not None:
                b.setText("检查中…")
                b.setEnabled(False)

            def done(text, url):
                if b is not None:
                    b.setEnabled(True)
                    b.setText("发现新版！去官网" if url else "检查更新")
                self.notify("检查更新", text, 6000)
                if url:
                    QDesktopServices.openUrl(QUrl(url))

            self.check_update(done)

        dlg.add_buttons(("检查更新", do_check, False),
                        ("联系我们", lambda: sponsor.open_contact(dlg), False),
                        ("关闭", dlg.accept, False))
        upd_holder["btn"] = None
        dlg.adjustSize()
        # add_buttons 不返回按钮实例，从布局里找回来给回调改文案用
        for b in dlg.findChildren(QPushButton):
            if b.text() == "检查更新":
                upd_holder["btn"] = b
                break
        dlg.exec_()

    def set_autostart(self, on):
        autostart.set_enabled(on)

    def quit(self):
        self._quitting = True
        self.store.save()
        if self.tray:
            self.tray.hide()
        if self.server is not None:
            ipc.close_server(self.server)
        QApplication.quit()

    def closeEvent(self, e):
        tst = getattr(self, "toast", None)
        if tst is not None:
            tst.hide()                # 提示条是独立顶层窗，关窗时不能留在屏上
        self.store.save()
        if self._quitting:
            e.accept()
            return
        # 关窗 != 退出：收成一条横线，进程继续在托盘后台运行
        e.ignore()
        if self.tray is None:
            # 没有系统托盘时不留后台，否则用户再没入口把它叫回来
            self.collapse()
            return
        self.set_hidden(True)
        self._hint_background()

    def contextMenuEvent(self, e):
        """胶囊上右键：托盘不可见时的备用入口"""
        m = QMenu(self)
        m.addAction("设置…", self.open_settings)
        m.addAction("关于", self.open_about)
        m.addSeparator()
        m.addAction("隐藏成横线", lambda: self.set_hidden(True))
        m.addAction("退出", self.quit)
        m.exec_(e.globalPos())

    def _hint_background(self):
        if self.store.settings.get("bg_hint"):
            return
        self.store.settings["bg_hint"] = True
        self.store.save()
        self.notify("麒麟灵动岛已收成横线",
                    "鼠标划过屏幕顶部那条横线，或点托盘图标就能唤回面板；"
                    "要彻底结束，用托盘菜单或胶囊右键菜单里的「退出」。",
                    8000)

    def start_ipc(self):
        """单实例唤醒通道：托盘不可见时，再次启动程序靠它把面板唤回"""
        self.server = ipc.listen(self)
        self.server.newConnection.connect(self._ipc_new)

    def _ipc_new(self):
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda c=conn: self._ipc_read(c))
        conn.disconnected.connect(conn.deleteLater)

    def _ipc_read(self, conn):
        try:
            data = bytes(conn.readAll()).strip().decode("utf-8", "ignore")
        except Exception:
            data = ""
        if data == "quit":
            self.quit()
        else:
            self.reveal()          # 二次启动/快捷键：取消隐藏并把面板唤到眼前
