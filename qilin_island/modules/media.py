# -*- coding: utf-8 -*-
"""应用层 · 音乐控制（M12 的媒体部分）"""
import os
import time
from PyQt5.QtCore import QPoint, QUrl, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout
from ..infra.lrc import parse_lrc
from ..services.mpris import Mpris
from .base import Page
from ..core.consts import CONTENT_PAD_X
from .widgets import ChoiceMenu
from ..core import theme as T


class MediaPage(Page):
    capabilities = ("media",)
    title = "音乐"
    LYRIC_DIRS = [os.path.expanduser("~/音乐/lyrics"), os.path.expanduser("~/.lyrics"),
                  os.path.expanduser("~/lyrics")]

    def __init__(self, host):
        super().__init__(host)
        self.mpris = Mpris()
        self._pos = 0
        self._length = 0
        self._last = 0
        self._lrc = []
        self._lyric_key = None
        self._art = None                      # 当前封面 URL，去重
        self._art_cache = {}                  # url -> QPixmap（含下载完成回调写入）
        self._last_state = {}                 # 最近一次 MPRIS 状态（循环模式等）

        v = QVBoxLayout(self)
        # 1.4.14：水平边距 14→CONTENT_PAD_X(=0)，与页签卡同一条列缘
        v.setContentsMargins(CONTENT_PAD_X, 8, CONTENT_PAD_X, 10)
        v.setSpacing(6)
        v.addStretch(1)             # 上下等分：未接播放器时整页不会堆在顶上

        head = QHBoxLayout()
        head.setSpacing(10)
        self.cover = QLabel()
        self.cover.setFixedSize(46, 46)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setObjectName("muted")
        self.cover.setVisible(False)          # 拿到封面再显示
        head.addWidget(self.cover)
        info = QVBoxLayout()
        info.setSpacing(1)
        self.title = QLabel("未检测到播放器")
        self.title.setFont(T.font(14, True))
        self.artist = QLabel("")
        self.artist.setObjectName("muted")
        info.addWidget(self.title)
        info.addWidget(self.artist)
        head.addLayout(info, 1)
        self.btn_player = QPushButton("播放器")
        self.btn_player.setProperty("nav", "true")
        self.btn_player.setToolTip("切换/固定播放器（MPRIS）")
        self.btn_player.setCursor(Qt.PointingHandCursor)
        self.btn_player.clicked.connect(self.pick_player)
        head.addWidget(self.btn_player)
        v.addLayout(head)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setEnabled(False)
        v.addWidget(self.slider)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_prev = QPushButton("⏮")
        self.btn_play = QPushButton("▶")
        self.btn_play.setProperty("kind", "primary")
        self.btn_next = QPushButton("⏭")
        self.btn_mode = QPushButton("↻")
        self.btn_mode.setToolTip("循环模式：关闭 / 单曲 / 列表")
        self.btn_rnd = QPushButton("⇄")
        self.btn_rnd.setToolTip("随机播放")
        self.btn_rnd.setCheckable(True)
        row.addStretch(1)           # 控制组（含进度时间）整段居中
        for b in (self.btn_prev, self.btn_play, self.btn_next,
                  self.btn_mode, self.btn_rnd):
            b.setFixedWidth(40)
            row.addWidget(b)
        row.addSpacing(10)
        self.time = QLabel("0:00 / 0:00")
        self.time.setObjectName("muted")
        row.addWidget(self.time)
        row.addStretch(1)
        v.addLayout(row)

        self.lyric = QLabel("歌词：把同名 .lrc 放到 ~/音乐/lyrics 下可自动显示")
        self.lyric.setObjectName("muted")
        self.lyric.setWordWrap(True)
        self.lyric.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.lyric.setMinimumHeight(46)
        v.addWidget(self.lyric)
        v.addStretch(1)

        self.btn_prev.clicked.connect(lambda: self.mpris.prev())
        self.btn_next.clicked.connect(lambda: self.mpris.next())
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_mode.clicked.connect(self.cycle_mode)
        self.btn_rnd.clicked.connect(self.toggle_shuffle)
        self.slider.sliderReleased.connect(self.seek)
        self._qnm = None                      # 懒建：有网络封面需求才用

    MODE_SEQ = [("None", "→"), ("Track", "①"), ("Playlist", "↻")]

    def cycle_mode(self):
        st = self._last_state or {}
        cur = st.get("loop", "None")
        names = [m[0] for m in self.MODE_SEQ]
        try:
            nxt = self.MODE_SEQ[(names.index(cur) + 1) % len(names)][0]
        except ValueError:
            nxt = "Playlist"
        self.mpris.set_loop(nxt)
        self.sync(force=True)

    def toggle_shuffle(self):
        self.mpris.set_shuffle(self.btn_rnd.isChecked())
        self.sync(force=True)

    def shell_skin(self):
        return self.host.sk()

    @staticmethod
    def player_label(service):
        return (service or "").replace("org.mpris.MediaPlayer2.", "") or "自动"

    def pick_player(self):
        names = self.mpris.players()
        if not names:
            self.notify("音乐", "未发现 MPRIS 播放器")
            return
        items = [(self.player_label(n), n) for n in names]
        items.insert(0, ("自动选择", ""))
        m = ChoiceMenu(items, current=self.mpris.service,
                       sk=self.shell_skin(), parent=self)
        act = m.exec_(self.btn_player.mapToGlobal(
            QPoint(0, self.btn_player.height() + 3)))
        if act is None:
            return
        self.use_player(act.data())

    def use_player(self, service):
        self.mpris.service = service or None
        self.host.store.settings["media_player"] = service or ""
        self.host.store.save()
        self.sync(force=True)

    def _apply_cover(self, art):
        """本地 file:// 直接读；http(s) 走 QNetworkAccessManager 异步下载并缓存"""
        if art == self._art:
            return
        self._art = art
        pm = QPixmap()
        if art:
            cached = self._art_cache.get(art)
            if cached is not None:
                pm = cached
            elif art.startswith("file://"):
                pm.load(art[7:])
                self._art_cache[art] = pm
            elif art.startswith(("http://", "https://")):
                # 下载中：先隐藏，到位后回调重绘
                self.cover.setVisible(False)
                self._fetch_cover(art)
                return
        self._set_cover(pm)

    def _set_cover(self, pm):
        if pm and not pm.isNull():
            self.cover.setPixmap(pm.scaled(
                46, 46, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            self.cover.setVisible(True)
        else:
            self.cover.setVisible(False)

    def _fetch_cover(self, url):
        try:
            from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
        except Exception:
            return
        if self._qnm is None:
            self._qnm = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        reply = self._qnm.get(req)

        def done():
            data = reply.readAll()
            pm = QPixmap()
            if not pm.loadFromData(bytes(data)):
                pm = QPixmap()
            self._art_cache[url] = pm
            if self._art == url:
                self._set_cover(pm)
            reply.deleteLater()

        reply.finished.connect(done)

    def toggle_play(self):
        self.mpris.play_pause()
        self.sync(force=True)

    def seek(self):
        if not self._length:
            return
        target = int(self.slider.value() / 1000.0 * self._length * 1e6)
        try:
            from PyQt5 import QtDBus
            if self.mpris.bus and self.mpris.service:
                msg = QtDBus.QDBusMessage.createMethodCall(
                    self.mpris.service, "/org/mpris/MediaPlayer2",
                    self.mpris.IFACE, "SetPosition")
                # 传空 trackid 时多数播放器按当前曲目处理
                msg << QtDBus.QDBusVariant(QtDBus.QDBusObjectPath("/org/mpris/MediaPlayer2/TrackList/NoTrack"))
                msg << QtDBus.QDBusVariant(int(target))
                self.mpris.bus.call(msg, QtDBus.QDBus.CallMode.Block, 400)
        except Exception:
            pass

    def _find_lyric(self, title, artist):
        if not title:
            return None
        names = []
        if artist:
            names.append("%s - %s.lrc" % (artist, title))
        names.append("%s.lrc" % title)
        for d in self.LYRIC_DIRS:
            for n in names:
                p = os.path.join(d, n)
                if os.path.exists(p):
                    return p
        return None

    def _load_lyric(self, title, artist):
        key = (title, artist)
        if key == self._lyric_key:
            return
        self._lyric_key = key
        p = self._find_lyric(title, artist)
        self._lrc = []
        if p:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    self._lrc = parse_lrc(f.read())
            except Exception:
                self._lrc = []
        if not self._lrc:
            self.lyric.setText("暂无本地歌词（把 歌手 - 歌名.lrc 放到 ~/音乐/lyrics）")

    def _current_lyric(self):
        if not self._lrc:
            return ""
        cur = ""
        for sec, word in self._lrc:
            if sec <= self._pos + 0.3:
                cur = word
            else:
                break
        return cur

    def sync(self, force=False):
        now = time.time()
        if not force and now - self._last < 2:
            return
        self._last = now
        # 用户固定了播放器且仍在线：优先用它
        fixed = (self.store.settings.get("media_player") or "")
        if fixed and fixed in self.mpris.players():
            self.mpris.service = fixed
        st = self.mpris.state()
        self._last_state = st or {}
        if not st:
            self.title.setText("未检测到播放器")
            self.artist.setText("启动网易云/VLC/mpv 等播放器后自动连接")
            self.time.setText("0:00 / 0:00")
            self.btn_play.setText("▶")
            self.slider.setEnabled(False)
            self.cover.setVisible(False)
            for b in (self.btn_prev, self.btn_play, self.btn_next,
                      self.btn_mode, self.btn_rnd):
                b.setEnabled(False)
            return
        for b in (self.btn_prev, self.btn_play, self.btn_next,
                  self.btn_mode, self.btn_rnd):
            b.setEnabled(True)
        self.btn_mode.setText("↻")
        self.btn_rnd.setChecked(False)
        self.btn_player.setText("播放器")
        self.slider.setEnabled(True)
        self.title.setText(st["title"] or "未知曲目")
        self.artist.setText(st["artist"] or "")
        self._pos = st["position"]
        self._length = st["length"] or 0
        self.btn_play.setText("⏸" if st["status"] == "Playing" else "▶")
        self.time.setText("%s / %s" % (T.fmt_duration(self._pos), T.fmt_duration(self._length)))
        if self._length > 0:
            self.slider.setValue(int(min(1.0, self._pos / self._length) * 1000))
        self._apply_cover(st.get("art") or "")
        for name, label in self.MODE_SEQ:       # MODE_SEQ 是 (模式名, 图标)，别写反
            if name == st.get("loop", "None"):
                self.btn_mode.setText(label)
                break
        self.btn_rnd.setChecked(bool(st.get("shuffle")))
        self.btn_player.setText(self.player_label(st.get("service") or ""))
        self._load_lyric(st["title"], st["artist"])
        line = self._current_lyric()
        if line:
            self.lyric.setText(line)

    def on_show(self):
        self.sync(force=True)

    def tick(self, now):
        if self.isVisible():
            self.sync()
