"""TFT-Consider 桌面应用主窗口。

MainWindow 提供无边框、置顶、半透明的覆盖式分析面板，
包含状态摘要、阵容可视化和行动建议三栏布局。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, override

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMenu,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 主题样式表
# ---------------------------------------------------------------------------

_DARK_THEME = """
QMainWindow {
    background-color: #1a1a2e;
}
QMainWindow > QWidget#centralWidget {
    background-color: #1a1a2e;
    border-radius: 12px;
}
QLabel {
    color: #e0e0e0;
    font-size: 13px;
}
QStatusBar {
    background-color: #16213e;
    color: #a0a0b0;
    font-size: 11px;
    border-top: 1px solid #0f3460;
}
QStatusBar QLabel {
    color: #a0a0b0;
    font-size: 11px;
    padding: 2px 8px;
}
QSplitter::handle {
    background-color: #0f3460;
    width: 2px;
}
QMenu {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
}
QMenu::item:selected {
    background-color: #0f3460;
}
"""

_LIGHT_THEME = """
QMainWindow {
    background-color: #f0f0f0;
}
QMainWindow > QWidget#centralWidget {
    background-color: #f0f0f0;
    border-radius: 12px;
}
QLabel {
    color: #333333;
    font-size: 13px;
}
QStatusBar {
    background-color: #e0e0e0;
    color: #666666;
    font-size: 11px;
    border-top: 1px solid #cccccc;
}
QStatusBar QLabel {
    color: #666666;
    font-size: 11px;
    padding: 2px 8px;
}
QSplitter::handle {
    background-color: #cccccc;
    width: 2px;
}
QMenu {
    background-color: #e0e0e0;
    color: #333333;
    border: 1px solid #cccccc;
}
QMenu::item:selected {
    background-color: #cccccc;
}
"""


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """TFT-Consider 桌面应用主窗口。

    提供三栏分析面板：状态摘要 | 阵容可视化 | 行动建议。
    窗口无边框、置顶显示、半透明，不抢夺游戏焦点。
    通过系统托盘控制显示/隐藏和退出。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化主窗口。

        Args:
            config: 应用配置字典，包含 ui.theme、ui.opacity、screenshot.temp_dir 等项。
        """
        super().__init__()
        self._config = config

        self._setup_window()
        self._setup_ui()
        self._setup_tray()
        self._apply_theme()

        logger.info("MainWindow 初始化完成")

    # ------------------------------------------------------------------
    # 窗口属性
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        """设置窗口标志、透明度和初始位置。"""
        self.setWindowTitle("TFT-Consider")

        # 无边框 + 置顶 + Tool 角色（macOS 上不显示额外 Dock 图标）
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 半透明
        ui_cfg = self._config.get("ui", {})
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}
        opacity = float(ui_cfg.get("opacity", 0.85))
        self.setWindowOpacity(opacity)

        # 初始位置: 屏幕右侧，宽度约 380px，高度约 80% 屏幕高度
        screen = QApplication.primaryScreen()
        if screen is not None:
            screen_geo = screen.availableGeometry()
            width = 380
            height = int(screen_geo.height() * 0.8)
            x = screen_geo.right() - width - 10
            y = (screen_geo.height() - height) // 2
            self.setGeometry(x, y, width, height)
            self.setMinimumSize(280, 400)
        else:
            self.resize(380, 600)

    # ------------------------------------------------------------------
    # UI 布局
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """构建三栏布局和底部状态栏。"""
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 4)
        main_layout.setSpacing(4)

        # --- QSplitter 三栏布局 ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 左侧: 状态摘要面板
        self._status_panel = self._make_panel("状态摘要")
        self._status_label = QLabel("等待对局开始...")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._status_label.setTextFormat(Qt.TextFormat.RichText)
        status_layout = self._status_panel.layout()
        assert status_layout is not None
        status_layout.addWidget(self._status_label)
        splitter.addWidget(self._status_panel)

        # 中间: 阵容可视化区域 (placeholder)
        self._comp_panel = self._make_panel("阵容可视化")
        comp_placeholder = QLabel("阵容可视化\n(后续实现)")
        comp_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        comp_placeholder.setStyleSheet("color: #666666; font-size: 12px;")
        comp_layout = self._comp_panel.layout()
        assert comp_layout is not None
        comp_layout.addWidget(comp_placeholder)
        splitter.addWidget(self._comp_panel)

        # 右侧: 行动建议面板
        self._advice_panel = self._make_panel("行动建议")
        self._advice_label = QLabel("暂无建议")
        self._advice_label.setWordWrap(True)
        self._advice_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._advice_label.setTextFormat(Qt.TextFormat.RichText)
        advice_layout = self._advice_panel.layout()
        assert advice_layout is not None
        advice_layout.addWidget(self._advice_label)
        splitter.addWidget(self._advice_panel)

        # 初始分割比例 (左 120 : 中 140 : 右 120)
        splitter.setSizes([120, 140, 120])
        main_layout.addWidget(splitter, stretch=1)

        # --- 底部状态栏 ---
        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(True)

        self._phase_label = QLabel("阶段: --")
        self._screenshot_label = QLabel("截图: --")
        self._llm_label = QLabel("LLM: 0")

        self._status_bar.addWidget(self._phase_label)
        self._status_bar.addWidget(self._screenshot_label)
        self._status_bar.addPermanentWidget(self._llm_label)

        self.setStatusBar(self._status_bar)

    @staticmethod
    def _make_panel(title: str) -> QWidget:
        """创建一个带标题的竖向面板容器。

        Args:
            title: 面板标题文本。

        Returns:
            包含标题 QLabel 和 QVBoxLayout 的 QWidget。
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; padding-bottom: 2px;")
        layout.addWidget(title_label)

        return panel

    # ------------------------------------------------------------------
    # 系统托盘
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        """初始化系统托盘图标和菜单。"""
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setIcon(self._create_tray_icon())
        self._tray_icon.setToolTip("TFT-Consider")

        tray_menu = QMenu()

        show_action = QAction("显示/隐藏", self)
        show_action.triggered.connect(self._toggle_visible)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.show()

    @staticmethod
    def _create_tray_icon() -> QIcon:
        """使用 QPainter 绘制托盘图标（红色圆形底 + 白色 \"TFT\" 文字）。

        Returns:
            生成的 QIcon。
        """
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 红色圆形背景
        painter.setBrush(QColor("#e94560"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, size - 8, size - 8)

        # 白色文字
        painter.setPen(QColor("#ffffff"))
        font = QFont("Arial", 16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "TFT")

        painter.end()
        return QIcon(pixmap)

    # ------------------------------------------------------------------
    # 主题
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        """从配置读取 ui.theme 并应用对应样式表。"""
        ui_cfg = self._config.get("ui", {})
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}
        theme = str(ui_cfg.get("theme", "dark")).lower()
        stylesheet = _DARK_THEME if theme == "dark" else _LIGHT_THEME
        self.setStyleSheet(stylesheet)
        logger.debug("应用主题: %s", theme)

    # ------------------------------------------------------------------
    # 公开 API —— 供其他模块调用
    # ------------------------------------------------------------------

    def update_status(self, game_state: dict[str, Any]) -> None:
        """更新左侧状态摘要面板。

        Args:
            game_state: 游戏状态字典，预期包含 level、gold、health、streak、round 等键。
        """
        if not isinstance(game_state, dict):
            return

        level = game_state.get("level", "--")
        gold = game_state.get("gold", "--")
        health = game_state.get("health", "--")
        streak = game_state.get("streak", "--")
        round_num = game_state.get("round", "--")

        # 连胜/连败显示
        streak_text = str(streak)
        if isinstance(streak, int) and streak > 0:
            streak_text = f"<span style='color:#4ecca3'>连胜 {streak}</span>"
        elif isinstance(streak, int) and streak < 0:
            streak_text = f"<span style='color:#e94560'>连败 {abs(streak)}</span>"

        text = (
            f"<b>等级:</b> {level}<br>"
            f"<b>经济:</b> {gold}<br>"
            f"<b>血量:</b> {health}<br>"
            f"<b>趋势:</b> {streak_text}<br>"
            f"<b>回合:</b> {round_num}"
        )
        self._status_label.setText(text)

    def update_advice(self, advice: str) -> None:
        """更新右侧行动建议面板。

        Args:
            advice: 建议文本（支持 HTML 富文本）。
        """
        self._advice_label.setText(advice)

    def update_phase(self, phase: str) -> None:
        """更新底部状态栏的对局阶段显示。

        Args:
            phase: 阶段标识，如 "1-1"、"3-2" 等。
        """
        self._phase_label.setText(f"阶段: {phase}")

    def set_screenshot_status(self, status: str) -> None:
        """更新底部状态栏的截图状态显示。

        Args:
            status: 截图状态文本，如 "已截图"、"失败" 等。
        """
        self._screenshot_label.setText(f"截图: {status}")

    def set_llm_calls(self, count: int) -> None:
        """更新底部状态栏的 LLM 调用次数显示。

        Args:
            count: LLM 调用次数。
        """
        self._llm_label.setText(f"LLM: {count}")

    # ------------------------------------------------------------------
    # 窗口事件
    # ------------------------------------------------------------------

    def _toggle_visible(self) -> None:
        """切换窗口显示/隐藏。"""
        if self.isVisible():
            self.hide()
        else:
            self.show()

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭窗口时清理资源：隐藏托盘图标、清理临时截图文件。

        Args:
            event: 关闭事件。
        """
        logger.info("MainWindow 关闭，开始清理...")

        # 隐藏托盘图标
        if hasattr(self, "_tray_icon"):
            self._tray_icon.hide()

        # 清理截图临时文件
        self._cleanup_temp_screenshots()

        event.accept()

    def _cleanup_temp_screenshots(self) -> None:
        """删除截图临时目录中的所有 PNG 文件。"""
        temp_dir = self._resolve_temp_dir()
        if not temp_dir.exists():
            logger.debug("截图临时目录不存在，跳过清理: %s", temp_dir)
            return

        count = 0
        for p in temp_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".png":
                try:
                    p.unlink()
                    count += 1
                except OSError as exc:
                    logger.warning("删除截图文件失败: %s, 原因: %s", p, exc)

        logger.info("已清理 %d 个截图临时文件 (目录: %s)", count, temp_dir)

    def _resolve_temp_dir(self) -> Path:
        """解析截图临时目录的实际路径。

        逻辑与 ScreenshotCapturer 目录解析保持一致：
        优先使用 config.screenshot.temp_dir，为空时自动解析系统临时/缓存目录。

        Returns:
            截图临时目录的 Path。
        """
        screenshot_cfg = self._config.get("screenshot", {})
        if not isinstance(screenshot_cfg, dict):
            screenshot_cfg = {}
        configured = str(screenshot_cfg.get("temp_dir", ""))

        if configured:
            return Path(configured)

        if os.name == "nt":
            default_temp = Path.home() / "AppData" / "Local" / "Temp"
            return Path(os.environ.get("TEMP", str(default_temp))) / "tft-consider"
        else:
            default_cache = Path.home() / ".cache"
            return (
                Path(os.environ.get("XDG_CACHE_HOME", str(default_cache)))
                / "tft-consider"
                / "screenshots"
            )
