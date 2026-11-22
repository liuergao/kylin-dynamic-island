# -*- coding: utf-8 -*-
"""支撑层 · 本地数据（M14 的持久化侧）

JSON 单文件存业务数据，剪贴板另用 sqlite。字段、写入方式与 1.2.8 完全一致，
老用户目录里的 data.json / clip.db 可直接沿用。

本模块不含 Qt 依赖，可以单独跑单测；时钟可注入，便于测提醒逻辑。
"""
import os
import time
import uuid
from datetime import datetime, date, timedelta

from . import config, ics, paths
from .clipstore import ClipboardStore
from .timeutil import (REPEAT_ALL, dow_bit, ev_occurrence, fmt_dt, parse_dt,
                       todo_is_done, today_str)


class Store:
    """单文件 JSON 存储，写入原子化；剪贴板单独用 sqlite"""

    def __init__(self, home=None, clock=None):
        self.home = home or paths.config_dir()
        os.makedirs(self.home, exist_ok=True)
        self.path = os.path.join(self.home, "data.json")
        self.clock = clock or time.time
        self.data = self._load()
        self.clip = ClipboardStore(os.path.join(self.home, "clip.db"),
                                   max_items=self.data["settings"]["clip"]["max"])

    def _load(self):
        raw = config.read_raw(self.path)
        data = {
            "settings": config.build_settings(raw.get("settings")),
            "todos": [], "events": [], "shelf": [],
            "water": {"date": today_str(), "cups": 0},
            "focus": {"date": today_str(), "done": 0, "seconds": 0},
        }
        for k in ("todos", "events", "shelf", "water", "focus"):
            if k in raw:
                data[k] = raw[k]
        return data

    def save(self):
        config.write_json(self.path, self.data)

    @property
    def settings(self):
        return self.data["settings"]

    def set_setting(self, key, value):
        self.settings[key] = value
        self.save()

    def todos(self):
        return self.data["todos"]

    def todo(self, tid):
        for t in self.data["todos"]:
            if t["id"] == tid:
                return t
        return None

    def add_todo(self, text, due=None, repeat=0):
        text = (text or "").strip()
        if not text:
            return None
        item = {
            "id": uuid.uuid4().hex[:10],
            "text": text,
            "due": fmt_dt(due) if due else "",
            "repeat": int(repeat or 0) & REPEAT_ALL,
            "done_on": "",
            "reminded": 0,
            "created": self.clock(),
        }
        self.data["todos"].append(item)
        self.save()
        return item

    def update_todo(self, tid, **kw):
        t = self.todo(tid)
        if not t:
            return None
        t.update(kw)
        self.save()
        return t

    def remove_todo(self, tid):
        self.data["todos"] = [t for t in self.data["todos"] if t["id"] != tid]
        self.save()

    def restore_todo(self, t):
        """删除撤销用：把整条记录原样放回（id 不变），已存在同 id 则忽略"""
        if t and not self.todo(t.get("id")):
            self.data["todos"].append(t)
            self.save()
            return t
        return None

    def toggle_todo(self, tid, on=None):
        t = self.todo(tid)
        if not t:
            return None
        if t.get("repeat"):
            # 重复待办：完成态按天重置
            cur = t.get("done_on") or ""
            if on is None:
                on = cur != today_str()
            t["done_on"] = today_str() if on else ""
        else:
            done = bool(t.get("done_on"))
            if on is None:
                on = not done
            t["done_on"] = today_str() if on else ""
        self.save()
        return t

    def todo_view(self, view="today", today=None):
        """view: today / week / all（1.4.4 起页面不再切视图，晨报与轮播仍用本函数）

        完成判定统一走 todo_is_done：非重复项 done_on 有值即完成（不再要求
        等于今天，前天做完的不会隔两天「复活」回今天列表）。"""
        day = today or date.today()
        out = []
        for t in self.data["todos"]:
            due = parse_dt(t.get("due"))
            rep = int(t.get("repeat") or 0)
            done = todo_is_done(t, day)
            if view == "all":
                out.append(t)
                continue
            if rep:
                hit = bool(rep & dow_bit(day))
                if view == "week":
                    hit = True
                if hit:
                    out.append(t)
                continue
            if due is None:
                if view == "today" and not done:
                    out.append(t)
                elif view == "week":
                    out.append(t)
                continue
            if view == "today":
                if due.date() <= day and not done:
                    out.append(t)
            else:
                week_end = day + timedelta(days=6 - day.weekday())
                if day <= due.date() <= week_end:
                    out.append(t)
        return out

    def due_todos(self, now=None):
        """到点未完成、且今天未提醒过的待办"""
        now = datetime.fromtimestamp(now or self.clock())
        hit = []
        for t in self.data["todos"]:
            rep = int(t.get("repeat") or 0)
            due = parse_dt(t.get("due"))
            if due is None:
                continue
            if rep and not (rep & dow_bit(now.date())):
                continue
            done = (t.get("done_on") or "") == now.date().isoformat()
            if done:
                continue
            if due <= now:
                if t.get("reminded") != 1 and not rep:
                    hit.append(t)
                elif rep and t.get("remind_key") != now.date().isoformat():
                    hit.append(t)
        return hit

    def mark_reminded(self, tid, now=None):
        t = self.todo(tid)
        if not t:
            return
        now = datetime.fromtimestamp(now or self.clock())
        if t.get("repeat"):
            t["remind_key"] = now.date().isoformat()
        else:
            t["reminded"] = 1
        self.save()

    def morning_report(self, now=None):
        now = datetime.fromtimestamp(now or self.clock())
        todos = self.todo_view("today", now.date())
        events = self.events_on(now.date())
        lines = ["今天 %d 项待办，%d 个日程" % (len(todos), len(events))]
        for t in todos[:4]:
            lines.append("· " + t["text"])
        for e in events[:3]:
            lines.append("· %s %s" % (parse_dt(e["start"]).strftime("%H:%M"), e["title"]))
        return "\n".join(lines), len(todos) + len(events)

    def events(self):
        return self.data["events"]

    def add_event(self, title, start, remind=10, end=None, note="", repeat=0):
        title = (title or "").strip()
        if not title or not start:
            return None
        rep = int(repeat or 0)
        ev = {"id": uuid.uuid4().hex[:10], "title": title,
              "start": fmt_dt(start), "end": fmt_dt(end) if end else "",
              "remind": int(remind), "reminded": 0, "note": note}
        if rep:                      # 旧记录没有 repeat 键：读取一律 .get(...,0)，不迁移
            ev["repeat"] = max(0, min(4, rep))
        self.data["events"].append(ev)
        self.data["events"].sort(key=lambda e: e["start"])
        self.save()
        return ev

    def remove_event(self, eid):
        self.data["events"] = [e for e in self.data["events"] if e["id"] != eid]
        self.save()

    def events_on(self, day):
        """当天发生的日程：非重复看原始日，重复按规则推进到 day（1.4.4）"""
        out = []
        for e in self.data["events"]:
            st = parse_dt(e["start"])
            if st is None:
                continue
            if ev_occurrence(st, int(e.get("repeat") or 0), day) is not None:
                out.append(e)
        return out

    def due_events(self, now=None):
        """到点该提醒的日程：非重复提醒一次（reminded），重复每天一次
        （remind_key=当天），老记录无 repeat 键一律按 0 处理，不迁移数据"""
        now = datetime.fromtimestamp(now or self.clock())
        hit = []
        for e in self.data["events"]:
            st = parse_dt(e["start"])
            if st is None:
                continue
            rep = int(e.get("repeat") or 0)
            if rep:
                occ = ev_occurrence(st, rep, now.date())
                if occ is None or e.get("remind_key") == now.date().isoformat():
                    continue
            else:
                if e.get("reminded"):
                    continue
                occ = st
            lead = timedelta(minutes=int(e.get("remind") or 0))
            if occ - lead <= now < occ + timedelta(minutes=1):
                hit.append(e)
        return hit

    def mark_event_reminded(self, ev, now=None):
        now = datetime.fromtimestamp(now or self.clock())
        if int(ev.get("repeat") or 0):
            ev["remind_key"] = now.date().isoformat()
        else:
            ev["reminded"] = 1
        self.save()

    def water_reset_if_needed(self):
        w = self.data["water"]
        if w.get("date") != today_str():
            w["date"] = today_str()
            w["cups"] = 0
            self.save()
        return w

    def water_add(self, delta=1):
        w = self.water_reset_if_needed()
        w["cups"] = max(0, int(w.get("cups", 0)) + delta)
        self.save()
        return w["cups"]

    def water_today(self):
        return self.water_reset_if_needed().get("cups", 0)

    def focus_today(self):
        f = self.data["focus"]
        if f.get("date") != today_str():
            f["date"] = today_str()
            f["done"] = 0
            f["seconds"] = 0
            self.save()
        return f

    def focus_add(self, seconds):
        f = self.focus_today()
        f["done"] = int(f.get("done", 0)) + 1
        f["seconds"] = int(f.get("seconds", 0)) + int(seconds)
        self.save()
        return f

    def shelf(self):
        return self.data["shelf"]

    def shelf_add(self, paths_):
        have = {s["path"] for s in self.data["shelf"]}
        added = 0
        for p in paths_:
            p = os.path.abspath(p)
            if p in have or not os.path.exists(p):
                continue
            self.data["shelf"].append({"path": p, "added": self.clock()})
            have.add(p)
            added += 1
        if added:
            # 只保留最近 20 个
            self.data["shelf"] = self.data["shelf"][-20:]
            self.save()
        return added

    def shelf_remove(self, path):
        self.data["shelf"] = [s for s in self.data["shelf"] if s["path"] != path]
        self.save()

    def shelf_clear(self):
        """清空整站，返回被清掉的条目（调用方留着做撤销）"""
        gone = list(self.data["shelf"])
        if gone:
            self.data["shelf"] = []
            self.save()
        return gone

    def shelf_restore(self, items):
        """撤销清空：按原顺序整批放回，已存在的路径跳过"""
        have = {s["path"] for s in self.data["shelf"]}
        for s in items:
            if s["path"] not in have:
                self.data["shelf"].append(s)
                have.add(s["path"])
        self.data["shelf"] = self.data["shelf"][-20:]
        self.save()

    def import_ics(self, text):
        """解析在 infra/ics.py，落盘与去重留在这里（保持与 1.2.8 相同的计数口径）"""
        added = 0
        for title, st, weeks in ics.parse_ics(text):
            for i in range(weeks):
                s = st + timedelta(weeks=i)
                if any(parse_dt(e["start"]) == s for e in self.data["events"]):
                    continue
                self.add_event(title, s, remind=10)
                added += 1
        return added
