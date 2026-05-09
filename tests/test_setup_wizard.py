"""TFT-Consider SetupWizard 模块单元测试。

覆盖 setup_wizard.py 的 WelcomePage, ApiKeyPage, DetectPage, FinishPage, SetupWizard,
以及 app.py 的 _maybe_run_setup_wizard 和 main.py 的 _cmd_setup。
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QWizard

# ---------------------------------------------------------------------------
# QApplication fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """创建 session 级 QApplication 实例，整个测试套件共享。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([sys.argv[0], "-platform", "offscreen"])
    assert isinstance(app, QApplication)
    yield app


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp: QApplication) -> None:
    """autouse fixture：确保每个 GUI 测试都有 QApplication 上下文。"""
    assert QApplication.instance() is qapp


# ---------------------------------------------------------------------------
# 常用配置字典
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config() -> dict[str, Any]:
    """返回默认的应用配置字典（包含已配置的 API Key）。"""
    return {
        "api": {"provider": "moonshot", "key": "test-key", "model": "kimi-k2-0719-preview"},
        "screenshot": {"interval_ms": 2000, "temp_dir": ""},
        "ui": {"theme": "dark", "opacity": 0.85},
        "data": {"sync_interval_hours": 6, "auto_sync": True},
        "log": {"level": "INFO"},
    }


@pytest.fixture
def empty_key_config() -> dict[str, Any]:
    """API Key 为空的配置（模拟首次启动）。"""
    return {
        "api": {"provider": "moonshot", "key": "", "model": "kimi-k2-0719-preview"},
        "ui": {"theme": "dark", "opacity": 0.85},
    }


# ---------------------------------------------------------------------------
# WelcomePage 测试
# ---------------------------------------------------------------------------


class TestWelcomePage:
    """WelcomePage 初始化：标题、副标题和内容标签。"""

    def test_title(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import WelcomePage

        page = WelcomePage()
        assert page.title() == "欢迎使用 TFT-Consider"

    def test_subtitle(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import WelcomePage

        page = WelcomePage()
        assert "云顶之弈" in page.subTitle()
        assert "几分钟完成配置" in page.subTitle()

    def test_intro_label_contains_project_description(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QLabel

        from tft_consider.ui.setup_wizard import WelcomePage

        page = WelcomePage()
        labels: list[QLabel] = page.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        combined = " ".join(texts)
        assert "TFT-Consider" in combined
        assert "核心功能" in combined
        assert "AI 辅助工具" in combined

    def test_features_label_covers_all_capabilities(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QLabel

        from tft_consider.ui.setup_wizard import WelcomePage

        page = WelcomePage()
        labels = page.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        combined = " ".join(texts)
        assert "截图分析" in combined
        assert "阵容推荐" in combined
        assert "行动建议" in combined
        assert "对局追踪" in combined
        assert "下一步" in combined


# ---------------------------------------------------------------------------
# ApiKeyPage 测试
# ---------------------------------------------------------------------------


class TestApiKeyPageInit:
    """ApiKeyPage 初始化：控件、属性和字段注册。"""

    def test_title(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert page.title() == "配置 API Key"

    def test_subtitle(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert "Moonshot" in page.subTitle()
        assert "platform.moonshot.cn" in page.subTitle()

    def test_key_edit_password_mode(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QLineEdit

        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert page._key_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_key_edit_placeholder(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert "请输入你的 API Key" in page._key_edit.placeholderText()

    def test_key_edit_minimum_width(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert page._key_edit.minimumWidth() == 360

    def test_skip_checkbox_exists(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert page._skip_checkbox is not None
        assert "我没有 API Key" in page._skip_checkbox.text()

    def test_error_label_starts_empty(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert page._error_label.text() == ""

    def test_register_field_api_key_in_wizard(self, qapp: QApplication) -> None:
        """registerField 需页面处于 wizard 内才可通过 field() 访问。"""
        from tft_consider.ui.setup_wizard import ApiKeyPage, SetupWizard

        config: dict[str, Any] = {"api": {"provider": "moonshot", "key": "", "model": "kimi"}, "ui": {"theme": "dark"}}
        wizard = SetupWizard(config)
        api_page = wizard.page(1)
        assert isinstance(api_page, ApiKeyPage)
        # 页面在 wizard 内时 field() 应返回注册的控件
        assert api_page.field("api_key") is not None


class TestApiKeyPageIsComplete:
    """ApiKeyPage.isComplete() 行为——始终返回 True，由 validatePage 做最终校验。"""

    def test_is_complete_always_true(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert page.isComplete() is True


class TestApiKeyPageSkipToggle:
    """ApiKeyPage._on_skip_toggled()：跳过复选框切换行为。"""

    def test_skip_disables_key_edit(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        assert page._key_edit.isEnabled()
        page._on_skip_toggled(True)
        assert not page._key_edit.isEnabled()

    def test_skip_clears_error_label(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        page._error_label.setText("some previous error")
        page._on_skip_toggled(True)
        assert page._error_label.text() == ""

    def test_unskip_enables_key_edit(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import ApiKeyPage

        page = ApiKeyPage()
        page._on_skip_toggled(True)
        assert not page._key_edit.isEnabled()
        page._on_skip_toggled(False)
        assert page._key_edit.isEnabled()


class TestApiKeyPageValidatePage:
    """ApiKeyPage.validatePage()：校验逻辑和 key 编码存储。

    测试需要 ApiKeyPage 处于 SetupWizard 内，因为 validatePage 会访问
    self.wizard()._config 来存储编码后的 key。
    """

    @staticmethod
    def _make_wizard_with_api_page(config: dict[str, Any] | None = None) -> tuple[Any, Any]:
        """创建 SetupWizard 并返回 (wizard, api_page)。"""
        from tft_consider.ui.setup_wizard import ApiKeyPage, SetupWizard

        if config is None:
            config = {"api": {"provider": "moonshot", "key": "", "model": "kimi"}, "ui": {"theme": "dark"}}
        wizard = SetupWizard(config)
        api_page = wizard.page(1)
        assert isinstance(api_page, ApiKeyPage)
        return wizard, api_page

    def test_validate_skip_checked_allows_continue(self, qapp: QApplication) -> None:
        _, page = self._make_wizard_with_api_page()
        page._skip_checkbox.setChecked(True)
        assert page.validatePage() is True

    def test_validate_empty_key_without_skip_fails(self, qapp: QApplication) -> None:
        _, page = self._make_wizard_with_api_page()
        page._key_edit.setText("")
        page._skip_checkbox.setChecked(False)
        assert page.validatePage() is False
        assert "请输入 API Key" in page._error_label.text()

    def test_validate_key_too_short_fails(self, qapp: QApplication) -> None:
        _, page = self._make_wizard_with_api_page()
        page._key_edit.setText("short")
        page._skip_checkbox.setChecked(False)
        assert page.validatePage() is False
        assert "格式不正确" in page._error_label.text()

    def test_validate_valid_key_stores_base64_encoded(self, qapp: QApplication) -> None:
        wizard, page = self._make_wizard_with_api_page()
        page._key_edit.setText("sk-my-valid-api-key-for-testing")
        page._skip_checkbox.setChecked(False)
        assert page.validatePage() is True
        assert page._error_label.text() == ""
        stored = wizard._config["api"]["key"]
        decoded = base64.b64decode(stored).decode("utf-8")
        assert decoded == "sk-my-valid-api-key-for-testing"

    def test_validate_whitespace_only_key_fails(self, qapp: QApplication) -> None:
        _, page = self._make_wizard_with_api_page()
        page._key_edit.setText("   ")
        page._skip_checkbox.setChecked(False)
        assert page.validatePage() is False
        assert "请输入 API Key" in page._error_label.text()

    def test_validate_exactly_10_char_key_passes(self, qapp: QApplication) -> None:
        """key 长度恰好为 10 时应通过校验（边界值 >= 10）。"""
        wizard, page = self._make_wizard_with_api_page()
        page._key_edit.setText("1234567890")
        page._skip_checkbox.setChecked(False)
        assert page.validatePage() is True
        stored = wizard._config["api"]["key"]
        assert base64.b64decode(stored).decode("utf-8") == "1234567890"

    def test_validate_9_char_key_fails(self, qapp: QApplication) -> None:
        """key 长度为 9 时应不通过校验（边界值 < 10）。"""
        _, page = self._make_wizard_with_api_page()
        page._key_edit.setText("123456789")
        page._skip_checkbox.setChecked(False)
        assert page.validatePage() is False
        assert "格式不正确" in page._error_label.text()


# ---------------------------------------------------------------------------
# DetectPage 测试
# ---------------------------------------------------------------------------


class TestDetectPageInit:
    """DetectPage 初始化：标题和初始状态。"""

    def test_title(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        assert page.title() == "检测英雄联盟"

    def test_subtitle(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        assert "检测" in page.subTitle()

    def test_initial_status_shows_detecting(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        assert "检测中" in page._status_label.text()

    def test_is_complete_false_before_initialize(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        assert page._detected is None
        assert page.isComplete() is False


class TestDetectPageInitializePage:
    """DetectPage.initializePage()：检测执行和标签更新。"""

    def test_initialize_detected_updates_labels(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        with patch.object(DetectPage, "_detect_lol_client", return_value=True):
            page.initializePage()
        assert page._detected is True
        assert "已检测到" in page._status_label.text()

    def test_initialize_not_detected_updates_labels(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        with patch.object(DetectPage, "_detect_lol_client", return_value=False):
            page.initializePage()
        assert page._detected is False
        assert "未检测到" in page._status_label.text()

    def test_initialize_only_runs_detection_once(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        with patch.object(DetectPage, "_detect_lol_client", return_value=True) as mock_detect:
            page.initializePage()
            page.initializePage()
        # 第一次 _detected 已设为 True，第二次应从 if self._detected is not None 直接返回
        mock_detect.assert_called_once()

    def test_initialize_sets_is_complete_true(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        page = DetectPage()
        with patch.object(DetectPage, "_detect_lol_client", return_value=True):
            page.initializePage()
        assert page.isComplete() is True


class TestDetectPageLolClient:
    """DetectPage._detect_lol_client() 静态方法：跨平台进程检测。"""

    def test_non_windows_returns_false(self) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        with patch.object(os, "name", "posix"):
            assert DetectPage._detect_lol_client() is False

    def test_non_windows_macos_returns_false(self) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        # macOS 也是 posix 变体
        with patch.object(os, "name", "darwin"):
            assert DetectPage._detect_lol_client() is False

    def test_windows_process_found(self) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="League of Legends.exe  1234 Console  1  1,024 K",
                returncode=0,
            )
            assert DetectPage._detect_lol_client() is True

    def test_windows_process_not_found(self) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="INFO: No tasks are running which match the specified criteria.",
                returncode=0,
            )
            assert DetectPage._detect_lol_client() is False

    def test_windows_timeout_returns_false(self) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("tasklist", 5)
            assert DetectPage._detect_lol_client() is False

    def test_windows_file_not_found_returns_false(self) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("tasklist not found")
            assert DetectPage._detect_lol_client() is False

    def test_windows_oserror_returns_false(self) -> None:
        from tft_consider.ui.setup_wizard import DetectPage

        with patch.object(os, "name", "nt"), patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("permission denied")
            assert DetectPage._detect_lol_client() is False


# ---------------------------------------------------------------------------
# FinishPage 测试
# ---------------------------------------------------------------------------


class TestFinishPage:
    """FinishPage 初始化与配置摘要生成。"""

    def test_title(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import FinishPage

        page = FinishPage()
        assert page.title() == "配置完成！"

    def test_subtitle(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import FinishPage

        page = FinishPage()
        assert "配置摘要" in page.subTitle()

    def test_initialize_with_key_configured(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import FinishPage, SetupWizard

        config: dict[str, Any] = {
            "api": {"provider": "moonshot", "key": "encoded-key-value", "model": "kimi"},
            "ui": {"theme": "dark"},
        }
        wizard = SetupWizard(config)
        finish_page = wizard.page(3)
        assert isinstance(finish_page, FinishPage)
        finish_page.initializePage()
        summary = finish_page._summary_label.text()
        assert "moonshot" in summary
        assert "已配置" in summary
        assert "dark" in summary
        assert "kimi" in summary

    def test_initialize_without_key_shows_unconfigured(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import FinishPage, SetupWizard

        config: dict[str, Any] = {"api": {"provider": "moonshot", "key": "", "model": "kimi"}, "ui": {"theme": "light"}}
        wizard = SetupWizard(config)
        finish_page = wizard.page(3)
        assert isinstance(finish_page, FinishPage)
        finish_page.initializePage()
        summary = finish_page._summary_label.text()
        assert "未配置（需手动补充）" in summary

    def test_initialize_light_theme_reflected(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import FinishPage, SetupWizard

        config: dict[str, Any] = {"api": {"key": "some-key"}, "ui": {"theme": "light"}}
        wizard = SetupWizard(config)
        finish_page = wizard.page(3)
        assert isinstance(finish_page, FinishPage)
        finish_page.initializePage()
        summary = finish_page._summary_label.text()
        assert "light" in summary

    def test_initialize_non_setup_wizard_returns_early(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import FinishPage

        page = FinishPage()
        # page.wizard() 为 None（未添加到任何 wizard），应安全返回
        page.initializePage()
        assert page._summary_label.text() == ""

    def test_initialize_missing_api_section_uses_defaults(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import FinishPage, SetupWizard

        config: dict[str, Any] = {"ui": {"theme": "dark"}}
        wizard = SetupWizard(config)
        finish_page = wizard.page(3)
        assert isinstance(finish_page, FinishPage)
        finish_page.initializePage()
        summary = finish_page._summary_label.text()
        # provider/model 缺失时显示 "N/A"
        assert "N/A" in summary
        assert "未配置（需手动补充）" in summary


# ---------------------------------------------------------------------------
# SetupWizard 测试
# ---------------------------------------------------------------------------


class TestSetupWizardInit:
    """SetupWizard.__init__：窗口属性、页面编排。"""

    def test_window_title(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        assert "TFT-Consider" in wizard.windowTitle()
        assert "配置向导" in wizard.windowTitle()

    def test_minimum_size(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        assert wizard.minimumWidth() == 520
        assert wizard.minimumHeight() == 440

    def test_wizard_style_is_modern(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        assert wizard.wizardStyle() == QWizard.WizardStyle.ModernStyle

    def test_four_pages(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        assert len(wizard.pageIds()) == 4

    def test_no_cancel_on_last_page(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        assert wizard.testOption(QWizard.WizardOption.NoCancelButtonOnLastPage)

    def test_page_types_in_order(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import (
            ApiKeyPage,
            DetectPage,
            FinishPage,
            SetupWizard,
            WelcomePage,
        )

        wizard = SetupWizard(default_config)
        assert isinstance(wizard.page(0), WelcomePage)
        assert isinstance(wizard.page(1), ApiKeyPage)
        assert isinstance(wizard.page(2), DetectPage)
        assert isinstance(wizard.page(3), FinishPage)


class TestSetupWizardGetConfig:
    """SetupWizard.get_config()：配置读取。"""

    def test_returns_dict(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        result = wizard.get_config()
        assert isinstance(result, dict)

    def test_returns_copy_not_same_object(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        result = wizard.get_config()
        assert result is not wizard._config
        assert result == wizard._config

    def test_modifying_copy_does_not_affect_internal(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        result = wizard.get_config()
        result["api"]["key"] = "modified-value"
        assert wizard._config["api"]["key"] == default_config["api"]["key"]


class TestSetupWizardApplyTheme:
    """SetupWizard._apply_theme()：主题样式表应用。"""

    def test_dark_theme_applied(self, qapp: QApplication, default_config: dict[str, Any]) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard(default_config)
        stylesheet = wizard.styleSheet()
        assert "#1a1a2e" in stylesheet

    def test_light_theme_applied(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        config: dict[str, Any] = {"ui": {"theme": "light"}}
        wizard = SetupWizard(config)
        stylesheet = wizard.styleSheet()
        assert "#f0f0f0" in stylesheet

    def test_theme_defaults_to_dark_when_missing(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard({})
        stylesheet = wizard.styleSheet()
        assert "#1a1a2e" in stylesheet

    def test_theme_ui_not_dict_falls_back_to_dark(self, qapp: QApplication) -> None:
        from tft_consider.ui.setup_wizard import SetupWizard

        wizard = SetupWizard({"ui": "not-a-dict"})
        stylesheet = wizard.styleSheet()
        assert "#1a1a2e" in stylesheet


# ---------------------------------------------------------------------------
# TftConsiderApp._maybe_run_setup_wizard 测试
# ---------------------------------------------------------------------------


class TestMaybeRunSetupWizard:
    """TftConsiderApp._maybe_run_setup_wizard()：首次启动向导决策。"""

    def test_api_key_present_skips_wizard(self, default_config: dict[str, Any]) -> None:
        """api.key 已配置时应直接返回 True，不弹出向导。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(default_config)
        assert app._maybe_run_setup_wizard() is True

    def test_api_key_empty_shows_wizard_accepted(self, empty_key_config: dict[str, Any]) -> None:
        """api.key 为空时弹出向导，用户接受则保存配置并返回 True。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(empty_key_config)
        with patch("tft_consider.ui.app.SetupWizard") as mock_wizard_cls, patch(
            "tft_consider.ui.app.save_config"
        ) as mock_save:
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Accepted
            mock_instance.get_config.return_value = {"api": {"key": "new-encoded-key"}}
            mock_wizard_cls.return_value = mock_instance

            assert app._maybe_run_setup_wizard() is True
            mock_save.assert_called_once_with({"api": {"key": "new-encoded-key"}})
            assert app._config == {"api": {"key": "new-encoded-key"}}

    def test_api_key_empty_shows_wizard_rejected(self, empty_key_config: dict[str, Any]) -> None:
        """api.key 为空时弹出向导，用户取消则返回 False。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(empty_key_config)
        with patch("tft_consider.ui.app.SetupWizard") as mock_wizard_cls:
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Rejected
            mock_wizard_cls.return_value = mock_instance

            assert app._maybe_run_setup_wizard() is False

    def test_api_section_not_dict_treated_as_empty(self) -> None:
        """api 配置为非 dict 时被当作空 key 处理，触发向导。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp({"api": "not-a-dict"})
        with patch("tft_consider.ui.app.SetupWizard") as mock_wizard_cls, patch(
            "tft_consider.ui.app.save_config"
        ):
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Accepted
            mock_instance.get_config.return_value = {}
            mock_wizard_cls.return_value = mock_instance

            assert app._maybe_run_setup_wizard() is True

    def test_no_api_section_triggers_wizard(self) -> None:
        """config 中完全没有 api 节时触发向导。"""
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp({"ui": {"theme": "dark"}})
        with patch("tft_consider.ui.app.SetupWizard") as mock_wizard_cls, patch(
            "tft_consider.ui.app.save_config"
        ):
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Accepted
            mock_instance.get_config.return_value = {}
            mock_wizard_cls.return_value = mock_instance

            assert app._maybe_run_setup_wizard() is True

    def test_api_key_whitespace_only_is_truthy_skips_wizard(self) -> None:
        """api.key 为空白字符（如 "   "）时是 truthy 字符串，跳过向导。

        Note: 当前实现仅检查 bool(api_key)，不 trim。这是需要关注的边界行为。
        """
        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp({"api": {"key": "   "}})
        # key 为非空字符串，被视为已配置，不弹出向导
        assert app._maybe_run_setup_wizard() is True

    def test_save_config_os_error_shows_warning_and_returns_false(
        self, empty_key_config: dict[str, Any]
    ) -> None:
        """save_config 抛出 OSError 时弹出 QMessageBox.warning 并返回 False。"""
        from PySide6.QtWidgets import QMessageBox

        from tft_consider.ui.app import TftConsiderApp

        app = TftConsiderApp(empty_key_config)
        with patch("tft_consider.ui.app.SetupWizard") as mock_wizard_cls, patch(
            "tft_consider.ui.app.save_config"
        ) as mock_save, patch.object(QMessageBox, "warning") as mock_warning:
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Accepted
            mock_instance.get_config.return_value = {"api": {"key": "encoded"}}
            mock_wizard_cls.return_value = mock_instance
            mock_save.side_effect = OSError("no disk space")

            assert app._maybe_run_setup_wizard() is False
            mock_warning.assert_called_once()
            call_kwargs = mock_warning.call_args
            assert "保存失败" in str(call_kwargs)


# ---------------------------------------------------------------------------
# _cmd_setup CLI 测试
# ---------------------------------------------------------------------------


class TestCmdSetup:
    """main._cmd_setup：CLI setup 命令。"""

    def test_setup_accepted_saves_and_prints_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        """用户完成向导后应保存配置并打印成功信息。"""
        from tft_consider.main import _cmd_setup

        with patch("tft_consider.config.load_config") as mock_load, patch(
            "tft_consider.config.save_config"
        ) as mock_save, patch("tft_consider.ui.setup_wizard.SetupWizard") as mock_wizard_cls:
            mock_load.return_value = {"api": {"key": ""}}
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Accepted
            mock_instance.get_config.return_value = {"api": {"key": "new-key"}}
            mock_wizard_cls.return_value = mock_instance

            _cmd_setup()

            captured = capsys.readouterr()
            assert "配置已保存" in captured.out
            mock_save.assert_called_once_with({"api": {"key": "new-key"}})

    def test_setup_rejected_prints_cancel(self, capsys: pytest.CaptureFixture[str]) -> None:
        """用户取消向导时应打印取消信息。"""
        from tft_consider.main import _cmd_setup

        with patch("tft_consider.config.load_config") as mock_load, patch(
            "tft_consider.ui.setup_wizard.SetupWizard"
        ) as mock_wizard_cls:
            mock_load.return_value = {"api": {"key": ""}}
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Rejected
            mock_wizard_cls.return_value = mock_instance

            _cmd_setup()

            captured = capsys.readouterr()
            assert "已取消配置" in captured.out

    def test_setup_save_os_error_exits_with_code_1(self) -> None:
        """save_config 失败时应以 exit code 1 退出。"""
        from tft_consider.main import _cmd_setup

        with patch("tft_consider.config.load_config") as mock_load, patch(
            "tft_consider.config.save_config"
        ) as mock_save, patch("tft_consider.ui.setup_wizard.SetupWizard") as mock_wizard_cls:
            mock_load.return_value = {"api": {"key": ""}}
            mock_instance = MagicMock()
            mock_instance.exec.return_value = QWizard.DialogCode.Accepted
            mock_instance.get_config.return_value = {"api": {"key": "encoded"}}
            mock_wizard_cls.return_value = mock_instance
            mock_save.side_effect = OSError("disk full")

            with pytest.raises(SystemExit) as exc_info:
                _cmd_setup()
            assert exc_info.value.code == 1

    def test_setup_main_dispatches_to_cmd_setup(self) -> None:
        """tft-consider setup 命令应分发到 _cmd_setup。"""
        from tft_consider.main import main

        with patch.object(sys, "argv", ["tft-consider", "setup"]), patch(
            "tft_consider.main._cmd_setup"
        ) as mock_setup:
            main()
            mock_setup.assert_called_once()
