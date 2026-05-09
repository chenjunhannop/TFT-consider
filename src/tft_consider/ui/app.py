"""TFT-Consider 桌面应用生命周期管理。

TftConsiderApp 负责初始化 QApplication、检测游戏客户端、
创建主窗口并进入事件循环。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Any

from PySide6.QtWidgets import QApplication, QMessageBox

from tft_consider import __version__
from tft_consider.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class TftConsiderApp:
    """TFT-Consider 应用生命周期管理。

    封装 QApplication 的创建、主窗口初始化和事件循环入口。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化应用实例。

        Args:
            config: 应用配置字典。
        """
        self._config = config
        self._app: QApplication | None = None
        self._window: MainWindow | None = None

    def run(self) -> None:
        """启动应用：初始化 QApplication、检测环境、创建并显示主窗口、进入事件循环。"""
        # QApplication 是单例：如果测试或嵌入场景已存在实例则复用
        existing = QApplication.instance()
        if isinstance(existing, QApplication):
            app = existing
        else:
            app = QApplication(sys.argv)
        app.setApplicationName("TFT-Consider")
        app.setApplicationVersion(__version__)
        app.setOrganizationName("tft-consider")
        app.setQuitOnLastWindowClosed(False)
        self._app = app

        logger.info("QApplication 初始化完成 (version=%s)", __version__)

        # 检测英雄联盟客户端
        self._check_lol_client()

        # 创建并显示主窗口
        self._window = MainWindow(self._config)
        self._window.show()

        logger.info("TFT-Consider 桌面应用已启动")
        app.exec()

    def shutdown(self) -> None:
        """清理资源：关闭主窗口、退出事件循环。"""
        logger.info("TFT-Consider 应用关闭...")
        if self._window is not None:
            self._window.close()
            self._window = None
        if self._app is not None:
            self._app.quit()
            self._app = None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _check_lol_client(self) -> None:
        """检测英雄联盟客户端是否运行。

        仅在 Windows 上通过 tasklist 进程名检测。
        macOS/Linux 上跳过此检测。
        未检测到客户端时显示友好提示但仍允许启动。
        """
        if os.name != "nt":
            logger.debug("非 Windows 平台，跳过英雄联盟客户端检测")
            return

        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq League of Legends.exe"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "League of Legends.exe" in result.stdout:
                logger.info("检测到英雄联盟客户端正在运行")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("检测英雄联盟客户端失败: %s", exc)

        # 未检测到客户端，显示友好提示
        QMessageBox.information(
            None,
            "提示",
            "未检测到英雄联盟客户端正在运行。\n\n"
            "TFT-Consider 依赖游戏截图进行分析，建议先启动游戏。\n"
            "你仍然可以启动应用，但分析功能可能无法正常工作。",
        )


# ---------------------------------------------------------------------------
# 模块级便捷函数
# ---------------------------------------------------------------------------


def run_app(config: dict[str, Any]) -> None:
    """便捷函数：创建 TftConsiderApp 实例并运行。

    Args:
        config: 应用配置字典。
    """
    app = TftConsiderApp(config)
    try:
        app.run()
    finally:
        app.shutdown()
