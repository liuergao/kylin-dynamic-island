# -*- coding: utf-8 -*-
"""功能页注册表（M6–M12）

PAGE_CLASSES 的顺序就是页签从左到右的顺序，也是设置里 pages[] 的下标顺序，
改动会让老用户记住的当前页错位——要加页面只能往末尾追加。"""
from .base import Page
from .calendar import CalendarPage
from .clipboard import ClipPage
from .focus import FocusPage
from .media import MediaPage
from .shelf import ShelfPage
from .system import SysPage
from .todo import TodoPage
from .water import WaterPage

PAGE_CLASSES = [TodoPage, FocusPage, WaterPage, ShelfPage, ClipPage, MediaPage,
                CalendarPage, SysPage]

__all__ = ["Page", "PAGE_CLASSES"]
