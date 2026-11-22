# -*- coding: utf-8 -*-
"""交付层 · M15 启动流程

顺序固定且不能调换：建 QApplication → 单实例探测 → 文件锁 → 图标 →
建岛 → 起唤醒通道 → 改窗口类型（必须在 show 之前）→ 显示。"""
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from ..core import brand
from ..meta import APP_ID, APP_NAME
from ..services import ipc
from .island import Island


def main(argv=None):
    argv = list(argv or sys.argv)
    app = QApplication(argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    want_quit = "--quit" in argv
    if ipc.send_to_instance(b"quit" if want_quit else b"show"):
        # 已有实例在后台：命令交给它，本进程直接退出
        return 0
    if want_quit:
        return 0

    lock = ipc.acquire_lock()
    if lock is None:
        print("麒麟灵动岛已在运行")
        return 0

    app.setWindowIcon(QIcon(brand.logo_pixmap(64)))
    island = Island()
    island.start_ipc()
    island.prepare_taskbar()      # 必须在 show() 之前：底栏不占位
    island.show()
    island.raise_()
    # 双保险：再补一次 skip_taskbar 状态，兼容个别 WM
    QTimer.singleShot(1200, island.skip_taskbar)
    return app.exec_()
