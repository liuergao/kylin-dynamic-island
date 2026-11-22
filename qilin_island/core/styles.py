# -*- coding: utf-8 -*-
"""核心层 · 全局样式表（M2/M5）

一份 QSS 供岛体与所有页面使用。数值不再写死在这里：圆角/间距取自 theme 的设计
token（控件 4px、卡片与浮层 8px，套在卡片里的条目按「外半径 − 内间距」递减），
墨色按对比度现算，每个可交互控件都给齐 静止/悬停/按下/聚焦/禁用 四态。
焦点环必须可见 —— 键盘操作时看不出焦点在哪，等于键盘不可用（无障碍验收项）。
"""
import os

from . import theme as T
from .consts import ASSETS


def _asset(kind, surface):
    """按底色挑字形素材：哪份在这块底上对比度高用哪份。

    以前按皮肤名判（只有 cream 走深色字形），再多一套亮色皮肤就会白勾配白底。
    """
    name = "%s-%s.png" % (kind, T.asset_variant(kind, surface))
    return os.path.join(ASSETS, name).replace("\\", "/")


def tokens(sk):
    """皮肤色板 → QSS 替换字典：颜色、圆角、间距一次算全"""
    d = T.states(sk)
    sp = T.SP
    d.update({
        "r_ctl": int(T.clamp_r(T.R["control"], 8)),
        "r_card": int(T.R["card"]),
        "r_ov": int(T.R["overlay"]),
        "r_tip": int(T.R["control"]),
        "r_item": int(T.nested(T.R["card"], sp["s"])),
        "r_scroll": int(T.clamp_r(T.R["bar"], 6)),
        "r_groove": int(T.clamp_r(T.R["bar"], 4)),
        "r_thumb": int(T.clamp_r(T.R["pill"], 10)),
        # 页签行按钮实测高约 22px（11px 字 + 上下各 2px 内边距 + 1px 边框），
        # 半径取它的一半就是正胶囊；再超就按 clamp 兜底，不会圆成橄榄
        "r_nav": int(T.clamp_r(T.R["pill"], 22)),
        "xs": sp["xs"], "s": sp["s"], "m": sp["m"], "l": sp["l"],
        "xl": sp["xl"], "xxl": sp["xxl"],
        # 下拉箭头在卡片底上，勾选块的字形跟 accent 底上的墨色同色
        "arrow": _asset("arrow", d["card"]),
        "check": _asset("check", d["accent"]),
        # 图钉墨色：深色皮肤纯白，浅色皮肤退回正文墨（同一份判定在 theme.pin_ink，
        # 自绘的 QPainterPath 与 QSS 的 color 必须同源，否则两处颜色会分叉）
        "pin_ink": T.pin_ink(sk).name(),
    })
    return d


_QSS = """
QWidget { font-size: 12px; color: %(text)s; }
QWidget#page, QWidget#head, QWidget#body { background: transparent; }
/* 页签行自带一条卡片底：8 个页签浮在面板渐变上会散成一排字，垫一层底色才是
   一个"可切换的组"。选中项是 accent 胶囊，未选中项透明，整条读作分段控件。
   这段注释只能待在 C 风格注释里：QSS 的井号是 ID 选择器，拿它当行注释会把
   后面整条规则吃掉；注释体内也不能出现反斜杠加星号那对字符，否则提前闭合。 */
QWidget#nav { background: %(card)s; border: 1px solid %(line)s;
              border-radius: %(r_card)spx; }
QToolTip { background: %(card)s; color: %(text)s; border: 1px solid %(line_strong)s;
           border-radius: %(r_tip)spx; padding: %(s)spx %(m)spx; }

QLabel { background: transparent; color: %(text)s; }
QLabel#muted { color: %(text2)s; font-size: 11px; }
QLabel#clock { color: %(text)s; font-size: 15px; font-weight: 600; }
QLabel#chips { color: %(text2)s; font-size: 12px; }
QLabel#badge { color: %(accent)s; font-size: 11px; }
QLabel#focuspill { color: %(accent)s; font-size: 11px; font-weight: 600;
                   background: %(card)s; border: 1px solid %(line)s;
                   border-radius: %(r_ctl)spx; padding: 1px %(m)spx; }

QPushButton { background: %(card)s; color: %(text)s; border: 1px solid %(line)s;
              border-radius: %(r_ctl)spx; padding: %(s)spx %(m)spx; }
QPushButton:hover { background: %(card_hover)s; border-color: %(line_strong)s; }
QPushButton:pressed { background: %(card_pressed)s; border-color: %(accent)s; }
QPushButton:focus { border-color: %(focus)s; }
QPushButton:disabled { background: %(card_dis)s; color: %(text3)s;
                       border-color: %(line)s; }
QPushButton[kind="primary"] { background: %(accent)s; color: %(on_accent)s;
                              border: 1px solid %(accent)s; font-weight: 600; }
QPushButton[kind="primary"]:hover { background: %(accent_hover)s;
                                    border-color: %(accent_hover)s; }
QPushButton[kind="primary"]:pressed { background: %(accent_pressed)s;
                                      border-color: %(accent_pressed)s; }
QPushButton[kind="primary"]:disabled { background: %(card_dis)s;
                                       color: %(text3)s; border-color: %(line)s; }
QPushButton[kind="danger"] { background: %(bad)s; color: %(on_bad)s;
                             border: 1px solid %(bad)s; font-weight: 600; }
QPushButton[kind="danger"]:hover { background: %(bad_hover)s;
                                   border-color: %(bad_hover)s; }
QPushButton[kind="danger"]:pressed { background: %(bad_pressed)s;
                                     border-color: %(bad_pressed)s; }
QPushButton[kind="danger"]:disabled { background: %(card_dis)s;
                                      color: %(text3)s; border-color: %(line)s; }
QPushButton[nav="true"] { background: transparent; border: 1px solid transparent;
                          color: %(text2)s; padding: %(xs)spx %(s)spx;
                          border-radius: %(r_nav)spx; font-size: 11px; }
QPushButton[nav="true"]:hover { color: %(text)s; background: %(card_hover)s; }
QPushButton[nav="true"]:pressed { background: %(card_pressed)s; }
QPushButton[nav="true"]:focus { border-color: %(focus)s; }
QPushButton[nav="true"]:checked { color: %(on_accent)s; background: %(accent)s;
                                  font-weight: 600; }
QPushButton[nav="true"]:checked:hover { background: %(accent_hover)s; }
/* 顶栏那颗钉子（[pin="true"]）钉住时不再铺整块 accent 底：白图钉压在 accent 上
   对比只有 1.94，基本糊成一片。改成卡片底 + accent 描边环，白钉两态都是 11 以上。
   选择器比上面那条多一个属性，QSS 权重更高，会盖住 nav 的 checked 配色。 */
QPushButton[nav="true"][pin="true"]:checked { color: %(pin_ink)s; background: %(card)s;
                                             border: 1px solid %(accent)s; }
QPushButton[nav="true"][pin="true"]:checked:hover { background: %(card_hover)s; }
QPushButton[nav="true"][pin="true"]:checked:pressed { background: %(card_pressed)s; }
/* 键盘焦点环不能因为上面那条就没了：勾上又聚焦时描边仍走 focus 色 */
QPushButton[nav="true"][pin="true"]:checked:focus { border: 1px solid %(focus)s; }
QPushButton[kind="choice"] { text-align: center; padding: %(s)spx %(m)spx; }

QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit {
    background: %(card)s; color: %(text)s; border: 1px solid %(line)s;
    border-radius: %(r_ctl)spx; padding: %(s)spx %(m)spx;
    selection-background-color: %(accent)s; selection-color: %(on_accent)s; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDateEdit:hover, QTimeEdit:hover {
    border-color: %(line_strong)s; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus {
    border: 1px solid %(focus)s; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    background: %(card_dis)s; color: %(text3)s; }
QLineEdit[err="true"] { border: 1px solid %(bad)s; }
QComboBox::drop-down, QDateEdit::drop-down, QTimeEdit::drop-down {
    border: 0; width: 16px; }
QComboBox::down-arrow, QDateEdit::down-arrow, QTimeEdit::down-arrow {
    image: url(%(arrow)s); width: 9px; height: 6px; }
QSpinBox::up-button, QSpinBox::down-button { width: 12px; border: 0;
                                             background: transparent; }
QSpinBox::up-arrow, QSpinBox::down-arrow { width: 0; height: 0; image: none; }
QComboBox QAbstractItemView { background: %(bg1)s; color: %(text)s;
                              border: 1px solid %(line)s;
                              border-radius: %(r_ov)spx; padding: %(s)spx;
                              outline: 0;
                              selection-background-color: %(accent)s;
                              selection-color: %(on_accent)s; }
QComboBox QAbstractItemView::item { min-height: 22px; padding: 0 %(s)spx;
                                    border-radius: %(r_item)spx; }
QComboBox QAbstractItemView::item:hover { background: %(card_hover)s; }
QComboBox QAbstractItemView::item:selected { background: %(accent)s;
                                             color: %(on_accent)s; }

QListWidget { background: transparent; border: none; outline: 0; }
/* 卡片列表与输入框/按钮同一套边距：原生 5px 框 + 4px 内边距会把行内容整体右移
   16px，看起来就是"待办的白框比上面输入框缩进去一截"。框宽收到 1px、内边距 2px，
   行首再配 ROW_PAD=4，勾选框与输入框文字左右对齐（1.4.5）。 */
QListWidget#card { background: %(card)s; border: 1px solid %(line)s;
                   border-radius: %(r_card)spx; padding: %(xs)spx;
                   qproperty-frameShape: 0; qproperty-frameShadow: 0; }
QListWidget::item { padding: 0px %(s)spx; border-radius: %(r_item)spx;
                    color: %(text)s; }
QListWidget::item:hover { background: %(card_hover)s; }
QListWidget::item:selected { background: %(sel_bg)s; color: %(sel_fg)s; }
QListWidget::item:disabled { color: %(text3)s; }
QListWidget::indicator { width: 16px; height: 16px; background: transparent;
                         border: none; }

QCheckBox { color: %(text)s; background: transparent; spacing: %(s)spx; }
QCheckBox::indicator { width: 16px; height: 16px; background: %(card)s;
                       border: 1px solid %(line_strong)s;
                       border-radius: %(r_ctl)spx; }
QCheckBox::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s;
                               image: url(%(check)s); }
QCheckBox::indicator:pressed { background: %(accent_pressed)s; }
QCheckBox::indicator:disabled { background: %(card_dis)s; border-color: %(line)s; }
QCheckBox:disabled { color: %(text3)s; }

QScrollBar { background: transparent; border: none; }
QScrollBar:vertical { width: 6px; }
QScrollBar::handle:vertical { background: %(line)s;
                              border-radius: %(r_scroll)spx; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: %(line_strong)s; }
QScrollBar::handle:vertical:pressed { background: %(accent)s; }
QScrollBar:horizontal { height: 6px; }
QScrollBar::handle:horizontal { background: %(line)s;
                                border-radius: %(r_scroll)spx; min-width: 20px; }
QScrollBar::handle:horizontal:hover { background: %(line_strong)s; }
QScrollBar::handle:horizontal:pressed { background: %(accent)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QSlider::groove:horizontal { height: 4px; background: %(line)s;
                             border-radius: %(r_groove)spx; }
QSlider::sub-page:horizontal { background: %(accent)s;
                               border-radius: %(r_groove)spx; }
QSlider::handle:horizontal { width: 10px; margin: -3px 0;
                             border-radius: %(r_thumb)spx; background: %(accent)s; }
QSlider::handle:horizontal:hover { background: %(accent_hover)s; }
QSlider::handle:horizontal:pressed { background: %(accent_pressed)s; }

QMenu { background: %(bg1)s; color: %(text)s; border: 1px solid %(line)s;
        border-radius: %(r_ov)spx; padding: %(s)spx; }
QMenu::item { padding: %(s)spx 26px %(s)spx %(s)spx;
              border-radius: %(r_item)spx; min-width: 0px; }
QMenu::item:hover { background: %(card_hover)s; }
QMenu::item:selected { background: %(accent)s; color: %(on_accent)s; }
QMenu::item:disabled { color: %(text3)s; background: transparent; }
QMenu::icon { padding-left: %(s)spx; }
QMenu::separator { height: 1px; background: %(line)s;
                   margin: %(s)spx %(m)spx; }

QDialog { background: %(bg1)s; }
"""


def global_qss(sk):
    """岛体与所有页面共用的那份 QSS；素材字形色随底色走，不再认皮肤名"""
    return _QSS % tokens(sk)


# 卡片弹窗（关于 / 赞助 / 联系 / 新建日程）里几种文字角色。字号沿用原白卡的排印，
# 颜色一律换成皮肤派生色：以前那套灰副文本压在白底上只有 3.1:1，小字根本看不清。
_CARD_EXTRA = """
QLabel#t1 { font-size: 17px; font-weight: 700; }
QLabel#t2 { color: %(text2)s; font-size: 12px; }
QLabel#word { color: %(text)s; font-size: 12.5px; }
QLabel#note { color: %(text2)s; font-size: 11px; }
QLabel#ident { color: %(ok)s; background: %(ok_soft)s; border: 1px solid %(ok_line)s;
               border-radius: %(r_ctl)spx; padding: %(s)spx %(m)spx; font-size: 12px; }
QLabel#qq { color: %(accent)s; font-size: 20px; font-weight: 700; }
"""


def card_qss(sk):
    """独立卡片弹窗自带的那套：岛体样式 + 卡片文字角色

    关于框是以「无父窗」创建的，拿不到岛体身上的全局表样式，不自己带一套就会
    退回系统主题（浅色标题栏配深色内容那种割裂）。"""
    return global_qss(sk) + _CARD_EXTRA % tokens(sk)

