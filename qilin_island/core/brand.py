# -*- coding: utf-8 -*-
"""麒麟灵动岛 · 原创标识（岛屿 + 浮标），全部本地绘制，不引用任何第三方素材"""
import os
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import (QPainter, QPainterPath, QLinearGradient, QPixmap,
                         QColor, QPen, QBrush, QImage)

G1 = QColor("#4ecdc4")
G2 = QColor("#3f7fbf")
SAND = QColor("#f6f1e6")
SUN = QColor("#ffd479")

# 素材字形墨色：文件名里的 dark/light 就是这两份颜色本身。标识配色不随皮肤变，
# 但"哪份压在底色上看得清"必须按对比度算，所以 theme.asset_variant 以这里为准。
ASSET_INK = {"arrow": {"dark": "#8b7c6b", "light": "#8fa5b4"},
             "check": {"dark": "#07222a", "light": "#ffffff"}}

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#4ecdc4"/>
      <stop offset="1" stop-color="#3f7fbf"/>
    </linearGradient>
    <radialGradient id="s" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#ffe3a3"/>
      <stop offset="1" stop-color="#ffd479"/>
    </radialGradient>
  </defs>
  <rect x="8" y="24" width="240" height="184" rx="56" fill="url(#g)"/>
  <circle cx="128" cy="26" r="20" fill="url(#g)"/>
  <circle cx="186" cy="74" r="14" fill="url(#s)" opacity="0.95"/>
  <path d="M40 168 C72 128 96 128 120 158 C138 180 160 178 178 150 C192 128 210 130 222 146 L222 190 C222 200 214 208 204 208 L56 208 C46 208 38 200 38 190 Z"
        fill="#f6f1e6" opacity="0.96"/>
  <path d="M40 178 C70 168 86 190 116 186 C146 182 162 196 190 186 C204 181 214 182 222 186"
        fill="none" stroke="#2f6a9e" stroke-opacity="0.35" stroke-width="5" stroke-linecap="round"/>
</svg>
"""


def _draw(p, size, simple=False):
    r = size
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, 0, r)
    grad.setColorAt(0.0, G1)
    grad.setColorAt(1.0, G2)

    body = QPainterPath()
    body.addRoundedRect(QRectF(r * 0.03, r * 0.10, r * 0.94, r * 0.72),
                        r * 0.22, r * 0.22)
    p.fillPath(body, QBrush(grad))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(r * 0.5, r * 0.10), r * 0.078, r * 0.078)

    if simple:
        p.setBrush(SAND)
        p.drawRoundedRect(QRectF(r * 0.22, r * 0.58, r * 0.56, r * 0.10),
                          r * 0.05, r * 0.05)
        return

    p.setBrush(QBrush(SUN))
    p.drawEllipse(QPointF(r * 0.73, r * 0.29), r * 0.055, r * 0.055)

    island = QPainterPath()
    island.moveTo(r * 0.16, r * 0.66)
    island.cubicTo(r * 0.28, r * 0.50, r * 0.37, r * 0.50, r * 0.47, r * 0.62)
    island.cubicTo(r * 0.54, r * 0.70, r * 0.63, r * 0.70, r * 0.70, r * 0.59)
    island.cubicTo(r * 0.75, r * 0.50, r * 0.82, r * 0.51, r * 0.87, r * 0.57)
    island.lineTo(r * 0.87, r * 0.74)
    island.lineTo(r * 0.16, r * 0.74)
    island.closeSubpath()
    p.setBrush(SAND)
    p.drawPath(island)

    pen = QPen(QColor(47, 106, 158, 90))
    pen.setWidthF(r * 0.02)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    wave = QPainterPath()
    wave.moveTo(r * 0.16, r * 0.70)
    wave.cubicTo(r * 0.27, r * 0.66, r * 0.34, r * 0.75, r * 0.45, r * 0.73)
    wave.cubicTo(r * 0.57, r * 0.71, r * 0.63, r * 0.77, r * 0.74, r * 0.73)
    wave.cubicTo(r * 0.80, r * 0.71, r * 0.84, r * 0.71, r * 0.87, r * 0.73)
    p.drawPath(wave)


def logo_pixmap(size=128, simple=False):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    _draw(p, size, simple=simple)
    p.end()
    return QPixmap.fromImage(img)


def arrow_asset(out_dir, color, name):
    """下拉小三角（QSS 用图，避免 Qt 三角边框不支持）"""
    pm = QPixmap(18, 12)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color)))
    path = QPainterPath()
    path.moveTo(4, 3)
    path.lineTo(14, 3)
    path.lineTo(9, 9)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    path_out = os.path.join(out_dir, name)
    pm.save(path_out, "PNG")
    return path_out


def check_asset(out_dir, color=ASSET_INK["check"]["dark"], name="check-dark.png"):
    pm = QPixmap(14, 14)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(3.2, 7.4)
    path.lineTo(6.0, 10.2)
    path.lineTo(11.0, 4.2)
    p.drawPath(path)
    p.end()
    out = os.path.join(out_dir, name)
    pm.save(out, "PNG")
    return out


def save_assets(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for s in (22, 32, 64, 128, 256):
        path = os.path.join(out_dir, "logo-%d.png" % s)
        logo_pixmap(s).save(path, "PNG")
        written.append(path)
    tray = os.path.join(out_dir, "tray.png")
    logo_pixmap(32, simple=True).save(tray, "PNG")
    written.append(tray)
    for kind, gen in (("arrow", arrow_asset), ("check", check_asset)):
        for tone in ("light", "dark"):
            written.append(gen(out_dir, ASSET_INK[kind][tone],
                               "%s-%s.png" % (kind, tone)))
    svg = os.path.join(out_dir, "logo.svg")
    with open(svg, "w", encoding="utf-8") as f:
        f.write(SVG)
    written.append(svg)
    return written
