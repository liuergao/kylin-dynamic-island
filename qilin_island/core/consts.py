# -*- coding: utf-8 -*-
"""核心层 · 岛体几何常量（M1）

1.2.8 的实测数值基本沿用；1.2.9 把折叠态宽度钉死成隐藏横线的长度（LINE_W），
不再跟随内容变化。改动这些数值会直接改变胶囊外观。"""
from PyQt5.QtCore import QSize
from ..infra.paths import ASSETS_DIR


LINE_W, LINE_H = 200, 6           # 隐藏横线
# 1.4.14：面板里只有一条内容列，列缘由 app/island.py 的 body 边距（左右各 12）
# 决定——顶栏、页签卡、每个功能页的内容都从这条线起、到右边那条线止。
# 页面自己的水平边距必须是 0：以前各页又叠了 10~14px，内容比页签卡缩进去一截，
# 用户手绘的那两条竖线指的就是这件事（"上面的底框和下面的内容左右要对齐"）。
# 左右各 12px 是"适中"的取值：既不贴住面板圆角，也不再空出 24px。
CONTENT_PAD_X = 0
# 折叠态宽度固定成横线的长度（1.2.9）：1.2.8 按内容现算，最短只有 120px，
# 且切轮播页、来消息时忽大忽小，这里改成常量后两种毛病一起消失。
COLLAPSED = QSize(LINE_W, 40)
COLLAPSED_V = QSize(40, 152)      # 停靠左右两侧时的竖版胶囊
COLLAPSED_V_LINE = QSize(LINE_H, COLLAPSED_V.height())   # 侧停靠的隐藏态：竖细线
EXPANDED = QSize(378, 348)

# 1.1.0 收起形态（仅顶部停靠生效；左右停靠沿用竖版胶囊）
NOTCH_H = 34                      # 刘海式：贴顶、只圆下两角
COLLAPSE_STYLES = [("pill", "胶囊"), ("notch", "刘海")]

# 圆角半径统一，收起是胶囊（高 40 → 半径 20 刚好半圆），展开沿用同一弧度，
# 两种形态看起来才是同一个东西在长大/缩小，而不是换了张脸。
PANEL_RADIUS = 20.0
CAROUSEL_SECS = 3.0               # 收起态信息轮播间隔（秒/条）
CAR_MAX = 210                     # 轮播区最大像素宽：超过则滚动显示（不用省略号）
NOTCH_RADIUS = 13.0

DOCK_SNAP = 64                    # 拖到离屏幕边缘这么近就吸附到该侧
EDGE_PAD = 2                      # 贴边留白


ASSETS = ASSETS_DIR
