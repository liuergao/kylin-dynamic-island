# -*- coding: utf-8 -*-
"""支撑层 · 剪贴板历史存储（M9 的数据侧）

sqlite 单表，固定项不参与 30 条淘汰。
"""
import sqlite3
import time


class ClipboardStore:
    def __init__(self, path, max_items=30):
        self.path = path
        self.max_items = max_items
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS clip("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,"
            "ts REAL NOT NULL, pinned INTEGER DEFAULT 0, hash TEXT)")
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_clip_ts ON clip(ts)")
        self.con.commit()

    def add(self, text):
        # X 剪贴板往返常引入 \r / 首尾空白差异，先归一化再去重，
        # 否则“点击历史条目复制”会被监听器当成新内容再次入库（B 机实测同一条连出 3 条）
        text = normalize(text)
        if not text or len(text) > 4000:
            return False
        h = str(hash(text))
        row = self.con.execute(
            "SELECT id FROM clip WHERE hash=? ORDER BY id DESC LIMIT 1", (h,)).fetchone()
        if row:
            self.con.execute("UPDATE clip SET ts=? WHERE id=?", (time.time(), row[0]))
            self.con.commit()
            return False
        self.con.execute("INSERT INTO clip(text, ts, pinned, hash) VALUES(?,?,0,?)",
                         (text, time.time(), h))
        self.con.execute(
            "DELETE FROM clip WHERE pinned=0 AND id NOT IN "
            "(SELECT id FROM clip WHERE pinned=0 ORDER BY ts DESC LIMIT ?)",
            (self.max_items,))
        self.con.commit()
        return True

    def items(self, limit=60):
        return self.con.execute(
            "SELECT id, text, ts, pinned FROM clip ORDER BY pinned DESC, ts DESC LIMIT ?",
            (limit,)).fetchall()

    def pin(self, cid, pinned=None):
        row = self.con.execute("SELECT pinned FROM clip WHERE id=?", (cid,)).fetchone()
        if not row:
            return
        val = (0 if row[0] else 1) if pinned is None else int(pinned)
        self.con.execute("UPDATE clip SET pinned=? WHERE id=?", (val, cid))
        self.con.commit()

    def remove(self, cid):
        self.con.execute("DELETE FROM clip WHERE id=?", (cid,))
        self.con.commit()

    def clear(self, keep_pinned=True):
        if keep_pinned:
            self.con.execute("DELETE FROM clip WHERE pinned=0")
        else:
            self.con.execute("DELETE FROM clip")
        self.con.commit()


def normalize(text):
    """剪贴板文本归一化：同一份内容在 X 往返后不该被记两次"""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
