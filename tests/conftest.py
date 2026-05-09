"""pytest 共享 fixtures。

提供 session 级 QApplication 单例，所有 GUI 测试共享。
"""

from __future__ import annotations

import sys
from collections.abc import Generator

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """创建 session 级 QApplication 实例（offscreen 模式）。

    PySide6 要求在操作任何 QWidget 前存在 QApplication 实例。
    此 fixture 不调用 app.exec()，仅提供 QApplication 上下文。
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([sys.argv[0], "-platform", "offscreen"])
    assert isinstance(app, QApplication)
    yield app
