"""首次启动引导向导。

SetupWizard 引导新用户完成 API Key 配置、游戏客户端检测，
并在完成后保存配置。
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
from typing import Any, override

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 主题样式表
# ---------------------------------------------------------------------------

_DARK_WIZARD_STYLE = """
QWizard {
    background-color: #1a1a2e;
}
QWizardPage {
    background-color: #1a1a2e;
}
QLabel {
    color: #e0e0e0;
    font-size: 13px;
}
QLineEdit {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #e94560;
}
QCheckBox {
    color: #a0a0b0;
    font-size: 12px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #0f3460;
    border-radius: 3px;
    background-color: #16213e;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}
QPushButton {
    background-color: #0f3460;
    color: #e0e0e0;
    border: 1px solid #0f3460;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #e94560;
    border-color: #e94560;
}
QPushButton:disabled {
    background-color: #2a2a3e;
    color: #666666;
}
"""

_LIGHT_WIZARD_STYLE = """
QWizard {
    background-color: #f0f0f0;
}
QWizardPage {
    background-color: #f0f0f0;
}
QLabel {
    color: #333333;
    font-size: 13px;
}
QLineEdit {
    background-color: #ffffff;
    color: #333333;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #e94560;
}
QCheckBox {
    color: #666666;
    font-size: 12px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #cccccc;
    border-radius: 3px;
    background-color: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border-color: #e94560;
}
QPushButton {
    background-color: #e0e0e0;
    color: #333333;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #e94560;
    color: #ffffff;
    border-color: #e94560;
}
QPushButton:disabled {
    background-color: #f5f5f5;
    color: #999999;
}
"""


# ---------------------------------------------------------------------------
# 各向导页
# ---------------------------------------------------------------------------


class WelcomePage(QWizardPage):
    """第 1 页 —— 欢迎页：项目简介与核心功能列表。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("欢迎使用 TFT-Consider")
        self.setSubTitle("云顶之弈 AI 对局分析助手，几分钟完成配置即可使用")

        layout = QVBoxLayout()

        intro = QLabel(
            "TFT-Consider 是一款云顶之弈 AI 辅助工具，帮助你在对局中做出更优决策。\n\n"
            "核心功能："
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        features = QLabel(
            "  对局中的截图分析 —— 实时识别当前棋盘状态\n"
            "  最佳阵容推荐 —— 结合 meta 数据推荐最优阵容\n"
            "  行动建议 —— 每回合给出升级、D 牌、变阵建议\n"
            "  对局追踪 —— 记录每局数据，赛后复盘分析\n\n"
            "点击「下一步」开始配置。"
        )
        features.setWordWrap(True)
        layout.addWidget(features)

        layout.addStretch()
        self.setLayout(layout)


class ApiKeyPage(QWizardPage):
    """第 2 页 —— API Key 配置：输入 Moonshot API Key。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("配置 API Key")
        self.setSubTitle(
            "请输入 Moonshot (Kimi) API Key。可在 https://platform.moonshot.cn 获取"
        )

        layout = QVBoxLayout()

        instr = QLabel("API Key:")
        layout.addWidget(instr)

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("请输入你的 API Key...")
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setMinimumWidth(360)
        layout.addWidget(self._key_edit)

        self._skip_checkbox = QCheckBox("我没有 API Key，稍后在配置文件中手动填写")
        self._skip_checkbox.toggled.connect(self._on_skip_toggled)
        layout.addWidget(self._skip_checkbox)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #e94560; font-size: 12px;")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        layout.addStretch()
        self.setLayout(layout)

        # 注册字段供后续页使用
        self.registerField("api_key", self._key_edit)

    def _on_skip_toggled(self, checked: bool) -> None:
        """跳过复选框切换时，更新输入框和错误提示状态。"""
        self._key_edit.setEnabled(not checked)
        if checked:
            self._error_label.setText("")
        self.completeChanged.emit()

    @override
    def isComplete(self) -> bool:
        """跳过勾选时始终可继续；否则需要填写有效 key。"""
        return True  # 始终允许尝试「下一步」，由 validatePage 做最终校验

    @override
    def validatePage(self) -> bool:
        """点击「下一步」时校验输入。

        跳过时允许继续；未跳过时校验 key 长度 >= 10。
        """
        if self._skip_checkbox.isChecked():
            logger.info("用户选择跳过 API Key 配置")
            return True

        raw_key = self._key_edit.text().strip()
        if not raw_key:
            self._error_label.setText("请输入 API Key，或勾选「我没有 API Key」跳过。")
            return False

        if len(raw_key) < 10:
            self._error_label.setText("API Key 格式不正确，长度应至少为 10 个字符。")
            return False

        # base64 编码后写入 config
        encoded = base64.b64encode(raw_key.encode("utf-8")).decode("utf-8")
        wizard = self.wizard()
        if isinstance(wizard, SetupWizard):
            wizard._config["api"]["key"] = encoded
            logger.info("API Key 已编码保存到配置")

        self._error_label.setText("")
        return True


class DetectPage(QWizardPage):
    """第 3 页 —— 游戏检测：自动检测英雄联盟客户端。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("检测英雄联盟")
        self.setSubTitle("正在检测英雄联盟客户端状态...")

        layout = QVBoxLayout()

        self._status_label = QLabel("检测中...")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("font-size: 15px; padding: 20px;")
        layout.addWidget(self._status_label)

        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet("font-size: 12px; color: #a0a0b0;")
        layout.addWidget(self._detail_label)

        layout.addStretch()
        self.setLayout(layout)

        self._detected: bool | None = None

    # ------------------------------------------------------------------
    # 页面生命周期
    # ------------------------------------------------------------------

    @override
    def initializePage(self) -> None:
        """页面首次显示时自动运行客户端检测。"""
        if self._detected is not None:
            return

        self._detected = self._detect_lol_client()
        if self._detected:
            self._status_label.setText("✅ 已检测到英雄联盟客户端")
            self._status_label.setStyleSheet(
                "font-size: 15px; padding: 20px; color: #4ecca3;"
            )
            self._detail_label.setText("客户端正在运行，准备就绪。")
        else:
            self._status_label.setText("⚠️ 未检测到英雄联盟客户端")
            self._status_label.setStyleSheet(
                "font-size: 15px; padding: 20px; color: #f0a040;"
            )
            self._detail_label.setText(
                "未检测到客户端，请确认游戏已启动。\n"
                "应用仍可启动，但分析功能需要游戏运行。"
            )

        self.completeChanged.emit()

    @override
    def isComplete(self) -> bool:
        """检测完成后始终允许继续。"""
        return self._detected is not None

    # ------------------------------------------------------------------
    # 检测实现
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_lol_client() -> bool:
        """检测英雄联盟客户端是否运行。

        Windows 上通过 tasklist 进程名检测；非 Windows 直接返回 False。
        """
        if os.name != "nt":
            logger.info("非 Windows 平台，跳过英雄联盟客户端检测")
            return False

        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq League of Legends.exe"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            found = "League of Legends.exe" in result.stdout
            if found:
                logger.info("检测到英雄联盟客户端正在运行")
            else:
                logger.info("未检测到英雄联盟客户端")
            return bool(found)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("检测英雄联盟客户端失败: %s", exc)
            return False


class FinishPage(QWizardPage):
    """第 4 页 —— 完成：显示配置摘要并允许保存。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle("配置完成！")
        self.setSubTitle("以下是你的配置摘要，点击「完成」保存并启动应用。")

        layout = QVBoxLayout()

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        layout.addStretch()
        self.setLayout(layout)

    @override
    def initializePage(self) -> None:
        """生成配置摘要。"""
        wizard = self.wizard()
        if not isinstance(wizard, SetupWizard):
            return

        cfg = wizard._config
        api_cfg = cfg.get("api", {}) if isinstance(cfg.get("api"), dict) else {}
        ui_cfg = cfg.get("ui", {}) if isinstance(cfg.get("ui"), dict) else {}

        provider = api_cfg.get("provider", "N/A")
        model = api_cfg.get("model", "N/A")
        key_raw = api_cfg.get("key", "")
        key_status = "已配置" if key_raw else "未配置（需手动补充）"
        theme = ui_cfg.get("theme", "dark")

        summary_text = (
            f"  API 提供商: {provider}\n"
            f"  API 模型: {model}\n"
            f"  API Key: {key_status}\n"
            f"  主题: {theme}\n\n"
            "配置将在点击「完成」后保存到 config.yaml。\n"
            "之后可在应用设置中修改或通过 tft-consider setup 重新运行向导。"
        )
        self._summary_label.setText(summary_text)


# ---------------------------------------------------------------------------
# SetupWizard
# ---------------------------------------------------------------------------


class SetupWizard(QWizard):
    """首次启动引导向导。

    引导用户完成基础配置：欢迎介绍、API Key 输入、游戏检测、完成。
    """

    def __init__(
        self, config: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        """初始化引导向导。

        Args:
            config: 当前应用配置字典（将被复制并原地修改）。
            parent: 可选的父级 QWidget。
        """
        super().__init__(parent)
        self._config: dict[str, Any] = dict(config)  # 深拷贝一层（浅层足够）

        self.setWindowTitle("TFT-Consider 首次配置向导")
        self.setMinimumSize(520, 440)
        self.resize(560, 480)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoCancelButtonOnLastPage, True)

        # 添加向导页
        self._welcome_page = WelcomePage()
        self._api_page = ApiKeyPage()
        self._detect_page = DetectPage()
        self._finish_page = FinishPage()

        self.addPage(self._welcome_page)
        self.addPage(self._api_page)
        self.addPage(self._detect_page)
        self.addPage(self._finish_page)

        self._apply_theme()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """返回用户在向导中修改后的配置字典。

        Returns:
            包含用户配置项的字典。
        """
        return dict(self._config)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        """从配置读取 ui.theme 并应用对应的 QSS 样式表。"""
        ui_cfg = self._config.get("ui", {})
        if not isinstance(ui_cfg, dict):
            ui_cfg = {}
        theme = str(ui_cfg.get("theme", "dark")).lower()
        stylesheet = _DARK_WIZARD_STYLE if theme == "dark" else _LIGHT_WIZARD_STYLE
        self.setStyleSheet(stylesheet)
        logger.debug("SetupWizard 应用主题: %s", theme)
