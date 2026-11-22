# -*- coding: utf-8 -*-
"""平台层 · X11 / UKUI 差异（M17）

麒麟桌面是 X11 + UKUI，几处行为只能靠 X 协议属性纠正：有没有合成器、
前台窗口是不是全屏、窗口要不要进任务栏。这些判断全部集中在这里，
上层只问结果——换到 Wayland 或别的发行版时只改这一层。

所有函数失败一律静默返回安全值：命令不存在（未装 x11-utils）时岛体仍要能跑。
"""
import ctypes
import ctypes.util
import os
import shutil
import subprocess


def _out(cmd, timeout=1):
    """跑一条 xprop 取输出；命令缺失或异常返回 None（不看退出码，属性提示在 stdout 里）"""
    if not shutil.which(cmd[0]):
        return None
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout
    except Exception:
        return None


def _cm_owner_via_x11():
    """用 X 协议问 _NET_WM_CM_S<n> 这个 selection 有没有属主（None=没查到，不是"没有"）

    合成器在场就声明并持有这个 selection，这是 EWMH 唯一的正式口径；它不往 root
    上写任何属性，所以 xprop -root 永远查不到。KWin/ukui-kwin 就是这样：桌面明明
    在合成，老写法一路判成"无合成器"，岛体退回 1-bit 遮罩，圆角就成了台阶。
    """
    try:
        name = ctypes.util.find_library("X11")
        if not name:
            return None
        x = ctypes.cdll.LoadLibrary(name)
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XScreenCount.restype = ctypes.c_int
        x.XScreenCount.argtypes = [ctypes.c_void_p]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetSelectionOwner.restype = ctypes.c_void_p
        x.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    except Exception:
        return None
    dpy = None
    try:
        dpy = x.XOpenDisplay(None)
        if not dpy:
            return None
        for n in range(max(1, x.XScreenCount(dpy))):
            atom = x.XInternAtom(dpy, ("_NET_WM_CM_S%d" % n).encode(), 0)
            if atom and x.XGetSelectionOwner(dpy, atom):
                return True
        return False
    except Exception:
        return None
    finally:
        if dpy:
            try:
                x.XCloseDisplay(dpy)
            except Exception:
                pass


def has_compositor():
    """有无合成器：没有才退化为 1-bit 遮罩的不透明绘制，避免黑边/不可见

    FUYU_COMPOSITE=0/1 用于现场对照测试，不用换窗口管理器就能验证两种绘制路径。
    先问 X 协议的 selection 属主；只有 libX11 都加载不了（非 X11 会话、精简系统）
    才退回 xprop 那个老口径——它偏保守（查不到就当没有），至少不会画出黑块。
    """
    env = os.environ.get("FUYU_COMPOSITE")
    if env in ("0", "1"):
        return env == "1"
    hit = _cm_owner_via_x11()
    if hit is not None:
        return hit
    out = _out(["xprop", "-root", "_NET_WM_CM_S0"])
    if out is None:
        return False
    return "not found" not in out


def skip_taskbar(wid):
    """让窗口不出现在底栏/任务栏：先试 wmctrl，再退回 xprop 写状态"""
    for cmd in (["wmctrl", "-i", "-r", hex(wid), "-b", "add,skip_taskbar"],
                ["xprop", "-id", hex(wid), "-f", "_NET_WM_STATE", "32a",
                 "-set", "_NET_WM_STATE", "_NET_WM_STATE_SKIP_TASKBAR"]):
        if shutil.which(cmd[0]) is None:
            continue
        try:
            if subprocess.run(cmd, capture_output=True, timeout=2).returncode == 0:
                return True
        except Exception:
            continue
    return False


def set_utility_type(wid):
    """把 _NET_WM_WINDOW_TYPE 改成只保留 UTILITY，必须在窗口 map 之前调用。

    麒麟 UKUI 的底栏只要发现类型里含 NORMAL 就建一个任务栏按钮（Qt 的 Qt.Tool 会
    写成 UTILITY + NORMAL，skip_taskbar 状态也不被采纳）。改类型后底栏不再占位，
    窗口仍由 WM 管理，键盘焦点、置顶、拖动都正常。
    """
    try:
        x11 = ctypes.CDLL("libX11.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XChangeProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_ulong), ctypes.c_int]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        dpy = x11.XOpenDisplay(None)
        if dpy:
            atom_type = x11.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE", False)
            atom_util = x11.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE_UTILITY", False)
            arr = (ctypes.c_ulong * 1)(atom_util)
            # 4 = XA_ATOM
            x11.XChangeProperty(dpy, ctypes.c_ulong(wid), ctypes.c_ulong(atom_type),
                                ctypes.c_ulong(4), 32, 0, arr, 1)
            x11.XFlush(dpy)
            return True
    except Exception:
        pass
    if shutil.which("xprop") is None:
        return False
    try:
        return subprocess.run(
            ["xprop", "-id", hex(wid), "-f", "_NET_WM_WINDOW_TYPE", "32a",
             "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_UTILITY"],
            capture_output=True, timeout=2).returncode == 0
    except Exception:
        return False
