# -*- coding: utf-8 -*-
"""支撑层 · 运行目录（M14/M17）

三类数据的落点：配置与业务数据在用户配置目录，素材随包走，日志（M16）在缓存目录。
"""
import os

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(PKG_DIR)

# 素材：下拉三角 / 对号 / logo（QSS 里的 url() 需要绝对路径）
ASSETS_DIR = os.path.join(PROJECT_DIR, "resources", "assets")


def config_dir():
    """数据目录，与 1.2.8 一致；FUYU_HOME 用于测试与便携运行"""
    return os.environ.get("FUYU_HOME") or os.path.join(
        os.path.expanduser("~"), ".config", "fuyu")


def log_dir():
    return os.path.join(os.environ.get("XDG_CACHE_HOME")
                        or os.path.expanduser("~/.cache"), "fuyu")
