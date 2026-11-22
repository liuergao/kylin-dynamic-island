# -*- coding: utf-8 -*-
"""应用层 · 文件中转站（M13 中转站的可视部分）"""
import os
import time
from PyQt5.QtCore import QMimeData, QPoint, QUrl, Qt
from PyQt5.QtGui import QDesktopServices, QDrag, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout)
from .base import Page
from ..core.consts import CONTENT_PAD_X
from .widgets import flatten_card_frame
from ..services import system as SI


def _dbg(msg):
    """拖出链路调试日志（FUYU_DEBUG_LOG=/path 时才写，正常使用零开销）"""
    path = os.environ.get("FUYU_DEBUG_LOG")
    if not path:
        return
    try:
        with open(path, "a") as f:
            f.write("%.3f [drag] %s\n" % (time.time(), msg))
    except OSError:
        pass


class DropList(QListWidget):
    """接收文件拖放的列表；直接把路径交给所属页面。

    同时支持把条目拖出：按住条目拖到文件管理器/桌面即复制过去
    （QMimeData 带 file:// URL，startDrag 完全接管，不走内建 move）。

    真机实测（1.2.8）：peony 这类文件管理器对拖入文件默认提议的是
    MoveAction，源端只申报 CopyAction 时 XDND 谈不拢，对方全程亮
    「禁止」、松手即取消——表现为「怎么都拖不出去」。所以这里申报
    Copy|Move|Link 全套动作、默认 Copy，拖拽期间并冻结岛体自动收起。"""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.CopyAction)

    def file_mime(self, paths):
        """条目路径 → 拖出用 MimeData（独立方法，便于测试）"""
        ok = [p for p in paths if p and os.path.exists(p)]
        if not ok:
            return None
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(p) for p in ok])
        md.setText("\n".join(ok))   # text/plain 兜底：个别目标只认文本路径
        # 真机实测（1.2.8，XDND 协议追踪）：peony 这类基于 QAbstractItemView
        # 的文件管理器，视图若沿用 Qt 默认 dragEnterEvent，则其模型的
        # canDropMimeData 只放行 application/x-qabstractitemmodeldatalist
        # ——外部文件拖拽（只有 file:// URL）会被全程亮「禁止」拒收。
        # 补一份该格式让默认门放行；真正落盘目标端仍按 file:// URL 处理。
        try:
            model = QStandardItemModel(1, 1)
            model.setItem(0, 0, QStandardItem(os.path.basename(ok[0])))
            src = model.mimeData([model.index(0, 0)])
            if src is not None:
                for fmt in src.formats():
                    if fmt.startswith("application/x-"):
                        md.setData(fmt, src.data(fmt))
        except Exception:
            pass
        return md

    def _drag_pixmap(self):
        """条目虚影：拖出去时有「文件跟着走」的视觉反馈"""
        items = self.selectedItems()
        if not items:
            return None
        try:
            pm = self.viewport().grab(self.visualItemRect(items[0]))
            return None if pm.isNull() else pm
        except Exception:
            return None

    def startDrag(self, actions):
        paths = [it.data(Qt.UserRole) for it in self.selectedItems()
                 if it.data(Qt.UserRole)]
        self._ext_drag_exec(paths)

    def _ext_drag_exec(self, paths):
        """真正把文件拖出去（独立方法，便于测试与手工触发）"""
        md = self.file_mime(paths)
        if md is None:
            _dbg("ext-drag skip: no valid paths %r" % (paths,))
            try:
                self.page.notify("拖不出去", "条目文件已失效或不可读", 2500)
            except Exception:
                pass
            return None
        drag = QDrag(self)
        drag.setMimeData(md)
        pm = self._drag_pixmap()
        if pm is not None:
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(12, 8))
        host = getattr(self.page, "host", None)
        frozen = host is not None and hasattr(host, "ext_drag")
        if frozen:
            host.ext_drag(True)      # 拖拽期间冻结岛体自动收起
        _dbg("ext-drag exec paths=%r" % (paths,))
        try:
            # 全套动作申报 + 默认复制：文件管理器（peony 等）提议 Move/Link
            # 时才能谈拢；只报 Copy 会被对方拒绝，表现为「拖不出去」
            act = drag.exec_(Qt.CopyAction | Qt.MoveAction | Qt.LinkAction,
                             Qt.CopyAction)
        finally:
            if frozen:
                host.ext_drag(False)
        _dbg("ext-drag done act=%r" % (act,))
        return act

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.page.add(paths)
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()


class ShelfPage(Page):
    capabilities = ("shelf",)
    title = "文件中转站"

    def __init__(self, host):
        super().__init__(host)
        v = QVBoxLayout(self)
        # 1.4.14：水平边距 CONTENT_PAD_X(=0)——顶栏与列表跟页签卡同一条列缘
        v.setContentsMargins(CONTENT_PAD_X, 6, CONTENT_PAD_X, 10)
        v.setSpacing(6)
        # 顶栏（1.4.9）：第一行左「添加文件」右「清空」，第二行居中提示文案。
        # 原本想让文案夹在两个按钮中间同一行，按真机 QSS（muted 11px）量过算不过来：
        # 文案 20 字墨宽 220px，按钮 66 + 42 加两处间距 12 共 120px，同排只剩
        # 330−120=210px < 220px（三列网格实测中间列正是 210px），heightForWidth(210)
        # =36px 即折两行。故文案独占第二行，单行 18px、居中偏差 0.00px。
        # 1.4.14 内容列加宽到 354 后，同排剩 234px，比文案墨宽只多 14px（不到两个
        # 汉字宽），真机字体略宽就会挤成省略号——两行版式维持不动，自检那条守护改成
        # 按「同排余量 < 两字宽」算，余量真的大到能容错时它会 FAIL 提醒回来复评。
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.btn = QPushButton("添加文件")
        self.btn.setAccessibleName("添加文件到中转站")
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setAccessibleName("清空中转站全部条目")
        head.addWidget(self.btn, 0, Qt.AlignLeft)
        head.addStretch(1)
        head.addWidget(self.btn_clear, 0, Qt.AlignRight)
        v.addLayout(head)
        tip = QLabel("文件拖进来暂存，按住条目拖出到任意文件夹")
        tip.setObjectName("muted")
        tip.setAlignment(Qt.AlignCenter)
        tip.setWordWrap(True)
        tip.setAccessibleName("中转站用法提示")
        self.tip = tip
        v.addWidget(tip)
        self.list = DropList(self)
        self.list.setObjectName("card")
        flatten_card_frame(self.list)   # 与页面其他控件同一套边距（1.4.5）
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        v.addWidget(self.list, 1)
        self.btn.clicked.connect(self.pick)
        self.btn_clear.clicked.connect(self.clear_all)
        # 单击/双击不打开文件：拖入即暂存、按住拖出到任意文件夹；打开只走右键菜单
        self.list.customContextMenuRequested.connect(self.menu)
        self.refresh()

    def clear_all(self):
        """清空 + Toast 撤销（5 秒窗口，条目原序放回，不删磁盘文件）"""
        gone = self.store.shelf_clear()
        self.refresh()
        if not gone:
            return

        def _undo():
            self.store.shelf_restore(gone)
            self.refresh()

        self.notify("已清空", "%d 个条目（文件本身没动）" % len(gone),
                    5000, action=("撤销", _undo))

    # 拖放
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.add(paths)
            e.acceptProposedAction()

    def add(self, paths):
        n = self.store.shelf_add(paths)
        if n:
            self.refresh()
            self.notify("已放入文件中转站", "%d 个文件" % n, 2500)
        return n

    def pick(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if files:
            self.add(files)

    def refresh(self):
        self.list.clear()
        for s in self.store.shelf():
            path = s["path"]
            name = os.path.basename(path) or path
            try:
                size = SI.human(os.path.getsize(path))
            except Exception:
                size = "已失效"
            it = QListWidgetItem("%s   %s" % (name, size))
            it.setData(Qt.UserRole, path)
            it.setToolTip(path)
            self.list.addItem(it)
        self.btn_clear.setEnabled(self.list.count() > 0)   # 空站时清空无意义

    def open_item(self, item):
        path = item.data(Qt.UserRole)
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            self.notify("文件不存在", path, 3000)

    def menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.UserRole)
        m = QMenu(self)
        a_open = m.addAction("打开")
        a_dir = m.addAction("打开所在目录")
        a_del = m.addAction("从中转站移除")
        act = m.exec_(self.list.mapToGlobal(pos))
        if act is a_open:
            self.open_item(item)
        elif act is a_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))
        elif act is a_del:
            self.store.shelf_remove(path)
            self.refresh()
