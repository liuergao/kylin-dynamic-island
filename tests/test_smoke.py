# -*- coding: utf-8 -*-
"""离线自检：不需要 X，用 offscreen Qt 跑一遍关键不变量。

跑法：python3 tests/test_smoke.py
"""
import io
import math
import os
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# 强制 offscreen：环境里可能已导出 QT_QPA_PLATFORM=xcb，setdefault 会顶不掉，
# 而这个自检的约定就是不需要 X
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["FUYU_HOME"] = tempfile.mkdtemp(prefix="qilin-smoke-")

from PyQt5.QtCore import (QEvent, QPointF, QPoint, QRect, QRectF, QSize, Qt)  # noqa: E402
from PyQt5.QtGui import (QImage, QMouseEvent, QPainter)                      # noqa: E402
from PyQt5.QtWidgets import (QApplication, QLabel, QStyleOptionViewItem)       # noqa: E402

from qilin_island import APP_ID, APP_NAME, VERSION                           # noqa: E402
from qilin_island.app.island import Island                                   # noqa: E402
from qilin_island.core import theme as T                                     # noqa: E402
from qilin_island.core.consts import (COLLAPSED, COLLAPSED_V, COLLAPSED_V_LINE,
                                      CONTENT_PAD_X, EXPANDED, LINE_H, LINE_W,
                                      NOTCH_H)            # noqa: E402
from qilin_island.core.shape import rounded_region                           # noqa: E402
from qilin_island.platform.x11 import _cm_owner_via_x11, has_compositor      # noqa: E402
from qilin_island.core.styles import global_qss, tokens                     # noqa: E402
from qilin_island.core.pill import CarWidget                                 # noqa: E402
from qilin_island.infra.store import Store                                   # noqa: E402
from qilin_island.modules import PAGE_CLASSES                                # noqa: E402

app = QApplication([])
fails = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("ok  " if cond else "FAIL", name,
                         "" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


check("标识", (APP_NAME, APP_ID, VERSION) == ("麒麟灵动岛", "fuyu", "1.4.15"))
check("皮肤数", len(T.SKIN_ORDER) == 8, T.SKIN_ORDER)
check("全局样式", all(len(global_qss(T.skin(s))) > 2000 for s in T.SKIN_ORDER))

isl = Island(store=Store())
check("页面数", len(isl.pages) == len(PAGE_CLASSES) == 8)
check("导航标题", [c.title for c in PAGE_CLASSES]
      == ["待办", "专注", "饮水", "文件中转站", "剪贴板", "音乐", "日历", "系统"],
      [c.title for c in PAGE_CLASSES])
for cap in ("todo", "focus", "water", "shelf", "clipboard", "media", "calendar", "system"):
    check("能力查询 %s" % cap, isl.provider(cap) is not None)


def _ends_spaced(layout):
    """左右（或上下）都有弹性占位 —— 内容才会落在中轴上而不是贴边"""
    if layout is None or layout.count() < 3:
        return False
    a = layout.itemAt(0)
    b = layout.itemAt(layout.count() - 1)
    return a.spacerItem() is not None and b.spacerItem() is not None


def _row_of(page, child):
    for k in range(page.layout().count()):
        lay = page.layout().itemAt(k).layout()
        if lay is None:
            continue
        for j in range(lay.count()):
            if lay.itemAt(j).widget() is child:
                return lay
    return None


# 1.3.0 居中修正的回归护栏
check("页签行左右等分", _ends_spaced(isl.nav_row))
# 页签胶囊化：QSS 里那个半径必须真的是按钮实高的一半，写死的 22 只是估法，
# 实测对不上就说明"胶囊"其实是个圆角矩形
_nav_btn = isl.nav_group.buttons()[0]
_nav_btn.ensurePolished()
check("页签半径=实高一半",
      abs(tokens(T.skin("deep"))["r_nav"] - _nav_btn.sizeHint().height() / 2.0) <= 1.0,
      "r_nav=%d 实高=%d" % (tokens(T.skin("deep"))["r_nav"],
                            _nav_btn.sizeHint().height()))
check("饮水按钮行居中", _ends_spaced(_row_of(isl.pages[2], isl.pages[2].btn_add)))
_sh_head = _row_of(isl.pages[3], isl.pages[3].btn)
check("中转站顶栏：两个按钮同一行、页面底部不再有按钮行",
      _sh_head.__class__.__name__ == "QHBoxLayout" and
      _row_of(isl.pages[3], isl.pages[3].btn_clear) is _sh_head and
      _row_of(isl.pages[3], isl.pages[3].list) is None,
      _sh_head.__class__.__name__)
check("中转站提示只留前半句（去掉右键菜单那句）",
      "右键菜单" not in isl.pages[3].tip.text()
      and isl.pages[3].tip.text().startswith("文件拖进来暂存"),
      isl.pages[3].tip.text())
check("音乐控制组居中", _ends_spaced(_row_of(isl.pages[5], isl.pages[5].btn_prev)))
check("歌词水平居中", bool(isl.pages[5].lyric.alignment() & Qt.AlignHCenter))
check("列表卡片底", [isl.pages[i].list.objectName() for i in (0, 3, 4)] == ["card"] * 3)
_qss = global_qss(T.skin("deep"))
check("下拉文字居中样式", 'QPushButton[kind="choice"] { text-align: center' in _qss)
# QSS 里 # 是 ID 选择器，不是行注释：写成"# 注释"会把紧随其后的整条规则当选择器
# 垃圾吞掉，页面看起来就是样式莫名失效（页签按钮退回系统默认 36px 高）。
# 只认"# 空格"或"# 汉字"开头这两种注释写法，`#nav {` 这种合法 ID 选择器不能误伤。
check("QSS 无井号行注释", not re.search(r"^\s*#(?:\s|[\u4e00-\u9fff])", _qss, re.M),
      [l for l in _qss.splitlines() if re.match(r"^\s*#(?:\s|[\u4e00-\u9fff])", l)][:3])
# 1.4.1 岛本体可见刷新：页签行有卡片底、胶囊有描边、轮播字号抬到 12px
_trans_rule = re.search(r"QWidget#page[^{]*\{[^}]*\}", _qss).group(0)
check("页签行卡片底", "QWidget#nav { background:" in _qss and "#nav" not in _trans_rule,
      _trans_rule)
_shape_src = open(os.path.join(ROOT, "qilin_island", "core", "shape.py"),
                  encoding="utf-8").read()
check("胶囊描边只在收起态画", "if not self.expanded:" in _shape_src
      and "self._paint_rim(p, sk)" in _shape_src)
check("轮播字号抬到 12px", CarWidget.FPIX == 12, CarWidget.FPIX)
check("设置数值居中", "setAlignment(Qt.AlignCenter)" in
      open(os.path.join(ROOT, "qilin_island", "app", "settings.py"),
           encoding="utf-8").read())

# 1.4.0 界面焕新：色值只准出现在两处 —— theme.py（皮肤与派生色）和 brand.py
# （标识与素材字形，本来就不随皮肤变）。其余文件一律从 theme 取。
# 正则要卡字边界：QLabel#badge 里的 "bad" 也是合法十六进制，不能误判成色值
_HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b|\brgba?\(")
_allowed_src = {"core/theme.py", "core/brand.py"}
_offenders = []
for _root, _dirs, _files in os.walk(os.path.join(ROOT, "qilin_island")):
    _dirs[:] = [d for d in _dirs if d != "__pycache__"]
    for _f in sorted(_files):
        if not _f.endswith(".py"):
            continue
        _rel = os.path.relpath(os.path.join(_root, _f),
                               os.path.join(ROOT, "qilin_island")).replace(os.sep, "/")
        if _rel in _allowed_src:
            continue
        for _ln, _line in enumerate(
                open(os.path.join(_root, _f), encoding="utf-8"), 1):
            if _HEX.search(_line):
                _offenders.append("%s:%d" % (_rel, _ln))
check("全仓库无散落脚本色值", not _offenders, _offenders[:6])
_tok = tokens(T.skin("deep"))
_allowed_r = {_tok[k] for k in ("r_ctl", "r_card", "r_ov", "r_tip", "r_item",
                                "r_scroll", "r_groove", "r_thumb", "r_nav")}
_used_r = {int(x) for x in re.findall(r"border-radius:\s*(\d+)px", _qss)}
check("圆角全部来自 token", _used_r and _used_r <= _allowed_r,
      sorted(_used_r - _allowed_r))
# 格点之外的三个数都有来历：1px 是 focuspill 的光学微调，-3px 是滑块把手压出
# 4px 槽，26px 是菜单项给勾选图标留的命中区
_grid = {T.SP[k] for k in T.SP} | {0, 1, -3, 26}
_geo = {int(n) for decl in re.findall(r"(?:padding|margin):\s*([^;]+)", _qss)
        for n in re.findall(r"-?\d+", decl)}
check("内外边距落在 4px 格点上", _geo and _geo <= _grid, sorted(_geo - _grid))
check("按钮四态齐全", all(("QPushButton:%s" % st) in _qss
                          for st in ("hover", "pressed", "focus", "disabled")))
check("变体按钮也有悬停按下", all(
    ('QPushButton[kind="%s"]:%s' % (kind, st)) in _qss
    for kind in ("primary", "danger") for st in ("hover", "pressed", "disabled")))
check("页签按钮四态齐全", all(('QPushButton[nav="true"]:%s' % st) in _qss
                              for st in ("hover", "pressed", "focus", "checked")))
check("输入框悬停聚焦禁用", all(("QLineEdit:%s" % st) in _qss
                                for st in ("hover", "focus", "disabled")))
check("勾选框按下禁用", all(("QCheckBox::indicator:%s" % st) in _qss
                            for st in ("hover", "pressed", "disabled")))
check("列表项三态", all(("QListWidget::item:%s" % st) in _qss
                        for st in ("hover", "selected", "disabled")))
check("菜单项三态", all(("QMenu::item:%s" % st) in _qss
                        for st in ("hover", "selected", "disabled")))
check("焦点环用主色", "QPushButton:focus { border-color: %s" % _tok["accent"] in _qss)
check("主按钮墨色按对比度挑",
      'QPushButton[kind="primary"] { background: %s; color: %s'
      % (_tok["accent"], _tok["on_accent"]) in _qss)
check("八套皮肤字形素材都随底色走", all(
    ("/arrow-%s.png" % T.asset_variant("arrow", T.states(T.skin(s))["card"]))
    in global_qss(T.skin(s)) for s in T.SKIN_ORDER))


# 1.2.9：折叠尺寸钉死成隐藏横线的长度，切轮播页、开信息模块都不再变宽变窄
isl.store.settings["style"] = "pill"
isl.dock = "top"
isl.show()
app.processEvents()
check("折叠尺寸固定", isl._collapsed_size() == COLLAPSED == QSize(LINE_W, 40),
      isl._collapsed_size())
isl.chips.setVisible(False)
check("折叠尺寸不随内容变", isl._collapsed_size() == COLLAPSED)
isl.chips.setVisible(True)
isl.store.settings["modules"] = {"clock": True, "todo": True, "meet": True,
                                 "cpu": True, "mem": True, "net": True,
                                 "battery": True, "music": True}
isl._update_chips()
check("全模块开启尺寸不变", isl._collapsed_size() == COLLAPSED,
      isl._collapsed_size())


def _spin(n=120):
    """等布局/动画跑到位：offscreen 下 processEvents 不会自己推进定时器"""
    for _ in range(n):
        app.processEvents()
        time.sleep(0.02)


# 1.3.2：收起胶囊里图标固定在左、上下找平，轮播文字按岛体中轴居中
_pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "qilin_island")
_keep = isl._update_chips              # 1s tick 会用真实页覆盖，先钉住测试文案
isl._update_chips = lambda *a: None
_pages = [([(u"时钟 12:34", "#35E0C8")], u"时钟 12:34", None),
          ([(u"CPU 100%  ·  内存 100%  ·  ↓999.9K ↑999.9K", "#35E0C8")],
           u"设备", None)]
isl.chips.set_pages(_pages, 0)
isl.collapse()
_spin()
check("收起态图标固定在左", isl.logo.mapTo(isl, QPoint(0, 0)).x() == 12,
      isl.logo.mapTo(isl, QPoint(0, 0)).x())
check("收起态轮播吃中段", isl.chips.x() > isl.logo.x() + isl.logo.width(),
      (isl.chips.x(), isl.logo.x(), isl.logo.width()))
_short_x = isl.logo.mapTo(isl, QPoint(0, 0)).x()
isl.chips.set_pages(_pages, 1)          # 换成最长的一页
_spin()
check("切页图标不动", isl.logo.mapTo(isl, QPoint(0, 0)).x() == _short_x,
      isl.logo.mapTo(isl, QPoint(0, 0)).x())
# 1.4.3：居中基准从「岛体中轴」改成「图标右侧剩余区」的中心；
# 图标墨迹贴左、且与文字墨迹中线重合（见 core/pill.py 文件头口径）
_chips_x = isl.chips.mapTo(isl, QPoint(0, 0)).x()
_axis = isl.chips._axis + _chips_x
_free_l = isl.logo.mapTo(isl, QPoint(0, 0)).x() + isl.logo.width()
_free_r = isl.width() - 12
check("文字居中基准是图标右侧剩余区的中心",
      abs(_axis - (_free_l + _free_r) / 2.0) <= 1.0,
      (_axis, (_free_l + _free_r) / 2.0, isl.width() / 2.0))
check("居中基准不再是岛体中轴", abs(_axis - isl.width() / 2.0) > 6.0,
      (_axis, isl.width() / 2.0))
check("文字基线下沉找平图标", "+ self.VDY" in
      open(os.path.join(_pkg, "core", "pill.py"), encoding="utf-8").read())
check("图标墨迹贴左内边距", isl.logo._ix >= 0 and
      isl.logo.mapTo(isl, QPoint(0, 0)).x() == 12,
      (isl.logo._ix, isl.logo.mapTo(isl, QPoint(0, 0)).x()))

# 墨迹中线重合：文字用度量公式推（base - (ascent-descent)/2 = h/2 + VDY），
# 图标用 pixmap 的实际 alpha 包围盒推 —— 不看图，也不吃字体差异
_pm = isl._logo_pm(isl.logo._size)
_img = _pm.toImage()
_ly0, _ly1 = 10 ** 6, -1
for _y in range(_img.height()):
    for _x in range(_img.width()):
        if _img.pixelColor(_x, _y).alpha() > 8:
            _ly0 = min(_ly0, _y)
            _ly1 = max(_ly1, _y)
_logo_cy = (isl.logo.mapTo(isl, QPoint(0, 0)).y() + isl.logo._dy
            + (_ly0 + _ly1 + 1) / 2.0)
_text_cy = (isl.chips.mapTo(isl, QPoint(0, 0)).y() + isl.chips.height() / 2.0
            + isl.chips.VDY)
check("图标与文字墨迹中线重合", abs(_logo_cy - _text_cy) <= 1.0,
      (_logo_cy, _text_cy))
isl.expand()
_spin()
check("展开态图标贴左", isl.logo.mapTo(isl, QPoint(0, 0)).x() == 12,
      isl.logo.mapTo(isl, QPoint(0, 0)).x())
check("展开态按钮贴右", isl.btn_pin.mapTo(isl, QPoint(0, 0)).x()
      + isl.btn_pin.width() == isl.width() - 12,
      isl.btn_pin.mapTo(isl, QPoint(0, 0)).x())
isl._update_chips = _keep
isl.collapse()
_spin()

# 隐藏态：顶部 200×6 横线、侧停靠 6×152 竖线，只能由 set_hidden 进入
isl.set_hidden(True)
check("隐藏横线尺寸", isl._collapsed_size() == QSize(LINE_W, LINE_H),
      isl._collapsed_size())
check("隐藏态收起头部内容", not isl.chips.isVisible())
isl.set_hidden(False)
check("取消隐藏回折叠", not isl._hidden and isl._collapsed_size() == COLLAPSED)
check("隐藏标记落盘", isl.store.settings.get("hidden") is False)

# 均衡条只在真的播放时才占位（1.2.8 静止时常驻，看着像一串没用的蓝点）
check("未播放不显示均衡条", not isl.eq.isVisible())
isl.store.settings["modules"] = {}
isl.store.settings["style"] = "notch"
isl.apply_style()
check("刘海尺寸", isl._collapsed_size() == QSize(LINE_W, NOTCH_H), isl._collapsed_size())
isl.store.settings["style"] = "pill"
isl.apply_style()
for side in ("left", "right"):
    isl.dock = side
    check("侧边收起尺寸 %s" % side, isl._collapsed_size() == COLLAPSED_V)
    isl.set_hidden(True)
    check("侧边隐藏尺寸 %s" % side, isl._collapsed_size() == COLLAPSED_V_LINE)
    isl.set_hidden(False)
isl.dock = "top"
isl.hide()
check("展开尺寸", (isl._target_rect(True).width(), isl._target_rect(True).height())
      == (378, 348))

# 无合成器的圆角遮罩：逐行像素区域（1.2.8 用粗折线，边缘一圈白色锯齿）
reg = rounded_region(QRect(0, 0, 200, 60), 20.0)
rows = {r.y(): r for r in reg.rects()}
check("遮罩顶行内缩", 0 < rows[0].left() < 20, rows[0].left())
check("遮罩中段满宽", rows[20].width() == 200, rows[20].width())
area = sum(r.width() * r.height() for r in reg.rects())
want = 200 * 60 - (4 - math.pi) * 20.0 * 20.0
check("遮罩面积贴合圆角矩形", abs(area - want) / want < 0.03, (area, round(want)))

# 1.4.2 边缘锯齿：有合成器时走抗锯齿图层，遮罩只能在没有合成器时上。
# 判定必须问 X 协议的 _NET_WM_CM_S<n> selection 属主——合成器从不往 root 写属性，
# 老写法 xprop -root 在 KWin 上永远查不到，明明在合成却一路走 1-bit 遮罩。
_x11_src = open(os.path.join(ROOT, "qilin_island", "platform", "x11.py"),
                encoding="utf-8").read()
_i_sel = _x11_src.find("_cm_owner_via_x11(")
_i_prop = _x11_src.find('"_NET_WM_CM_S0"')
check("合成器判定走 selection",
      "_NET_WM_CM_S%d" in _x11_src and _i_sel >= 0
      and (_i_prop < 0 or _i_sel < _i_prop), (_i_sel, _i_prop))
check("selection 判定不抛异常", has_compositor.__doc__ is not None
      and _cm_owner_via_x11() in (True, False, None), _cm_owner_via_x11())
_shape_src2 = open(os.path.join(ROOT, "qilin_island", "core", "shape.py"),
                   encoding="utf-8").read()
check("面板不透底", "alpha=246" not in _shape_src2 and "alpha=255" in _shape_src2)
_toast_src = open(os.path.join(ROOT, "qilin_island", "core", "toast.py"),
                  encoding="utf-8").read()
check("有合成器时提示条不上遮罩", "clearMask()" in _toast_src)
# 抗锯齿图层本身：ARGB 底图上画面板，四角必须全透明、中心必须全不透明，
# 弧上还要有 0<alpha<255 的过渡像素——遮罩路径给不出这第三种像素。
_img = QImage(200, 60, QImage.Format_ARGB32_Premultiplied)
_img.fill(Qt.transparent)
_p = QPainter(_img)
T.paint_panel(_p, _img.rect(), T.skin("deep"), radius=20.0, alpha=255,
              border=False, opaque=False)
_p.end()
_alpha = [[(_img.pixel(x, y) >> 24) & 0xFF for x in range(200)] for y in range(60)]
_partial = sum(1 for y in range(60) for x in range(200) if 0 < _alpha[y][x] < 255)
check("抗锯齿图层有过渡像素", _partial > 100, _partial)
check("图层四角全透明", all(_alpha[e][c] == 0 for e, c in
      ((0, 0), (0, 199), (59, 0), (59, 199))),
      [_alpha[e][c] for e, c in ((0, 0), (0, 199), (59, 0), (59, 199))])
check("图层中心全不透明", _alpha[30][100] == 255, _alpha[30][100])

# 音乐页：sync 里的 return 曾经误置在 for 循环内，检测到播放器后曲名/进度/封面
# 永不刷新（1.3.3 修）——用假 Mpris 把「有播放器就刷新、掉线才提示」钉住
class _FakeMpris(object):
    def __init__(self):
        self.service = "org.mpris.MediaPlayer2.fake"
        self.st = None

    def players(self):
        return [self.service]

    def state(self):
        return self.st


media = isl.providers["media"]      # MediaPage.title 被曲名 QLabel 占了，按能力取名
_real_mpris = media.mpris
media.mpris = _FakeMpris()
media.mpris.st = {"title": u"第一首", "artist": u"歌手A", "position": 12,
                  "length": 180, "status": "Playing", "art": "", "loop": "None",
                  "shuffle": False, "service": "org.mpris.MediaPlayer2.fake"}
media.sync(force=True)
check("接上播放器即刷曲名", media.title.text() == u"第一首", media.title.text())
media.mpris.st = dict(media.mpris.st, title=u"第二首", position=60,
                      loop="Track", shuffle=True)
media.sync(force=True)
check("换曲即刷新曲名", media.title.text() == u"第二首", media.title.text())
check("进度跟着刷新", media.time.text() == u"1:00 / 3:00", media.time.text())
check("播放中按钮可用", media.btn_play.isEnabled() and media.slider.isEnabled())
check("循环模式按真值显示", media.btn_mode.text() == u"①", media.btn_mode.text())
check("随机开关按真值显示", media.btn_rnd.isChecked())
media.mpris.st = None
media.sync(force=True)
check("播放器掉线才提示未检测到",
      media.title.text() == u"未检测到播放器", media.title.text())
media.mpris = _real_mpris

# 1.4.0 连续动效：时长与曲线只有 theme.token 一个来源，别处不许再手写毫秒
_motion_files = {}
for _m in ("form", "pill", "focus"):
    _p = os.path.join(_pkg, "core" if _m != "focus" else "modules", "%s.py" % _m)
    _motion_files[_m] = open(_p, encoding="utf-8").read()
check("动效不走 Qt 内置曲线", all("QEasingCurve" not in s for s in _motion_files.values()))
check("动效不写死毫秒", all(not re.search(r"setDuration\(\s*\d", s)
                           for s in _motion_files.values()))
check("动效时长取自 token", all("T.DUR[" in s for s in _motion_files.values()))
check("跑马灯淡入不再按帧手加", "+ 0.06" not in _motion_files["pill"])

# 缓动曲线本身：端点闭合、单调；进场先快后慢，退场先慢后快
for _k in T.CURVE:
    _f = T.curve(_k)
    _xs = [_f(i / 20.0) for i in range(21)]
    check("曲线端点 %s" % _k, abs(_xs[0]) < 1e-6 and abs(_xs[-1] - 1.0) < 1e-6)
    check("曲线单调 %s" % _k, all(b >= a - 1e-9 for a, b in zip(_xs, _xs[1:])))
check("进场先快后慢", all(T.curve("enter")(x) > x for x in (0.25, 0.5, 0.75)))
check("退场先慢后快", all(T.curve("exit")(x) < x for x in (0.25, 0.5, 0.75)))
check("场内两头慢", 0.0 < T.curve("inout")(0.25) < 0.5 < T.curve("inout")(0.75) < 1.0)


def _r(g):
    return (g.x(), g.y(), g.width(), g.height())


def _morph_frames(action):
    """跑完一次形变，返回沿途采到的矩形序列（含起点与终点）"""
    out = [isl.geometry()]
    action()
    guard = 0
    while isl._anim is not None and guard < 400:
        app.processEvents()
        time.sleep(0.005)
        guard += 1
        if isl.geometry() != out[-1]:
            out.append(isl.geometry())
    app.processEvents()
    if isl.geometry() != out[-1]:
        out.append(isl.geometry())
    return out


isl.show()
_spin(20)
_coll = isl._target_rect(False)
_exp = isl._target_rect(True)
fr = _morph_frames(isl.expand)
check("展开是连续形变", len(fr) >= 4, [_r(g) for g in fr])
check("展开逐帧长大", all(b.width() >= a.width() and b.height() >= a.height()
                          for a, b in zip(fr, fr[1:])), [g.width() for g in fr])
check("展开落位精确", fr[-1] == _exp, (fr[-1], _exp))
check("动画跑完即放手", isl._anim is None)
fr2 = _morph_frames(isl.collapse)
check("收起同样连续", len(fr2) >= 4, [_r(g) for g in fr2])
check("收起逐帧收窄", all(b.width() <= a.width() and b.height() <= a.height()
                          for a, b in zip(fr2, fr2[1:])), [g.width() for g in fr2])
check("收起落位精确", fr2[-1] == _coll, (fr2[-1], _coll))
# 退场时长比进场短，两条曲线一个进场一个退场
check("退场比进场快", T.DUR["fast"] < T.DUR["normal"], (T.DUR["fast"], T.DUR["normal"]))

# 连点打断：每次新形变都要接管上一个，跑完必须精确停在当前状态的目标矩形上
for _i in range(12):
    (isl.expand if _i % 2 == 0 else isl.collapse)()
    _spin(2)
_spin(80)
check("反复打断仍落位", isl.geometry() == isl._target_rect(isl.expanded),
      (isl.geometry(), isl._target_rect(isl.expanded)))
# processEvents 不处理 DeferredDelete，这里按事件循环正常跑完的情形显式清一次
app.sendPostedEvents(None, QEvent.DeferredDelete)
_eased = [c for c in isl.children() if type(c).__name__ == "_Eased"]
check("打断不留动画残骸", len(_eased) <= 1, len(_eased))

# 进度环：秒级推进（千分之几）直接落值，重置/换段的大跨度才补中间帧
ring = isl.provider("focus").ring
ring.goto(0.0)
_spin(40)
ring.set_state(0.9, "20:00", "专注中")
_seen, _guard = [ring.ratio], 0
while ring._anim is not None and _guard < 400:
    app.processEvents()
    time.sleep(0.005)
    _guard += 1
    if abs(ring.ratio - _seen[-1]) > 1e-6:
        _seen.append(ring.ratio)
check("进度环补中间帧", len(_seen) >= 4, [round(v, 3) for v in _seen])
check("进度环单调推进", all(b >= a for a, b in zip(_seen, _seen[1:])),
      [round(v, 3) for v in _seen])
check("进度环落位精确", abs(ring.ratio - 0.9) < 1e-9, ring.ratio)
check("进度环跑完即放手", ring._anim is None)
ring.set_state(ring.ratio + 1.0 / 1500.0, "19:59", "专注中")   # 一秒的常规推进
check("秒级推进不过渡", ring._anim is None
      and abs(ring.ratio - (0.9 + 1.0 / 1500.0)) < 1e-9, ring.ratio)

# 切页淡入：alpha 从 0 缓到 1，位移跟着 alpha 走（不再是每帧 +0.06 的线性爬升）
isl._update_chips = lambda *a: None
isl.chips.set_pages(_pages, 0)
_spin(60)
isl.chips.set_pages(_pages, 1)
_alpha, _guard = [isl.chips._fade], 0
while isl.chips._anim is not None and _guard < 400:
    app.processEvents()
    time.sleep(0.005)
    _guard += 1
    if abs(isl.chips._fade - _alpha[-1]) > 1e-6:
        _alpha.append(isl.chips._fade)
check("切页淡入连续", len(_alpha) >= 4 and _alpha[0] == 0.0,
      [round(v, 3) for v in _alpha])
check("淡入单调变实", all(b >= a for a, b in zip(_alpha, _alpha[1:])),
      [round(v, 3) for v in _alpha])
check("淡入落位全不透明", abs(isl.chips._fade - 1.0) < 1e-9, isl.chips._fade)
isl._update_chips = _keep

# ── 改造试验版：动效总开关 / 自绘开关 / 明暗模式 / 岛内 Toast ─────────────
from PyQt5.QtTest import QTest                                             # noqa: E402
from qilin_island.app.settings import SettingsDialog                          # noqa: E402


def _click(w):
    """在控件正中按一下左键：offscreen 也能把事件投进去"""
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier,
                     QPoint(w.width() // 2, w.height() // 2))
from qilin_island.modules.widgets import ToggleSwitch                         # noqa: E402

_src_widgets = io.open(os.path.join(ROOT, "qilin_island", "modules",
                                    "widgets.py"), encoding="utf-8").read()
_src_toast = io.open(os.path.join(ROOT, "qilin_island", "core",
                                  "toast.py"), encoding="utf-8").read()
check("开关不写死色值", "#123456" not in _src_widgets
      and not re.search(r"QColor\(\s*\d+\s*,\s*\d+\s*,\s*\d+", _src_widgets))
check("提示条不引第三方特效", "QGraphicsOpacityEffect" not in _src_toast
      and "QPropertyAnimation" not in _src_toast)
check("提示条时长取自 token", "setDuration(" not in _src_toast
      and _src_toast.count("T.DUR[") >= 1)
check("开关尺寸在 4px 格点", all(v % 4 == 0 for v in
      (ToggleSwitch.W, ToggleSwitch.H, ToggleSwitch.PAD, ToggleSwitch.KNOB)),
      (ToggleSwitch.W, ToggleSwitch.H, ToggleSwitch.PAD, ToggleSwitch.KNOB))

# 动效总开关：关掉只该没中间帧，落值、句柄接口、收尾都不变
T.set_motion(False)
_sw = ToggleSwitch(False, "试验")
_h = T.animate(_sw, "_p", 0.0, 1.0, T.DUR["fast"], "inout", _sw)
check("关动效仍落终值", abs(_sw._p - 1.0) < 1e-9, _sw._p)
check("关动效不建缓动对象", _h is not None and not isinstance(_h, T._Eased),
      type(_h).__name__)
_f0 = _morph_frames(isl.expand)
check("关动效：展开只有起终两帧", len(_f0) == 2, [_r(g) for g in _f0])
_f0b = _morph_frames(isl.collapse)
check("关动效：收起只有起终两帧", len(_f0b) == 2, [_r(g) for g in _f0b])
T.set_motion(True)
_f1 = _morph_frames(isl.expand)
check("开动效：展开恢复连续形变", len(_f1) >= 4, len(_f1))
_spin(20)
isl.collapse()
_spin(20)

# 明暗分组：八套皮肤必须一个不漏地分成两组
check("明暗分组不重不漏",
      sorted(T.DARK_SKINS + T.LIGHT_SKINS) == sorted(T.SKIN_ORDER)
      and not (set(T.DARK_SKINS) & set(T.LIGHT_SKINS)),
      (T.DARK_SKINS, T.LIGHT_SKINS))
check("亮皮认对", set(["cream", "github_light"]) <= set(T.LIGHT_SKINS),
      T.LIGHT_SKINS)
check("暗皮认对", set(["deep", "github_dark"]) <= set(T.DARK_SKINS), T.DARK_SKINS)

# 设置页：开关 ↔ 皮肤 双向同步，且各组记住自己上次用的皮肤
_dlg = SettingsDialog(isl)
_start_skin = isl.store.settings.get("skin", "deep")
_dlg.skin.setCurrentIndex(max(0, _dlg.skin.findData("cream")))
check("选亮皮→开关拨到暗侧OFF", _dlg.mode.isChecked() is False, _dlg.mode.isChecked())
_click(_dlg.mode)          # 真点击，走的是用户那条路（setChecked 按 QCheckBox 语义不发信号）
check("拨回暗色→回到这组上次那套", _dlg.skin.currentData() == _start_skin,
      (_dlg.skin.currentData(), _start_skin))
_click(_dlg.mode)
check("再拨亮色→回到亮色那组", _dlg.skin.currentData() == "cream",
      _dlg.skin.currentData())
_click(_dlg.motion)
_dlg.save()
check("保存写动动效开关", isl.store.settings.get("motion") is False
      and T.motion_on() is False, isl.store.settings.get("motion"))
check("保存记下两组偏好", set(isl.store.settings.get("skin_last") or {}) ==
      {"dark", "light"}, isl.store.settings.get("skin_last"))
T.set_motion(True)
_dlg.deleteLater()

# 岛内 Toast：看得见、不抢焦点、跟着岛体重贴
isl.notify("自检", "提示条内容")
_t = isl.toast
check("通知落到 Toast", _t.isVisible() and _t.text() == "自检 · 提示条内容",
      (_t.isVisible(), _t.text()))
check("Toast 不抢焦点", bool(_t.windowFlags() & Qt.WindowDoesNotAcceptFocus)
      and _t.testAttribute(Qt.WA_ShowWithoutActivating), int(_t.windowFlags()))
check("Toast 宽度守上下限", 120 <= _t.width() <= 480 and _t.height() == 32,
      (_t.width(), _t.height()))
_gi, _ar = isl.geometry(), isl._screen()
check("Toast 落在岛下方且不越屏", _t.y() >= _gi.bottom()
      and _t.x() >= _ar.left() and _t.geometry().right() <= _ar.right(),
      (_t.x(), _t.y(), _gi.bottom()))
# 面板长大的时候提示条必须让位，不能压在面板上：等形变跑完再量
_morph_frames(isl.expand)
check("形变落位后提示条自动让位", isl.toast.isVisible()
      and isl.toast.geometry().top() >= isl.geometry().bottom(),
      (isl.toast.geometry().top(), isl.geometry().bottom()))
_morph_frames(isl.collapse)
isl.move(_ar.left() + 200, _ar.top() + 60)
isl.toast.sync()
check("岛体移动后提示条跟着重贴", isl.toast.y() >= isl.geometry().bottom(),
      (isl.toast.y(), isl.geometry().bottom()))
_spin(60)
check("Toast 淡入到位", abs(_t._a - 1.0) < 1e-9, _t._a)
T.set_motion(False)
isl.notify("自检", "关动效提示")
check("关动效直接可见", abs(_t._a - 1.0) < 1e-9 and _t.isVisible(), _t._a)
# 关动效留下的替身句柄，绝不能把紧接着建的新句柄清成 None：
# 引用一掉，正在跑的缓动对象就地析构，offscreen 下是段错误而不是报错
T.set_motion(False)
_sw2 = ToggleSwitch(False, "试验")
_sw2._anim = T.animate(_sw2, "_p", 0.0, 0.5, T.DUR["fast"], "inout", _sw2)
_sw2._anim.stop()
_sw2._anim = T.animate(_sw2, "_p", 0.5, 1.0, T.DUR["fast"], "inout", _sw2)
_new = _sw2._anim
_spin(10)
check("替身句柄不顶掉新句柄", _sw2._anim is _new and abs(_sw2._p - 1.0) < 1e-9,
      (_sw2._anim is _new, _sw2._p))
T.set_motion(True)
_t.fade_out()
_spin(60)
check("Toast 超时淡出后收起", not _t.isVisible() and abs(_t._a) < 1e-9,
      (_t.isVisible(), _t._a))

# ── 1.4.4 待办轻量化 + 日历重复 ────────────────────────────────────────
from datetime import date as _d, datetime as _dt, timedelta as _td       # noqa: E402
from qilin_island.infra.timeutil import (EV_R_DAILY, EV_R_MONTH, EV_R_WEEK,
                                         EV_R_WDAY, added_label,
                                         ev_occurrence, next_occurrence,
                                         todo_is_done)                    # noqa: E402
from qilin_island.modules.calendar import EventDialog                    # noqa: E402
from qilin_island.modules.widgets import META_ROLE as _MR                # noqa: E402

_tp = isl.provider("todo")
_r1 = _tp.layout().itemAt(0).layout()
_n1 = sum(1 for i in range(_r1.count()) if _r1.itemAt(i).widget() is not None)
check("待办第一行只剩两个控件", _n1 == 2, _n1)
check("到期/重复/视图切换控件已下线",
      not any(hasattr(_tp, a) for a in ("due", "repeat", "view")))
_morph_frames(isl.expand)       # 收起态页面量不到真实行宽，先展开
check("输入框实测宽度>=240", _tp.input.width() >= 240,
      (_tp.input.width(), _tp.width()))
check("计数行已删（1.4.12 前它在列表下方）", not hasattr(_tp, "count"),
      hasattr(_tp, "count"))
check("待办页标注非空", all(w.accessibleName() for w in
      (_tp.input, _tp.btn_add, _tp.list)),
      [w.accessibleName() for w in (_tp.input, _tp.btn_add, _tp.list)])

# ── 1.4.5 卡片列表与输入框边距对齐（用户反馈：白框上下要对齐）───────────
from qilin_island.modules.widgets import ROW_PAD as _RP                  # noqa: E402
_lv = _tp.list.viewport().geometry()
_cb_left = _tp.list.x() + _lv.x() + _RP          # 勾选框左缘（页面坐标）
_cb_right = _tp.list.x() + _lv.x() + _lv.width() - _RP   # 行内容右缘
check("卡片列表外缘与输入框/按钮外缘同轴",
      _tp.list.x() == _tp.input.x()
      and _tp.list.x() + _tp.list.width() == _tp.btn_add.x() + _tp.btn_add.width(),
      (_tp.list.x(), _tp.input.x(),
       _tp.list.x() + _tp.list.width(), _tp.btn_add.x() + _tp.btn_add.width()))
check("原生 5px 框已压掉（框宽<=3）", _tp.list.frameWidth() <= 3,
      _tp.list.frameWidth())
check("勾选框左缘贴近输入框文字左缘（差<=8px）",
      abs(_cb_left - (_tp.input.x() + 5)) <= 8,
      (_cb_left, _tp.input.x() + 5))
check("行内容右缘贴近按钮右缘（差<=4px）",
      abs(_cb_right - (_tp.btn_add.x() + _tp.btn_add.width() - 1)) <= 4,
      (_cb_right, _tp.btn_add.x() + _tp.btn_add.width() - 1))
_qss_card = global_qss(isl.sk())
check("card 列表内边距收到 2px 且 item 左右 4px",
      "padding: 2px;\n                   qproperty" in _qss_card.replace("\r", "")
      or ("QListWidget#card" in _qss_card and "padding: 2px" in
          _qss_card.split("QListWidget#card")[1].split("}")[0]),
      _qss_card.split("QListWidget#card")[1][:120])
check("剪贴板/中转站卡片列表同样压框",
      all("flatten_card_frame(self.list)" in
          io.open(os.path.join(ROOT, "qilin_island", "modules", _m),
                  encoding="utf-8").read()
          for _m in ("clipboard.py", "shelf.py")))

_st = isl.store
_a = _st.add_todo("轻量化A")
_b = _st.add_todo("轻量化B")
_st.toggle_todo(_a["id"], True)
_tp.refresh()
_tx = [_tp.list.item(i).text() for i in range(_tp.list.count())]
_id_of = {t["text"]: t for t in _st.todos()}
check("未完成在前、最新在上", _tx[0] == "轻量化B", _tx[:3])
_iA = _tx.index("轻量化A")
check("已完成沉底（前面的都未完成）",
      all(not todo_is_done(_id_of[_tx[i]]) for i in range(_iA)), _tx[:_iA + 1])
_i0 = _tp.list.item(_iA)
check("行勾选=已完成", _i0.checkState() == Qt.Checked)
check("行时间戳是添加时间", (_i0.data(_MR) or "").endswith("刚刚"),
      _i0.data(_MR))

# done_on 三处口径一致：行勾选 / 未完成计数 / 收起态轮播都问 todo_is_done
_g = _st.add_todo("前天截止", _dt.now() - _td(days=2), 0)
_st.update_todo(_g["id"], done_on=(_d.today() - _td(days=2)).isoformat())
_tp.refresh()
_it = [i for i in range(_tp.list.count())
       if _tp.list.item(i).data(Qt.UserRole) == _g["id"]][0]
_left = int(_tp.list.accessibleName().split("未完成 ")[1].split(" ")[0])
_true_left = sum(1 for t in _st.todos() if not todo_is_done(t))
check("计数与行勾选同口径（旧完成不复活的显示）",
      _tp.list.item(_it).checkState() == Qt.Checked and _left == _true_left,
      (_tp.list.accessibleName(), _true_left))
check("旧完成不再回今天视图",
      all(t["id"] != _g["id"] for t in _st.todo_view("today")))
_src = open(os.path.join(_pkg, "core", "content.py"), encoding="utf-8").read()
check("收起态轮播用统一口径", "if not todo_is_done(t)" in _src)

# 老数据不清洗：带 due / 带 repeat 的老记录照旧触发 due_todos
_old = _st.add_todo("老到点记录", _dt.now() - _td(hours=1), 0)
_hit = [t["id"] for t in _st.due_todos(_dt.now().timestamp() + 10)]
check("带 due 老记录仍触发提醒", _old["id"] in _hit, _hit)
_orep = _st.add_todo("老重复记录", _dt.now() - _td(days=3), 0b1111111)
check("带 repeat 老记录仍进 due_todos",
      _orep["id"] in [t["id"] for t in _st.due_todos()])

# 键位：空格勾选、Delete 删除 + Toast 撤销（id 不变）
_tp.list.setCurrentRow(0)
_k0 = _tp.list.currentItem().data(Qt.UserRole)
_t0 = _st.todo(_k0)["text"]
_before = bool(_st.todo(_k0).get("done_on"))
QTest.keyClick(_tp.list, Qt.Key_Space)
check("空格切换勾选", bool(_st.todo(_k0).get("done_on")) != _before)
# 勾选会触发整表重排，找回同一行再删
_i = [i for i in range(_tp.list.count())
      if _tp.list.item(i).data(Qt.UserRole) == _k0][0]
_tp.list.setCurrentRow(_i)
QTest.keyClick(_tp.list, Qt.Key_Delete)
check("Delete 删除选中行", _st.todo(_k0) is None)
check("删除弹出可点撤销", isl.toast._action is not None
      and isl.toast._action[0] == "撤销", isl.toast._text)
isl.toast._action[1]()
check("撤销回位且 id 不变", _st.todo(_k0) is not None
      and _st.todo(_k0)["text"] == _t0, _k0)
check("added_label 当天显示刚刚", added_label(time.time()) == "刚刚")

# 日历重复：纯规则 + store 推进
_mon = _dt(2026, 1, 5, 9, 0)                       # 周一
check("每周=同星期几",
      ev_occurrence(_mon, EV_R_WEEK, _d(2026, 1, 12)) == _dt(2026, 1, 12, 9)
      and ev_occurrence(_mon, EV_R_WEEK, _d(2026, 1, 13)) is None)
check("工作日跳周末",
      ev_occurrence(_mon, EV_R_WDAY, _d(2026, 1, 10)) is None
      and ev_occurrence(_mon, EV_R_WDAY, _d(2026, 1, 9)) == _dt(2026, 1, 9, 9))
check("每天=天天有", ev_occurrence(_mon, EV_R_DAILY, _d(2026, 12, 31))
      == _dt(2026, 12, 31, 9))
_j31 = _dt(2026, 1, 31, 20, 0)
check("每月月末钳位",
      ev_occurrence(_j31, EV_R_MONTH, _d(2026, 2, 28)) == _dt(2026, 2, 28, 20)
      and ev_occurrence(_j31, EV_R_MONTH, _d(2026, 2, 27)) is None
      and ev_occurrence(_j31, EV_R_MONTH, _d(2026, 3, 31)) == _dt(2026, 3, 31, 20))
check("闰年月末钳到29", ev_occurrence(_dt(2024, 1, 31, 20, 0), EV_R_MONTH,
      _d(2024, 2, 29)) == _dt(2024, 2, 29, 20))
check("next_occurrence 推进到匹配日",
      next_occurrence(_j31, EV_R_MONTH, _dt(2026, 2, 15, 12, 0),
                      horizon_days=30) == _dt(2026, 2, 28, 20))
check("不重复=只认原始日", ev_occurrence(_mon, 0, _d(2026, 1, 6)) is None
      and ev_occurrence(_mon, 0, _d(2026, 1, 5)) == _mon)

_d0 = _dt(2026, 11, 21, 20, 0)
_ev = _st.add_event("重复站会", _d0, remind=10, repeat=EV_R_DAILY)
_ts1 = _dt(2026, 11, 21, 19, 55).timestamp()
check("重复日程到点提醒", _ev["id"] in [e["id"] for e in _st.due_events(_ts1)])
_st.mark_event_reminded(_ev, _ts1)
check("重复日程每天只响一次", _ev["id"] not in [e["id"] for e in _st.due_events(_ts1)])
_ts2 = _dt(2026, 11, 22, 19, 55).timestamp()
check("重复日程次日再响", _ev["id"] in [e["id"] for e in _st.due_events(_ts2)])
check("月历/当日列表含重复项",
      any(e["id"] == _ev["id"] for e in _st.events_on(_d(2026, 11, 23))))
_ev2 = _st.add_event("一次性事", _d0, remind=10)
check("旧记录无 repeat 键按不重复", _ev2["id"] in [e["id"] for e in _st.due_events(_ts1)]
      and "repeat" not in _ev2)
_st.mark_event_reminded(_ev2, _ts1)
check("不重复只响一次", _ev2["id"] not in [e["id"] for e in _st.due_events(_ts1)]
      and _ev2["id"] not in [e["id"] for e in _st.due_events(_ts2)])

_dlg = EventDialog(_tp, _d.today(), sk_getter=isl.sk)
check("新建日程有重复行", [lbl for lbl, _v in _dlg.repeat._items]
      == ["不重复", "每天", "工作日", "每周", "每月"], _dlg.repeat._items)
check("新建日程标注非空", all(w.accessibleName() for w in
      (_dlg.title, _dlg.date, _dlg.time, _dlg.remind, _dlg.repeat)))
check("EventDialog.value 返回四项", len(_dlg.value()) == 4)
_sstore = open(os.path.join(_pkg, "infra", "store.py"), encoding="utf-8").read()
check("ics 导入路径不写 repeat（互不覆盖）", "add_event(title, s, remind=10)" in _sstore)
_spage = open(os.path.join(_pkg, "modules", "calendar.py"), encoding="utf-8").read()
check("新建日程写入 repeat", "add_event(title, start, remind, repeat=repeat)" in _spage)
_deb = open(os.path.join(ROOT, "packaging", "build_deb.sh"), encoding="utf-8").read()
check("启动脚本导出 QT_ACCESSIBILITY=1", "export QT_ACCESSIBILITY=1" in _deb)

# ── 1.4.6 专注页底行：开始/暂停靠左、重置靠右、统计居中 ─────────────────
isl.goto(1)
_spin(20)
_fp = isl.provider("focus")
_fp.refresh_stat()
_spin(5)
_pc = _fp.width() // 2
check("专注统计落在页面正中",
      abs(_fp.stat.geometry().center().x() - _pc) <= 1,
      (_fp.stat.geometry().center().x(), _pc))
check("重置贴内容右缘",
      _fp.btn_reset.x() + _fp.btn_reset.width() == _fp.width() - CONTENT_PAD_X,
      (_fp.btn_reset.x() + _fp.btn_reset.width(), _fp.width() - CONTENT_PAD_X))
check("开始/暂停贴内容左缘", _fp.btn.x() == CONTENT_PAD_X,
      (_fp.btn.x(), CONTENT_PAD_X))
check("专注页底行标注非空",
      all(_w.accessibleName() for _w in (_fp.btn, _fp.btn_reset, _fp.stat)),
      [_w.accessibleName() for _w in (_fp.btn, _fp.btn_reset, _fp.stat)])

# ── 1.4.7/1.4.8 饮水页：梯形水杯，放大但封顶不成桶、杯口不填色 ─────────
isl.goto(2)
_spin(20)
_wp = isl.provider("water")
for _ in range(5):
    _wp.add(1)
_spin(5)
_cs = _wp.cups.cell_rects()
_cols, _rows = _wp.cups._grid()
_w0 = _cs[0][0].width()
_h0 = _cs[0][0].height()
check("杯区仍吃掉页面剩余高度(>=140)", _wp.cups.height() >= 140,
      (_wp.cups.height(), _wp.cups.geometry()))
check("杯子折成多行而不是挤成一排", _cols <= 4 and _rows >= 2, (_cols, _rows))
check("单杯比旧版(28x35)大一档",
      all(38 <= r.width() <= _wp.cups.CUP_MAX_W + 0.01 for r, _f in _cs)
      and all(r.height() >= 48 for r, _f in _cs),
      (_w0, _h0, _wp.cups.CUP_MAX_W))
check("单杯封顶：不铺满格子，宽<=44",
      _w0 <= _wp.cups.CUP_MAX_W + 0.01, (_w0, _wp.cups.CUP_MAX_W))
check("竖杯不是桶：高比宽至少多 25%",
      _h0 >= _w0 * 1.25, (_w0, _h0, _h0 / _w0))
check("梯形：下底比上边窄至少 15%",
      _wp.cups.TAPER >= 0.08 and
      all(r.width() * (1 - 2 * _wp.cups.TAPER) < r.width() * 0.85 for r, _f in _cs),
      (_wp.cups.TAPER, _cs[0][0].width(),
       _cs[0][0].width() * (1 - 2 * _wp.cups.TAPER)))
check("相邻杯间隙封顶（不被拉散）",
      (_cs[1][0].left() - _cs[0][0].right()) <= _wp.cups.MAX_GAP + 0.01 and
      (_cs[_cols][0].top() - _cs[0][0].bottom()) <= _wp.cups.MAX_GAP + 0.01,
      (_cs[1][0].left() - _cs[0][0].right(),
       _cs[_cols][0].top() - _cs[0][0].bottom(), _wp.cups.MAX_GAP))
check("整组左右留白对称，且不小于间隙以外贴边",
      abs(_cs[0][0].left() - (_wp.cups.width() - _cs[3][0].right())) <= 0.6 and
      _cs[0][0].left() >= _wp.cups.EDGE - 0.1,
      (_cs[0][0].left(), _wp.cups.width() - _cs[3][0].right()))
check("整组上下留白对称",
      abs(_cs[0][0].top() - (_wp.cups.height() - _cs[-1][0].bottom())) <= 0.6,
      (_cs[0][0].top(), _wp.cups.height() - _cs[-1][0].bottom()))
check("整只杯子（含杯口）不越出杯区，第一行不被裁",
      all(r.top() >= 0 and r.bottom() <= _wp.cups.height() and r.left() >= 0
          for r, _f in _cs),
      [(r.x(), r.y(), r.bottom(), _wp.cups.height()) for r, _f in _cs[:1]])
_im = _wp.cups.grab().toImage()
_empty = [(_r, _f) for _r, _f in _cs if not _f][0][0]
_my = int(_empty.top() + _empty.width() * 0.05)      # 杯口椭圆上半部内侧
_in = _im.pixelColor(int(_empty.center().x()), _my)
_out = _im.pixelColor(int(_empty.left()) - 4, _my)   # 同一行的杯外空白
check("杯口不填色：空杯杯口内与杯外同色（1.4.7 的 card 补丁消失）",
      max(abs(_in.red() - _out.red()), abs(_in.green() - _out.green()),
          abs(_in.blue() - _out.blue())) <= 8,
      ((_in.red(), _in.green(), _in.blue()),
       (_out.red(), _out.green(), _out.blue())))
check("描边仍在（同张图上取得到杯子墨迹）",
      any(_im.pixelColor(int(_r.center().x()),
                         int(_r.bottom()) - 3).blue() > 60
          for _r, _f in _cs if _f),
      [_im.pixelColor(int(_cs[0][0].center().x()),
                      int(_cs[0][0].bottom()) - 3).name()])
check("饮水页标注非空",
      all(_w.accessibleName() for _w in
          (_wp.big, _wp.cups, _wp.btn_add, _wp.btn_sub, _wp.info)),
      [_w.accessibleName() for _w in (_wp.big, _wp.cups, _wp.info)])
check("统计字号走样式表且收到 16px",
      "font-size: 16px" in _wp.big.styleSheet(), _wp.big.styleSheet())

# ── 1.4.9 文件中转站顶栏：左添加文件、中文案、右清空 ──────────────────
isl.goto(3)
_spin(20)
_sp = isl.provider("shelf")
_pw = _sp.width()
check("添加文件贴内容左缘", _sp.btn.x() == CONTENT_PAD_X,
      (_sp.btn.x(), _sp.geometry()))
check("清空贴内容右缘", abs(_sp.btn_clear.x() + _sp.btn_clear.width()
                        - (_pw - CONTENT_PAD_X)) <= 2,
      (_sp.btn_clear.x() + _sp.btn_clear.width(), _pw - CONTENT_PAD_X))
check("提示文案落在顶栏正中",
      abs((_sp.tip.x() + _sp.tip.width() / 2.0) - _pw / 2.0) <= 2.0,
      (_sp.tip.x(), _sp.tip.width(), _pw / 2.0))
check("顶栏在列表上方（y 小于列表）", _sp.btn.y() < _sp.list.y(),
      (_sp.btn.y(), _sp.list.y()))
check("空站时清空置灰", not _sp.btn_clear.isEnabled(),
      (_sp.btn_clear.isEnabled(), _sp.list.count()))
_tmp1 = os.path.join(os.environ["FUYU_HOME"], "中转A.txt")
_tmp2 = os.path.join(os.environ["FUYU_HOME"], "中转B.txt")
io.open(_tmp1, "w").close()
io.open(_tmp2, "w").close()
_sp.add([_tmp1, _tmp2])
_spin(5)
check("两条条目进站且清空可用", _sp.list.count() == 2 and _sp.btn_clear.isEnabled(),
      (_sp.list.count(), _sp.btn_clear.isEnabled()))
_gone = _sp.store.shelf_clear()
_sp.refresh()
check("清空只移走条目、不删磁盘文件",
      _sp.list.count() == 0 and os.path.exists(_tmp1) and os.path.exists(_tmp2),
      (_sp.list.count(), os.path.exists(_tmp1), os.path.exists(_tmp2)))
_sp.store.shelf_restore(_gone)
_sp.refresh()
check("撤销原序放回", [s["path"] for s in _sp.store.shelf()] ==
      [g["path"] for g in _gone], (_gone, _sp.store.shelf()))
check("中转站顶栏标注非空",
      all(_w.accessibleName() for _w in (_sp.btn, _sp.btn_clear, _sp.tip)),
      [_w.accessibleName() for _w in (_sp.btn, _sp.btn_clear, _sp.tip)])
# 顶栏为什么是两行：把账算进守护里。_CW = 真机内容宽 = 面板 378 − 面板内缘 12×2
# − 页面 contentsMargins CONTENT_PAD_X×2（1.4.14 起水平边距归 0）= 354
# （offscreen 页面自身报 640 默认宽，取不得），所以按真机宽算。
# 1.4.14 内容列加宽 24px 后，"同排放不下"其实变成了"勉强放得下"：余量只有
# 十几个像素，不到两个汉字宽，真机字体比 offscreen 略宽就会挤成省略号。
# 版式因此不动（仍是两行），这条守护改成"余量必须小于两字宽"——将来文案改短
# 或按钮改窄到余量 ≥ 两字宽，它会 FAIL，提醒回来复评要不要合排。
_CW = EXPANDED.width() - 12 * 2 - CONTENT_PAD_X * 2
_tip_ink = _sp.tip.fontMetrics().width(_sp.tip.text())
_row_left = _CW - _sp.btn.sizeHint().width() - _sp.btn_clear.sizeHint().width() - 12
_char_w = _sp.tip.fontMetrics().width("字")
check("文案走 QSS 的 muted 字号(11px)", _sp.tip.font().pixelSize() == 11,
      (_sp.tip.font().pixelSize(),))
check("同排余量 < 两字宽 ⇒ 维持两行版式",
      0 <= _row_left - _tip_ink < 2 * _char_w,
      (_tip_ink, _row_left, _row_left - _tip_ink, _char_w, _CW))
check("两行制下文案按真机宽仍是单行", _sp.tip.heightForWidth(_CW) <= 18,
      (_sp.tip.heightForWidth(_CW), _sp.tip.heightForWidth(_row_left)))

# ── 1.4.10 剪贴板：每行行尾的钉子（固定/置顶），文案删掉「右键可固定」───
from qilin_island.modules.widgets import (ClipPinDelegate, PIN_GLYPH,          # noqa: E402
                                          PIN_HIT_W, PIN_ROLE)
isl.goto(4)
_spin(20)
_cl = isl.provider("clipboard")
check("提示文案只留前半句", _cl.tip.text() == "最近 30 条文字，点击复制",
      _cl.tip.text())
check("提示文案不再提右键", "右键" not in _cl.tip.text(), _cl.tip.text())
check("钉子委托已挂上", isinstance(_cl.list.itemDelegate(), ClipPinDelegate),
      type(_cl.list.itemDelegate()).__name__)
_LONG = "很长的剪贴板内容" * 30
for _t in ("钉子甲", _LONG, "钉子丙"):
    _cl.store.clip.add(_t)
_cl.refresh()
_n = _cl.list.count()
check("三条都在列", _n >= 3, _n)
check("正文不再靠 ★ 表状态",
      not any(_cl.list.item(_i).text().startswith("★") for _i in range(_n)),
      [_cl.list.item(_i).text()[:10] for _i in range(_n)])
check("条目存的是原文，省略改到 paint 时算",
      all("…" not in _cl.list.item(_i).text() for _i in range(_n)),
      [_cl.list.item(_i).text()[-3:] for _i in range(_n)])
_vp = _cl.list.viewport().geometry().topLeft()
_rows = []
for _i in range(_n):
    _r = QRect(_cl.list.visualItemRect(_cl.list.item(_i)))
    _rows.append((_r, ClipPinDelegate.pin_rect(_r)))
check("钉子热区宽 %d 且贴行右缘" % PIN_HIT_W,
      all(abs(_p.right() - _r.right()) <= 1.0 and abs(_p.width() - PIN_HIT_W) <= 0.01
          for _r, _p in _rows),
      [(round(_p.width(), 1), round(_p.right() - _r.right(), 1)) for _r, _p in _rows[:3]])
_fm = _cl.list.fontMetrics()
check("正文按当前行宽切，不侵入钉子热区",
      all(_fm.width(_cl.delegate.elided(_cl.list.item(_i).text(), _fm, _rows[_i][0]))
          <= _rows[_i][0].width() - PIN_HIT_W - 5 for _i in range(_n)),
      [(_fm.width(_cl.delegate.elided(_cl.list.item(_i).text(), _fm, _rows[_i][0])),
        _rows[_i][0].width()) for _i in range(_n)])
check("长文案确实是被切过的（原文比行宽长得多）",
      _fm.width(_LONG) > 3 * _rows[0][0].width()
      and _fm.width(_cl.delegate.elided(_LONG, _fm, _rows[0][0]))
      <= _rows[0][0].width() - PIN_HIT_W - 5,
      (_fm.width(_LONG), _rows[0][0].width(),
       _fm.width(_cl.delegate.elided(_LONG, _fm, _rows[0][0]))))
check("行高容得下 %dpx 钉子" % PIN_GLYPH,
      all(_p.height() >= PIN_GLYPH for _r, _p in _rows),
      [round(_p.height(), 1) for _r, _p in _rows[:3]])

# 数像素前把皮肤钉成 deep：跑到这里时前面「设置框」那条用例已把皮肤留在 cream
# （亮色）。亮色下 pin_ink 是深色正文墨、卡片底接近白，"数白墨"会数到背景上去，
# 实心/描边两态的大小关系也可能反过来。1.4.13 的用户口径本来就是深色面板，
# 深色态才是这轮的验收对象；本节末尾把皮肤拨回去，后面的用例不受影响。
_skin_prev13 = isl.store.settings.get("skin", "deep")
isl.store.settings["skin"] = "deep"
isl.apply_skin()
_spin(4)
_img = _cl.list.grab().toImage()
_acc = T.c(isl.sk(), "accent")
_AR, _AG, _AB = _acc.red(), _acc.green(), _acc.blue()


def _accent_px(_p):
    """数热区里的 accent 像素（1.4.13 起图钉不再用 accent，这条变成「必须为 0」的
    回归守护：accent 若又回到钉子身上，说明 widgets.py 里的墨色被人改回去了）"""
    _x0 = max(0, int(_p.left()) + _vp.x())
    _x1 = min(_img.width() - 1, int(_p.right()) + _vp.x())
    _y0 = max(0, int(_p.top()) + _vp.y())
    _y1 = min(_img.height() - 1, int(_p.bottom()) + _vp.y())
    _hit = 0
    for _yy in range(_y0, _y1 + 1):
        for _xx in range(_x0, _x1 + 1):
            _c = _img.pixel(_xx, _yy)
            if (abs(((_c >> 16) & 255) - _AR) <= 40 and abs(((_c >> 8) & 255) - _AG) <= 40
                    and abs((_c & 255) - _AB) <= 40):
                _hit += 1
    return _hit


def _white_px(_p):
    """数热区里的白墨像素（1.4.13 图钉墨色：深色皮肤纯白）。
    白离这套皮肤的任何 token 都 >=100，容差 45 只会数到图案本体，不会数到底色。"""
    _x0 = max(0, int(_p.left()) + _vp.x())
    _x1 = min(_img.width() - 1, int(_p.right()) + _vp.x())
    _y0 = max(0, int(_p.top()) + _vp.y())
    _y1 = min(_img.height() - 1, int(_p.bottom()) + _vp.y())
    _hit = 0
    for _yy in range(_y0, _y1 + 1):
        for _xx in range(_x0, _x1 + 1):
            _c = _img.pixel(_xx, _yy)
            if ((((_c >> 16) & 255) - 255) ** 2 + (((_c >> 8) & 255) - 255) ** 2
                    + ((_c & 255) - 255) ** 2) ** 0.5 <= 45:
                _hit += 1
    return _hit


_cid0 = _cl.list.item(0).data(Qt.UserRole)[0]
_r0, _p0 = _rows[0]
_opt0 = QStyleOptionViewItem()
_opt0.rect = _r0
_idx0 = _cl.list.model().index(0, 0)
_px_off = _accent_px(_p0)
_w_off = _white_px(_p0)
_ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(_p0.center()), Qt.LeftButton,
                  Qt.NoButton, Qt.NoModifier)
check("点钉子由委托接管（不会顺手复制）",
      _cl.delegate.editorEvent(_ev, _cl.list.model(), _opt0, _idx0) is True, None)
check("点钉子后该行 pinned=1",
      dict((_c, _p) for _c, _t, _s, _p in _cl.store.clip.items())[_cid0] == 1, _cid0)
_cl.refresh()
_img = _cl.list.grab().toImage()
_px_on = _accent_px(_p0)
_w_on = _white_px(_p0)
# 1.4.13：图钉换成用户给的 SVG 图标 + 白墨，状态只靠填充区分。实测（330 宽真行）
# 未固定 14px 描边 39 像素、已固定 14px 实心 48 像素，热区里 accent 一个都没有。
check("固定行是白实心、未固定行是白描边（实心像素多于描边）",
      _w_off >= 20 and _w_on > _w_off, (_w_off, _w_on))
check("图钉热区不出现 accent（accent 只留给顶栏钉住态的描边环）",
      _px_off == 0 and _px_on == 0, (_px_off, _px_on))
_ev2 = QMouseEvent(QEvent.MouseButtonRelease, QPointF(_r0.left() + 20.0, _r0.center().y()),
                   Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
check("点正文不接管事件（仍走点击复制）",
      _cl.delegate.editorEvent(_ev2, _cl.list.model(), _opt0, _idx0) is False, None)
# 长文案行：正文右缘与钉子左缘之间那 6px 必须干净，压上了就说明 elide 口径又分叉了
_long_i = [i for i in range(_n) if _cl.list.item(i).text().startswith("很长的剪贴板内容")]
_gap_px = -1
if _long_i:
    _li = _long_i[0]
    _lr = _cl.list.visualItemRect(_cl.list.item(_li))
    _tr = ClipPinDelegate.text_rect(_lr)
    _pr2 = ClipPinDelegate.pin_rect(_lr)
    _gx0 = int(_tr.right()) + 1 + _vp.x()
    _gx1 = int(_pr2.left()) - 1 + _vp.x()
    _gy0 = int(_lr.top()) + _vp.y()
    _gy1 = int(_lr.bottom()) + _vp.y()
    _bg = _img.pixel(3, 3)          # 卡片底色取样点
    _gap_px = 0
    for _yy in range(_gy0, min(_img.height(), _gy1 + 1)):
        for _xx in range(_gx0, max(_gx0, _gx1) + 1):
            _c = _img.pixel(_xx, _yy)
            if (abs((( _c >> 16) & 255) - ((_bg >> 16) & 255)) > 60 or
                    abs(((_c >> 8) & 255) - ((_bg >> 8) & 255)) > 60 or
                    abs((_c & 255) - (_bg & 255)) > 60):
                _gap_px += 1
check("长文案行正文与钉子之间 6px 间隙无墨（没压住钉子）",
      bool(_long_i) and _gap_px == 0, (_long_i, _gap_px))
_cap = []
_cl.notify = lambda *a, **k: _cap.append(a)
_cl.toggle_pin(_cid0)
check("取消固定有 Toast 反馈", bool(_cap) and _cap[-1][0] == "已取消固定",
      _cap[-1] if _cap else None)
_cl.toggle_pin(_cid0)
check("固定有 Toast 反馈", _cap[-1][0] == "已固定", _cap[-1])
_it0 = _cl.list.item(0)
_ax = _it0.data(Qt.AccessibleTextRole)
check("读屏文本带固定态且不是被省略号截断的预览",
      ("已固定" in _ax or "未固定" in _ax) and "…" not in _ax, _ax[:48])
check("钉子状态位与 store 一致（委托只读 PIN_ROLE）",
      bool(_it0.data(PIN_ROLE)) == bool(dict((_c, _p) for _c, _t, _s, _p
                                             in _cl.store.clip.items())[_it0.data(Qt.UserRole)[0]]),
      (_it0.data(PIN_ROLE), _it0.data(Qt.AccessibleTextRole)[-6:]))
check("剪贴板页标注非空",
      all(_w.accessibleName() for _w in (_cl.tip, _cl.btn_clear, _cl.list)),
      [_w.accessibleName() for _w in (_cl.tip, _cl.btn_clear, _cl.list)])
_cl.store.clip.pin(_cid0, 1)
for _i2 in range(40):
    _cl.store.clip.add("淘汰测试%02d" % _i2)
_items = list(_cl.store.clip.items())
_pin_first = [(_c, _p) for _c, _t, _s, _p in _items]
_unfixed = len([1 for _c, _t, _s, _p in _items if not _p])
check("固定项不被 30 条上限挤掉",
      _cid0 in [c for c, p in _pin_first if p] and _unfixed <= 30,
      (_cid0 in [c for c, p in _pin_first if p], _unfixed, len(_items)))
check("固定项排在最前",
      all(_p for _c, _t, _s, _p in _items[:max(1, len([1 for x in _pin_first if x[1]]))]),
      [_p for _c, _t, _s, _p in _items[:4]])

# ── 1.4.11 / 1.4.13 顶栏右上角钉子：1.4.13 起画的是用户给的 SVG 图钉，墨色改白 ──
import inspect                                                          # noqa: E402
from PyQt5.QtGui import QColor                                          # noqa: E402
from qilin_island.infra import svgpath as _SV                           # noqa: E402
from qilin_island.modules.widgets import ClipPinDelegate as _CPD        # noqa: E402
from qilin_island.modules.widgets import (PIN_ASSET, PIN_STROKE,        # noqa: E402
                                          PinGlyphButton, paint_pin)

_pb = isl.btn_pin
check("顶栏钉子是自绘按钮", isinstance(_pb, PinGlyphButton), type(_pb).__name__)
check("顶栏不再显示「钉」字", _pb.text() == "", repr(_pb.text()))
check("顶栏钉子提示仍是「常驻展开」", _pb.toolTip() == "常驻展开", _pb.toolTip())
check("顶栏钉子有读屏名", _pb.accessibleName() != "", _pb.accessibleName())
check("顶栏钉子热区 %d×24" % PIN_HIT_W,
      (_pb.width(), _pb.height()) == (PIN_HIT_W, 24), (_pb.width(), _pb.height()))
check("顶栏钉子可勾选且初值跟配置一致",
      _pb.isCheckable() and _pb.isChecked() == bool(isl.store.settings.get("pinned")),
      (_pb.isChecked(), isl.store.settings.get("pinned")))
check("顶栏与剪贴板共用同一份钉子绘制", "paint_pin(" in inspect.getsource(_CPD._pin),
      inspect.getsource(_CPD._pin))
check("钉子绘制走 SVG 素材解析（本机没有 QtSvg，只能自己解 path）",
      "load_asset(" in inspect.getsource(paint_pin), inspect.getsource(paint_pin))
check("顶栏与行尾用同一份素材", _pb.property("pin") == "true" and PIN_ASSET == "pushpin.svg",
      (_pb.property("pin"), PIN_ASSET))

_skd = isl.sk()          # 上面已把皮肤钉成 deep，这里取的就是要验收的那套


def _pin_canvas():
    """把按钮合成到真机面板底色上再数像素。
    grab() 出来的图胶囊外是透明，透明黑会被当成深色墨，未钉住那态没法比。"""
    _img = QImage(_pb.width(), _pb.height(), QImage.Format_RGB32)
    _img.fill(T.c(_skd, "bg1"))
    _p = QPainter(_img)
    _pb.render(_p, QPoint(0, 0))
    _p.end()
    return _img


def _ink(_img, _tgt, _tol, _x0=4, _x1=21, _y0=2, _y1=21):
    """在图案可能出现的窗口内数墨色像素，返回（像素数, bbox）"""
    _xs, _ys = [], []
    for _y in range(_y0, _y1 + 1):
        for _x in range(_x0, _x1 + 1):
            _q = QColor.fromRgb(_img.pixel(_x, _y))
            if (((_q.red() - _tgt[0]) ** 2 + (_q.green() - _tgt[1]) ** 2
                 + (_q.blue() - _tgt[2]) ** 2) ** 0.5) <= _tol:
                _xs.append(_x)
                _ys.append(_y)
    return len(_xs), ((min(_xs), max(_xs), min(_ys), max(_ys)) if _xs else None)


def _bbox_wh(_bb):
    return None if _bb is None else (_bb[1] - _bb[0] + 1, _bb[3] - _bb[2] + 1)


# 素材解析本身：形状对不对、缩放居中对不对、解析器各命令对不对（没有 QtSvg 兜底，
# 这层是唯一能保证「用户给的那个图标就是我们画的那个」的地方）
_src, _vb = _SV.load_asset(PIN_ASSET)
check("SVG viewBox 24×24", (_vb.x(), _vb.y(), _vb.width(), _vb.height())
      == (0.0, 0.0, 24.0, 24.0), (_vb.x(), _vb.y(), _vb.width(), _vb.height()))
check("SVG 解析出 32 个路径元素", _src.elementCount() == 32, _src.elementCount())
_srcbb = _src.boundingRect()
check("SVG 图钉在 viewBox 里是偏心的（所以缩放按图形 bbox，不按 viewBox）",
      (round(_srcbb.x(), 2), round(_srcbb.y(), 2), round(_srcbb.width(), 2),
       round(_srcbb.height(), 2)) == (5.36, 1.38, 15.88, 18.76),
      (round(_srcbb.x(), 2), round(_srcbb.y(), 2), round(_srcbb.width(), 2),
       round(_srcbb.height(), 2)))
check("素材按 mtime 缓存（每帧重读文件会拖慢绘制）",
      _SV.load_asset(PIN_ASSET)[0] is _src, _SV.load_asset(PIN_ASSET)[0] is _src)
_c16 = _SV.scaled_into(_src, _vb, QRectF(0, 0, 26, 24), 16.0).boundingRect()
check("scaled_into：最长边缩到 16 且图形中心对齐盒子中心",
      abs(max(_c16.width(), _c16.height()) - 16.0) < 0.01
      and abs(_c16.center().x() - 13.0) < 0.01 and abs(_c16.center().y() - 12.0) < 0.01,
      (round(_c16.width(), 2), round(_c16.height(), 2),
       round(_c16.center().x(), 2), round(_c16.center().y(), 2)))
check("解析 M/L/Z", _SV.path_from_d("M2 3 L9 3 L9 10 Z").boundingRect().getRect()
      == (2, 3, 7, 7), _SV.path_from_d("M2 3 L9 3 L9 10 Z").boundingRect().getRect())
check("解析相对坐标与隐式续段（m 后的裸数字续成 l）",
      _SV.path_from_d("m2 3 l7 0 0 7").boundingRect().getRect() == (2, 3, 7, 7),
      _SV.path_from_d("m2 3 l7 0 0 7").boundingRect().getRect())
check("解析 A：端点参数→中心参数，r10 半拱高 10",
      abs(_SV.path_from_d("M2 12 A10 10 0 0 1 22 12").boundingRect().height() - 10.0) < 0.05,
      _SV.path_from_d("M2 12 A10 10 0 0 1 22 12").boundingRect().height())
_rt = _SV.transform_from("rotate(45 12 12)").map(QPointF(12, 2))
check("transform rotate 带旋转中心",
      abs(_rt.x() - (12 + 10 * math.sin(math.pi / 4))) < 1e-6
      and abs(_rt.y() - (12 - 10 * math.cos(math.pi / 4))) < 1e-6, (_rt.x(), _rt.y()))
check("transform matrix 六参数",
      _SV.transform_from("matrix(2 0 0 2 1 1)").map(QPointF(0, 0)) == QPointF(1, 1),
      _SV.transform_from("matrix(2 0 0 2 1 1)").map(QPointF(0, 0)))
check("transform 列表按 SVG 语义左→右复合（先 scale 再 translate）",
      _SV.transform_from("translate(4 0) scale(2)").map(QPointF(1, 1)) == QPointF(6, 2),
      _SV.transform_from("translate(4 0) scale(2)").map(QPointF(1, 1)))

_A = T.c(_skd, "accent")
_ACC = (_A.red(), _A.green(), _A.blue())
_C2 = T.c(_skd, "text2")
_T2 = (_C2.red(), _C2.green(), _C2.blue())
_WHT = (255, 255, 255)
_pb.setChecked(False)
_pb.repaint()
_off_img = _pin_canvas()
_n_w_off, _bb_off = _ink(_off_img, _WHT, 45)
check("未钉住：图钉是白描边（>=20 像素）", _n_w_off >= 20, _n_w_off)
check("未钉住：图案 bbox 14×16（顶栏最长边 16px）",
      _bbox_wh(_bb_off) == (14, 16), _bbox_wh(_bb_off))
check("未钉住：一个 accent 像素都没有（描边环只在钉住态出现）",
      _ink(_off_img, _ACC, 45, 0, 25, 0, 23)[0] == 0,
      _ink(_off_img, _ACC, 45, 0, 25, 0, 23)[0])
# 旧的 text2 描边墨必须真退场。容差只能收到 8：白↔card 的抗锯齿过渡带正好穿过
# text2 附近（50% 混合 ≈ (141,152,159)，对 text2 (143,165,180) 距离 25），
# 容差 45 会把这圈边缘像素误当成旧墨。
check("未钉住：旧 text2 墨已退场（容差 8 数到 0）", _ink(_off_img, _T2, 8)[0] == 0,
      _ink(_off_img, _T2, 8)[0])
_ref = QImage(_pb.width(), _pb.height(), QImage.Format_RGB32)
_ref.fill(T.c(_skd, "bg1"))
_rp = QPainter(_ref)
_rp.setRenderHint(QPainter.Antialiasing, True)   # 与 PinGlyphButton.paintEvent 同一套
paint_pin(_rp, QRectF(0.0, 0.0, float(_pb.width()), float(_pb.height())),
          False, T.pin_ink(_skd), PinGlyphButton.GLYPH)
_rp.end()
check("paint_pin 单独画的与按钮上那枚同一 bbox",
      _bbox_wh(_ink(_ref, _WHT, 45)[1]) == _bbox_wh(_bb_off),
      (_bbox_wh(_ink(_ref, _WHT, 45)[1]), _bbox_wh(_bb_off)))
_inkv = T.ink_over(T.c(_skd, "accent"), _skd)
_pb.setChecked(True)
_pb.repaint()
_on_img = _pin_canvas()
_n_w_on, _bb_on = _ink(_on_img, _WHT, 45)
_n_ring = _ink(_on_img, _ACC, 45, 0, 25, 0, 23)[0]
check("钉住：白实心像素多于描边态（>=40）", _n_w_on >= 40 and _n_w_on > _n_w_off,
      (_n_w_off, _n_w_on))
check("钉住：图案 bbox 12×14（实心填轮廓，bbox 比描边小一圈）",
      _bbox_wh(_bb_on) == (12, 14), _bbox_wh(_bb_on))
# 用户选的方案是「白实心 + accent 描边环」：环是一圈 1px，26×24 周长 ≈ 96px，
# 实测 39 个 accent 像素；铺满整块胶囊底的老写法是 200+ 像素，两边都留余量。
check("钉住：accent 只描一圈环（20~80 像素，不是整块 accent 底）",
      20 <= _n_ring <= 80, _n_ring)
check("钉住态旧深色墨（ink_over(accent)）已让位给白",
      _ink(_on_img, (_inkv.red(), _inkv.green(), _inkv.blue()), 8)[0] <= 2,
      _ink(_on_img, (_inkv.red(), _inkv.green(), _inkv.blue()), 8)[0])
check("两态图案中心一致（钉住不偏移）",
      (_bb_off[0] + _bb_off[1]) == (_bb_on[0] + _bb_on[1])
      and (_bb_off[2] + _bb_off[3]) == (_bb_on[2] + _bb_on[3]), (_bb_off, _bb_on))
_qss13 = global_qss(_skd)
check("钉住态 QSS 四态齐全（静止/hover/pressed/focus）",
      all(_k in _qss13 for _k in ('QPushButton[nav="true"][pin="true"]:checked {',
                                  'QPushButton[nav="true"][pin="true"]:checked:hover',
                                  'QPushButton[nav="true"][pin="true"]:checked:pressed',
                                  'QPushButton[nav="true"][pin="true"]:checked:focus')),
      [ln for ln in _qss13.splitlines() if 'pin="' in ln][:1])
check("钉住态静止规则：白墨 + card 底 + 1px accent 环（逐 token 校）",
      ('QPushButton[nav="true"][pin="true"]:checked { color: %s; background: %s;'
       % (tokens(_skd)["pin_ink"], tokens(_skd)["card"])) in _qss13
      and ("border: 1px solid %s;" % tokens(_skd)["accent"]) in _qss13,
      [ln for ln in _qss13.splitlines()
       if 'pin="true"]:checked {' in ln or 'pin="true"]:checked' in ln][:1])
# 八套皮肤逐个算：图钉本体贴在面板底（顶栏）和卡片底（行尾）上，两都得 >=3。
# 老写法（line 色描边）对 card 只有 1.1，等于看不见；白对 accent 又只有 1.93，
# 所以钉住态不能铺 accent 底——这条把设计约束本身钉住。
check("八套皮肤：图钉墨色对面板底对比度 >= 3",
      all(T.contrast(T.pin_ink(T.skin(s)), T.c(T.skin(s), "bg1")) >= 3.0
          for s in T.SKIN_ORDER),
      [(s, round(T.contrast(T.pin_ink(T.skin(s)), T.c(T.skin(s), "bg1")), 2))
       for s in T.SKIN_ORDER])
check("八套皮肤：图钉墨色对卡片底对比度 >= 3",
      all(T.contrast(T.pin_ink(T.skin(s)), T.c(T.skin(s), "card")) >= 3.0
          for s in T.SKIN_ORDER),
      [(s, round(T.contrast(T.pin_ink(T.skin(s)), T.c(T.skin(s), "card")), 2))
       for s in T.SKIN_ORDER])
_light13 = [s for s in T.SKIN_ORDER if T.is_light(s)]
_wht_skins = sorted(s for s in T.SKIN_ORDER
                    if T.pin_ink(T.skin(s)) == QColor("#ffffff"))
check("深色皮肤图钉纯白、浅色皮肤退回正文墨（分组成员由底色亮度算，不写死皮肤名）",
      _wht_skins == sorted(set(T.SKIN_ORDER) - set(_light13)) and len(_light13) == 2,
      (_light13, _wht_skins))
check("两套浅色皮肤：白墨压不住（对白底对比 1.0），所以用该皮肤正文墨",
      all(T.contrast(QColor("#ffffff"), T.c(T.skin(s), "bg1")) < 3.0
          and T.pin_ink(T.skin(s)) == T.c(T.skin(s), "text") for s in _light13),
      [(s, round(T.contrast(QColor("#ffffff"), T.c(T.skin(s), "bg1")), 2))
       for s in _light13])
check("顶栏钉住态不能铺整块 accent 底：默认皮肤 deep 上白墨对 accent 只有 1.93",
      T.contrast(QColor("#ffffff"), T.c(T.skin("deep"), "accent")) < 3.0,
      [(s, round(T.contrast(QColor("#ffffff"), T.c(T.skin(s), "accent")), 2))
       for s in T.SKIN_ORDER])
check("描边粗细 %gpx 在 12~16px 图标上不断线" % PIN_STROKE, PIN_STROKE >= 1.0, PIN_STROKE)
isl.store.settings["skin"] = _skin_prev13
isl.apply_skin()

# 行为：钉住后鼠标离开不收起；取消钉住后照旧收起
isl.expand()
_orig = isl._cursor_inside
isl._cursor_inside = lambda: False
isl._hover_at = 0.0
_pb.setChecked(True)
isl.toggle_pin()
isl._maybe_collapse()
check("钉住 + 鼠标在外：面板不收起不折叠", isl.expanded, isl.expanded)
check("钉住已落盘", Store().settings.get("pinned") is True, Store().settings.get("pinned"))
_pb.setChecked(False)
isl.toggle_pin()
isl.expand()
isl._hover_at = 0.0
isl._maybe_collapse()
check("取消钉住 + 鼠标在外：照旧收起", not isl.expanded, isl.expanded)
check("取消钉住也落盘", Store().settings.get("pinned") is False,
      Store().settings.get("pinned"))
isl._cursor_inside = _orig
isl.expand()

# ── 1.4.12 待办页：删掉底部计数行，列表拉到页面最下面 ─────────────────
_tp = isl.provider("todo")
_pg12 = isl.current_index()
isl.goto(0)                    # 待办页必须真显示：offscreen 下隐藏页不重算几何
_morph_frames(isl.expand)          # 让布局跑一遍，否则量不到页面真实高度
_v12 = _tp.layout()
check("待办页只剩两个条目（第一行 + 列表）", _v12.count() == 2, _v12.count())
check("列表是页面最后一项", _v12.itemAt(1).widget() is _tp.list,
      type(_v12.itemAt(1).widget()).__name__)
check("列表仍吃掉全部剩余高度（stretch=1）", _v12.stretch(1) == 1, _v12.stretch(1))
check("页面下边距 10→6", _v12.contentsMargins().bottom() == 6,
      [_v12.contentsMargins().left(), _v12.contentsMargins().top(),
       _v12.contentsMargins().right(), _v12.contentsMargins().bottom()])
check("页面上再无「未完成」字样",
      not any(isinstance(_w, QLabel) and "未完成" in _w.text()
              for _w in _tp.findChildren(QLabel)),
      [_w.text() for _w in _tp.findChildren(QLabel)])
# 纵向账目不写死，改成真实测量。offscreen 两个陷阱：
# ①isl.expand()/resize() 不会把页面重排成面板尺寸，页面停在宿主给的 (176,5) 假尺寸，
#   量到的高度全是假的；必须先把待办页钉成面板里的真实尺寸（354×300）；
# ②隐藏页（当前页签不是待办）根本不算几何，activate() 也白搭，量到的是上一轮的残留
#   值 216——所以前面先 isl.goto(0) 把待办页切到当前，再 activate()+processEvents
#   循环到两次几何完全一致才算数。
def _settle12(_w, _l, _tries=6):
    _prev = None
    for _ in range(_tries):
        app.processEvents()
        _l.activate()
        app.processEvents()
        _cur = (_w.input.geometry().getRect(), _w.list.geometry().getRect(),
                _w.list.viewport().geometry().getRect())
        if _cur == _prev:
            return _cur
        _prev = _cur
    return _prev


_tp.setMinimumSize(0, 0)
_tp.setMaximumSize(16777215, 16777215)
_tp.setFixedSize(354, 300)
for _i12 in range(12):
    _st.add_todo("填充项%02d" % _i12, None)
_tp.refresh()
_r_in, _r_list, _r_vp = _settle12(_tp, _v12)
_h_after, _vp_after = _r_list[3], _r_vp[3]
check("真实尺寸（354×300）稳定后：列表 (0,45,354,249)，可视区高 243",
      _r_list == (0, 45, 354, 249) and _vp_after == 243, (_r_list, _r_vp))
check("列表高 = 页面高 300 − 上边距6 − 输入行%d − 间距6 − 下边距6（顶部没留白）"
      % _r_in[3], _h_after == 300 - 6 - _r_in[3] - 6 - 6, (_h_after, _r_in))
check("列表底边贴到页面下沿减 6（bottom 闭区间：y+h == 300−6）",
      _r_list[1] + _h_after == 300 - 6, (_r_list[1] + _h_after, 300 - 6))
check("列表下面没有多余空隙：300 − 下边距6 − 列表底 = 0",
      300 - 6 - (_r_list[1] + _h_after) == 0, 300 - 6 - (_r_list[1] + _h_after))
# 把「改前」那一行原样装回去（muted 计数 QLabel + 下边距 10），量出真正的旧列表高度
_lab12 = QLabel("待办 12 · 未完成 12")
_lab12.setObjectName("muted")
_v12.addWidget(_lab12, 0)
_v12.setContentsMargins(CONTENT_PAD_X, 6, CONTENT_PAD_X, 10)
_b_in, _b_list, _b_vp = _settle12(_tp, _v12)
_h_before, _vp_before = _b_list[3], _b_vp[3]
_lab_h = _lab12.geometry().height()
_v12.removeWidget(_lab12)
_lab12.setParent(None)
_v12.setContentsMargins(CONTENT_PAD_X, 6, CONTENT_PAD_X, 6)
check("改前重建实测：列表 221、可视区 215、计数行 18",
      (_h_before, _vp_before, _lab_h) == (221, 215, 18),
      (_h_before, _vp_before, _lab_h))
check("省出来的 28px 算得过账：计数行 18 + 那格间距 6 + 下边距 10→6 的 4",
      _h_after - _h_before == _lab_h + 6 + 4, (_h_after, _h_before, _lab_h))
check("拆掉重建后布局回到改后 249", _settle12(_tp, _v12)[1][3] == _h_after,
      _settle12(_tp, _v12)[1][3])
# 行高真量：走委托的 sizeHint（TodoDelegate 里是 max(26, 文本高)），不写死 26
_opt12 = QStyleOptionViewItem()
_opt12.rect = QRect(0, 0, max(_r_vp[2], 1), 26)
_idx12 = _tp.list.model().index(0) if _tp.list.model() is not None else None
_row12 = (_tp.list.itemDelegate().sizeHint(_opt12, _idx12).height()
          if _idx12 is not None and _idx12.isValid() else _tp.list.sizeHintForRow(0))
_rows_after, _rows_before = _vp_after // _row12, _vp_before // _row12
check("整行数：改后 %d 行（改前 %d 行），行高 %d，可视区 %d→%d"
      % (_rows_after, _rows_before, _row12, _vp_before, _vp_after),
      _rows_after == 9 and _rows_before == 8 and _row12 == 26,
      (_vp_after // _row12, _vp_before // _row12, _row12, _vp_after, _vp_before))
_an12 = _tp.list.accessibleName()
_n12 = len(_st.todos())
_l12 = sum(1 for _t12 in _st.todos() if not todo_is_done(_t12))
check("计数改挂 accessibleName 且与 store 一致",
      _an12 == "待办列表，共 %d 条，未完成 %d 条" % (_n12, _l12), (_an12, _n12, _l12))
check("读屏名里的数字不是空占位", _n12 > 0 and _l12 >= 0, (_n12, _l12))
_tp.setMinimumSize(0, 0)                       # 释放探针用的固定尺寸，交回宿主排布
_tp.setMaximumSize(16777215, 16777215)
isl.goto(_pg12)                                # 恢复原来的页签

# ── 1.4.14：面板里只有一条内容列 ────────────────────────────────────────
# 用户手绘的两条青色竖线（截图 x≈5 与 x≈362，换算到面板坐标 x≈8/365）圈的是
# 页签卡那条底框的左右缘，而下面每一页的内容当时只到面板 x=24..353——上下差了
# 12px，看着就是"上面的白框比下面的内容宽出一截"。这一节把口径钉死：
# 顶栏、页签卡、每一页的内容，左右缘都必须在面板 x=12 与 x=365，两侧各 12px。
# 量法沿用 1.4.12 的教训：offscreen 下隐藏页不算几何，必须逐页 goto 后
# activate()+processEvents 循环到左右缘两次一致才算数。
_col = 12 + CONTENT_PAD_X                      # 内容列左缘 = body 边距 12 + 页面水平边距
check("CONTENT_PAD_X 归 0：列缘只由 body 边距决定", CONTENT_PAD_X == 0, CONTENT_PAD_X)
_bm = isl.body.layout().contentsMargins()
check("body 边距左右各 12（列缘基准）", _bm.left() == 12 and _bm.right() == 12,
      [_bm.left(), _bm.top(), _bm.right(), _bm.bottom()])
for _nm, _w in (("顶栏", isl.head), ("页签卡", isl.nav), ("页面容器", isl.stack)):
    _x = _w.mapTo(isl, QPoint(0, 0)).x()
    check("%s 占满内容列 %d..%d" % (_nm, _col, isl.width() - _col - 1),
          (_x, _x + _w.width() - 1) == (_col, isl.width() - _col - 1),
          (_x, _w.width(), isl.width()))
check("顶栏钉子右缘贴内容列右缘",
      isl.btn_pin.mapTo(isl, QPoint(0, 0)).x() + isl.btn_pin.width() - 1
      == isl.width() - _col - 1,
      (isl.btn_pin.mapTo(isl, QPoint(0, 0)).x(), isl.btn_pin.width()))


def _settle14(_p, _tries=10):
    """切到 _p 后反复排布，直到「页面左缘 + 水平边距」这组数两次一致"""
    _prev = None
    for _ in range(_tries):
        isl.body.layout().activate()
        _p.layout().activate()
        app.processEvents()
        _m = _p.layout().contentsMargins()
        _o = _p.mapTo(isl, QPoint(0, 0))
        _cur = (_m.left(), _m.right(), _o.x(), _p.width())
        if _cur == _prev:
            return _cur
        _prev = _cur
    return _prev


for _i, _p in enumerate(isl.pages):
    isl.goto(_i)
    _ml, _mr, _ox, _pw14 = _settle14(_p)
    _l14 = _ox + _ml
    _r14 = _ox + _pw14 - _mr - 1
    check("页「%s」内容列 %d..%d、左右空隙各 %d 相等"
          % (_p.title, _col, isl.width() - _col - 1, _col),
          _l14 == _col and _r14 == isl.width() - _col - 1
          and _l14 == isl.width() - 1 - _r14,
          (_l14, _r14, isl.width() - 1 - _r14, _ox, _pw14, _ml, _mr))

# 内容列里具体那几个框：卡片列表必须和页签卡同缘，行内容必须和输入框文字同轴
isl.goto(0)
_settle14(isl.provider("todo"))
_tp14 = isl.provider("todo")
_tx14 = _tp14.list.mapTo(isl, QPoint(0, 0)).x()
check("待办列表卡片 12..365",
      (_tx14, _tx14 + _tp14.list.width() - 1) == (_col, isl.width() - _col - 1),
      (_tx14, _tp14.list.width()))
check("待办输入框贴列左缘、添加按钮贴列右缘",
      _tp14.input.x() == CONTENT_PAD_X
      and _tp14.btn_add.x() + _tp14.btn_add.width() == _tp14.width() - CONTENT_PAD_X,
      (_tp14.input.x(), _tp14.btn_add.x() + _tp14.btn_add.width(), _tp14.width()))
isl.goto(4)
_settle14(isl.provider("clipboard"))
_cl14 = isl.provider("clipboard")
_cx14 = _cl14.list.mapTo(isl, QPoint(0, 0)).x()
_cvp14 = _cl14.list.viewport().geometry()
_row14 = _cl14.list.visualItemRect(_cl14.list.item(0)) if _cl14.list.count() else None
check("剪贴板列表卡片 12..365（比 1.4.13 宽 24px）",
      (_cx14, _cx14 + _cl14.list.width() - 1) == (_col, isl.width() - _col - 1),
      (_cx14, _cl14.list.width()))
# 条目多到要滚时，QSS 里那根 6px 竖直滚动条是从可视区右缘让出来的，不是从卡片
# 右缘让出来的：不把它算进账，"行右缘 = 卡片右缘 − 3"就会假 FAIL（实测 356 vs 362）。
_sb14 = 6 if _cl14.list.verticalScrollBar().isVisible() else 0
check("剪贴板可视区 = 卡片内缘 %d..%d（左右各 3px 框+padding，右侧再让 %dpx 滚动条）"
      % (_col + 3, isl.width() - _col - 4 - _sb14, _sb14),
      (_cx14 + _cvp14.left(), _cx14 + _cvp14.right())
      == (_col + 3, isl.width() - _col - 4 - _sb14),
      (_cx14 + _cvp14.left(), _cx14 + _cvp14.right(), _cvp14.width(), _sb14))
if _row14 is not None:
    _base14 = _cx14 + _cvp14.left()
    _t14 = ClipPinDelegate.text_rect(_row14)
    _p14 = ClipPinDelegate.pin_rect(_row14)
    check("剪贴板正文左缘 = 面板 21（= 输入框 12+1px 框+8px 内边距，同一根轴）",
          int(_base14 + _t14.left()) == 21, (int(_base14 + _t14.left()),))
    check("剪贴板钉子热区右缘贴行右缘（面板 %d，离列缘只余 3px+%dpx）"
          % (isl.width() - _col - 4 - _sb14, _sb14),
          int(_base14 + _p14.right()) == isl.width() - _col - 4 - _sb14
          and abs(_p14.width() - PIN_HIT_W) <= 0.01,
          (int(_base14 + _p14.right()), round(_p14.width(), 1), _sb14))
isl.goto(3)
_settle14(isl.provider("shelf"))
_sh14 = isl.provider("shelf")
_sx14 = _sh14.list.mapTo(isl, QPoint(0, 0)).x()
check("中转站列表卡片 12..365",
      (_sx14, _sx14 + _sh14.list.width() - 1) == (_col, isl.width() - _col - 1),
      (_sx14, _sh14.list.width()))

# ── 1.4.15 日历页铺满纵向空间：空日程日不再有 48px 死白，网格行高 23.7→29.7 ──
# 用户口径是「下面还有空白，把整体日历间距拉大一点，尽量铺满」。空白不是边距，
# 是当天 0 条日程时那条透明的日程列表（定高 48 + 一格间距 4）。这一节把两件事
# 钉死：①账本必须闭合（月份行 + 网格 + 按钮行 + 列表 + 3 格间距 = 可用高），
# ②条目之间零重叠——1.3.3 遗留的「日历页纵向挤压」就是网格下限 160 加列表下限
# 40 加起来 200 > 192，布局压不下去，在网格与按钮行之间叠了 4px。
from qilin_island.modules.calendar import GRID_MIN_H, EV_LIST_H        # noqa: E402
isl.goto(6)
_cp15 = isl.provider("calendar")
_v15 = _cp15.layout()
_settle14(_cp15)
_m15 = _v15.contentsMargins()
_SP15 = _v15.spacing()
_av15 = _cp15.height() - _m15.top() - _m15.bottom()


def _boxes15(_v):
    """可见条目的 (名, y, 高)。隐藏件不占空间，它的 geometry() 还是上一轮残留值，
    留着会把「零重叠」算成 259px 的假重叠。"""
    _out = []
    for _i in range(_v.count()):
        _it = _v.itemAt(_i)
        _w = _it.widget()
        if _w is not None and not _w.isVisible():
            continue
        _g = _it.geometry()
        _out.append((_w.metaObject().className() if _w else "行布局",
                     _g.y(), _g.height()))
    return _out


def _ov15(_v):
    """相邻可见条目之间最大的压叠像素（正数=重叠，0=正好接上）"""
    _b = _boxes15(_v)
    return max([0] + [_b[i][1] + _b[i][2] - _b[i + 1][1]
                      for i in range(len(_b) - 1)])


check("日历页仍是四个条目（月份行/网格/按钮行/日程列表）",
      _v15.count() == 4, _v15.count())
check("日历页可用高 = 页面 %d − 上 %d − 下 %d = %d"
      % (_cp15.height(), _m15.top(), _m15.bottom(), _av15),
      (_cp15.height(), _m15.top(), _m15.bottom(), _av15) == (267, 2, 8, 257),
      (_cp15.height(), _m15.top(), _m15.bottom(), _av15))
check("网格下限 + 列表定高刚好填满账本（144+48 = 257−22−31−3×4）",
      GRID_MIN_H + EV_LIST_H
      == _av15 - _boxes15(_v15)[0][2] - _boxes15(_v15)[2][2] - 3 * _SP15,
      (GRID_MIN_H, EV_LIST_H, _boxes15(_v15)[0][2], _boxes15(_v15)[2][2], _SP15))
check("日程列表有读屏名（它现在会整条消失，得让读屏知道那是啥）",
      _cp15.list.accessibleName() == "当天日程列表", _cp15.list.accessibleName())
check("日期字号随格子抬到 11px",
      "p.setFont(T.font(11, d == today))" in _spage,
      [l.strip() for l in _spage.splitlines() if "T.font(11" in l])

# ① 当天有日程：列表可见、定高 48，网格压到下限 144（行高 21.0）
_today15 = _d.today()
_evs15 = [dict(e) for e in _st.data["events"]]
for _i15 in range(2):
    _st.add_event("自检日程%d" % _i15,
                  _dt(_today15.year, _today15.month, _today15.day, 8 + _i15, 30), 10)
_cp15.grid.select(_today15)          # on_change → refresh
_settle14(_cp15)
_b15 = _boxes15(_v15)
_n15 = _cp15.list.count()
_rh15 = _cp15.list.sizeHintForRow(0)
check("当天 %d 条日程：列表可见、高 = EV_LIST_H %d" % (_n15, EV_LIST_H),
      _cp15.list.isVisible() and _b15[3][2] == EV_LIST_H,
      (_cp15.list.isVisible(), _b15[3][2], _n15))
check("有日程时网格 = 下限 %d、行高 %.2f" % (GRID_MIN_H, (GRID_MIN_H - 18) / 6.0),
      _b15[1][2] == GRID_MIN_H, (_b15[1][2], (GRID_MIN_H - 18) / 6.0))
check("有日程时条目零重叠", _ov15(_v15) == 0, (_ov15(_v15), _b15))
check("列表可视行数 2 行（可视区 %d ÷ 行高 %d）"
      % (_cp15.list.viewport().height(), _rh15),
      _cp15.list.viewport().height() // _rh15 == 2,
      (_cp15.list.viewport().height(), _rh15))
check("列表底缘只余页面下边距 %d（下面没有死白）" % _m15.bottom(),
      _cp15.height() - (_b15[3][1] + _b15[3][2]) == _m15.bottom(),
      (_cp15.height(), _b15[3][1] + _b15[3][2], _m15.bottom()))

# ② 当天 0 条：整条列表收起，省出的 52px（48+4 间距）全进网格行高
for _e in list(_st.data["events"]):
    _st.remove_event(_e["id"])
_cp15.refresh()
_settle14(_cp15)
_b0 = _boxes15(_v15)
check("当天 0 条：列表隐藏，只剩三个可见条目",
      not _cp15.list.isVisible() and len(_b0) == 3,
      (int(_cp15.list.isVisible()), len(_b0), _cp15.list.count()))
check("空日程日网格吃掉全部余量 = 257−22−31−2×4 = 196",
      _b0[1][2] == _av15 - _b0[0][2] - _b0[2][2] - 2 * _SP15 == 196,
      (_b0[1][2], _av15, _b0[0][2], _b0[2][2]))
check("空日程日行高 %.2f（改前 23.67）" % ((196 - 18) / 6.0),
      abs((_b0[1][2] - 18) / 6.0 - 29.6667) < 0.01, (_b0[1][2] - 18) / 6.0)
check("空日程日零重叠", _ov15(_v15) == 0, (_ov15(_v15), _b0))
check("网格底缘到页面下沿 = 间距4 + 按钮行31 + 下边距8（底部不再空一块）",
      _cp15.height() - (_b0[1][1] + _b0[1][2]) == _SP15 + _b0[2][2] + _m15.bottom(),
      (_cp15.height() - (_b0[1][1] + _b0[1][2]), _SP15, _b0[2][2], _m15.bottom()))

# ③ 把「改前」那套参数原样装回去（网格下限 160、列表 min40/max88、stretch 3/2、
#    列表不隐藏），在同一份几何上量出旧的 4px 挤压与 40px 死白
_cp15.grid.setMinimumHeight(160)
_cp15.list.setMinimumHeight(40)
_cp15.list.setMaximumHeight(88)
_cp15.list.setVisible(True)
_v15.setStretch(1, 3)
_v15.setStretch(3, 2)
_settle14(_cp15)
_bb = _boxes15(_v15)
check("改前重建：网格 160 + 列表 40 装不进 192 → 网格与按钮行叠 %d px"
      % _ov15(_v15), _bb[1][2] == 160 and _ov15(_v15) == 4,
      (_bb[1][2], _bb[2][1], _bb[1][1] + _bb[1][2], _ov15(_v15)))
check("改前空日程日也占 40px 透明高度（用户截图里那块空白）",
      _cp15.list.count() == 0 and _bb[3][2] == 40, (_bb[3][2], _cp15.list.count()))
# 装回新参数与原数据
_cp15.grid.setMinimumHeight(GRID_MIN_H)
_cp15.list.setFixedHeight(EV_LIST_H)
_v15.setStretch(1, 1)
_v15.setStretch(3, 0)
_st.data["events"] = _evs15
_st.save()
_cp15.refresh()
_settle14(_cp15)
check("装回新参数后回到有日程形态：网格 144、列表可见",
      _cp15.grid.minimumHeight() == GRID_MIN_H
      and _boxes15(_v15)[1][2] == GRID_MIN_H and _cp15.list.isVisible(),
      (_cp15.grid.minimumHeight(), _boxes15(_v15)[1][2]))
check("自检日程已清干净（events 数回到进来时）",
      len(_st.data["events"]) == len(_evs15),
      (len(_st.data["events"]), len(_evs15)))
isl.goto(_pg12)

isl.hide()

st = isl.store
st.add_todo("自检项", None)
st.water_add(1)
st.save()
again = Store()
check("落盘往返", len(again.todos()) == len(st.todos())
      and again.water_today() == st.water_today()
      and again.settings.get("style") == st.settings.get("style"))

print("\n%s" % ("自检通过" if not fails else "失败项：%s" % fails))
sys.exit(1 if fails else 0)
