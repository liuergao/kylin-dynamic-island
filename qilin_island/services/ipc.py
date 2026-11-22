# -*- coding: utf-8 -*-
"""能力层 · M15 单实例与唤醒

岛体常驻后台，用户再次点开图标时不该起第二个进程，而该把面板唤回前台。
两条通道叠着用：本地 socket 负责传命令，文件锁兜住 socket 起不来的环境。

通道名沿用 APP_ID（fuyu-instance），老用户正在跑的旧进程仍能被新版本唤回。
收到命令之后的处理留在应用层（那里才知道“显示/展开/退出”是什么意思）。
"""
from PyQt5.QtCore import QLockFile
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

from ..meta import APP_ID

IPC_NAME = APP_ID + "-instance"
LOCK_PATH = "/tmp/%s-lite.lock" % APP_ID


def send_to_instance(command):
    """已有实例在跑 → 把命令（b"show" / b"quit"）丢给它并返回 True"""
    sock = QLocalSocket()
    sock.connectToServer(IPC_NAME)
    if not sock.waitForConnected(300):
        return False
    sock.write(command)
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def acquire_lock():
    """拿到独占锁返回锁对象；拿不到返回 None（已有实例在跑）"""
    lock = QLockFile(LOCK_PATH)
    return lock if lock.tryLock(100) else None


def listen(parent):
    """起本地 socket 服务；newConnection 由调用方连接"""
    QLocalServer.removeServer(IPC_NAME)
    server = QLocalServer(parent)
    server.listen(IPC_NAME)
    return server


def close_server(server):
    """退出前收掉通道，否则下一次启动会被残留的服务名挡住"""
    server.close()
    QLocalServer.removeServer(IPC_NAME)
