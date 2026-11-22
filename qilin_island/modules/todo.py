# -*- coding: utf-8 -*-
"""应用层 · 待办（M6）

1.4.4 轻量化：待办只管「写什么、做没做」。
- 到期/重复控件与视图切换行整体下线（重复能力迁到日历 #38）；
  老记录里的 due/repeat 字段不清洗，due_todos 照旧读取并触发提醒。
- 第一行只剩 输入框 + 添加；计数改列表底部一行小字。
- 排序：未完成在前 → 按添加时间倒序 → 已完成沉底（委托绘制里降透明度）。
- 键位：回车添加、空格勾选（选中行）、Delete 删除（选中行，带撤销）、
  Esc 收起面板（input.py 全局过滤器已有，这里不重复实现）。
- 完成判定统一走 timeutil.todo_is_done，行勾选/计数/收起态轮播同一个口径。"""
from datetime import date, datetime, timedelta
from PyQt5.QtCore import QDateTime, Qt, QTimer
from PyQt5.QtWidgets import (QAbstractItemView, QHBoxLayout, QInputDialog,
                             QLineEdit, QListWidget, QListWidgetItem, QMenu,
                             QPushButton, QVBoxLayout)
from ..infra.timeutil import (added_label, fmt_dt, parse_dt, repeat_label,
                              todo_is_done)
from .base import Page
from ..core.consts import CONTENT_PAD_X
from .widgets import META_ROLE, TodoDelegate, flatten_card_frame


class _TodoList(QListWidget):
    """键盘直达的待办列表：空格切换勾选、Delete 删除选中行（不新增按钮）"""

    def __init__(self, page):
        super().__init__()
        self._page = page

    def keyPressEvent(self, e):
        it = self.currentItem()
        if e.key() == Qt.Key_Space and it is not None:
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked
                             else Qt.Checked)
            return                      # itemChanged 会接住后面的落库与刷新
        if e.key() == Qt.Key_Delete and it is not None:
            self._page.remove_item(it)
            return
        super().keyPressEvent(e)


class TodoPage(Page):
    capabilities = ("todo",)
    title = "待办"

    def __init__(self, host):
        super().__init__(host)
        v = QVBoxLayout(self)
        # 1.4.12：底部那行「待办 7 · 未完成 3」按用户口径删了，下边距 10→6，
        # 省出来的高度全给列表——条目栏拉到页面最下面，内容尽量铺满画面。
        # 1.4.14：水平边距 12→CONTENT_PAD_X(0)，列表与输入框一起对齐到页签卡那条列缘。
        v.setContentsMargins(CONTENT_PAD_X, 6, CONTENT_PAD_X, 6)
        v.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText("要做什么？回车即添加")
        self.input.setMinimumWidth(60)
        self.btn_add = QPushButton("添加")
        self.btn_add.setProperty("kind", "primary")
        self.btn_add.setFixedWidth(56)
        self.input.setAccessibleName("待办内容输入框")
        self.btn_add.setAccessibleName("添加待办")
        row.addWidget(self.input, 1)
        row.addWidget(self.btn_add)
        v.addLayout(row)

        self.list = _TodoList(self)
        self.list.setObjectName("card")
        flatten_card_frame(self.list)   # 与输入框同一套边距（1.4.5）
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setWordWrap(False)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setItemDelegate(TodoDelegate(host, self.list))
        self.list.setAccessibleName("待办列表")
        v.addWidget(self.list, 1)
        # 计数不再占一行（1.4.12）：数字改挂到列表的 accessibleName 上，
        # 视觉上没有了那行字，读屏仍然问得到共几条、未完成几条。

        self._loading = False
        self.input.returnPressed.connect(self.add_from_input)
        self.btn_add.clicked.connect(self.add_from_input)
        self.list.itemChanged.connect(self.on_item_changed)
        self.list.itemDoubleClicked.connect(self.rename)
        self.list.customContextMenuRequested.connect(self.menu)
        self._remind_at = 0
        self.refresh()

    def add_from_input(self):
        text = self.input.text().strip()
        if not text:
            # 空输入不再静默失败：红框 + 提示文案
            self.input.setProperty("err", True)
            self.input.style().unpolish(self.input)
            self.input.style().polish(self.input)
            self.input.setPlaceholderText("先输入内容，再点添加")
            QTimer.singleShot(1200, self._clear_input_err)
            return
        self.store.add_todo(text)       # 新记录 due=""、repeat=0
        self.input.clear()
        self.refresh()
        self.host.refresh_badge()

    def _clear_input_err(self):
        self.input.setProperty("err", False)
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)
        self.input.setPlaceholderText("要做什么？回车即添加")

    def add(self, text, repeat=0, due=None):
        """脚本/自检入口；界面路径不再传 due/repeat（老调用保持兼容）"""
        item = self.store.add_todo(text, due, repeat)
        self.refresh()
        self.host.refresh_badge()
        return item

    def refresh(self):
        self._loading = True
        self.list.clear()
        items = list(self.store.todos())
        # 未完成在前 → 按添加时间倒序 → 已完成沉底（沉底层内部同样新在上）
        items.sort(key=lambda t: (todo_is_done(t), -float(t.get("created") or 0)))
        for t in items:
            suffix = []
            rep = int(t.get("repeat") or 0)
            if rep:
                suffix.append(repeat_label(rep))
            due = parse_dt(t.get("due"))
            if due and not rep:
                suffix.append(due.strftime("%m-%d %H:%M"))
            suffix.append(added_label(t.get("created")))
            meta = " · ".join(suffix)
            it = QListWidgetItem(t["text"])
            it.setData(Qt.UserRole, t["id"])
            it.setData(META_ROLE, meta)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if todo_is_done(t) else Qt.Unchecked)
            it.setToolTip(t["text"] + ("\n" + meta if meta else ""))
            self.list.addItem(it)
        left = sum(1 for i in items if not todo_is_done(i))
        # 1.4.12：这组数字原来写在列表下面那行 QLabel 上，现在只挂进 accessibleName
        self.list.setAccessibleName("待办列表，共 %d 条，未完成 %d 条" % (len(items), left))
        self._loading = False

    def on_item_changed(self, item):
        if self._loading:
            return
        tid = item.data(Qt.UserRole)
        on = item.checkState() == Qt.Checked
        self.store.toggle_todo(tid, on)
        self.refresh()
        self.host.refresh_badge()

    def remove_item(self, item):
        """删除 + Toast 撤销（5 秒窗口，撤销后 id 不变）"""
        tid = item.data(Qt.UserRole)
        t = self.store.todo(tid)
        if not t:
            return
        self.store.remove_todo(tid)
        self.refresh()
        self.host.refresh_badge()

        def _undo():
            self.store.restore_todo(t)
            self.refresh()
            self.host.refresh_badge()

        self.notify("已删除", t["text"], 5000, action=("撤销", _undo))

    def rename(self, item):
        tid = item.data(Qt.UserRole)
        t = self.store.todo(tid)
        if not t:
            return
        text, ok = QInputDialog.getText(self, "修改待办", "内容：", text=t["text"])
        if ok and text.strip():
            self.store.update_todo(tid, text=text.strip())
            self.refresh()

    def menu(self, pos):
        """右键菜单整体保留：老记录的到期/重复还能在这里改，删除走带撤销的路径"""
        item = self.list.itemAt(pos)
        if item is None:
            return
        tid = item.data(Qt.UserRole)
        m = QMenu(self)
        a_del = m.addAction("删除")
        a_due = m.addAction("预期完成时间…")
        a_nodue = m.addAction("清除时限")
        m.addSeparator()
        a_today = m.addAction("改为今天 20:00")
        a_tom = m.addAction("改为明天 09:00")
        a_clear = m.addAction("清除重复")
        act = m.exec_(self.list.mapToGlobal(pos))
        if act is a_del:
            self.remove_item(item)
            return
        elif act is a_due:
            t = self.store.todo(tid) or {}
            cur = parse_dt(t.get("due")) or datetime.combine(date.today(), datetime.min.time()).replace(hour=20)
            dt, ok = QInputDialog.getDateTime(self, "预期完成时间", "完成时限：",
                                              QDateTime(cur))
            if ok:
                self.store.update_todo(tid, due=fmt_dt(dt.toPyDateTime()),
                                       reminded=0)
        elif act is a_nodue:
            self.store.update_todo(tid, due="", reminded=0)
        elif act is a_today:
            self.store.update_todo(tid, due=fmt_dt(datetime.combine(date.today(), datetime.min.time()).replace(hour=20)), reminded=0)
        elif act is a_tom:
            self.store.update_todo(tid, due=fmt_dt(datetime.combine(date.today() + timedelta(days=1), datetime.min.time()).replace(hour=9)), reminded=0)
        elif act is a_clear:
            self.store.update_todo(tid, repeat=0)
        self.refresh()

    def tick(self, now):
        if now - self._remind_at < 20:
            return
        self._remind_at = now
        hit = self.store.due_todos(now)   # 老记录（带 due/repeat）照旧触发
        for t in hit:
            self.notify("待办到点", t["text"])
            self.store.mark_reminded(t["id"], now)
        if hit:
            self.refresh()
