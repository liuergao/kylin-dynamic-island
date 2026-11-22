# -*- coding: utf-8 -*-
"""能力层 · M15 开机自启

麒麟/UKUI 认 XDG autostart 目录，写一个 .desktop 就够，不需要 root、
不碰 systemd。条目名沿用 APP_ID（fuyu.desktop），老用户的自启不会失效。
"""
import os

from ..meta import APP_ID, APP_NAME

DESKTOP_PATH = os.path.expanduser("~/.config/autostart/%s.desktop" % APP_ID)


def set_enabled(on):
    if on:
        os.makedirs(os.path.dirname(DESKTOP_PATH), exist_ok=True)
        with open(DESKTOP_PATH, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nType=Application\nName=%s\n"
                    "Comment=桌面信息岛\nExec=%s\nIcon=%s\n"
                    "X-GNOME-Autostart-enabled=true\nTerminal=false\n"
                    % (APP_NAME, APP_ID, APP_ID))
    elif os.path.exists(DESKTOP_PATH):
        os.remove(DESKTOP_PATH)
