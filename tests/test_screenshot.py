"""ScreenshotCapturer 单元测试。

覆盖 stage 净化、降采样、初始化（默认/自定义/配置临时目录）、
截图（mock mss）、窗口截图回退以及临时文件清理。
所有测试在 macOS 和非 Windows 平台均可通过。
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from tft_consider.screenshot.capturer import ScreenshotCapturer

# ---------------------------------------------------------------------------
# _sanitize_stage 静态方法
# ---------------------------------------------------------------------------


class TestSanitizeStage:
    """_sanitize_stage 静态方法：各种输入的净化行为。"""

    def test_sanitize_stage_normal(self) -> None:
        """正常格式 "3-1" 应保持不变。"""
        assert ScreenshotCapturer._sanitize_stage("3-1") == "3-1"

    def test_sanitize_stage_special_chars(self) -> None:
        """特殊字符应被替换为短横线。"""
        assert ScreenshotCapturer._sanitize_stage("3/1:test") == "3-1-test"

    def test_sanitize_stage_empty(self) -> None:
        """空字符串应返回 'unknown'。"""
        assert ScreenshotCapturer._sanitize_stage("") == "unknown"

    def test_sanitize_stage_none_like(self) -> None:
        """只含特殊字符的字符串净化后为空，应返回 'unknown'。"""
        assert ScreenshotCapturer._sanitize_stage("!@#$%") == "unknown"

    def test_sanitize_stage_strips_dashes(self) -> None:
        """首尾短横线应被去除。"""
        assert ScreenshotCapturer._sanitize_stage("-3-1-") == "3-1"

    def test_sanitize_stage_spaces_to_dashes(self) -> None:
        """空格也会被正则匹配并替换为短横线。"""
        result = ScreenshotCapturer._sanitize_stage("stage 3 1")
        assert result == "stage-3-1"

    def test_sanitize_stage_chinese_chars(self) -> None:
        """中文字符应被替换为短横线。"""
        result = ScreenshotCapturer._sanitize_stage("阶段3-1")
        # "阶段" 被 [^a-zA-Z0-9_\-]+ 替换为单个 "-"，strip 后为 "3-1"
        assert result == "3-1"


# ---------------------------------------------------------------------------
# _downscale 静态方法
# ---------------------------------------------------------------------------


class TestDownscale:
    """_downscale 静态方法：图片缩放逻辑。"""

    def test_downscale_small_image(self) -> None:
        """宽度 <= 1920 的图片应原样返回（同一对象）。"""
        img = Image.new("RGB", (800, 600))
        result = ScreenshotCapturer._downscale(img)
        assert result is img
        assert result.width == 800
        assert result.height == 600

    def test_downscale_exact_boundary(self) -> None:
        """宽度恰为 1920 的图片应原样返回。"""
        img = Image.new("RGB", (1920, 1080))
        result = ScreenshotCapturer._downscale(img)
        assert result is img

    def test_downscale_large_image(self) -> None:
        """宽度 > 1920 时应等比缩放至宽度 1920。"""
        img = Image.new("RGB", (2560, 1440))
        result = ScreenshotCapturer._downscale(img)
        assert result is not img  # 应返回新对象
        assert result.width == 1920
        assert result.height == 1080  # 1440 * (1920/2560) = 1080

    def test_downscale_ultrawide(self) -> None:
        """超宽屏 (3440x1440) 应等比缩放至 1920x803。"""
        img = Image.new("RGB", (3440, 1440))
        result = ScreenshotCapturer._downscale(img)
        assert result.width == 1920
        assert result.height == 803  # int(1440 * 1920 / 3440) = int(803.72) = 803


# ---------------------------------------------------------------------------
# ScreenshotCapturer 初始化
# ---------------------------------------------------------------------------


class TestCapturerInit:
    """ScreenshotCapturer.__init__ 临时目录处理。"""

    @pytest.mark.skipif(os.name == "nt", reason="Windows 使用 TEMP 而非 XDG_CACHE_HOME")
    def test_capturer_init_default_temp_dir(self, monkeypatch, tmp_path: Path) -> None:
        """未指定 temp_dir 且无配置时，使用默认 XDG_CACHE_HOME 路径并创建。"""
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        capturer = ScreenshotCapturer(config={})
        expected = tmp_path / "tft-consider" / "screenshots"
        assert capturer._temp_dir_path == expected
        assert expected.exists()

    def test_capturer_init_custom_temp_dir(self, tmp_path: Path) -> None:
        """构造传入自定义 temp_dir 时应使用该路径并创建。"""
        custom = tmp_path / "my_captures"
        capturer = ScreenshotCapturer(config={}, temp_dir=str(custom))
        assert capturer._temp_dir_path == custom
        assert custom.exists()

    def test_capturer_init_config_temp_dir(self, tmp_path: Path) -> None:
        """config 中 screenshot.temp_dir 优先于默认路径。"""
        config = {"screenshot": {"temp_dir": str(tmp_path / "from_config")}}
        capturer = ScreenshotCapturer(config=config)
        assert capturer._temp_dir_path == tmp_path / "from_config"
        assert (tmp_path / "from_config").exists()

    def test_capturer_init_priority(self, tmp_path: Path) -> None:
        """显式 temp_dir 参数优先级最高。"""
        config = {"screenshot": {"temp_dir": str(tmp_path / "from_config")}}
        capturer = ScreenshotCapturer(config=config, temp_dir=str(tmp_path / "explicit"))
        assert capturer._temp_dir_path == tmp_path / "explicit"

    def test_capturer_init_creates_parents(self, tmp_path: Path) -> None:
        """嵌套目录应通过 mkdir(parents=True) 递归创建。"""
        deep = tmp_path / "a" / "b" / "c"
        _ = ScreenshotCapturer(config={}, temp_dir=str(deep))
        assert deep.exists()


# ---------------------------------------------------------------------------
# capture 基本截图
# ---------------------------------------------------------------------------


class TestCapture:
    """ScreenshotCapturer.capture 基本截图流程。"""

    def test_capture_basic(self, tmp_path: Path) -> None:
        """mock _capture_fullscreen_mss 后 capture() 应正常保存 PNG 文件。"""
        test_img = Image.new("RGB", (100, 100), color="blue")
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        with patch.object(capturer, "_capture_fullscreen_mss", return_value=test_img):
            result = capturer.capture(stage="1-1")

        assert result is not None
        assert result.suffix == ".png"
        assert result.parent == tmp_path
        assert result.exists()
        # 验证文件确实是有效的 PNG
        saved = Image.open(result)
        assert saved.size == (100, 100)

    def test_capture_uses_stage_in_filename(self, tmp_path: Path) -> None:
        """stage 参数应出现在生成的文件名中。"""
        test_img = Image.new("RGB", (50, 50))
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        with patch.object(capturer, "_capture_fullscreen_mss", return_value=test_img):
            result = capturer.capture(stage="3-2-combat")

        assert result is not None
        assert "3-2-combat" in result.name

    def test_capture_downscale_applied(self, tmp_path: Path) -> None:
        """宽图 (2560px) 应被降采样至 1920px 再保存。"""
        test_img = Image.new("RGB", (2560, 1440))
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        with patch.object(capturer, "_capture_fullscreen_mss", return_value=test_img):
            result = capturer.capture(stage="test")

        assert result is not None
        saved = Image.open(result)
        assert saved.width == 1920
        assert saved.height == 1080

    def test_capture_mss_returns_none(self, tmp_path: Path) -> None:
        """当 _capture_fullscreen_mss 返回 None 时，capture 应返回 None。"""
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        with patch.object(capturer, "_capture_fullscreen_mss", return_value=None):
            result = capturer.capture(stage="test")

        assert result is None


# ---------------------------------------------------------------------------
# capture_window
# ---------------------------------------------------------------------------


class TestCaptureWindow:
    """ScreenshotCapturer.capture_window 窗口截图。"""

    def test_capture_window_fallback_on_macos(self, tmp_path: Path) -> None:
        """在非 Windows 平台，_find_window_rect 返回 None，
        _capture_window_region 返回 None，应回退到全屏截图。
        """
        test_img = Image.new("RGB", (100, 100))
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        with patch.object(capturer, "_capture_fullscreen_mss", return_value=test_img):
            result = capturer.capture_window(window_title="League of Legends")

        assert result is not None
        assert result.suffix == ".png"
        assert "window_fullscreen_fallback" in result.name

    def test_capture_window_region_success(self, tmp_path: Path) -> None:
        """当 _capture_window_region 成功返回图片时，应直接使用该区域截图。"""
        test_img = Image.new("RGB", (200, 150))
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        with patch.object(capturer, "_capture_window_region", return_value=test_img):
            result = capturer.capture_window(window_title="Test")

        assert result is not None
        assert result.suffix == ".png"
        assert "window" in result.name  # stage="window" 用于直接窗口截图


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    """ScreenshotCapturer.cleanup 清理逻辑。"""

    def test_cleanup(self, tmp_path: Path) -> None:
        """cleanup 应删除临时目录中的所有 .png 文件，保留非 .png 文件。"""
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        # 创建测试文件
        (tmp_path / "shot1.png").write_text("fake png content")
        (tmp_path / "shot2.png").write_text("another fake png")
        (tmp_path / "config.json").write_text('{"key": "value"}')
        (tmp_path / "log.txt").write_text("some log")

        capturer.cleanup()

        # .png 文件应被删除
        assert not (tmp_path / "shot1.png").exists()
        assert not (tmp_path / "shot2.png").exists()
        # 非 .png 文件应保留
        assert (tmp_path / "config.json").exists()
        assert (tmp_path / "log.txt").exists()

    def test_cleanup_empty_dir(self, tmp_path: Path) -> None:
        """临时目录为空时，cleanup 不应抛异常。"""
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))
        capturer.cleanup()  # 不抛异常

    def test_cleanup_nonexistent_dir(self, tmp_path: Path) -> None:
        """临时目录不存在时，cleanup 应安全返回。"""
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))
        # 手动删除目录模拟外部删除
        import shutil
        shutil.rmtree(tmp_path)
        capturer.cleanup()  # 不抛异常

    def test_cleanup_only_png_files(self, tmp_path: Path) -> None:
        """cleanup 应只删除 .png 后缀文件（不区分大小写）。"""
        capturer = ScreenshotCapturer(config={}, temp_dir=str(tmp_path))

        (tmp_path / "image.PNG").write_text("uppercase png")
        (tmp_path / "image.png").write_text("lowercase png")
        (tmp_path / "image.Png").write_text("mixed case png")
        (tmp_path / "readme.md").write_text("# docs")

        capturer.cleanup()

        # 所有大小写的 .png 都应删除（suffix 比较已处理为 .lower()）
        assert not (tmp_path / "image.PNG").exists()
        assert not (tmp_path / "image.png").exists()
        assert not (tmp_path / "image.Png").exists()
        # .md 文件保留
        assert (tmp_path / "readme.md").exists()
