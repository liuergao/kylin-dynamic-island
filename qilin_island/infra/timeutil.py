# -*- coding: utf-8 -*-
"""支撑层 · 时间与重复规则（纯逻辑，无 Qt 依赖）"""
import time
from calendar import monthrange
from datetime import datetime, date, timedelta


def now_ts():
    return time.time()


def today_str():
    return date.today().isoformat()


def parse_dt(s):
    """'2026-11-07 18:00' / '2026-11-07' → datetime；失败返回 None"""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d":
                d = d.replace(hour=23, minute=59)
            return d
        except ValueError:
            continue
    return None


def fmt_dt(d, with_time=True):
    if d is None:
        return ""
    return d.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


def dow_bit(d):
    """周一=bit0 … 周日=bit6"""
    return 1 << d.weekday()


REPEAT_ALL = 0b1111111


def repeat_label(mask):
    if not mask:
        return "不重复"
    if mask == REPEAT_ALL:
        return "每天"
    if mask == 0b0011111:
        return "工作日"
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    picked = [names[i] for i in range(7) if mask & (1 << i)]
    return "每" + "·".join(picked) if len(picked) <= 2 else "每周" + ",".join(picked)


# ── 待办完成口径（1.4.4 统一：行勾选 / 未完成计数 / 收起态轮播共用这一个函数）──
#
# 此前三处各判各的：store.todo_view 判 done_on==今天，页面计数判 not done_on，
# 轮播又判一遍 not done_on —— 一条前天完成的待办会「显示没做、计数算做了」。
# 规则：非重复项 done_on 有值即永久完成；重复项只认当天（按天重置）。
def todo_is_done(t, day=None):
    done_on = t.get("done_on") or ""
    if not done_on:
        return False
    if int(t.get("repeat") or 0):
        return done_on == (day or date.today()).isoformat()
    return True


def added_label(created_ts, now=None):
    """待办行右侧时间戳：当天「刚刚」，否则「11-21 添加」"""
    if not created_ts:
        return ""
    d = date.fromtimestamp(float(created_ts))
    today = (now or date.today())
    if d == today:
        return "刚刚"
    return "%02d-%02d 添加" % (d.month, d.day)


# ── 日程重复（1.4.4，重复能力从待办迁到日历）─────────────────────────────
EV_R_NONE, EV_R_DAILY, EV_R_WDAY, EV_R_WEEK, EV_R_MONTH = range(5)
EV_REPEAT_OPTIONS = [("不重复", EV_R_NONE), ("每天", EV_R_DAILY),
                     ("工作日", EV_R_WDAY), ("每周", EV_R_WEEK),
                     ("每月", EV_R_MONTH)]


def ev_occurrence(start_dt, repeat, day):
    """重复日程在 day 当天的开始时刻；不匹配返回 None。

    repeat=0 只在原始日匹配；每周=同星期几；每月=同日期号，
    月末溢出钳到当月最后一天（1月31日每月 → 2月只落 28/29 日，
    绝不会构造出 2月31日 这种不存在的日期）。"""
    if start_dt is None or day is None:
        return None
    rep = int(repeat or 0)
    if rep == EV_R_NONE:
        return start_dt if start_dt.date() == day else None
    if rep == EV_R_DAILY:
        return datetime.combine(day, start_dt.time())
    if rep == EV_R_WDAY:
        return datetime.combine(day, start_dt.time()) if day.weekday() < 5 else None
    if rep == EV_R_WEEK:
        return datetime.combine(day, start_dt.time()) if day.weekday() == start_dt.weekday() else None
    if rep == EV_R_MONTH:
        target = min(start_dt.day, monthrange(day.year, day.month)[1])
        return datetime.combine(day, start_dt.time()) if day.day == target else None
    return None


def next_occurrence(start_dt, repeat, now, horizon_days=1):
    """[now-2h, now+horizon] 窗口内最早的一次开始时刻（重复项逐日推进）；
    没有则 None。非重复项等价于原始时刻本身。"""
    rep = int(repeat or 0)
    best = None
    for off in range(0, horizon_days + 1):
        occ = ev_occurrence(start_dt, rep, (now + timedelta(days=off)).date())
        if occ is None:
            continue
        if occ + timedelta(hours=2) < now:      # 已结束 2 小时的不再算
            continue
        if best is None or occ < best:
            best = occ
    return best
