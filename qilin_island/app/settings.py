# -*- coding: utf-8 -*-
"""应用层 · 设置（M14 的唯一写入口）

所有设置项都通过 host 门面读改，保存后由岛体统一重放样式与停靠。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QPushButton, QSpinBox, QTimeEdit, QWidget)
from ..core.consts import COLLAPSE_STYLES
from . import sponsor
from ..core import theme as T
from ..modules.widgets import ToggleSwitch


def _centered(w):
    """把定宽控件放进左右等分的容器里，使其落在表单字段列的中轴上。"""
    box = QWidget()
    h = QHBoxLayout(box)
    h.setContentsMargins(0, 0, 0, 0)
    h.addStretch(1)
    h.addWidget(w)
    h.addStretch(1)
    return box


def _pair(*ws):
    """开关和它配套的输入框同行：开关在左、输入框在右，整组居中。"""
    box = QWidget()
    h = QHBoxLayout(box)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(T.SP["l"])
    h.addStretch(1)
    for w in ws:
        h.addWidget(w)
    h.addStretch(1)
    return box


class SettingsDialog(QDialog):
    def __init__(self, host):
        super().__init__(None)
        self.host = host
        self.store = host.store
        self.setWindowTitle("麒麟灵动岛 · 设置")
        # 岛体是「总在最前」的窗口，设置窗是普通窗口，展开态下会压住窗顶。
        # 跟着置顶，两边谁都不挡谁。
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumWidth(340)
        f = QFormLayout(self)
        f.setSpacing(8)

        self.skin = QComboBox()
        for key in T.SKIN_ORDER:
            self.skin.addItem(T.SKINS[key]["name"], key)
        idx = max(0, self.skin.findData(self.store.settings.get("skin")))
        self.skin.setCurrentIndex(idx)

        # 明暗一键切换：分组只看底色亮度（皮肤名会骗人，GitHub 亮色的 accent 反而是
        # 深色），组内各自记住上次用的皮肤，来回切不会每次都掉回默认那套。
        self._skin_last = dict(self.store.settings.get("skin_last") or {})
        cur = self.store.settings.get("skin", "deep")
        self.mode = ToggleSwitch(checked=not T.is_light(cur), label="暗色模式",
                                 sk_provider=self.host.sk)
        self.mode.toggled.connect(self._to_mode)
        self.skin.currentIndexChanged.connect(self._from_combo)

        # 动效总开关：关掉只是不补中间帧，值照样落位，重启后维持
        self.motion = ToggleSwitch(checked=bool(self.store.settings.get("motion", True)),
                                   label="动效", sk_provider=self.host.sk)

        # 收起形态（仅顶部停靠生效；左右停靠沿用竖版胶囊）
        self.cb_style = QComboBox()
        for key, label in COLLAPSE_STYLES:
            self.cb_style.addItem(label, key)
        idx = max(0, self.cb_style.findData(self.store.settings.get("style", "pill")))
        self.cb_style.setCurrentIndex(idx)
        self.cb_style.setToolTip("收起后的形状（停靠在左右两侧时固定为竖版胶囊）")

        # 收起态信息模块：时钟/待办/CPU/内存/网速/电量/音乐
        mods = self.store.settings.get("modules") or {}
        self.mod_boxes = {}
        mods_row = QWidget()
        mh = QHBoxLayout(mods_row)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(6)
        for key, label in [("clock", "时钟"), ("todo", "待办"), ("meet", "会议"),
                           ("cpu", "CPU"),
                           ("mem", "内存"), ("net", "网速"), ("battery", "电量"),
                           ("music", "音乐")]:
            b = QCheckBox(label)
            b.setChecked(bool(mods.get(key, key in ("clock", "todo", "meet"))))
            self.mod_boxes[key] = b
            mh.addWidget(b)
        mh.addStretch(1)

        self.morning = ToggleSwitch(label="每日晨报", sk_provider=self.host.sk)
        self.morning.setChecked(bool(self.store.settings["morning"].get("on")))
        self.mtime = QTimeEdit()
        hh, mm = (self.store.settings["morning"].get("time") or "08:30").split(":")
        from PyQt5.QtCore import QTime
        self.mtime.setTime(QTime(int(hh), int(mm)))

        self.goal = QSpinBox()
        self.goal.setRange(1, 20)
        self.goal.setValue(int(self.store.settings["water"].get("goal", 8)))
        self.interval = QSpinBox()
        self.interval.setRange(10, 240)
        self.interval.setValue(int(self.store.settings["water"].get("interval", 45)))
        self.interval.setSuffix(" 分钟")

        self.work = QSpinBox()
        self.work.setRange(5, 90)
        self.work.setValue(int(self.store.settings["focus"].get("work", 25)))
        self.work.setSuffix(" 分钟")
        self.rest = QSpinBox()
        self.rest.setRange(1, 30)
        self.rest.setValue(int(self.store.settings["focus"].get("rest", 5)))
        self.rest.setSuffix(" 分钟")

        self.clip = ToggleSwitch(label="记录剪贴板历史", sk_provider=self.host.sk)
        self.clip.setChecked(bool(self.store.settings["clip"].get("on", True)))
        self.autostart = ToggleSwitch(label="开机自动启动", sk_provider=self.host.sk)
        self.autostart.setChecked(bool(self.store.settings.get("autostart")))

        # 控件被表单拉满整列宽，短值（"8"「上午8:30」）贴左会在右侧留下
        # 300px 空白，整窗重心偏左；一律居中显示。
        for w in (self.mtime, self.goal, self.interval, self.work, self.rest):
            w.setAlignment(Qt.AlignCenter)
        # QSS 的 text-align 对 QComboBox 不生效，改为定宽 + 左右等分，
        # 让下拉框本身落在列中轴上。
        self.skin.setFixedWidth(200)
        self.cb_style.setFixedWidth(200)

        f.addRow("皮肤", _centered(self.skin))
        f.addRow("明暗模式", _centered(self.mode))
        f.addRow("收起样式", _centered(self.cb_style))
        f.addRow("收起信息", mods_row)
        f.addRow("每日晨报", _pair(self.morning, self.mtime))
        f.addRow("每日饮水目标", self.goal)
        f.addRow("饮水提醒间隔", self.interval)
        f.addRow("专注时长", self.work)
        f.addRow("休息时长", self.rest)
        f.addRow("记录剪贴板历史", _centered(self.clip))
        f.addRow("开机自动启动", _centered(self.autostart))
        f.addRow("动效", _centered(self.motion))

        # 联系我们 / 赞助作者
        extra = QWidget()
        eh = QHBoxLayout(extra)
        eh.setContentsMargins(0, 6, 0, 0)
        eh.setSpacing(8)
        self.btn_contact = QPushButton("联系我们")
        self.btn_sponsor = QPushButton("赞助作者")
        for b in (self.btn_contact, self.btn_sponsor):
            b.setCursor(Qt.PointingHandCursor)
        self.btn_contact.clicked.connect(lambda: sponsor.open_contact(self))
        self.btn_sponsor.clicked.connect(lambda: sponsor.open_sponsor(self))
        eh.addWidget(self.btn_contact)
        eh.addWidget(self.btn_sponsor)
        eh.addStretch(1)
        f.addRow(extra)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("保存")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        box.accepted.connect(self.save)
        box.rejected.connect(self.reject)
        f.addRow(box)

    # ── 明暗 ↔ 皮肤 ───────────────────────────────────────────────────────
    def _grp(self, dark):
        return T.DARK_SKINS if dark else T.LIGHT_SKINS

    def _to_mode(self, dark):
        """拨开关 → 换皮肤：先回到这一组上次用的那套，没记过就用组内第一个"""
        grp = self._grp(dark)
        want = self._skin_last.get("dark" if dark else "light")
        i = self.skin.findData(want if want in grp else grp[0])
        if i >= 0 and i != self.skin.currentIndex():
            self.skin.setCurrentIndex(i)      # 触发 _from_combo：记账并同步开关

    def _from_combo(self):
        """选皮肤 → 拨开关，并把这一组的偏好记下来；setChecked 不发 toggled，
        两条路径不会互相触发成死循环"""
        key = self.skin.currentData()
        if not key:
            return
        dark = not T.is_light(key)
        self._skin_last["dark" if dark else "light"] = key
        self.mode.setChecked(dark)

    def save(self):
        s = self.store.settings
        s["skin"] = self.skin.currentData()
        s["style"] = self.cb_style.currentData()
        mods = dict(s.get("modules") or {})
        for key, b in self.mod_boxes.items():
            mods[key] = b.isChecked()
        s["modules"] = mods
        s["morning"]["on"] = self.morning.isChecked()
        s["morning"]["time"] = self.mtime.time().toString("HH:mm")
        s["water"]["goal"] = self.goal.value()
        s["water"]["interval"] = self.interval.value()
        s["focus"]["work"] = self.work.value()
        s["focus"]["rest"] = self.rest.value()
        s["clip"]["on"] = self.clip.isChecked()
        s["autostart"] = self.autostart.isChecked()
        s["motion"] = self.motion.isChecked()
        s["skin_last"] = dict(self._skin_last)
        self.store.save()
        self.host.set_autostart(s["autostart"])
        self.host.reload_pages()
        self.host.apply_motion()
        self.host.apply_skin()
        self.host.apply_style()
        self.accept()
