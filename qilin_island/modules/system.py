# -*- coding: utf-8 -*-
"""应用层 · 系统状态页（M11 的可视部分）"""
import time
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout
from .base import Page
from ..core.consts import CONTENT_PAD_X
from ..services import system as SI


class SysPage(Page):
    capabilities = ("system",)
    title = "系统"

    def __init__(self, host):
        super().__init__(host)
        self.cpu = SI.CpuMeter()
        self.net = SI.NetMeter()
        v = QVBoxLayout(self)
        # 1.4.14：水平边距 14→CONTENT_PAD_X(=0)，与页签卡同一条列缘
        v.setContentsMargins(CONTENT_PAD_X, 8, CONTENT_PAD_X, 10)
        v.setSpacing(4)
        v.addStretch(1)             # 上下等分：九行读数落在面板纵向中轴
        self.rows = {}
        for key, label in [("cpu", "CPU"), ("mem", "内存"), ("disk", "磁盘"),
                           ("net", "网络"), ("bat", "电量"), ("temp", "温度"),
                           ("vol", "音量"), ("up", "已运行"), ("rss", "本程序")]:
            row = QHBoxLayout()
            k = QLabel(label)
            k.setObjectName("muted")
            val = QLabel("—")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(k)
            row.addStretch(1)
            row.addWidget(val)
            v.addLayout(row)
            self.rows[key] = val
        v.addStretch(1)
        self._last = 0

    def on_show(self):
        self._last = 0
        self.tick(time.time())

    def tick(self, now):
        if not self.isVisible() or now - self._last < 2:
            return
        self._last = now
        cpu = self.cpu.sample()
        used, total = SI.mem_info()
        du, dt = SI.disk_info()
        rx, tx = self.net.sample()
        pct, charging = SI.battery()
        vol = SI.volume()
        self.rows["cpu"].setText("%.0f%%" % cpu)
        self.rows["mem"].setText("%s / %s" % (SI.human(used), SI.human(total)))
        self.rows["disk"].setText("%s / %s" % (SI.human(du), SI.human(dt)))
        self.rows["net"].setText("↓%s/s ↑%s/s" % (SI.human(rx), SI.human(tx)))
        self.rows["bat"].setText("—" if pct is None else "%d%%%s" % (pct, " ⚡" if charging else ""))
        tmp = SI.cpu_temp()
        self.rows["temp"].setText("—" if tmp is None else "%.0f℃" % tmp)
        self.rows["vol"].setText("—" if vol is None else "%d%%" % vol)
        self.rows["up"].setText("%dh%02dm" % (int(SI.uptime_sec()) // 3600,
                                             (int(SI.uptime_sec()) % 3600) // 60))
        self.rows["rss"].setText(SI.human(SI.self_rss()))
