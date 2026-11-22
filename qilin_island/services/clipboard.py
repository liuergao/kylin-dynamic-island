# -*- coding: utf-8 -*-
"""能力层 · M9 剪贴板读写

界面不直接碰 QApplication.clipboard()：文本进出都先过一遍归一化。
X 的剪贴板往返会带来 \\r 和首尾空白差异，不归一化就会把同一条内容记成两三条
（B 机实测同一链接连出 3 条），归一化规则和存库那边共用同一个函数。
"""
from PyQt5.QtWidgets import QApplication

from ..infra.clipstore import normalize


def read_text():
    """当前剪贴板文本（已归一化，可能为空串）"""
    return normalize(QApplication.clipboard().text())


def write_text(text):
    QApplication.clipboard().setText(normalize(text))
