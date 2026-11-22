# -*- coding: utf-8 -*-
"""交互层 · M4 停靠

拖到边缘吸附左/右停靠。1.2.9 起本模块不再动窗口的显隐：全屏自动隐藏、
最大化缩成细线都去掉了，隐藏只有一个入口（托盘右键 / 关窗），见 M1 set_hidden。"""
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QCursor
from .consts import DOCK_SNAP


class DockMixin:
    def moveEvent(self, e):
        super().moveEvent(e)
        # 外部移动兜底（xdotool/窗口管理器直接改窗口位置，走不到拖拽松手链路，
        # B 机实测拖到左缘窗口被丢在 (0,0) 且不吸附）。这里同步判定贴边；
        # 动画期间的 moveEvent 跳过，避免动画路过边缘被误判停靠。
        if self._drag is not None or self._anim is not None:
            return
        if not self.isVisible() or not self.expanded:
            return
        area = self._screen()
        left_gap = self.x() - area.x()
        right_gap = area.x() + area.width() - (self.x() + self.width())
        if left_gap <= DOCK_SNAP or right_gap <= DOCK_SNAP:
            self._last_pos = (self.x(), self.y())
            self._dock_after_drag()
            if self.dock != "top" and not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
                # 鼠标不在窗口内（外部移动场景）不会再有 leaveEvent，主动走一次收起判定
                QTimer.singleShot(450, self._maybe_collapse)

    def _dock_after_drag(self):
        """松手时判定停靠：窗口贴到屏幕左/右边缘就竖过来，其余回到顶部横版"""
        area = self._screen()
        if self._last_pos:
            x, y = self._last_pos
        else:
            x, y = self.x(), self.y()
        w, h = self.width(), self.height()
        cx = x + w / 2.0
        cy = y + h / 2.0

        old = self.dock
        left_gap = x - area.x()
        right_gap = area.x() + area.width() - (x + w)
        if left_gap <= DOCK_SNAP and left_gap <= right_gap:
            self.dock = "left"
        elif right_gap <= DOCK_SNAP:
            self.dock = "right"
        else:
            self.dock = "top"
        self._dbg("dock x=%s y=%s w=%s h=%s left_gap=%s right_gap=%s -> %s (old %s)" % (
            x, y, w, h, left_gap, right_gap, self.dock, old))

        self.store.settings["dock"] = self.dock
        self.store.settings["screen"] = self._screen_tag()
        if self.dock == "top":
            mid = area.x() + area.width() / 2.0
            # 松手时离正中 8px 内直接吸附正中，省得差一点点又不像居中
            self.store.settings["cx"] = None if abs(cx - mid) <= 8 else int(round(cx))
        else:
            mid = area.y() + area.height() / 2.0
            self.store.settings["cy"] = None if abs(cy - mid) <= 8 else int(round(cy))
        self.store.save()

        if old != self.dock:
            self._sync_visibility(self.expanded)
        self._animate(self._target_rect(self.expanded))
        self.update()
