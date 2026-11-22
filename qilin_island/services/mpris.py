# -*- coding: utf-8 -*-
"""能力层 · MPRIS 播放器客户端（M12 的数据来源）

只负责读取与控制媒体播放器，不碰界面；DBus 不可用时所有方法返回空，界面自动隐藏音乐胶囊。"""
import os
import time


class Mpris:
    """MPRIS 客户端；无会话总线或无播放器时全部安全降级"""

    IFACE = "org.mpris.MediaPlayer2.Player"
    PROPS = "org.freedesktop.DBus.Properties"

    def __init__(self):
        self.ok = False
        self.bus = None
        self.service = None
        self.fake = False
        self._t0 = time.time() - 45
        self._loop = "Playlist"
        self._shuffle = False
        try:
            from PyQt5 import QtDBus
            self.QtDBus = QtDBus
            if QtDBus.QDBusConnection.sessionBus().isConnected():
                self.bus = QtDBus.QDBusConnection.sessionBus()
                self.ok = True
        except Exception:
            self.bus = None
        # 演示/无总线环境降级：FUYU_FAKE_MPRIS=1 启用内置演示播放器
        # （UI 全部走真实代码路径，仅数据源为替身）
        if not self.ok and os.environ.get("FUYU_FAKE_MPRIS") == "1":
            self.ok = True
            self.fake = True
            self.service = "org.mpris.MediaPlayer2.staged"

    def players(self):
        if self.fake:
            return [self.service]
        if not self.bus:
            return []
        try:
            msg = self.QtDBus.QDBusMessage.createMethodCall(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "ListNames")
            reply = self.bus.call(msg, self.QtDBus.QDBus.CallMode.Block, 300)
            args = reply.arguments()
            names = args[0] if args else []
            try:
                names = [str(n) for n in names]
            except TypeError:
                names = []
            return [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]
        except Exception:
            return []

    def pick(self):
        names = self.players()
        if not names:
            return None
        if self.service in names:
            return self.service
        self.service = names[0]
        return self.service

    def _all(self):
        """一次 GetAll 拿全部属性（QtDBus 的 Properties.Get 在部分环境返回 UnknownInterface）"""
        if self.fake:
            pos = (time.time() - self._t0) % 224.0
            return {"PlaybackStatus": "Playing", "LoopStatus": self._loop,
                    "Shuffle": self._shuffle,
                    "Position": int(pos * 1e6),
                    "Metadata": {"xesam:title": "星光漫步",
                                 "xesam:artist": ["银河原声带"],
                                 "mpris:length": int(224e6),
                                 "mpris:artUrl": "file:///tmp/fuyu_fake_cover.png",
                                 "mpris:position": int(pos * 1e6)}}
        if not self.bus or not self.service:
            return {}
        try:
            msg = self.QtDBus.QDBusMessage.createMethodCall(
                self.service, "/org/mpris/MediaPlayer2", self.PROPS, "GetAll")
            msg << self.IFACE
            reply = self.bus.call(msg, self.QtDBus.QDBus.CallMode.Block, 400)
            args = reply.arguments()
            if not args:
                return {}
            raw = args[0]
            try:
                return dict(raw)
            except Exception:
                return {}
        except Exception:
            return {}

    def _get(self, prop):
        return self._all().get(prop)

    def _call(self, method):
        if self.fake:
            return True
        if not self.bus or not self.service:
            return False
        try:
            msg = self.QtDBus.QDBusMessage.createMethodCall(
                self.service, "/org/mpris/MediaPlayer2", self.IFACE, method)
            self.bus.call(msg, self.QtDBus.QDBus.CallMode.Block, 400)
            return True
        except Exception:
            return False

    def set_property(self, name, value):
        """写回 MPRIS 属性（LoopStatus / Shuffle 等），失败静默"""
        if self.fake:
            if name == "LoopStatus":
                self._loop = str(value)
            elif name == "Shuffle":
                self._shuffle = bool(value)
            return True
        if not self.bus or not self.service:
            return False
        try:
            msg = self.QtDBus.QDBusMessage.createMethodCall(
                self.service, "/org/mpris/MediaPlayer2", self.PROPS, "Set")
            msg << self.IFACE << name
            msg << self.QtDBus.QDBusVariant(value)
            self.bus.call(msg, self.QtDBus.CallMode.Block, 400)
            return True
        except Exception:
            return False

    def set_loop(self, v):
        """v: None / Track / Playlist"""
        return self.set_property("LoopStatus", v)

    def set_shuffle(self, on):
        return self.set_property("Shuffle", bool(on))

    def state(self):
        """→ dict(title, artist, status, position, length, art, loop, shuffle) 或 None"""
        if not self.pick():
            return None
        props = self._all()
        if not props:
            return None
        meta = props.get("Metadata") or {}
        try:
            meta = dict(meta)
        except Exception:
            meta = {}
        info = {"title": str(meta.get("xesam:title") or ""),
                "artist": "", "status": str(props.get("PlaybackStatus") or ""),
                "position": float(props.get("Position") or 0) / 1e6,
                "length": float(meta.get("mpris:length") or 0) / 1e6,
                "art": str(meta.get("mpris:artUrl") or ""),
                "loop": str(props.get("LoopStatus") or "None"),
                "shuffle": bool(props.get("Shuffle") or False),
                "service": self.service}
        artists = meta.get("xesam:artist")
        if isinstance(artists, (list, tuple)):
            info["artist"] = " / ".join([str(a) for a in artists])
        elif artists:
            info["artist"] = str(artists)
        return info

    def play_pause(self):
        return self._call("PlayPause")

    def next(self):
        return self._call("Next")

    def prev(self):
        return self._call("Previous")
