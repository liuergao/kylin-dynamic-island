# -*- coding: utf-8 -*-
"""交互层 · M1 形态与几何

三状态（折叠/展开/隐藏）迁移、停靠坐标与动画目标矩形全在这里；
尺寸只由 _collapsed_size + _target_rect 两处算出，别处不得自行 resize。"""
from PyQt5.QtCore import QRect, QSize
from PyQt5.QtGui import QGuiApplication
from . import theme as T
from .consts import (COLLAPSED, COLLAPSED_V, COLLAPSED_V_LINE, EDGE_PAD, EXPANDED,
                     LINE_H, LINE_W, NOTCH_H)


class FormMixin:
    def form_init(self):
        """M1 初始状态：展开标记、动画句柄、停靠与收起形态（都从配置还原）"""
        self.expanded = False
        self._hidden = bool(self.store.settings.get("hidden"))
        self._anim = None
        self.dock = self.store.settings.get("dock") or "top"
        if self.dock not in ("top", "left", "right"):
            self.dock = "top"
        self.style = self.store.settings.get("style") or "pill"
        if self.style not in ("pill", "notch"):
            self.style = "pill"
        self.providers = {}

    def _mod(self, key):
        return bool((self.store.settings.get("modules") or {}).get(key))

    def _style_now(self):
        """当前生效的收起形态：隐藏态一律细线，其余按设置（侧停靠为竖版）"""
        if self._hidden:
            return "line"
        if self.dock != "top":
            return "pill"
        st = self.store.settings.get("style", "pill")
        return st if st in ("pill", "notch") else "pill"

    def apply_style(self):
        """设置里改了形态/模块：重摆位置并重绘"""
        self._place(collapsed=not self.expanded)
        self._update_chips()
        self.update()

    def _collapsed_size(self):
        """收起尺寸：折叠态恒为 COLLAPSED（宽 = 隐藏横线），隐藏态为细线"""
        if self.dock in ("left", "right"):
            return COLLAPSED_V_LINE if self._hidden else COLLAPSED_V
        if self._hidden:
            return QSize(LINE_W, LINE_H)
        return QSize(COLLAPSED.width(),
                     NOTCH_H if self._style_now() == "notch" else COLLAPSED.height())

    def _screen(self):
        scr = QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    def _screen_tag(self):
        """当前屏幕可用区的尺寸指纹，用来判断分辨率/缩放有没有变过"""
        a = self._screen()
        return [int(a.width()), int(a.height())]

    def _recall(self, key):
        """取回用户拖拽记住的中心坐标。

        分辨率一变（换显示器、调缩放、远程桌面改分辨率），存下来的绝对像素
        就没有意义了，这时一律作废、回到屏幕正中，保证任何屏幕下都是居中的。
        """
        val = self.store.settings.get(key)
        if val is None:
            return None
        if list(self.store.settings.get("screen") or []) != self._screen_tag():
            # 含老版本升级上来的数据（当时还没记 screen 字段）
            self.store.settings[key] = None
            self.store.settings["screen"] = self._screen_tag()
            try:
                self.store.save()
            except Exception:
                pass
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _watch_screen(self):
        """盯住屏幕分辨率变化（换显示器、改缩放、远程桌面切分辨率）"""
        scr = QGuiApplication.primaryScreen()
        if scr is not None:
            scr.geometryChanged.connect(self._on_screen_changed)
            scr.availableGeometryChanged.connect(self._on_screen_changed)

    def _center_x(self):
        """岛体中心的横坐标：同分辨率下沿用拖过的位置，否则恒为屏幕正中"""
        area = self._screen()
        mid = area.x() + area.width() / 2.0
        cx = self._recall("cx")
        return mid if cx is None else cx

    def _center_y(self, area):
        """停靠左右两侧时的纵向中心：用展开高度的一半做边界，两种尺寸共用同一中心"""
        cy = self._recall("cy")
        if cy is None:
            cy = area.y() + area.height() / 2.0
        half = EXPANDED.height() / 2.0
        lo, hi = area.y() + half + 2, area.y() + area.height() - half - 2
        if lo <= hi:
            return max(lo, min(cy, hi))
        return max(area.y() + COLLAPSED_V.height() / 2.0 + 2,
                   min(cy, area.y() + area.height() - COLLAPSED_V.height() / 2.0 - 2))

    def _target_rect(self, expanded):
        area = self._screen()
        if self.dock in ("left", "right"):
            size = EXPANDED if expanded else self._collapsed_size()
            cy = self._center_y(area)
            y = cy - size.height() / 2.0
            if self.dock == "left":
                x = area.x() + EDGE_PAD
            else:
                x = area.x() + area.width() - size.width() - EDGE_PAD
            return QRect(int(round(x)), int(round(y)), size.width(), size.height())

        size = EXPANDED if expanded else self._collapsed_size()
        half = size.width() / 2.0
        # 用「最大宽度」的半宽做边界，保证收起与展开得到同一个中心点，
        # 否则拖到屏幕边缘后两种尺寸各自夹取，中心会漂移。
        max_half = EXPANDED.width() / 2.0
        cx = self._center_x()
        lo, hi = area.x() + max_half + 2, area.x() + area.width() - max_half - 2
        if lo <= hi:
            cx = max(lo, min(cx, hi))
        else:
            cx = max(area.x() + half + 2, min(cx, area.x() + area.width() - half - 2))
        x = cx - half
        # 刘海式贴住屏幕顶边（只圆下两角），其余形态留 4px 呼吸缝
        y = area.y() if (not expanded and self._style_now() == "notch") else area.y() + 4
        return QRect(int(round(x)), int(y), size.width(), size.height())

    def _place(self, collapsed=True):
        r = self._target_rect(not collapsed)
        self.setGeometry(r)
        self._sync_visibility(not collapsed)

    def recenter(self):
        """托盘「回到屏幕正中」：清掉拖拽记忆，按当前屏幕重新居中"""
        self.store.settings["cx"] = None
        self.store.settings["cy"] = None
        self.store.settings["dock"] = "top"
        self.store.settings["screen"] = self._screen_tag()
        self.store.save()
        self._sync_visibility(self.expanded)
        self._animate(self._target_rect(self.expanded))
        self.update()

    def _on_screen_changed(self, *_a):
        """分辨率 / 缩放变了：_recall 发现尺寸对不上会自动归中，这里重新摆位"""
        self._place(collapsed=not self.expanded)
        self.update()

    def _sync_visibility(self, expanded):
        self.expanded = expanded
        self.nav.setVisible(expanded)
        self.stack.setVisible(expanded)
        # 侧边竖版收起态由 paintEvent 自绘（logo + 竖排时间），横版头部整体隐藏
        style = self._style_now()
        line = style == "line"
        top = self.dock == "top"
        self.head.setVisible(expanded or (top and not line))
        self.btn_pin.setVisible(expanded)           # 钉住只在展开态有意义
        collapsed_pill = (not expanded) and top and not line
        self.chips.setVisible(collapsed_pill)
        # 均衡条只在真正播放时才出现（1.2.9）：静止的四根短条看着像一串没用的蓝点，
        # 有没有在放歌由 _update_chips 按 MPRIS 状态决定
        self.eq.setVisible(False)
        self.clock.setVisible(expanded)       # 展开面板顶部保留时钟
        self._update_badge()

    def expand(self):
        if self._hidden:
            self.set_hidden(False)      # 隐藏态先回折叠胶囊，再悬停才展开面板
            return
        if self.expanded:
            return
        self._sync_visibility(True)
        self._animate(self._target_rect(True))

    def collapse(self):
        if not self.expanded or self.store.settings.get("pinned"):
            return
        self._sync_visibility(False)
        self._animate(self._target_rect(False))

    def set_hidden(self, on):
        """折叠胶囊 ↔ 隐藏横线：1.2.9 起隐藏只有一个入口（托盘右键/关窗），
        不再由全屏或最大化自动触发"""
        on = bool(on)
        if on == self._hidden:
            return
        self._hidden = on
        self.store.settings["hidden"] = on
        self.store.save()
        self._sync_visibility(False if on else self.expanded)
        self._animate(self._target_rect(self.expanded))
        self.update()

    def reveal(self):
        """取消隐藏并展开面板：托盘左键、二次启动唤回都走这里"""
        if self._hidden:
            self._hidden = False
            self.store.settings["hidden"] = False
            self.store.save()
        if not self.isVisible():
            self.show()
        self._sync_visibility(True)
        self._animate(self._target_rect(True))
        self.raise_()
        self.activateWindow()
        self.skip_taskbar()

    def _animate(self, rect):
        """岛体形变：收起↔展开↔隐藏横线的几何迁移，时长/缓动全部取自 token"""
        if self._anim is not None:
            self._anim.stop()
        growing = rect.height() > self.geometry().height()
        self._anim = T.animate(
            self, "geometry", self.geometry(), rect,
            T.DUR["normal"] if growing else T.DUR["fast"],
            "enter" if growing else "exit")
        # 动画结束即清引用：靠 _anim 判定「是否在动」的逻辑（轮播冻结等）
        # 不会被一个已结束的动画永久卡住。重贴提示条必须写在同一个槽里、且在放
        # 引用之前做：清掉句柄会把 _Eased 的引用放掉，排在后面的第二个槽就丢了。
        def _done():
            tst = getattr(self, "toast", None)
            if tst is not None:
                tst.sync()          # 面板刚长大，提示条得跟着挪到面板下沿
            self._anim = None

        self._anim.finished.connect(_done)

    def toggle_pin(self):
        pinned = self.btn_pin.isChecked()
        self.store.settings["pinned"] = pinned
        self.store.save()
        if pinned:
            self.expand()
        else:
            self.collapse()
