# -*- coding: utf-8 -*-
"""支撑层 · 配置（M14）

配置只有一份 data.json，字段全部有默认值：文件缺失或损坏时按内置默认启动，
未知字段原样保留（便于回退旧版本），写入用临时文件 + 重命名，掉电不留半个文件。

落盘结构与 1.2.8 完全一致，老用户的配置与数据可直接沿用。
"""
import copy
import json
import os

DEFAULT_SETTINGS = {
    "skin": "deep",
    "x": None,                      # 旧字段：距屏幕左侧；已由 cx/cy + dock 取代
    "cx": None,                     # 停靠顶部时的水平中心；None 表示屏幕正中
    "cy": None,                     # 停靠左右两侧时的竖直中心；None 表示屏幕正中
    "pinned": False,                # 常驻展开
    "page": 0,
    "pages": [True] * 8,            # 待办/专注/饮水/置物/剪贴/音乐/日历/系统
    "morning": {"on": True, "time": "08:30", "sent": ""},
    "water": {"goal": 8, "cup": 250, "interval": 45, "from": 9, "to": 21},
    "focus": {"work": 25, "rest": 5},
    "clip": {"on": True, "max": 30},
    "autostart": False,
    "dock": "top",
    "style": "pill",                # 收起形态：pill 胶囊 / notch 刘海
    "motion": True,                 # 动效总开关：关掉只是不补中间帧，值照样落位
    "skin_last": {},                # 明暗两组各自记住上次用的皮肤 {dark:xx, light:yy}
    "hidden": False,                # 1.2.9 隐藏态：收成一条横线（托盘右键/关窗触发）
    "modules": {"clock": True, "todo": True, "meet": True, "cpu": False, "mem": False,
                "net": False, "battery": True, "music": True},
    # 下面两项 1.2.9 起不再读取（全屏自动隐藏、最大化缩细线都取消了），
    # 留在默认结构里只为兼容老 data.json 与回退旧版本
    "fullscreen_hide": True,
    "maxline": True,
    "media_player": "",             # 固定的 MPRIS 服务名；空=自动选择
}

# 嵌套字典项：老文件里少某个子键时补齐，避免界面读配置时 KeyError
NESTED = ("morning", "water", "focus", "clip", "modules", "skin_last")

ENUMS = {
    "dock": ("top", "left", "right"),
    "style": ("pill", "notch"),
}


def defaults():
    return copy.deepcopy(DEFAULT_SETTINGS)


def normalize(settings):
    """模式校验：枚举值非法回退默认，嵌套字典缺项补默认，未知键原样留着"""
    for key, allowed in ENUMS.items():
        if settings.get(key) not in allowed:
            settings[key] = DEFAULT_SETTINGS[key]
    for key in NESTED:
        val = settings.get(key)
        base = DEFAULT_SETTINGS[key]
        if not isinstance(val, dict):
            settings[key] = copy.deepcopy(base)
            continue
        for sub, sub_default in base.items():
            val.setdefault(sub, sub_default)
    return settings


def read_raw(path):
    """读整个 data.json；文件缺失或损坏返回空字典，绝不上抛"""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass
    return {}


def build_settings(raw):
    """原始 settings → 可用配置：先叠默认值再校验，未知键原样保留"""
    settings = defaults()
    if isinstance(raw, dict):
        settings.update(raw)
    return normalize(settings)


def read(path):
    return build_settings(read_raw(path).get("settings"))


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
