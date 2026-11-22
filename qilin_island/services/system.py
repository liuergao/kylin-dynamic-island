# -*- coding: utf-8 -*-
"""麒麟灵动岛 · 系统信息采集（读 /proc 与少量系统命令，全部带降级）"""
import os
import re
import subprocess
import time


def _read(path, default=""):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return default


class CpuMeter:
    def __init__(self):
        self.prev = None

    def sample(self):
        parts = _read("/proc/stat").splitlines()[0].split()
        if len(parts) < 5:
            return 0.0
        vals = [int(x) for x in parts[1:8]]
        idle = vals[3] + vals[4]
        total = sum(vals)
        if self.prev is None:
            self.prev = (idle, total)
            return 0.0
        d_idle = idle - self.prev[0]
        d_total = total - self.prev[1]
        self.prev = (idle, total)
        if d_total <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (d_total - d_idle) / d_total))


class NetMeter:
    def __init__(self):
        self.prev = None
        self.t = time.time()

    def sample(self):
        rx = tx = 0
        for line in _read("/proc/net/dev").splitlines()[2:]:
            if ":" not in line:
                continue
            name, rest = line.split(":", 1)
            if name.strip() == "lo":
                continue
            cols = rest.split()
            if len(cols) < 9:
                continue
            rx += int(cols[0])
            tx += int(cols[8])
        now = time.time()
        dt = max(0.001, now - self.t)
        if self.prev is None:
            self.prev = (rx, tx)
            self.t = now
            return 0.0, 0.0
        d_rx = (rx - self.prev[0]) / dt
        d_tx = (tx - self.prev[1]) / dt
        self.prev = (rx, tx)
        self.t = now
        return max(0.0, d_rx), max(0.0, d_tx)


def mem_info():
    d = {}
    for line in _read("/proc/meminfo").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    def kb(key):
        m = re.match(r"(\d+)", d.get(key, "0"))
        return int(m.group(1)) if m else 0
    total = kb("MemTotal")
    avail = kb("MemAvailable") or kb("MemFree")
    used = max(0, total - avail)
    return used * 1024, total * 1024


def disk_info(path="/"):
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        return total - free, total
    except Exception:
        return 0, 0


def uptime_sec():
    try:
        return float(_read("/proc/uptime").split()[0])
    except Exception:
        return 0.0


def self_rss():
    try:
        with open("/proc/self/statm", "r") as f:
            return int(f.read().split()[1]) * 4096
    except Exception:
        return 0


def battery():
    """返回 (百分比, 是否充电中) 或 (None, None)"""
    base = "/sys/class/power_supply"
    try:
        for name in os.listdir(base):
            cap = os.path.join(base, name, "capacity")
            if os.path.exists(cap):
                pct = int(_read(cap).strip() or 0)
                status = _read(os.path.join(base, name, "status")).strip()
                return pct, status.lower().startswith("charg")
    except Exception:
        pass
    return None, None


def cpu_temp():
    """CPU 温度（℃）或 None：thermal_zone → hwmon 降级"""
    # 1) thermal_zone*：取名字带 cpu/soc/x86 的，否则取第一个
    base = "/sys/class/thermal"
    try:
        zones = []
        for name in os.listdir(base):
            if not name.startswith("thermal_zone"):
                continue
            ztype = _read(os.path.join(base, name, "type")).strip().lower()
            try:
                mv = int(_read(os.path.join(base, name, "temp")).strip())
            except ValueError:
                continue
            zones.append((ztype, mv))
        if zones:
            for key in ("cpu", "soc", "x86_pkg", "acpi"):
                for ztype, mv in zones:
                    if key in ztype:
                        return mv / 1000.0
            return zones[0][1] / 1000.0
    except Exception:
        pass
    # 2) hwmon*：name 含 coretemp/k10temp/cpu_thermal 的 temp1_input
    base = "/sys/class/hwmon"
    try:
        for name in sorted(os.listdir(base)):
            chip = _read(os.path.join(base, name, "name")).strip().lower()
            if not any(k in chip for k in ("coretemp", "k10temp", "cpu", "soc")):
                continue
            p = os.path.join(base, name, "temp1_input")
            if os.path.exists(p):
                try:
                    return int(_read(p).strip()) / 1000.0
                except ValueError:
                    continue
    except Exception:
        pass
    return None


def volume():
    """返回 0-100 或 None（pactl → amixer 降级）"""
    try:
        out = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                             capture_output=True, text=True, timeout=1.5).stdout
        m = re.search(r"(\d+)%", out)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    try:
        out = subprocess.run(["amixer", "get", "Master"],
                             capture_output=True, text=True, timeout=1.5).stdout
        m = re.search(r"\[(\d+)%\]", out)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def net_connected():
    try:
        out = subprocess.run(["nmcli", "-t", "-f", "STATE", "general"],
                             capture_output=True, text=True, timeout=1.5).stdout.strip()
        return out.endswith("connected")
    except Exception:
        return None


def human(nbytes):
    n = float(nbytes)
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            return ("%.0f%s" % (n, unit)) if unit in ("B",) else ("%.1f%s" % (n, unit))
        n /= 1024.0
    return "%.1fG" % (nbytes / (1024.0 ** 3))
