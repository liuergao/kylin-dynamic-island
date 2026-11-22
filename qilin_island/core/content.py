# -*- coding: utf-8 -*-
"""交互层 · M1 4.2 胶囊内容与每秒驱动

_tick 是唯一的心跳：先走页面 tick，再刷徽标，按秒数节流地采样指标、盯剪贴板与前台窗口。
轮播页在此组装，顺序即展示顺序；新增内容只能插进这个队列，不改排布。"""
import time
from datetime import datetime, timedelta
from PyQt5.QtGui import QFontMetricsF
from ..infra.timeutil import next_occurrence, parse_dt, todo_is_done, today_str
from .consts import CAROUSEL_SECS
from . import theme as T
from ..services import clipboard, system as SI


class ContentMixin:
    def content_init(self):
        """M1 内容驱动初始状态：心跳计数、剪贴板去重、指标采样器"""
        self._tick_n = 0
        self._last_clip = ""
        self.cpu_m = SI.CpuMeter()
        self.net_m = SI.NetMeter()

    def _tick(self):
        now = time.time()
        self._tick_n += 1
        self.clock.setText(time.strftime("%H:%M"))
        for p in self.pages:
            try:
                p.tick(now)
            except Exception:
                pass
        self._update_badge()
        if self._tick_n % 3 == 0:
            self._watch_clipboard()
        if self._tick_n % 20 == 0:
            self._refresh_comp()     # 合成器中途被打开时自动升级成抗锯齿圆角
        if self._tick_n % 2 == 0 and not self.expanded:
            self._update_chips()         # 收起态信息模块（2s 一次）
        # 收起态信息轮播：CAROUSEL_SECS 秒切下一条（待办逐条→会议→设备→电量）
        if (not self.expanded and self.dock == "top"
                and self._style_now() == "pill"
                and len(self._car_pages) > 1
                and now - self._car_at >= CAROUSEL_SECS):
            self._car_idx = (self._car_idx + 1) % len(self._car_pages)
            self._car_at = now
            self._update_chips()      # set_pages 检测到页变化自动淡入
        # 隐藏横线只有 6px 高，靠 1Hz 轮询补一次悬停判定，鼠标划过就能展开
        if self._hidden and self.isVisible() and self._cursor_inside():
            self._hover_at = now
            self.expand()
        self.eq.advance()
        self.toast.sync()           # 岛体刚形变/拖动过，提示条跟着重贴一次
        self._morning(now)

    def _next_meeting(self):
        """→ (datetime, event) 下一场会议（含进行中，重复项按规则推进），无则 None"""
        now = datetime.now()
        best = None
        for e in self.store.events():
            try:
                st = parse_dt(e["start"])
            except Exception:
                st = None
            if st is None:
                continue
            occ = next_occurrence(st, int(e.get("repeat") or 0), now)
            if occ is None or occ > now + timedelta(days=1):
                continue
            if best is None or occ < best[0]:
                best = (occ, e)
        return best

    def _car_build_pages(self):
        """收起态轮播页（段式）：待办逐条 / 会议 / 设备 / 电量；
        专注倒计时与「该喝水了」运行中插队首。→ [(segs, text)]"""
        mods = self.store.settings.get("modules") or {}
        pg_on = self.store.settings.get("pages") or [True] * 8
        sk = self.sk()
        t2, t3 = T.c(sk, "text2").name(), T.c(sk, "text3").name()
        text_c = T.c(sk, "text").name()
        accent, warn = T.c(sk, "accent").name(), T.c(sk, "warn").name()
        now_dt = datetime.now()
        now = time.time()
        pages = []

        # 时钟（图标后的系统时间）：作为轮播第一页，模块开关控制、默认显示
        if mods.get("clock", True):
            hm = now_dt.strftime("%H:%M")
            pages.append(([(hm, text_c)], "时钟 " + hm, None))

        # 专注中 → 插队首
        fp = self._focus_running()
        if fp is not None and pg_on[1]:
            left = T.fmt_duration(fp.remaining)
            pages.append(([("专注", t2), ("　" + left, accent)],
                          "专注　" + left, None))

        # 该喝水了 → 插队（展示 3 分钟或到喝够目标为止）
        wp = self.provider("water")
        if wp is not None and pg_on[2]:
            due, cups, goal = wp.water_due(now)
            if due and cups < goal:
                self._water_show_until = now + 180
            if cups >= goal:
                self._water_show_until = 0
            if now < self._water_show_until:
                pages.append(([("该喝水了", accent),
                               ("　%d/%d 杯" % (cups, goal), warn)],
                              "该喝水了　%d/%d 杯" % (cups, goal), None))

        # 待办：一次显示一条，多条轮播（最多 5 条）；完成判定走统一口径
        if mods.get("todo", True) and pg_on[0]:
            todos = [t for t in self.store.todo_view("today")
                     if not todo_is_done(t)]
            for t in todos[:5]:
                txt = (t.get("text") or "").strip() or "待办"
                pages.append(([("待办", t2), ("　" + txt, text_c)],
                              "待办　" + txt, None))

        # 会议
        if mods.get("meet", True) and pg_on[6]:
            nxt = self._next_meeting()
            if nxt is not None:
                st, ev = nxt
                name = (ev["title"] or "").replace(" ", "")[:6] or "会议"
                if st <= now_dt:
                    pages.append(([("会议", t2),
                                   ("　%s 进行中" % name, accent)],
                                  "会议　%s 进行中" % name, None))
                else:
                    delta = (st - now_dt).total_seconds() / 60.0
                    color = warn if delta <= 30 else text_c
                    pages.append(([("会议", t2),
                                   ("　%s %s" % (st.strftime("%H:%M"), name), color)],
                                  "会议　%s %s" % (st.strftime("%H:%M"), name), None))

        # 设备（CPU · 内存 · 网速合一条，超宽自动滚动）
        dev = []
        if mods.get("cpu"):
            dev.append(("CPU %.0f%%" % self.cpu_m.sample(), t2))
        if mods.get("mem"):
            used, total = SI.mem_info()
            pct = int(100 * used / total) if total else 0
            dev.append(("内存 %d%%" % pct, t2))
        if mods.get("net"):
            rx, tx = self.net_m.sample()
            dev.append(("↓%s ↑%s" % (SI.human(rx), SI.human(tx)), t2))
        if dev:
            segs = []
            for k, (txt, col) in enumerate(dev):
                if k:
                    segs.append((" · ", t3))
                segs.append((txt, col))
            # 最坏情况预算宽：CPU/内存 100%、网速 999.9K —— 数据抖动不引起胶囊宽度变化
            fmc = QFontMetricsF(self.chips._mfont)
            bw = (fmc.horizontalAdvance("CPU 100%")
                  + fmc.horizontalAdvance("内存 100%")
                  + fmc.horizontalAdvance("↓999.9K ↑999.9K")
                  + 2 * fmc.horizontalAdvance(" · "))
            pages.append((segs, " ".join(t for t, _ in segs), bw))

        # 电量
        if mods.get("battery"):
            pct, chg = SI.battery()
            if pct is not None:
                color = t2
                if not chg and pct <= 15:
                    color = T.c(sk, "bad").name()
                elif not chg and pct <= 25:
                    color = warn
                pages.append(([("⚡" if chg else "电", t2),
                               ("%d%%" % pct, color)],
                              "%s%d%%" % ("⚡" if chg else "电", pct), None))
        return pages

    def _update_chips(self):
        if self._anim is not None:
            return          # 动画进行中不重排内容，免得中途改布局把动画帧拖花
        if self.expanded or self.dock != "top" or self._style_now() == "line":
            return
        pages = self._car_build_pages()
        self._car_pages = pages
        self._car_pages_text = [p[1] for p in pages]
        self.chips.set_pages(pages, self._car_idx)

        # 音乐均衡条：只在真的在播放时才出现（1.2.9）
        playing = False
        media = self.provider("media")
        if self._mod("music") and media is not None:
            try:
                media.sync()               # 顺带让播放器状态保持新鲜
            except Exception:
                pass
            st = getattr(media, "_last_state", None) or {}
            playing = (st.get("status") == "Playing")
        self.eq.set_playing(playing)
        self.eq.setVisible(playing)
        self.clock.setVisible(False)          # 收起态时间由轮播页承担

    def _update_header(self):
        self.clock.setText(time.strftime("%H:%M"))
        self._update_badge()

    def _focus_running(self):
        fp = self.provider("focus")
        if fp is None or not getattr(fp, "running", False):
            return None
        left = int(getattr(fp, "remaining", 0) or 0)
        if left <= 0:
            return None
        return fp

    def _update_badge(self):
        """待办数/专注倒计时均已由收起态轮播承担，右侧徽标全部退役隐藏"""
        self.badge.setVisible(False)
        if hasattr(self, "focus_badge"):
            self.focus_badge.setVisible(False)
        self.update()

    def refresh_badge(self):
        self._update_badge()

    def _watch_clipboard(self):
        """每 3 秒采样一次剪贴板：与上次不同才交给剪贴板页入库"""
        if not self.store.settings.get("clip", {}).get("on", True):
            return
        text = clipboard.read_text()
        if text and text != self._last_clip:
            self._last_clip = text
            page = self.provider("clipboard")
            if page is not None:
                page.capture(text)

    def _morning(self, now):
        cfg = self.store.settings.get("morning") or {}
        if not cfg.get("on", True):
            return
        hh, mm = (cfg.get("time") or "08:30").split(":")
        target = datetime.now().replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if datetime.fromtimestamp(now) < target:
            return
        if cfg.get("sent") == today_str():
            return
        body, n = self.store.morning_report(now)
        cfg["sent"] = today_str()
        self.store.save()
        if n:
            self.notify("晨报", body, 8000)
