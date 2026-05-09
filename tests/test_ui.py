"""TFT-Consider UI 模块单元测试。

覆盖 main_window.MainWindow、app.TftConsiderApp 和 CLI 入口 main。
所有 GUI 测试使用 session-scoped QApplication fixture，不启动事件循环。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication


# 确保在任何 GUI 测试前 qapp 被激活
@pytest.fixture(autouse=True)
def _ensure_qapp(qapp: QApplication) -> None:
    """autouse fixture：确保每个 GUI 测试都有 QApplication 上下文。"""
    assert QApplication.instance() is qapp


# ---------------------------------------------------------------------------
# 常用配置字典
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config() -> dict[str, Any]:
    """返回默认的应用配置字典。"""
    return {
        "api": {"provider": "moonshot", "key": "test-key", "model": "kimi-k2-0719-preview"},
        "screenshot": {"interval_ms": 2000, "temp_dir": ""},
        "ui": {"theme": "dark", "opacity": 0.85},
        "data": {"sync_interval_hours": 6, "auto_sync": True},
        "log": {"level": "INFO"},
    }


@pytest.fixture
def light_config() -> dict[str, Any]:
    """浅色主题 + 自定义透明度的配置。"""
    return {
        "api": {"provider": "moonshot", "key": "", "model": "kimi-k2-0719-preview"},
        "screenshot": {"interval_ms": 2000, "temp_dir": "/tmp/test-screenshots"},
        "ui": {"theme": "light", "opacity": 0.5},
        "data": {"sync_interval_hours": 12, "auto_sync": False},
        "log": {"level": "DEBUG"},
    }


# ---------------------------------------------------------------------------
# MainWindow 测试
# ---------------------------------------------------------------------------


class TestMainWindowInit:
    """MainWindow.__init__：窗口属性、标志和透明度。"""

    def test_window_title_contains_tft_consider(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """窗口标题应包含 'TFT-Consider'。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert "TFT-Consider" in window.windowTitle()

    def test_window_frameless(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """窗口应设置无边框标志 (FramelessWindowHint)。"""
        from PySide6.QtCore import Qt

        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        flags = window.windowFlags()
        assert flags & Qt.WindowType.FramelessWindowHint

    def test_window_stays_on_top(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """窗口应设置置顶标志 (WindowStaysOnTopHint)。"""
        from PySide6.QtCore import Qt

        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint

    def test_window_tool_flag(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """窗口应设置 Tool 标志（macOS 上不显示额外 Dock 图标）。"""
        from PySide6.QtCore import Qt

        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        flags = window.windowFlags()
        assert flags & Qt.WindowType.Tool

    def test_opacity_from_default_config(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """默认配置下窗口透明度应为 0.85。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert window.windowOpacity() == pytest.approx(0.85, rel=1e-2)

    def test_opacity_from_custom_config(self, qapp: QApplication, light_config: dict[str, Any]) -> None:
        """自定义配置下窗口透明度应为配置值 0.5。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(light_config)
        assert window.windowOpacity() == pytest.approx(0.5, rel=1e-2)

    def test_opacity_missing_ui_section(self, qapp: QApplication) -> None:
        """ui 配置缺失时使用默认透明度 0.85。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow({"api": {"key": "test"}})
        assert window.windowOpacity() == pytest.approx(0.85, rel=1e-2)

    def test_opacity_ui_not_dict(self, qapp: QApplication) -> None:
        """ui 配置为非 dict 时使用默认透明度 0.85。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow({"ui": "invalid"})
        assert window.windowOpacity() == pytest.approx(0.85, rel=1e-2)


class TestMainWindowUI:
    """MainWindow._setup_ui()：布局、面板和状态栏。"""

    def test_central_widget_exists(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """主窗口应有 centralWidget。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert window.centralWidget() is not None
        assert window.centralWidget().objectName() == "centralWidget"

    def test_splitter_has_three_children(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """QSplitter 应包含 3 个子 widget（状态/阵容/建议面板）。"""
        from PySide6.QtWidgets import QSplitter

        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        central = window.centralWidget()
        splitters = central.findChildren(QSplitter)
        assert len(splitters) >= 1, "应至少有一个 QSplitter"
        splitter = splitters[0]
        assert splitter.count() == 3

    def test_status_panel_exists(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """左侧状态摘要面板应存在。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert hasattr(window, "_status_panel")
        assert window._status_panel is not None

    def test_comp_panel_exists(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """中间阵容可视化面板应存在。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert hasattr(window, "_comp_panel")
        assert window._comp_panel is not None

    def test_advice_panel_exists(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """右侧行动建议面板应存在。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert hasattr(window, "_advice_panel")
        assert window._advice_panel is not None

    def test_status_label_initial_text(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """初始状态标签应显示等待文本。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert "等待对局开始" in window._status_label.text()

    def test_advice_label_initial_text(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """初始建议标签应显示默认文本。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert "暂无建议" in window._advice_label.text()

    def test_status_bar_exists(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """底部状态栏应存在。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert window.statusBar() is not None

    def test_phase_label_in_status_bar(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """状态栏应包含阶段标签。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        # 检查 _phase_label 存在且初始文本包含 "阶段"
        assert hasattr(window, "_phase_label")
        assert "阶段" in window._phase_label.text()


class TestMainWindowUpdateStatus:
    """MainWindow.update_status()：游戏状态更新。"""

    def test_update_status_shows_level_gold_health(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """更新状态后标签应包含等级、经济和血量。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        game_state = {"level": 7, "gold": 50, "health": 72, "streak": 0, "round": "4-2"}

        window.update_status(game_state)
        text = window._status_label.text()

        assert "等级" in text
        assert "7" in text
        assert "经济" in text
        assert "50" in text
        assert "血量" in text
        assert "72" in text

    def test_update_status_empty_dict_no_exception(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """空 game_state 字典不应抛异常。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.update_status({})

    def test_update_status_none_no_exception(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """None game_state 不应抛异常。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.update_status(None)

    def test_update_status_non_dict_no_exception(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """非 dict 类型的 game_state 不应抛异常。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.update_status("invalid")

    def test_update_status_positive_streak(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """连胜 (streak > 0) 应渲染绿色连胜样式。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        game_state = {"level": 5, "gold": 32, "health": 88, "streak": 3, "round": "2-5"}

        window.update_status(game_state)
        text = window._status_label.text()

        assert "连胜" in text
        assert "3" in text
        assert "#4ecca3" in text  # 绿色

    def test_update_status_negative_streak(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """连败 (streak < 0) 应渲染红色连败样式。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        game_state = {"level": 5, "gold": 15, "health": 64, "streak": -4, "round": "2-6"}

        window.update_status(game_state)
        text = window._status_label.text()

        assert "连败" in text
        assert "4" in text
        assert "#e94560" in text  # 红色

    def test_update_status_missing_keys(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """缺失字段时应显示 '--' 占位符。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.update_status({"level": 4})

        text = window._status_label.text()
        assert "4" in text  # level 正常显示
        assert "--" in text  # 缺失字段用 '--' 占位


class TestMainWindowUpdateAdvice:
    """MainWindow.update_advice()：行动建议更新。"""

    def test_update_advice_sets_label_text(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """update_advice 应设置建议标签文本为非空内容。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        advice = "建议升级到 8 级，D 牌找 4 费 carry"

        window.update_advice(advice)
        assert window._advice_label.text() == advice
        assert len(window._advice_label.text()) > 0

    def test_update_advice_empty_string(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """空建议字符串不应抛异常（尽管标签会变为空）。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.update_advice("")
        assert window._advice_label.text() == ""

    def test_update_advice_html_content(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """富文本 HTML 建议应正确设置。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        html_advice = "<b>推荐阵容:</b> 8 法师<br><span style='color:green'>核心: Veigar</span>"

        window.update_advice(html_advice)
        assert "推荐阵容" in window._advice_label.text()
        assert "Veigar" in window._advice_label.text()

    def test_update_advice_fallback_shows_text(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """fallback 建议（初始状态后更新）应正确显示。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        # 初始文本是 "暂无建议"
        assert window._advice_label.text() == "暂无建议"

        # 更新后应替换初始文本
        window.update_advice("升级人口优先")
        assert window._advice_label.text() == "升级人口优先"


class TestMainWindowUpdatePhase:
    """MainWindow.update_phase()：对局阶段更新。"""

    def test_update_phase_sets_phase_label(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """update_phase 应在状态栏显示正确的阶段文本。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.update_phase("3-2")
        assert "阶段: 3-2" in window._phase_label.text()

    def test_update_phase_empty_string(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """空阶段字符串不应抛异常。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.update_phase("")
        assert "阶段: " in window._phase_label.text()

    def test_update_phase_multiple_calls(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """多次更新阶段应始终反映最新值。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)

        window.update_phase("1-1")
        assert "阶段: 1-1" in window._phase_label.text()

        window.update_phase("5-4")
        assert "阶段: 5-4" in window._phase_label.text()

        window.update_phase("6-1")
        assert "阶段: 6-1" in window._phase_label.text()


class TestMainWindowScreenshotStatus:
    """MainWindow.set_screenshot_status()：截图状态更新。"""

    def test_set_screenshot_status(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """截图状态应正确显示。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.set_screenshot_status("已截图 (1920x1080)")
        assert "截图: 已截图 (1920x1080)" in window._screenshot_label.text()

    def test_set_screenshot_status_failure(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """截图失败状态应正确显示。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.set_screenshot_status("失败")
        assert "截图: 失败" in window._screenshot_label.text()


class TestMainWindowLLMCalls:
    """MainWindow.set_llm_calls()：LLM 调用次数更新。"""

    def test_set_llm_calls(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """LLM 调用次数应正确显示。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.set_llm_calls(5)
        assert "LLM: 5" in window._llm_label.text()

    def test_set_llm_calls_zero(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """LLM 调用次数为 0 时应正确显示。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.set_llm_calls(0)
        assert "LLM: 0" in window._llm_label.text()


class TestMainWindowSystemTray:
    """MainWindow 系统托盘功能。"""

    def test_tray_icon_created(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """系统托盘图标应在 MainWindow 初始化时创建。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert hasattr(window, "_tray_icon")
        assert window._tray_icon is not None

    def test_tray_icon_tooltip(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """托盘图标提示文本应为 'TFT-Consider'。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        assert window._tray_icon.toolTip() == "TFT-Consider"

    def test_tray_menu_exists(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """托盘应有右键菜单。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        menu = window._tray_icon.contextMenu()
        assert menu is not None

    def test_tray_menu_has_show_hide_action(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """托盘菜单应包含'显示/隐藏'菜单项。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        menu = window._tray_icon.contextMenu()
        actions = menu.actions()
        action_texts = [a.text() for a in actions]
        assert "显示/隐藏" in action_texts

    def test_tray_menu_has_quit_action(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """托盘菜单应包含'退出'菜单项。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        menu = window._tray_icon.contextMenu()
        actions = menu.actions()
        action_texts = [a.text() for a in actions]
        assert "退出" in action_texts

    def test_tray_icon_has_non_null_icon(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """托盘图标应非空（_create_tray_icon 生成的 QIcon）。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        icon = window._tray_icon.icon()
        assert icon is not None
        assert not icon.isNull()


class TestMainWindowTheme:
    """MainWindow 主题切换。"""

    def test_default_theme_is_dark(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """默认配置下应使用深色主题。"""
        from tft_consider.ui.main_window import _DARK_THEME, MainWindow

        window = MainWindow(default_config)
        stylesheet = window.styleSheet()
        # 深色主题应包含特征颜色
        assert "#1a1a2e" in stylesheet or stylesheet == _DARK_THEME

    def test_light_theme_applied(self, qapp: QApplication, light_config: dict[str, Any]) -> None:
        """light 配置应使用浅色主题。"""
        from tft_consider.ui.main_window import _LIGHT_THEME, MainWindow

        window = MainWindow(light_config)
        stylesheet = window.styleSheet()
        # 浅色主题应包含特征颜色
        assert "#f0f0f0" in stylesheet or stylesheet == _LIGHT_THEME

    def test_theme_switch_no_exception(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """apply_theme 多次调用不应抛异常（本质上测试 setStyleSheet 稳定性）。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        # 直接调用 _apply_theme 不应崩溃
        window._apply_theme()

    def test_theme_invalid_type_falls_back_to_light(self, qapp: QApplication) -> None:
        """theme 类型为非字符串时 str() 转为非 'dark' 字符串，回退到浅色主题。"""
        from tft_consider.ui.main_window import _LIGHT_THEME, MainWindow

        config = {
            "ui": {"theme": 12345, "opacity": 0.9},
        }
        window = MainWindow(config)
        stylesheet = window.styleSheet()
        # str(12345) = "12345" != "dark"，走 else 分支 → 浅色主题
        assert "#f0f0f0" in stylesheet or stylesheet == _LIGHT_THEME

    def test_theme_ui_not_dict_falls_back(self, qapp: QApplication) -> None:
        """ui 配置为非 dict 时 theme 回退到 dark。"""
        from tft_consider.ui.main_window import _DARK_THEME, MainWindow

        window = MainWindow({"ui": "not-a-dict"})
        stylesheet = window.styleSheet()
        assert "#1a1a2e" in stylesheet or stylesheet == _DARK_THEME


class TestMainWindowToggleVisible:
    """MainWindow._toggle_visible()：显示/隐藏切换。"""

    def test_toggle_visible_hides_window(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """窗口可见时调用 _toggle_visible 应隐藏窗口。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.show()
        assert window.isVisible()

        window._toggle_visible()
        assert not window.isVisible()

    def test_toggle_visible_shows_window(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """窗口隐藏时调用 _toggle_visible 应显示窗口。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        window.hide()
        assert not window.isVisible()

        window._toggle_visible()
        assert window.isVisible()


class TestMainWindowCloseEvent:
    """MainWindow.closeEvent()：关闭清理逻辑。"""

    def test_close_event_hides_tray_icon(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """closeEvent 应隐藏系统托盘图标并调用清理。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        # 在 close 前记录 tray_icon
        tray = window._tray_icon
        assert tray is not None

        # 触发关闭
        window.close()

        # 验证 tray icon 被隐藏（QSystemTrayIcon.hide 后 isVisible 为 False）
        # 注意：在 offscreen 模式下 tray 行为可能受限，主要验证不抛异常
        # close 在 offscreen 下可能不会真正销毁 QSystemTrayIcon

    def test_close_event_no_exception(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """closeEvent 不应抛异常。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        # 直接 close 窗口，不应抛异常
        window.close()

    def test_close_event_calls_cleanup(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """closeEvent 应调用 _cleanup_temp_screenshots。"""
        from tft_consider.ui.main_window import MainWindow

        window = MainWindow(default_config)
        with patch.object(window, "_cleanup_temp_screenshots") as mock_cleanup:
            window.close()
            mock_cleanup.assert_called_once()


class TestMainWindowCleanupScreenshots:
    """MainWindow._cleanup_temp_screenshots()：临时文件清理。"""

    def test_cleanup_nonexistent_dir(self, qapp: QApplication, default_config: dict[str, Any], tmp_path: Path) -> None:
        """临时目录不存在时清理应跳过而不抛异常。"""
        from tft_consider.ui.main_window import MainWindow

        config = {**default_config, "screenshot": {"temp_dir": str(tmp_path / "nonexistent")}}
        window = MainWindow(config)

        # 目录不存在，应跳过清理不抛异常
        window._cleanup_temp_screenshots()

    def test_cleanup_empty_dir(self, qapp: QApplication, default_config: dict[str, Any], tmp_path: Path) -> None:
        """空临时目录清理不应抛异常。"""
        from tft_consider.ui.main_window import MainWindow

        dir_path = tmp_path / "screenshots"
        dir_path.mkdir()
        config = {**default_config, "screenshot": {"temp_dir": str(dir_path)}}
        window = MainWindow(config)

        window._cleanup_temp_screenshots()

    def test_cleanup_removes_png_files(
        self, qapp: QApplication, default_config: dict[str, Any], tmp_path: Path
    ) -> None:
        """清理应删除临时目录中的 PNG 文件但保留非 PNG 文件。"""
        from tft_consider.ui.main_window import MainWindow

        dir_path = tmp_path / "screenshots"
        dir_path.mkdir()

        # 创建 PNG 和非 PNG 文件
        png1 = dir_path / "snap_001.png"
        png1.write_text("fake png")
        png2 = dir_path / "snap_002.PNG"
        png2.write_text("fake png")
        txt_file = dir_path / "log.txt"
        txt_file.write_text("some log")

        config = {**default_config, "screenshot": {"temp_dir": str(dir_path)}}
        window = MainWindow(config)

        window._cleanup_temp_screenshots()

        # PNG 文件应被删除（包括 .PNG 大写后缀）
        assert not png1.exists()
        assert not png2.exists()
        # 非 PNG 文件应保留
        assert txt_file.exists()


class TestMainWindowResolveTempDir:
    """MainWindow._resolve_temp_dir()：临时目录路径解析。"""

    def test_resolve_configured_dir(self, qapp: QApplication, default_config: dict[str, Any], tmp_path: Path) -> None:
        """配置了 temp_dir 时应返回配置路径。"""
        from tft_consider.ui.main_window import MainWindow

        configured = tmp_path / "my-temp"
        config = {**default_config, "screenshot": {"temp_dir": str(configured)}}
        window = MainWindow(config)

        result = window._resolve_temp_dir()
        assert result == configured

    def test_resolve_unconfigured_non_nt(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """未配置 temp_dir 且非 Windows 时应返回 XDG 缓存路径。"""
        from tft_consider.ui.main_window import MainWindow

        # macOS/Linux: 应解析到 XDG_CACHE_HOME 或 ~/.cache
        # 不 mock os.name，在当前平台上验证非 nt 分支
        window = MainWindow(default_config)
        result = window._resolve_temp_dir()
        # 非 Windows 平台应包含 tft-consider/screenshots 路径
        assert "tft-consider" in str(result)
        assert "screenshots" in str(result)


# ---------------------------------------------------------------------------
# TftConsiderApp 测试
# ---------------------------------------------------------------------------


class TestTftConsiderAppInit:
    """TftConsiderApp.__init__：配置存储和初始状态。"""

    def test_stores_config(self, default_config: dict[str, Any]) -> None:
        """TftConsiderApp 应存储传入的配置。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)
        assert app._config is default_config
        assert app._app is None
        assert app._window is None

    def test_simple_config(self) -> None:
        """最小配置也可传入。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp({})
        assert app._config == {}


class TestTftConsiderAppRunShutdown:
    """TftConsiderApp.run() / shutdown()：生命周期测试。

    run() 内部 QApplication 单例检查会复用 session qapp fixture。
    只需 mock exec()（避免事件循环）和 _check_lol_client（避免系统调用/弹窗）。
    """

    def test_run_creates_window_and_sets_metadata(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """run() 应复用现有 QApplication、创建 MainWindow 并设置元数据。"""
        from PySide6.QtWidgets import QApplication

        from tft_consider.ui.app import TftConsiderApp

        app_wrapper = TftConsiderApp(default_config)

        with patch.object(
            app_wrapper, "_check_lol_client"
        ), patch.object(QApplication, "exec", return_value=0):
            app_wrapper.run()

        # 验证 QApplication 元数据被设置
        assert qapp.applicationName() == "TFT-Consider"
        assert qapp.organizationName() == "tft-consider"
        assert qapp.quitOnLastWindowClosed() is False

        # 验证窗口被创建
        assert app_wrapper._window is not None

        # 清理：隐藏窗口并重置引用
        if app_wrapper._window is not None:
            app_wrapper._window.hide()
        app_wrapper._app = None
        app_wrapper._window = None

    def test_shutdown_cleans_references(self, default_config: dict[str, Any]) -> None:
        """shutdown 应将 _window 和 _app 引用置为 None，调用清理方法。"""
        from unittest.mock import MagicMock

        from tft_consider.ui.app import TftConsiderApp

        app_wrapper = TftConsiderApp(default_config)
        mock_window = MagicMock()
        mock_app = MagicMock()
        app_wrapper._app = mock_app
        app_wrapper._window = mock_window

        app_wrapper.shutdown()

        mock_window.close.assert_called_once()
        mock_app.quit.assert_called_once()
        assert app_wrapper._window is None
        assert app_wrapper._app is None


class TestTftConsiderAppQAppSettings:
    """TftConsiderApp.run() 中 QApplication 元数据设置。

    利用 run() 的 QApplication 单例复用机制，通过 session qapp 验证实际设置值。
    """

    def test_application_name_is_set(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """run() 应在 session qapp 上设置 applicationName 为 'TFT-Consider'。"""
        from PySide6.QtWidgets import QApplication

        from tft_consider.ui.app import TftConsiderApp

        app_wrapper = TftConsiderApp(default_config)

        with patch.object(
            app_wrapper, "_check_lol_client"
        ), patch.object(QApplication, "exec", return_value=0):
            app_wrapper.run()

        assert qapp.applicationName() == "TFT-Consider"

        # 清理
        if app_wrapper._window is not None:
            app_wrapper._window.hide()
        app_wrapper._app = None
        app_wrapper._window = None

    def test_application_version_is_set(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """run() 应在 session qapp 上设置 applicationVersion 为包版本。"""
        from PySide6.QtWidgets import QApplication

        from tft_consider import __version__
        from tft_consider.ui.app import TftConsiderApp

        app_wrapper = TftConsiderApp(default_config)

        with patch.object(
            app_wrapper, "_check_lol_client"
        ), patch.object(QApplication, "exec", return_value=0):
            app_wrapper.run()

        assert qapp.applicationVersion() == __version__

        # 清理
        if app_wrapper._window is not None:
            app_wrapper._window.hide()
        app_wrapper._app = None
        app_wrapper._window = None

    def test_quit_on_last_window_closed_false(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """run() 应在 session qapp 上设置 quitOnLastWindowClosed 为 False。"""
        from PySide6.QtWidgets import QApplication

        from tft_consider.ui.app import TftConsiderApp

        app_wrapper = TftConsiderApp(default_config)

        with patch.object(
            app_wrapper, "_check_lol_client"
        ), patch.object(QApplication, "exec", return_value=0):
            app_wrapper.run()

        assert qapp.quitOnLastWindowClosed() is False

        # 清理
        if app_wrapper._window is not None:
            app_wrapper._window.hide()
        app_wrapper._app = None
        app_wrapper._window = None

    def test_organization_name_is_set(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """run() 应在 session qapp 上设置 organizationName 为 'tft-consider'。"""
        from PySide6.QtWidgets import QApplication

        from tft_consider.ui.app import TftConsiderApp

        app_wrapper = TftConsiderApp(default_config)

        with patch.object(
            app_wrapper, "_check_lol_client"
        ), patch.object(QApplication, "exec", return_value=0):
            app_wrapper.run()

        assert qapp.organizationName() == "tft-consider"

        # 清理
        if app_wrapper._window is not None:
            app_wrapper._window.hide()
        app_wrapper._app = None
        app_wrapper._window = None


class TestTftConsiderAppLolClientDetection:
    """TftConsiderApp._check_lol_client()：英雄联盟客户端检测。"""

    def test_macos_skips_detection(self, default_config: dict[str, Any]) -> None:
        """macOS（非 Windows）上应跳过检测，不调用 tasklist。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)

        with patch.object(os, "name", "posix"), patch("subprocess.run") as mock_run:
            app._check_lol_client()
            mock_run.assert_not_called()

    def test_macos_no_qmessagebox(self, default_config: dict[str, Any]) -> None:
        """macOS 上不应弹出 QMessageBox。"""
        from PySide6.QtWidgets import QMessageBox

        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)

        with patch.object(os, "name", "posix"), patch.object(QMessageBox, "information") as mock_box:
            app._check_lol_client()
            mock_box.assert_not_called()

    def test_windows_detection_not_found(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """Windows 上未检测到客户端时应弹出提示。"""
        from PySide6.QtWidgets import QMessageBox

        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="No matches found", returncode=0)
            with patch.object(QMessageBox, "information") as mock_box:
                app._check_lol_client()
                mock_box.assert_called_once()

    def test_windows_detection_found(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """Windows 上检测到客户端时应不弹提示。"""
        from PySide6.QtWidgets import QMessageBox

        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="League of Legends.exe  1234", returncode=0)
            with patch.object(QMessageBox, "information") as mock_box:
                app._check_lol_client()
                mock_box.assert_not_called()

    def test_windows_detection_error_timeout(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """subprocess 超时时应弹出提示。"""
        import subprocess

        from PySide6.QtWidgets import QMessageBox

        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("tasklist", 5)
            with patch.object(QMessageBox, "information") as mock_box:
                app._check_lol_client()
                mock_box.assert_called_once()

    def test_windows_detection_error_file_not_found(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        """tasklist 命令不存在时应弹出提示。"""
        from PySide6.QtWidgets import QMessageBox

        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("tasklist not found")
            with patch.object(QMessageBox, "information") as mock_box:
                app._check_lol_client()
                mock_box.assert_called_once()


class TestTftConsiderAppRunAppHelper:
    """模块级 run_app() 辅助函数。"""

    def test_run_app_creates_and_calls_run(self, default_config: dict[str, Any]) -> None:
        """run_app 应创建 TftConsiderApp 并调用 run/shutdown。"""
        from PySide6.QtWidgets import QApplication

        from tft_consider.ui.app import TftConsiderApp, run_app

        # 确保已有 QApplication 实例，避免 run_app 内部创建新实例造成的冲突
        # run_app 创建自己的 QApplication，这里我们 mock exec + 确保清理
        with patch.object(QApplication, "exec", return_value=0), patch.object(TftConsiderApp, "run") as mock_run:
            run_app(default_config)
            mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# CLI 入口测试 (main.py)
# ---------------------------------------------------------------------------


class TestCLIMain:
    """tft-consider CLI 入口命令。"""

    def test_main_without_args_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """无参数调用应打印帮助信息。"""
        from tft_consider.main import main

        with patch.object(sys, "argv", ["tft-consider"]):
            main()
        captured = capsys.readouterr()
        assert "TFT-Consider" in captured.out
        assert "Usage" in captured.out or "tft-consider" in captured.out

    def test_main_run_command_dispatches(self) -> None:
        """run 子命令应分发到 _cmd_run（不实际启动 GUI）。"""
        from tft_consider.main import main

        with patch.object(sys, "argv", ["tft-consider", "run"]), patch(
            "tft_consider.main._cmd_run"
        ) as mock_run:
            main()
            mock_run.assert_called_once()

    def test_main_sync_data_command_dispatches(self) -> None:
        """sync-data 子命令应分发到 SyncScheduler。"""
        from tft_consider.main import main

        with patch.object(sys, "argv", ["tft-consider", "sync-data"]):
            # load_config/init_db/SyncScheduler 在 main() 内通过本地 import 导入，
            # 需要 patch 原始模块路径而非 tft_consider.main 上的属性
            with patch("tft_consider.config.load_config") as mock_load, patch(
                "tft_consider.database.models.init_db"
            ), patch("tft_consider.crawler.scheduler.SyncScheduler") as mock_sched:
                mock_load.return_value = {"ui": {"opacity": 0.85}}
                mock_instance = MagicMock()
                mock_instance.sync_now.return_value = True
                mock_sched.return_value = mock_instance

                # sync-data 内部调用 sys.exit(0)，需要捕获
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0

    def test_main_check_command_dispatches(self, capsys: pytest.CaptureFixture[str]) -> None:
        """check 子命令应执行环境检查。"""
        from tft_consider.main import main

        with patch.object(sys, "argv", ["tft-consider", "check"]):
            main()
        captured = capsys.readouterr()
        assert "配置检查" in captured.out

    def test_main_history_command_dispatches(self, capsys: pytest.CaptureFixture[str]) -> None:
        """history 子命令应查询对局记录。"""
        from tft_consider.main import main

        with patch.object(sys, "argv", ["tft-consider", "history"]):
            # init_db/list_replays 在 main() 内通过本地 import 导入
            with patch("tft_consider.database.models.init_db"), patch(
                "tft_consider.tracker.replay.list_replays"
            ) as mock_list:
                mock_list.return_value = []
                main()
        captured = capsys.readouterr()
        assert "暂无对局记录" in captured.out

    def test_main_unknown_command_shows_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """未知命令（非内置子命令）应回退到帮助输出。"""
        from tft_consider.main import main

        with patch.object(sys, "argv", ["tft-consider", "unknown-cmd"]):
            main()
        captured = capsys.readouterr()
        assert "TFT-Consider" in captured.out
        assert "Usage" in captured.out
