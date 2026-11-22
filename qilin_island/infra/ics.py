# -*- coding: utf-8 -*-
"""支撑层 · .ics 解析（M10 的导入入口）

极简实现：只取 SUMMARY / DTSTART / RRULE，FREQ=WEEKLY 展开未来 8 周，
避免无限展开占满内存与列表。解析结果由 Store 落盘，本模块不写数据。
"""
from datetime import datetime


def parse_ics(text):
    """→ [(title, start_datetime, weeks)]"""
    out = []
    for block in _unfold(text or "").split("BEGIN:VEVENT")[1:]:
        block = block.split("END:VEVENT")[0]
        fields = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            fields[k.split(";")[0].upper()] = v.strip()
        st = _ics_dt(fields.get("DTSTART", ""))
        if st is None:
            continue
        weeks = 8 if "FREQ=WEEKLY" in fields.get("RRULE", "") else 1
        out.append((fields.get("SUMMARY", "导入日程"), st, weeks))
    return out


def _unfold(t):
    return t.replace("\r\n", "\n").replace("\r", "\n").replace("\n ", "")


def _ics_dt(raw):
    raw = (raw or "").strip().replace("Z", "")
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            d = datetime.strptime(raw, fmt)
            if fmt == "%Y%m%d":
                d = d.replace(hour=9, minute=0)
            return d
        except ValueError:
            continue
    return None
