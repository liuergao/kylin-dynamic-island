# -*- coding: utf-8 -*-
"""核心层 · 主题（M2/M5 共用）

八款皮肤的色板、设计 token（圆角/间距/时长/缓动）与圆角渐变环形等绘制工具。
标识信息不在这里定义，只从 meta 转发，保证「一个产品只有一个版本号来源」。

token 数值抄自公开规范，不引任何第三方库（麒麟离线 + 系统 Qt5.12 是硬约束）：
圆角与几何见 Win11 「Geometry」，控件面 4px、浮层与顶层容器 8px、条状 4px；
时长与缓动见 WinUI「Timing and easing」，83/167/250ms，进场 fast-out-slow-in、
退场 slow-out-fast-in。这里只取数字和曲线，代码全部自己实现。
"""
from PyQt5.QtCore import (QEasingCurve, QObject, QRect, QRectF, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QLinearGradient, QPen, QBrush

from ..meta import APP_EN, APP_ID, APP_NAME, VERSION  # noqa: F401（供各层引用）
from . import brand

# ── 设计 token ────────────────────────────────────────────────────────────
# 圆角：短边一半是上限，所以小控件用 clamp_r 兜底，不会出现"圆成橄榄"的怪形
R = {"none": 0.0, "control": 4.0, "bar": 4.0, "card": 8.0,
     "overlay": 8.0, "panel": 8.0, "pill": 20.0}
# 间距：4px 格点，页面里所有 margins/spacing 只能取这些值
SP = {"xs": 2, "s": 4, "m": 8, "l": 12, "xl": 16, "xxl": 20, "huge": 24}
# 时长：WinUI 标准档；slow 只给岛体形变这类"大跨度"动效
DUR = {"faster": 83, "fast": 167, "normal": 250, "slow": 400}
# 缓动：cubic-bezier 四点（P0/P3 固定 0/1）
CURVE = {"enter": (0.0, 0.0, 0.0, 1.0),     # fast-out-slow-in：入场
         "exit": (1.0, 0.0, 1.0, 1.0),      # slow-out-fast-in：退场
         "inout": (0.4, 0.0, 0.2, 1.0)}     # 场内位移/尺寸变化


def clamp_r(radius, box_h, box_w=None):
    """圆角不能超过短边一半（QSS 里写死半径时也要守这条）"""
    short = box_h if box_w is None else min(box_h, box_w)
    return max(0.0, min(float(radius), short / 2.0))


def nested(outer, gap):
    """套在容器里面的元素，圆角按「外半径 - 间距」递减才贴得住边"""
    return max(0.0, float(outer) - float(gap))


def _bez(a, b):
    """三次贝塞尔的一维求值与导数（P0=0、P3=1）"""
    def f(t):
        u = 1.0 - t
        return 3.0 * u * u * t * a + 3.0 * u * t * t * b + t * t * t

    def d(t):
        u = 1.0 - t
        return 3.0 * u * u * a + 6.0 * u * t * (b - a) + 3.0 * t * t * (1.0 - b)
    return f, d


def curve(name="inout"):
    """返回 f(x)->y 的缓动函数：给定线性进度 x，算出 eased 值。

    Qt 的 QEasingCurve 不接受任意 bezier 控制点，所以这里对 x 反解 t（牛顿迭代
    后二分兜底），再回代求 y。规范里那两条曲线的控制点都在轴上，牛顿一步到位，
    二分只是给 inout 这类常规曲线保底。"""
    p1x, p1y, p2x, p2y = CURVE.get(name, CURVE["inout"])
    fx, dfx = _bez(p1x, p2x)
    fy, _ = _bez(p1y, p2y)

    def ease(x):
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        t = x
        for _ in range(6):                    # 牛顿迭代
            d = dfx(t)
            if d <= 1e-6:
                break
            t -= (fx(t) - x) / d
            if not (0.0 <= t <= 1.0):
                t = x
                break
        lo, hi = 0.0, 1.0                     # 出界就二分夹回
        if not (0.0 <= t <= 1.0) or abs(fx(t) - x) > 1e-3:
            for _ in range(24):
                t = (lo + hi) / 2.0
                if fx(t) < x:
                    lo = t
                else:
                    hi = t
        return fy(t)
    return ease


class _Eased(QObject):
    """QVariantAnimation + 自定义 bezier：Qt 没有任意曲线入口，只能先线性取 0..1
    再自己映射，动画值与 eased 值都从这里出，自检才能按帧断言"""

    finished = pyqtSignal()

    def __init__(self, obj, prop, frm, to, dur, ease, parent=None):
        super().__init__(parent)
        self._ease = ease
        self._frm, self._to = frm, to
        self._va = QVariantAnimation(self)
        self._va.setStartValue(0.0)
        self._va.setEndValue(1.0)
        self._va.setDuration(int(dur))
        self._va.setEasingCurve(QEasingCurve.Linear)
        self._va.valueChanged.connect(
            lambda p, o=obj, n=prop: self._frame(o, n, _mix(frm, to, self._ease(p))))
        self._va.finished.connect(self._cleanup)

    @staticmethod
    def _frame(obj, prop, val):
        # geometry 这类有 WRITE 访问器的元属性必须走 setProperty 才会调回
        # setGeometry；自绘控件（进度环、轮播淡入）读的是普通实例属性，只能 setattr
        mo = obj.metaObject()
        i = mo.indexOfProperty(prop)
        if i >= 0 and mo.property(i).isWritable():
            obj.setProperty(prop, val)
        else:
            setattr(obj, prop, val)
        # 自绘控件靠属性驱动重绘，不然缓动跑完了画面也不动
        if hasattr(obj, "update"):
            obj.update()

    def _cleanup(self):
        self.finished.emit()
        self.deleteLater()

    def start(self):
        self._va.start()

    def stop(self):
        self._va.stop()
        # 被打断的动画不会被重指向，留在树上就是泄漏：形变每秒可能被打断好几次
        self.deleteLater()


def _mix(frm, to, k):
    if isinstance(frm, QColor) and isinstance(to, QColor):
        return QColor(int(frm.red() + (to.red() - frm.red()) * k),
                      int(frm.green() + (to.green() - frm.green()) * k),
                      int(frm.blue() + (to.blue() - frm.blue()) * k),
                      int(frm.alpha() + (to.alpha() - frm.alpha()) * k))
    if isinstance(frm, QRect) and isinstance(to, QRect):
        # 岛体形变：四边各自插值，逐分量取整才不会一边被舍掉 1px
        def _i(a, b):
            return int(round(a + (b - a) * k))
        return QRect(_i(frm.x(), to.x()), _i(frm.y(), to.y()),
                     _i(frm.width(), to.width()), _i(frm.height(), to.height()))
    try:
        return frm + (to - frm) * k           # float / int
    except TypeError:
        return to if k >= 1.0 else frm        # 其余类型（如 str）只能在终点切换


# ── 动效总开关 ────────────────────────────────────────────────────────────
# 关掉动效不等于关掉落值：animate 照样把属性写到终点，只是不补中间帧，
# 调用方（形变、进度环、轮播淡入）一行都不用分支。给低配机和前庭敏感的用户
# 一个"立刻不晃"的选项，比整套动画各自加 if 好维护。
_MOTION = {"on": True}


def set_motion(on):
    _MOTION["on"] = bool(on)


def motion_on():
    return _MOTION["on"]


class _Instant(QObject):
    """动效关闭时的替身句柄：接口与 _Eased 一致，值已落位，finished 下一轮补发，
    所以"动画跑完把句柄置空"的收尾逻辑照旧生效，不会留残骸。

    补发前一定要过 _dead 这道闸：调用方都是「先 stop 旧句柄、再建新句柄」，
    如果旧替身在它那一轮到点时照常发 finished，就会把新句柄当成旧的清成 None，
    新动画失去 Python 引用被就地析构——offscreen 下直接段错误。"""

    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._dead = False
        QTimer.singleShot(0, self._fire)

    def _fire(self):
        if not self._dead:
            self._dead = True
            self.finished.emit()

    def stop(self):
        self._dead = True


def animate(obj, prop, frm, to, dur=DUR["normal"], ease="inout", parent=None):
    """把 obj.prop 从 frm 缓动到 to；返回句柄，调用方可提前 stop。
    动效总开关关闭时直接落终值并返回替身句柄。"""
    if not _MOTION["on"]:
        _Eased._frame(obj, prop, to)
        return _Instant()
    h = _Eased(obj, prop, frm, to, dur, curve(ease), parent or obj)
    h.start()
    return h


# 八款皮肤：深海（默认）/ 奶油 + 六套经典配色（对标 BrimDeck 主题体系）
SKINS = {
    "deep": {
        "name": "深海",
        "bg1": "#132532", "bg2": "#0d1b26",
        "card": "#1b3140", "card2": "#16283610",
        "text": "#e8f1f6", "text2": "#8fa5b4", "text3": "#5f7181",
        "accent": "#4ecdc4", "accent2": "#7fd7ff",
        "line": "#243a49", "ok": "#5ad19a", "warn": "#f2b661", "bad": "#ef7b7b",
    },
    "cream": {
        "name": "奶油",
        "bg1": "#fdf9f3", "bg2": "#f6efe4",
        "card": "#ffffff", "card2": "#ffffff80",
        "text": "#3d3227", "text2": "#8b7c6b", "text3": "#b0a294",
        "accent": "#7a6cff", "accent2": "#ff9f6e",
        "line": "#e8ddcd", "ok": "#3fae74", "warn": "#d68f2a", "bad": "#d9615f",
    },
    "one_dark": {
        "name": "One Dark",
        "bg1": "#282c34", "bg2": "#21252b",
        "card": "#2c313a", "card2": "#2c313a80",
        "text": "#abb2bf", "text2": "#9da5b4", "text3": "#5c6370",
        "accent": "#61afef", "accent2": "#98c379",
        "line": "#3e4451", "ok": "#98c379", "warn": "#e5c07b", "bad": "#e06c75",
    },
    "github_dark": {
        "name": "GitHub 暗色",
        "bg1": "#161b22", "bg2": "#0d1117",
        "card": "#21262d", "card2": "#21262d80",
        "text": "#e6edf3", "text2": "#8b949e", "text3": "#6e7681",
        "accent": "#2f81f7", "accent2": "#a371f7",
        "line": "#30363d", "ok": "#3fb950", "warn": "#d29922", "bad": "#f85149",
    },
    "dracula": {
        "name": "Dracula",
        "bg1": "#282a36", "bg2": "#21222c",
        "card": "#343746", "card2": "#34374680",
        "text": "#f8f8f2", "text2": "#8be9fd", "text3": "#6272a4",
        "accent": "#bd93f9", "accent2": "#ff79c6",
        "line": "#44475a", "ok": "#50fa7b", "warn": "#ffb86c", "bad": "#ff5555",
    },
    "cyberpunk": {
        "name": "赛博朋克",
        "bg1": "#170b2e", "bg2": "#0d0620",
        "card": "#241447", "card2": "#24144780",
        "text": "#f9f6ff", "text2": "#9d8cff", "text3": "#6b5aa8",
        "accent": "#00f0ff", "accent2": "#ff2e88",
        "line": "#33206b", "ok": "#2bffa0", "warn": "#ffe14d", "bad": "#ff3860",
    },
    "night_owl": {
        "name": "Night Owl",
        "bg1": "#011627", "bg2": "#0a1929",
        "card": "#12233a", "card2": "#12233a80",
        "text": "#d6deeb", "text2": "#8badc1", "text3": "#5f7e9e",
        "accent": "#c792ea", "accent2": "#82aaff",
        "line": "#1d3b53", "ok": "#addb67", "warn": "#ffeb95", "bad": "#ef5350",
    },
    "github_light": {
        "name": "GitHub 亮色",
        "bg1": "#ffffff", "bg2": "#f6f8fa",
        "card": "#f6f8fa", "card2": "#f6f8fa80",
        "text": "#1f2328", "text2": "#656d76", "text3": "#8c959f",
        "accent": "#0969da", "accent2": "#8250df",
        "line": "#d0d7de", "ok": "#1a7f37", "warn": "#9a6700", "bad": "#cf222e",
    },
}
SKIN_ORDER = ["deep", "cream", "one_dark", "github_dark", "dracula",
              "cyberpunk", "night_owl", "github_light"]


def skin(name):
    return SKINS.get(name) or SKINS["deep"]


def is_light(name):
    """亮/暗归类只看底色亮度：皮肤名和文字色都会骗人（GitHub 亮色的 accent 是深色，
    One Dark 的文字是浅色），而「切暗色」要的只是背景。"""
    return luma(c(skin(name), "bg1")) >= 0.5


# 素材字形本身的颜色：唯一来源在 brand（那里就是按这两个值画出 PNG 的），
# 挑素材只能拿它跟底色比对比度：按皮肤名或"亮度过半"判都会挑反
# （One Dark 的文字是浅的，但 accent 底也是深的，勾就得用浅字形那份）。
ASSET_INK = brand.ASSET_INK


def asset_variant(kind, surface):
    """同一素材的 dark/light 两份里，哪份在这块底色上对比度高就用哪份"""
    best, ratio = "light", -1.0
    for name in ("dark", "light"):
        r = contrast(QColor(ASSET_INK[kind][name]), QColor(surface))
        if r > ratio:
            best, ratio = name, r
    return best


def c(sk, key):
    return QColor(sk[key])


def _lin(v):
    """sRGB 单通道转线性（WCAG 相对亮度定义要求）"""
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luma(color):
    return (0.2126 * _lin(color.red()) + 0.7152 * _lin(color.green())
            + 0.0722 * _lin(color.blue()))


def contrast(a, b):
    """WCAG 对比度：1.0~21.0。界面可读性只用这个数验收，不靠看图"""
    la, lb = luma(a), luma(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a, b, k):
    return _mix(a, b, k)


# 亮/暗分组，按 SKIN_ORDER 原序：设置页的「明暗模式」在组内取第一个当落地皮肤，
# 组内顺序就是推荐顺序。放在 luma/c 之后，模块加载时才轮得到 is_light。
DARK_SKINS = [k for k in SKIN_ORDER if not is_light(k)]
LIGHT_SKINS = [k for k in SKIN_ORDER if is_light(k)]


def ink_candidates(sk):
    """这套皮肤里能当墨色用的三种：压暗的底色系 / 纯白 / 正文色"""
    deep = mix(c(sk, "bg2"), QColor(0, 0, 0), 0.35)
    return [deep, QColor("#ffffff"), c(sk, "text")]


def ink_on(bg, cands):
    """给一块底色挑墨色：取对比度最高者，深色底自然走到浅色、亮底走到深色。
    以前 QSS 里写死 #07222a / #ffffff，换皮肤就会糊成一片。"""
    best, ratio = cands[0], -1.0
    for cand in cands:
        r = contrast(cand, bg)
        if r > ratio:
            best, ratio = cand, r
    return best


def ink_over(surface, sk):
    """自绘控件（勾选对号、选中日）在任意底色上要用的墨色，按对比度现算"""
    return ink_on(QColor(surface), ink_candidates(sk))


def pin_ink(sk):
    """图钉这类自绘小图标的墨色（1.4.13）。

    用户口径：面板底本来就是深色，图钉再走深色描边就看不见，要白色。深色底给纯白
    （对 bg1 13.5~18.7、对 card 11.8~16.6）；cream / github_light 两套浅色皮肤白墨
    对比只有 1.0，退回该皮肤正文墨，否则就变成"白钉配白底"。
    判据直接看底色亮度，不看皮肤名——sk["name"] 是「深海」这种显示名，拿它喂
    is_light(skin(name)) 会一路兜底到 deep，浅色皮肤也误判成深色（第一版就栽在这）。
    """
    bg = c(sk, "bg1")
    return QColor("#ffffff") if contrast(QColor("#ffffff"), bg) >= 3.0 else c(sk, "text")


_STATES = {}


def states(sk):
    """皮肤色板 + 由它派生的四态/描边/墨色 + token 数值，一次算全给 QSS 用

    自绘控件每次重绘都要问一遍 line_strong/on_accent，所以按皮肤名缓存；
    SKINS 是模块级字面量，运行期不改，缓存不用失效。"""
    hit = _STATES.get(sk.get("name"))
    if hit is not None:
        return hit
    base = dict(sk)
    text = c(sk, "text")
    card = c(sk, "card")
    line = c(sk, "line")
    accent = c(sk, "accent")
    bad = c(sk, "bad")
    dark = luma(c(sk, "bg1")) < 0.5
    # hover/pressed 用文本色往卡片上叠，浅色皮肤叠深、深色皮肤叠亮，方向才不会错
    hover = mix(card, text, 0.10 if dark else 0.06)
    pressed = mix(card, text, 0.18 if dark else 0.11)
    strong = mix(line, text, 0.30)
    inks = ink_candidates(sk)
    on_accent = ink_on(accent, inks)
    on_bad = ink_on(bad, inks)
    # 主色按钮的悬停/按下：往文本色方向推一档。on_accent 是按对比度挑出来的
    # 反端色，所以这一步恒好地拉开对比，不必为亮皮/暗皮各写一套。
    accent_hover = mix(accent, text, 0.12)
    accent_pressed = mix(accent, text, 0.22)
    bad_hover = mix(bad, text, 0.12)
    bad_pressed = mix(bad, text, 0.22)
    sel_bg = mix(card, accent, 0.26)
    base.update({
        "card_hover": hover.name(), "card_pressed": pressed.name(),
        "card_dis": mix(card, c(sk, "bg2"), 0.45).name(),
        "line_strong": strong.name(),
        "accent_hover": accent_hover.name(), "accent_pressed": accent_pressed.name(),
        "bad_hover": bad_hover.name(), "bad_pressed": bad_pressed.name(),
        "sel_bg": sel_bg.name(), "sel_fg": ink_on(sel_bg, inks + [text]).name(),
        # 成功色的浅底/浅边：卡片弹窗里"收款身份已核对"这类提示条用
        "ok_soft": mix(card, c(sk, "ok"), 0.14).name(),
        "ok_line": mix(line, c(sk, "ok"), 0.45).name(),
        "on_accent": on_accent.name(), "on_bad": on_bad.name(),
        "focus": accent.name(),
        "r_control": int(clamp_r(R["control"], 8)), "r_card": int(R["card"]),
        "r_overlay": int(R["overlay"]), "r_panel": int(R["panel"]),
        "r_bar": int(R["bar"]), "r_tip": int(R["control"]),
        "sp_s": SP["s"], "sp_m": SP["m"], "sp_l": SP["l"], "sp_xl": SP["xl"],
    })
    _STATES[sk.get("name")] = base
    return base


def font(size=13, bold=False):
    f = QFont()
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


def rounded_path(rect, radius):
    p = QPainterPath()
    p.addRoundedRect(QRectF(rect), radius, radius)
    return p


def paint_panel(painter, rect, sk, radius=18, alpha=246, border=True, opaque=False):
    """主面板：竖向渐变 + 细边

    opaque=True 时先把整个矩形铺成同一份渐变再画圆角面板。无合成器的机器上
    窗口没有透明通道，圆角的抗锯齿像素会混到窗口默认的浅色底上，看起来就是
    一圈白色锯齿；先铺底，混色两端都是面板自己的颜色，边缘立刻干净。"""
    painter.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g1 = c(sk, "bg1")
    g2 = c(sk, "bg2")
    g1.setAlpha(alpha)
    g2.setAlpha(alpha)
    grad.setColorAt(0.0, g1)
    grad.setColorAt(1.0, g2)
    if opaque:
        painter.fillRect(rect, grad)
    path = rounded_path(rect, radius)
    painter.fillPath(path, QBrush(grad))
    if border:
        pen = QPen(c(sk, "line"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)


def paint_ring(painter, rect, ratio, sk, width=6.0, base=True):
    painter.setRenderHint(QPainter.Antialiasing, True)
    ratio = max(0.0, min(1.0, ratio))
    if base:
        pen = QPen(c(sk, "line"))
        pen.setWidthF(width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
    pen = QPen(c(sk, "accent"))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawArc(rect, 90 * 16, -int(360 * 16 * ratio))


def elide(painter, text, width):
    return painter.fontMetrics().elidedText(text, Qt.ElideRight, int(width))


def hhmm(ts):
    import time
    return time.strftime("%H:%M", time.localtime(ts))


def fmt_duration(sec):
    sec = int(max(0, sec))
    return "%d:%02d" % (sec // 60, sec % 60)
