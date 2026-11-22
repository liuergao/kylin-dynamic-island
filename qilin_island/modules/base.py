# -*- coding: utf-8 -*-
"""应用层 · 页面基类（表 2：M6/M7/M8/M9/M10/M11/M12 的公共部分）

页面只认 host 门面——配色、数据、通知、徽标刷新、写剪贴板、拖拽冻结，
其余不依赖岛窗口内部实现，因此任一页损坏可以单独降级而不拖垮整体。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget


class Page(QWidget):
    title = ""
    # 能力名：胶囊内容（core/content）按名字找提供者，不认类名也不认页序
    capabilities = ()

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.store = host.store
        self.setObjectName("page")
        self.setAttribute(Qt.WA_StyledBackground, True)

    def on_show(self):
        pass

    def on_hide(self):
        pass

    def tick(self, now):
        pass

    # 便捷
    def notify(self, title, body, ms=6000, action=None):
        """action=(label, callback)：岛内 Toast 右侧的可点区域（如删除撤销）"""
        self.host.notify(title, body, ms, action=action)
