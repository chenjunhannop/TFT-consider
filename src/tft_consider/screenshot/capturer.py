"""截图采集模块。

使用 mss 库进行全屏截图，PySide6 作为窗口截图的备选方案。
支持手动快捷键截图（Ctrl+Shift+S）。
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_MAX_WIDTH: int = 1920
_STAGE_SANITIZE_PATTERN: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9_\-]+")

# ---------------------------------------------------------------------------
# ScreenshotCapturer
# ---------------------------------------------------------------------------


class ScreenshotCapturer:
    """截图采集器。

    首选方案：mss 全屏截图（快、可靠）。
    备选方案：PySide6 QScreen.grabWindow 截取特定窗口句柄。
    截图前自动降采样：宽度超过 1920 时等比缩放到 1920。
    """

    def __init__(self, config: dict[str, Any], temp_dir: str | None = None) -> None:
        """初始化截图采集器。

        Args:
            config: 应用配置字典，可选包含 screenshot.temp_dir 项。
            temp_dir: 截图临时目录。默认读取配置项或使用 %TEMP%/tft-consider/。
        """
        self._config = config

        screenshot_cfg = config.get("screenshot", {}) if isinstance(config, dict) else {}
        configured_dir = screenshot_cfg.get("temp_dir", "") if isinstance(screenshot_cfg, dict) else ""

        if temp_dir:
            self._temp_dir_path = Path(temp_dir)
        elif configured_dir:
            self._temp_dir_path = Path(configured_dir)
        elif os.name == "nt":
            default_temp = Path.home() / "AppData" / "Local" / "Temp"
            self._temp_dir_path = Path(os.environ.get("TEMP", str(default_temp))) / "tft-consider"
        else:
            default_cache = Path.home() / ".cache"
            self._temp_dir_path = (
                Path(os.environ.get("XDG_CACHE_HOME", str(default_cache)))
                / "tft-consider"
                / "screenshots"
            )

        self._temp_dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug("截图临时目录: %s", self._temp_dir_path)

    # --- 公共 API ----------------------------------------------------------------

    def capture(self, stage: str = "unknown") -> Path | None:
        """截取全屏并保存为 PNG。

        Args:
            stage: 阶段标识，用于文件命名。例如 "1-1"、"3-1-combat"。

        Returns:
            截图文件路径，失败时返回 None。
        """
        logger.info("全屏截图请求, stage=%s", stage)
        img = self._capture_fullscreen_mss()
        if img is None:
            logger.error("全屏截图失败: mss 未能获取屏幕像素")
            return None
        img = self._downscale(img)
        return self._save_png(img, stage)

    def capture_window(self, window_title: str = "League of Legends") -> Path | None:
        """截取指定窗口，失败时回退全屏。

        先尝试用 ctypes 查找窗口并获取区域，再用 mss 截取该区域。
        若窗口查找或区域截图失败，回退为全屏截图。

        Args:
            window_title: 目标窗口标题（仅 Windows 支持）。

        Returns:
            截图文件路径，失败时返回 None。
        """
        stage = "window"
        logger.info("窗口截图请求, title=%s", window_title)
        img = self._capture_window_region(window_title)
        if img is not None:
            img = self._downscale(img)
            return self._save_png(img, stage)

        logger.warning("窗口截图失败，回退全屏, title=%s", window_title)
        return self.capture(stage="window_fullscreen_fallback")

    def cleanup(self) -> None:
        """清理临时目录中由本采集器生成的所有截图文件。"""
        logger.info("清理截图临时文件, dir=%s", self._temp_dir_path)
        if not self._temp_dir_path.exists():
            return
        count = 0
        for p in self._temp_dir_path.iterdir():
            if p.is_file() and p.suffix.lower() == ".png":
                try:
                    p.unlink()
                    count += 1
                except OSError as exc:
                    logger.warning("删除截图文件失败: %s, 原因: %s", p, exc)
        logger.info("已清理 %d 个截图文件", count)

    # --- 内部实现 ----------------------------------------------------------------

    def _capture_fullscreen_mss(self) -> Image.Image | None:
        """使用 mss 截取主显示器全屏。

        Returns:
            PIL Image 对象，失败时返回 None。
        """
        try:
            import mss
        except ImportError:
            logger.error("mss 库不可用，无法截图")
            return None

        try:
            with mss.mss() as sct:
                if len(sct.monitors) < 2:
                    logger.error("未检测到显示器 (monitors=%d)", len(sct.monitors))
                    return None
                monitor = sct.monitors[1]  # 主显示器
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.rgb)
        except Exception:
            logger.exception("mss 全屏截图异常")
            return None

    def _capture_window_region(self, window_title: str) -> Image.Image | None:
        """查找窗口并用 mss 截取其区域。

        Args:
            window_title: 目标窗口标题。

        Returns:
            PIL Image 对象，失败时返回 None。
        """
        rect = self._find_window_rect(window_title)
        if rect is None:
            return None

        left, top, right, bottom = rect
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            logger.warning("窗口区域无效: (%d,%d,%d,%d)", left, top, right, bottom)
            return None

        logger.debug("窗口区域: left=%d, top=%d, width=%d, height=%d", left, top, width, height)

        try:
            import mss
        except ImportError:
            logger.error("mss 库不可用，无法截取窗口区域")
            return None

        try:
            region = {"left": left, "top": top, "width": width, "height": height}
            with mss.mss() as sct:
                sct_img = sct.grab(region)
                return Image.frombytes("RGB", sct_img.size, sct_img.rgb)
        except Exception:
            logger.exception("mss 窗口区域截图异常")
            return None

    def _find_window_rect(self, window_title: str) -> tuple[int, int, int, int] | None:
        """使用 Win32 API 查找窗口并返回其矩形区域。

        仅在 Windows 平台上可用。

        Args:
            window_title: 目标窗口标题。

        Returns:
            (left, top, right, bottom) 元组，失败返回 None。
        """
        if os.name != "nt":
            logger.debug("非 Windows 平台，跳过窗口查找")
            return None

        try:
            import ctypes
        except ImportError:
            logger.error("ctypes 不可用")
            return None

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            logger.error("无法加载 user32.dll")
            return None
        user32 = windll.user32

        # 查找窗口
        hwnd = user32.FindWindowW(None, window_title)
        if not hwnd:
            # 尝试部分匹配的常见变体
            alt_titles = [
                "League of Legends (TM) Client",
                "League of Legends",
                "英雄联盟",
            ]
            for alt in alt_titles:
                if alt == window_title:
                    continue
                hwnd = user32.FindWindowW(None, alt)
                if hwnd:
                    logger.debug("使用备用标题找到窗口: %s", alt)
                    break

        if not hwnd:
            logger.warning("未找到窗口: %s", window_title)
            return None

        # 获取窗口矩形
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            logger.warning("GetWindowRect 失败, hwnd=%d", hwnd)
            return None

        logger.debug(
            "窗口找到: hwnd=%d, rect=(%d,%d,%d,%d)",
            hwnd, rect.left, rect.top, rect.right, rect.bottom,
        )
        return (rect.left, rect.top, rect.right, rect.bottom)

    @staticmethod
    def _downscale(image: Image.Image) -> Image.Image:
        """若图片宽度超过 _MAX_WIDTH，等比缩放到宽度 1920。

        Args:
            image: 原始 PIL Image。

        Returns:
            缩放后的 PIL Image（可能返回原图，不复制）。
        """
        if image.width <= _MAX_WIDTH:
            return image

        ratio = _MAX_WIDTH / image.width
        new_width = _MAX_WIDTH
        new_height = int(image.height * ratio)
        logger.debug("降采样: %dx%d -> %dx%d", image.width, image.height, new_width, new_height)

        try:
            return image.resize((new_width, new_height), Image.LANCZOS)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("降采样失败，返回原图")
            return image

    def _save_png(self, image: Image.Image, stage: str) -> Path | None:
        """将 PIL Image 另存为 PNG 到临时目录。

        文件命名: {stage}_{YYYYMMDD_HHMMSS}.png。

        Args:
            image: PIL Image 对象。
            stage: 阶段标识。

        Returns:
            保存的文件路径，失败返回 None。
        """
        safe_stage = self._sanitize_stage(stage)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{safe_stage}_{timestamp}"

        file_path = self._temp_dir_path / f"{base_name}.png"

        # 处理文件名冲突 (极少发生，如同秒内多次截图)
        counter = 2
        while file_path.exists():
            file_path = self._temp_dir_path / f"{base_name}_{counter}.png"
            counter += 1

        try:
            image.save(file_path, "PNG")
            logger.info("截图已保存: %s (size=%dx%d)", file_path, image.width, image.height)
            return file_path
        except Exception:
            logger.exception("截图保存失败: %s", file_path)
            return None

    @staticmethod
    def _sanitize_stage(stage: str) -> str:
        """净化阶段标识，移除文件名不安全字符。

        Args:
            stage: 原始阶段标识。

        Returns:
            净化后的标识字符串。
        """
        if not stage:
            return "unknown"
        sanitized = _STAGE_SANITIZE_PATTERN.sub("-", stage)
        sanitized = sanitized.strip("-")
        if not sanitized:
            return "unknown"
        return sanitized


# ---------------------------------------------------------------------------
# ManualCapture
# ---------------------------------------------------------------------------


class ManualCapture:
    """手动截图快捷键监听器。

    使用 pynput 监听 Ctrl+Shift+S 快捷键触发截图。
    pynput 作为可选依赖，不可用时打印警告并降级为无操作。
    """

    def __init__(self, capturer: ScreenshotCapturer) -> None:
        """初始化手动截图监听器。

        Args:
            capturer: ScreenshotCapturer 实例。
        """
        self._capturer = capturer
        self._listener: Any = None
        self._pynput_available = False
        try:
            import pynput  # noqa: F401
            self._pynput_available = True
        except ImportError:
            logger.warning("pynput 不可用，手动快捷键监听已禁用。请安装 pynput 以启用 Ctrl+Shift+S 快捷键。")

    def start_listener(self) -> None:
        """启动快捷键监听器 (Ctrl+Shift+S 触发截图)。"""
        if not self._pynput_available:
            print("[WARN] pynput 未安装，手动快捷键 (Ctrl+Shift+S) 不可用")
            logger.warning("尝试启动快捷键监听但 pynput 不可用")
            return

        if self._listener is not None:
            logger.debug("快捷键监听器已在运行")
            return

        try:
            from pynput.keyboard import GlobalHotKeys

            def on_activate() -> None:
                path = self._capturer.capture(stage="manual")
                if path:
                    print(f"Screenshot saved: {path}")

            self._listener = GlobalHotKeys({"<ctrl>+<shift>+s": on_activate})
            self._listener.start()
            logger.info("快捷键监听已启动: Ctrl+Shift+S")
            print("[INFO] 快捷键监听已启动: Ctrl+Shift+S 手动截图")
        except Exception:
            logger.exception("启动快捷键监听失败")
            self._listener = None

    def stop_listener(self) -> None:
        """停止快捷键监听器。"""
        if self._listener is None:
            return
        try:
            self._listener.stop()
            logger.info("快捷键监听已停止")
        except Exception:
            logger.exception("停止快捷键监听异常")
        finally:
            self._listener = None
