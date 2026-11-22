# -*- coding: utf-8 -*-
"""支撑层 · .lrc 歌词解析（M12 音乐页用）"""


def parse_lrc(text):
    """[mm:ss.xx]词 → [(秒, 词)]，按时间升序"""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        parts = line.split("]")
        stamp = parts[0].strip("[]")
        word = "]".join(parts[1:]).strip()
        if not word:
            continue
        try:
            m, s = stamp.split(":")
            out.append((int(m) * 60 + float(s), word))
        except ValueError:
            continue
    out.sort(key=lambda x: x[0])
    return out
