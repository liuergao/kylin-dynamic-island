# -*- coding: utf-8 -*-
"""应用层 · 剪贴板历史（M9）"""
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout)
from .base import Page
from ..core.consts import CONTENT_PAD_X
from .widgets import ClipPinDelegate, PIN_ROLE, flatten_card_frame


class ClipPage(Page):
    capabilities = ("clipboard",)
    title = "剪贴板"

    def __init__(self, host):
        super().__init__(host)
        v = QVBoxLayout(self)
        # 1.4.14：水平边距交给 CONTENT_PAD_X（=0），提示行与列表卡片一起对齐到
        # 页签卡那条列缘（面板 x=12..365），左右各留 12px。
        v.setContentsMargins(CONTENT_PAD_X, 6, CONTENT_PAD_X, 10)
        v.setSpacing(6)
        row = QHBoxLayout()
        # 1.4.10：固定改成每行行尾的钉子图标，提示里那句「右键可固定」按用户要求删掉。
        # 右键菜单仍留着（还有「删除」），只是不再拿它当唯一的固定入口。
        self.tip = QLabel("最近 30 条文字，点击复制")
        self.tip.setObjectName("muted")
        self.tip.setAccessibleName("剪贴板用法提示")
        row.addWidget(self.tip, 1)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setAccessibleName("清空剪贴板未固定的记录")
        row.addWidget(self.btn_clear)
        v.addLayout(row)
        self.empty = QLabel("暂无剪贴记录\n复制文字后会自动出现在这里")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setVisible(False)
        v.addWidget(self.empty)
        self.list = QListWidget()
        self.list.setObjectName("card")
        self.list.setAccessibleName("剪贴板历史列表")
        flatten_card_frame(self.list)   # 与顶部按钮行同一套边距（1.4.5）
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        # 长文本用省略号收尾，不要出现横向滚动条（深色皮肤上会露出系统白条）
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setWordWrap(False)
        self.delegate = ClipPinDelegate(host, self.list)
        self.delegate.pinToggled.connect(self.toggle_pin)
        self.list.setItemDelegate(self.delegate)
        v.addWidget(self.list, 1)
        self.list.itemClicked.connect(self.copy_item)
        self.list.customContextMenuRequested.connect(self.menu)
        self.btn_clear.clicked.connect(self.clear)
        self._clear_arm = False
        self.refresh()

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.list.clear()
        # 这里只放原文（折行压成空格），省略交给委托在 paint 里按当前行宽算。
        # 在 refresh 里预切是 1.4.10 之前长文案压住钉子的根因：那一刻的视口宽
        # 可能还没落定（刚展开/刚换皮肤），切出来的字符串会一路用到下次 refresh。
        for cid, text, ts, pinned in self.store.clip.items():
            it = QListWidgetItem(text.replace("\n", " "))
            it.setData(Qt.UserRole, (cid, text))
            it.setData(PIN_ROLE, 1 if pinned else 0)
            # 读屏取原文 + 固定态，不取被省略号截断的预览
            it.setData(Qt.AccessibleTextRole,
                       "%s，%s" % (text[:120], "已固定" if pinned else "未固定"))
            it.setToolTip("%s%s" % ("[已固定] " if pinned else "", text[:400]))
            self.list.addItem(it)
        has = self.list.count() > 0
        self.list.setVisible(has)
        self.empty.setVisible(not has)

    def toggle_pin(self, cid):
        """行尾钉子：切固定态。固定项不参与 30 条淘汰，并排在最前（clipstore 的
        ORDER BY pinned DESC 已经保证），所以这里只改状态、重画。"""
        self.store.clip.pin(cid)
        pinned = any(c == cid and p for c, t, s, p in self.store.clip.items())
        self.refresh()
        self.notify("已固定" if pinned else "已取消固定",
                    "固定项不会被 30 条上限挤掉" if pinned else "恢复参与淘汰", 1800)

    def copy_item(self, item):
        cid, text = item.data(Qt.UserRole)
        self.host.set_clipboard(text)
        self.notify("已复制", text[:40], 2000)

    def menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        cid, text = item.data(Qt.UserRole)
        m = QMenu(self)
        a_pin = m.addAction("固定 / 取消固定")
        a_del = m.addAction("删除")
        act = m.exec_(self.list.mapToGlobal(pos))
        if act is a_pin:
            self.store.clip.pin(cid)
        elif act is a_del:
            self.store.clip.remove(cid)
        self.refresh()

    def _restyle_clear(self, danger):
        self.btn_clear.setProperty("kind", "danger" if danger else None)
        self.btn_clear.style().unpolish(self.btn_clear)
        self.btn_clear.style().polish(self.btn_clear)

    def clear(self):
        # 二次确认：第一次点变成“确认清空？”（红色警示），2.5 秒内再点才真清
        if not self._clear_arm:
            self._clear_arm = True
            self.btn_clear.setText("确认清空？")
            self._restyle_clear(True)
            QTimer.singleShot(2500, self._disarm_clear)
            return
        self._disarm_clear()
        self.store.clip.clear(keep_pinned=True)
        self.refresh()

    def _disarm_clear(self):
        self._clear_arm = False
        self.btn_clear.setText("清空")
        self._restyle_clear(False)

    def capture(self, text):
        """由外壳守护线程/定时器调用"""
        if not self.store.settings.get("clip", {}).get("on", True):
            return False
        ok = self.store.clip.add(text)
        if ok and self.isVisible():
            self.refresh()
        return ok
