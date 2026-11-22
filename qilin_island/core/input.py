# -*- coding: utf-8 -*-
"""交互层 · M3 输入与焦点

悬停展开、离开收起、整窗拖动、Esc 收起、菜单/对话框期间的冻结。事件过滤器挂在全应用上，
因此先判断“是不是自己的控件”，否则会抢掉页面里按钮和输入框的点击。"""
import os
import time
from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtGui import QCursor, QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox, QDialog, QLineEdit, QMenu, QScrollBar)
from .consts import EDGE_PAD


class InputMixin:
    def input_init(self):
        """M3 初始状态：悬停计时、拖拽会话、菜单/拖出冻结标记"""
        self._hover_at = 0
        self._drag = None
        self._drag_origin = None
        self._drag_moved = False
        self._last_pos = None
        self._drag_gp = None
        self._menu_open = False
        self._ext_drag = False    # 文件中转站拖出进行中：冻结自动收起

    def enterEvent(self, e):
        self._hover_at = time.time()
        # 不直接 expand：走光标校验，挡掉 WM/平台合成的虚假进入事件
        QTimer.singleShot(140, self._eval_hover)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover_at = time.time()
        QTimer.singleShot(420, self._maybe_collapse)
        super().leaveEvent(e)

    def _cursor_inside(self):
        """光标算不算「压在岛体上」。

        隐藏横线只有 6px 高（侧停靠时只有 6px 宽），按精确矩形判定，鼠标明明
        划过横线也会因为差一两个像素而不算悬停，横线就再也展不开。细的时候纵向
        各放 8px 容差。"""
        r = self.rect()
        if min(r.width(), r.height()) <= 8:
            r = r.adjusted(-8, -8, 8, 8)
        return r.contains(self.mapFromGlobal(QCursor.pos()))

    def _maybe_collapse(self):
        if not self.expanded or self.store.settings.get("pinned"):
            return
        if self._drag is not None or self._menu_open or self._ext_drag:
            return
        if self._cursor_inside():
            return
        if time.time() - self._hover_at < 0.35:
            return
        self.collapse()

    def eventFilter(self, obj, ev):
        # 悬浮判定：鼠标进出任意子控件后重新评估
        if ev.type() in (QEvent.Enter, QEvent.Leave) and self.isVisible():
            QTimer.singleShot(60, self._eval_hover)
        # 弹出菜单（下拉选项、右键菜单）挂在窗口之外，鼠标离开窗口矩形会误判成
        # 「移出」而收起面板。这里统一跟踪 QMenu 的显隐，弹出期间冻结收起逻辑。
        elif isinstance(obj, QMenu):
            if ev.type() == QEvent.Show:
                self._menu_open = True
                self._hover_at = time.time()
            elif ev.type() in (QEvent.Hide, QEvent.Close):
                # 菜单关闭后延迟恢复：Hide 与“鼠标仍在菜单原位置”之间有个窗口期，
                # 立刻清标志会让悬停判定在下一帧把面板收走（偶发右键菜单消失）。
                QTimer.singleShot(150, self._menu_closed)
        # 任何对话框（设置、关于、赞助、联系我们，以及待办改文字、选文件这些）
        # 弹出时都先把面板收起来：岛体是置顶窗口，展开态 378×350 正好压在屏幕
        # 中上部，会把对话框的标题栏盖住。
        elif isinstance(obj, QDialog) and ev.type() == QEvent.Show:
            QTimer.singleShot(0, self._settle_before_dialog)
        # Esc 关闭展开面板（对标 BrimDeck）：菜单/弹窗自身的 Esc 不拦截
        elif ev.type() == QEvent.KeyPress and self._is_own(obj):
            if (isinstance(ev, QKeyEvent) and ev.key() == Qt.Key_Escape
                    and self.expanded
                    and not self.store.settings.get("pinned")
                    and not self._menu_open
                    and QApplication.activePopupWidget() is None):
                self.collapse()
                return True
        # 拖动：按住岛体任意位置（含标签、页面等子控件）都能拖走窗口。
        # 子控件会吞掉 press，靠这里统一接管，窗口才不会「某些位置拖不动」。
        elif ev.type() in (QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.MouseButtonRelease):
            if self._is_own(obj) and self._drag_allowed(obj, ev):
                gp = ev.globalPos()
                if ev.type() == QEvent.MouseButtonPress:
                    if self._drag is None:
                        self._drag_begin(gp)
                elif ev.type() == QEvent.MouseMove:
                    self._drag_to(gp)
                else:
                    self._drag_end(gp)
        return False

    def _menu_closed(self):
        """菜单真正关完（没有别的弹窗接着弹出）才解除冻结"""
        if QApplication.activePopupWidget() is not None:
            return
        self._menu_open = False
        self._hover_at = time.time()

    def _is_own(self, obj):
        """事件对象是否属于岛体自身（递归找父级），排除设置对话框、托盘菜单等独立窗口"""
        w = obj
        while w is not None:
            if w is self:
                return True
            w = w.parentWidget() if hasattr(w, "parentWidget") else None
        return False

    def _drag_allowed(self, obj, ev):
        """按钮、输入框这类「本来就要吃掉鼠标」的控件不当作拖动把手"""
        for w in (obj, obj.parentWidget() if hasattr(obj, "parentWidget") else None):
            if isinstance(w, (QAbstractButton, QLineEdit, QAbstractSpinBox,
                              QComboBox, QScrollBar, QAbstractSlider)):
                return False
            # 列表类（文件中转站拖出文件、待办勾选/重命名、剪贴板复制）自己吃鼠标手势，
            # 不能当作窗口拖动把手——否则拖文件会变成拖岛体
            if isinstance(w, QAbstractItemView):
                return False
        if isinstance(ev, QMouseEvent):
            if ev.type() == QEvent.MouseButtonPress and ev.button() != Qt.LeftButton:
                return False
            if ev.type() == QEvent.MouseButtonRelease and ev.button() != Qt.LeftButton:
                return False
        return True

    def _eval_hover(self):
        if not self.isVisible():
            return
        inside = self._cursor_inside()
        if inside:
            # 只有「真实进入过」（enterEvent 刷新过 _hover_at）才自动展开；
            # 否则离屏/远程环境下光标坐标失真，会出现看不见鼠标却一直展开的怪象
            if time.time() - self._hover_at < 1.2:
                self.expand()
        elif self.expanded and not self._menu_open and not self.store.settings.get("pinned"):
            self._maybe_collapse()

    # 拖动：按住并移动超过 4px 才算拖动，避免误触把岛体挪走

    def _dbg(self, msg):
        """拖动链路调试日志（FUYU_DEBUG_LOG=/path 时才写，正常使用零开销）"""
        path = os.environ.get("FUYU_DEBUG_LOG")
        if not path:
            return
        try:
            with open(path, "a") as f:
                f.write("%.3f %s\n" % (time.time(), msg))
        except OSError:
            pass

    def _drag_begin(self, gp):
        self._drag = (gp.x() - self.x(), gp.y() - self.y())
        self._drag_origin = gp
        self._drag_moved = False
        self._last_pos = None
        self._drag_gp = None
        self._hover_at = time.time()
        self._dbg("press g=%s self=%s off=%s" % ((gp.x(), gp.y()), (self.x(), self.y()), self._drag))

    def _drag_to(self, gp):
        """拖动中：按位移挪窗口，超过 4px 才算真拖动（避免误触把岛体挪走）"""
        if not self._drag:
            return
        # 同一次移动会被子控件冒泡上来重复送达，按坐标去重，避免重复 move
        if self._drag_gp is not None and gp == self._drag_gp:
            return
        self._drag_gp = gp
        if not self._drag_moved:
            d = gp - self._drag_origin
            if abs(d.x()) < 4 and abs(d.y()) < 4:
                return
            self._drag_moved = True
        area = self._screen()
        x = gp.x() - self._drag[0]
        y = gp.y() - self._drag[1]
        x = max(area.x() + EDGE_PAD, min(x, area.x() + area.width() - self.width() - EDGE_PAD))
        y = max(area.y() + EDGE_PAD, min(y, area.y() + area.height() - self.height() - EDGE_PAD))
        # 记下最后一次真实拖动到的位置：某些窗口系统下 move() 不会立刻回读到 x()/y()，
        # 松手判定停靠时只能依赖这份缓存，否则会读到起始位置。
        self._last_pos = (int(x), int(y))
        self.move(int(x), int(y))
        self._dbg("move g=%s -> %s" % ((gp.x(), gp.y()), self._last_pos))

    def _drag_end(self, gp):
        if not self._drag:
            return
        self._dbg("release g=%s moved=%s last=%s" % (
            (gp.x(), gp.y()), self._drag_moved, self._last_pos))
        self._drag = None
        if self._drag_moved:
            self._drag_moved = False
            self._dock_after_drag()
        else:
            self._drag_moved = False
            # 细线太细，悬停容易错过：原地点一下也算展开手势
            if self._hidden and not self.expanded:
                self.expand()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag is None:
            self._drag_begin(e.globalPos())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self._drag_to(e.globalPos())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_end(e.globalPos())
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.btn_pin.setChecked(not self.btn_pin.isChecked())
        self.toggle_pin()

    def _settle_before_dialog(self):
        """弹窗之前先把面板收起来。

        岛体是置顶窗口，展开时是 378×350、正好占住屏幕中上部；对话框一般都摆在
        屏幕中间，两者会叠在一起，对话框的标题栏就被岛体压住。收起后岛体只剩
        200×40，与居中的对话框不再重叠。顺手把动画直接跳到终点，免得
        对话框按展开时的尺寸去定位。
        """
        try:
            if self.store.settings.get("pinned"):
                return
            target = self._target_rect(False)
            if self.geometry() != target:
                self.collapse()
                # 越过展开动画直接落到收起后的位置
                self.setGeometry(target)
            QApplication.processEvents()
        except Exception:
            pass
