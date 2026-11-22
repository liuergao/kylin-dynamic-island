# -*- coding: utf-8 -*-
"""支撑层 · 零依赖 SVG 图标加载

机上的 PyQt5 没编 QtSvg（`import PyQt5.QtSvg` 直接 ModuleNotFoundError），
QIcon 也认不了 .svg，所以素材里的图标只能自己解析成 QPainterPath：矢量随 DPR
缩放、想换色就换个 QColor，不用预栅格化成一堆 PNG。

只覆盖本项目素材用到的 SVG 子集：
- <path d="…">，命令 M/m、H/h、V/v、L/l、C/c、S/s、Q/q、T/t、A/a、Z/z；
- <g transform="…">，函数 translate / scale / rotate / skewX / skewY / matrix；
- <svg viewBox="x y w h">。
fill / stroke 一律忽略——颜色由调用方在绘制时决定（深色皮肤上必须能换成白墨，
见 modules/widgets.py::pin_ink）。
"""
import math
import os
import re

from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import (QPainterPath, QTransform)

_CMD = set("MmHhVvLlCcSsQqTtAaZz")
_NUM = re.compile(r"[-+]?(?:[0-9]*\.[0-9]+|[0-9]+\.?)(?:[eE][-+]?[0-9]+)?")
_TAG = re.compile(r"<(/?)(g|svg|path)\b([^>]*?)/?>")
_ATTR = re.compile(r"([a-zA-Z-]+)\s*=\s*\"([^\"]*)\"")
_FUNC = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")

# 每种命令的参数个数（用于按组切分隐式重复，如 "L 1 2 3 4" = 两段直线）
_ARITY = {"M": 2, "H": 1, "V": 1, "L": 2, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}

_CACHE = {}


def _segments(d):
    """把 path 的 d 切成 (命令, [参数…])；处理隐式重复（"M1 2 3 4" 后半按 L 走）、
    省略的逗号，以及负号当分隔符（"0-2" 是两个数）"""
    out = []
    i, n = 0, len(d)
    while i < n:
        while i < n and d[i] in " \t\r\n,":
            i += 1
        if i >= n or d[i] not in _CMD:
            break
        cmd = d[i]
        i += 1
        if cmd in "Zz":
            out.append((cmd, []))
            continue
        arity = _ARITY[cmd.upper()]
        first = True
        while True:
            nums, j = [], i
            while len(nums) < arity:
                while j < n and d[j] in " \t\r\n,":
                    j += 1
                m = _NUM.match(d, j)
                if not m:
                    break
                nums.append(float(m.group()))
                j = m.end()
            if len(nums) < arity:
                break
            if first:
                eff = cmd
            elif cmd == "M":
                eff = "L"
            elif cmd == "m":
                eff = "l"
            else:
                eff = cmd
            out.append((eff, nums))
            first, i = False, j
    return out


def _arc(path, x1, y1, rx, ry, rot_deg, large, sweep, x2, y2):
    """椭圆弧端点参数 → 圆心参数 → 三次贝塞尔近似（W3C F.6.5/F.6.6）"""
    if x1 == x2 and y1 == y2:
        return
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        path.lineTo(QPointF(x2, y2))
        return
    phi = math.radians(rot_deg % 360)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1.0:                             # 半径不够，按比例放大到刚好过两点
        rx *= math.sqrt(lam)
        ry *= math.sqrt(lam)
    sign = -1.0 if large == sweep else 1.0
    disc = (rx * ry) ** 2 - (rx * y1p) ** 2 - (ry * x1p) ** 2
    coef = sign * math.sqrt(max(0.0, disc) / ((rx * y1p) ** 2 + (ry * x1p) ** 2 or 1.0))
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2.0

    def _ang(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        len_ = math.hypot(ux, uy) * math.hypot(vx, vy) or 1.0
        a = math.acos(max(-1.0, min(1.0, dot / len_)))
        return -a if ux * vy - uy * vx < 0 else a

    theta1 = _ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = _ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if sweep == 0 and delta > 0:
        delta -= 2 * math.pi
    elif sweep == 1 and delta < 0:
        delta += 2 * math.pi
    segs = int(math.ceil(abs(delta) / (math.pi / 2.0))) or 1
    step = delta / segs
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    for _ in range(segs):
        c1, s1 = math.cos(theta1), math.sin(theta1)
        theta1 += step
        c2, s2 = math.cos(theta1), math.sin(theta1)
        e1x = cos_p * rx * c1 - sin_p * ry * s1 + cx
        e1y = sin_p * rx * c1 + cos_p * ry * s1 + cy
        e2x = cos_p * rx * c2 - sin_p * ry * s2 + cx
        e2y = sin_p * rx * c2 + cos_p * ry * s2 + cy
        d1x = cos_p * rx * (-s1) - sin_p * ry * c1
        d1y = sin_p * rx * (-s1) + cos_p * ry * c1
        d2x = cos_p * rx * (-s2) - sin_p * ry * c2
        d2y = sin_p * rx * (-s2) + cos_p * ry * c2
        path.cubicTo(QPointF(e1x + k * d1x, e1y + k * d1y),
                     QPointF(e2x - k * d2x, e2y - k * d2y),
                     QPointF(e2x, e2y))


def path_from_d(d, cur=None, start=QPointF(0, 0)):
    """d 字符串 → QPainterPath（绝对坐标）"""
    path = cur if cur is not None else QPainterPath()
    px, py = start.x(), start.y()
    c_prev = None                             # 上一条 C/S 的第一个控制点
    q_prev = None                             # 上一条 Q/T 的控制点
    for cmd, a in _segments(d):
        rel = cmd.islower()
        up = cmd.upper()
        if up == "M":
            px, py = (px + a[0], py + a[1]) if rel else (a[0], a[1])
            path.moveTo(px, py)
        elif up == "H":
            px = px + a[0] if rel else a[0]
            path.lineTo(px, py)
        elif up == "V":
            py = py + a[0] if rel else a[0]
            path.lineTo(px, py)
        elif up == "L":
            px, py = (px + a[0], py + a[1]) if rel else (a[0], a[1])
            path.lineTo(px, py)
        elif up == "C":
            x1, y1 = (px + a[0], py + a[1]) if rel else (a[0], a[1])
            x2, y2 = (px + a[2], py + a[3]) if rel else (a[2], a[3])
            px, py = (px + a[4], py + a[5]) if rel else (a[4], a[5])
            path.cubicTo(QPointF(x1, y1), QPointF(x2, y2), QPointF(px, py))
            c_prev = (x2, y2)
            q_prev = None
            continue
        elif up == "S":
            x1, y1 = (2 * px - c_prev[0], 2 * py - c_prev[1]) if c_prev else (px, py)
            x2, y2 = (px + a[0], py + a[1]) if rel else (a[0], a[1])
            px, py = (px + a[2], py + a[3]) if rel else (a[2], a[3])
            path.cubicTo(QPointF(x1, y1), QPointF(x2, y2), QPointF(px, py))
            c_prev = (x2, y2)
            q_prev = None
            continue
        elif up == "Q":
            x1, y1 = (px + a[0], py + a[1]) if rel else (a[0], a[1])
            px, py = (px + a[2], py + a[3]) if rel else (a[2], a[3])
            path.quadTo(QPointF(x1, y1), QPointF(px, py))
            q_prev = (x1, y1)
            c_prev = None
            continue
        elif up == "T":
            x1, y1 = (2 * px - q_prev[0], 2 * py - q_prev[1]) if q_prev else (px, py)
            px, py = (px + a[0], py + a[1]) if rel else (a[0], a[1])
            path.quadTo(QPointF(x1, y1), QPointF(px, py))
            q_prev = (x1, y1)
            c_prev = None
            continue
        elif up == "A":
            rx, ry, rot = a[0], a[1], a[2]
            large, sweep = int(a[3]), int(a[4])
            ex, ey = (px + a[5], py + a[6]) if rel else (a[5], a[6])
            _arc(path, px, py, rx, ry, rot, large, sweep, ex, ey)
            px, py = ex, ey
        elif up == "Z":
            path.closeSubpath()
        c_prev, q_prev = None, None       # 只有 C/S/Q/T 会留下反射控制点
    return path


def transform_from(spec):
    """transform 属性串 → QTransform（SVG 的列表语义就是从左到右复合）"""
    t = QTransform()
    for name, arg in _FUNC.findall(spec or ""):
        nums = [float(n) for n in _NUM.findall(arg)]
        if name == "translate":
            t.translate(nums[0], nums[1] if len(nums) > 1 else 0)
        elif name == "scale":
            t.scale(nums[0], nums[1] if len(nums) > 1 else nums[0])
        elif name == "rotate":
            if len(nums) >= 3:
                t.translate(nums[1], nums[2])
                t.rotate(nums[0])
                t.translate(-nums[1], -nums[2])
            else:
                t.rotate(nums[0])
        elif name == "skewX":
            t.shear(math.tan(math.radians(nums[0])), 0)
        elif name == "skewY":
            t.shear(0, math.tan(math.radians(nums[0])))
        elif name == "matrix":
            t = t * QTransform(nums[0], nums[1], 0, nums[2], nums[3], 0,
                               nums[4], nums[5], 1)
    return t


def load_asset(fname):
    """读素材里的 SVG，返回 (QPainterPath, viewBox QRectF)；按 mtime 缓存"""
    from .paths import ASSETS_DIR
    fp = os.path.join(ASSETS_DIR, fname)
    mtime = os.path.getmtime(fp)
    hit = _CACHE.get(fp)
    if hit and hit[0] == mtime:
        return hit[1], hit[2]
    with open(fp, "r", encoding="utf-8") as f:
        text = f.read()
    vb = QRectF(0, 0, 24, 24)
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', text)
    if m:
        n = [float(v) for v in _NUM.findall(m.group(1))]
        if len(n) == 4:
            vb = QRectF(n[0], n[1], n[2], n[3])
    out = QPainterPath()
    stack = []                                # 当前 <g> 链的复合变换
    for tag in _TAG.finditer(text):
        closing, name, rest = tag.group(1), tag.group(2), tag.group(3)
        attrs = dict(_ATTR.findall(rest))
        if name == "svg":
            continue
        if closing:
            if stack:
                stack.pop()
            continue
        parent = stack[-1] if stack else QTransform()
        t = parent
        if "transform" in attrs:
            # 行向量约定：p' = p·(M_self·M_parent)，先走元素自己的、再走父级的
            t = transform_from(attrs["transform"]) * parent
        if name == "g":
            stack.append(t)
            continue
        if name == "path" and "d" in attrs:
            piece = t.map(path_from_d(attrs["d"]))
            out = out.united(piece) if not out.isEmpty() else piece
    _CACHE[fp] = (mtime, out, vb)
    return out, vb


def scaled_into(src, src_box, box, size):
    """把图形等比缩到 box 内居中的 size（size 指图形自身的**最长边**）。

    居中用的是图形自己的 boundingRect，不是 viewBox：素材里那条 path 在 24×24 的
    框内本来就偏右上（实测 bbox x5.36..21.24、y1.38..20.14），照 viewBox 居中就会
    画歪，12px 的钉子在 26px 热区里看着像贴边。src_box 留着只作 viewBox 参考。
    """
    sb = src.boundingRect()
    span = max(sb.width(), sb.height()) or 1.0
    k = float(size) / span
    t = QTransform()
    t.translate(box.center().x(), box.center().y())
    t.scale(k, k)
    t.translate(-sb.center().x(), -sb.center().y())
    return t.map(src)


__all__ = ["load_asset", "path_from_d", "scaled_into", "transform_from"]
