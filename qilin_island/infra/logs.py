# -*- coding: utf-8 -*-
"""支撑层 · 诊断日志（M16）

现场排障用：只有设了 FUYU_DEBUG_LOG 才落盘，正常运行零开销、不弹窗。
"""
import os
import time


def debug_path():
    return os.environ.get("FUYU_DEBUG_LOG")


def dbg(msg):
    """拖动/拖放链路的时序日志"""
    path = debug_path()
    if not path:
        return
    try:
        with open(path, "a") as f:
            f.write("%.3f %s\n" % (time.time(), msg))
    except OSError:
        pass


def dbg_tag(tag, msg):
    path = debug_path()
    if not path:
        return
    try:
        with open(path, "a") as f:
            f.write("%.3f [%s] %s\n" % (time.time(), tag, msg))
    except OSError:
        pass
