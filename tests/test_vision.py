"""Spec 002: LLM 视觉识别 单元测试。

覆盖 BaseProvider 抽象约束、MoonshotProvider 初始化/API 调用/重试/降采样/
token usage 日志、以及 SYSTEM_PROMPT 内容校验。
所有测试在 macOS 上运行，不发起真实 HTTP 请求。
"""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image

from tft_consider.config import get_api_key, mask_key
from tft_consider.vision.base import BaseProvider
from tft_consider.vision.moonshot import (
    _DEFAULT_MODEL,
    _DOWNSCALE_HEIGHT,
    _DOWNSCALE_WIDTH,
    _MAX_RETRIES,
    MoonshotProvider,
)
from tft_consider.vision.prompts import SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_config(api_key: str = "dummy-key", model: str | None = None) -> dict[str, Any]:
    """构建测试用最小 config，总是包含 api.key 避免 get_api_key 抛 ValueError。"""
    api_cfg: dict[str, Any] = {"key": api_key}
    if model is not None:
        api_cfg["model"] = model
    return {"api": api_cfg}


def create_test_image(tmp_path: Path, width: int = 100, height: int = 100, name: str = "test.png") -> Path:
    """在 tmp_path 下创建一张纯色 PNG 测试图片并返回路径。"""
    img = Image.new("RGB", (width, height), color="red")
    path = tmp_path / name
    img.save(path, format="PNG")
    return path


def make_mock_response(
    status_code: int = 200,
    content: str | None = None,
    *,
    usage: dict[str, int] | None = None,
    is_json_error: bool = False,
) -> MagicMock:
    """构建 mock httpx.Response。

    Args:
        status_code: HTTP 状态码。
        content: choices[0].message.content 字符串。若为 None，使用默认 JSON。
        usage: token usage dict，默认 {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}。
        is_json_error: True 时 .json() 抛出 json.JSONDecodeError。
    """
    if usage is None:
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    if content is None:
        content = json.dumps({"result": "ok"})

    resp_body = {
        "choices": [{"message": {"content": content}}],
        "usage": usage,
    }

    resp = MagicMock(spec=httpx.Response)
    resp.is_success = 200 <= status_code < 300
    resp.status_code = status_code
    resp.text = json.dumps(resp_body)

    if is_json_error:
        resp.json.side_effect = json.JSONDecodeError("bad json", "", 0)
    else:
        resp.json.return_value = resp_body

    return resp


# ---------------------------------------------------------------------------
# TestBaseProvider — 抽象基类约束
# ---------------------------------------------------------------------------


class TestBaseProvider:
    """验证 BaseProvider 的抽象行为。"""

    def test_cannot_instantiate_abstract(self) -> None:
        """直接实例化 BaseProvider 应抛出 TypeError。"""
        with pytest.raises(TypeError, match="abstract"):
            BaseProvider({})

    def test_subclass_must_implement_methods(self) -> None:
        """未实现全部抽象方法的子类无法实例化。"""

        class IncompleteProvider(BaseProvider):  # type: ignore[misc]
            def provider_name(self) -> str:  # 只实现了 provider_name
                return "incomplete"

        with pytest.raises(TypeError, match="abstract"):
            IncompleteProvider({})

    def test_config_passed_to_init(self) -> None:
        """__init__ 将 config 存储到 self._config。"""

        class ConcreteProvider(BaseProvider):  # type: ignore[misc]
            def analyze_screenshot(self, image_path: Path) -> dict[str, Any] | None:
                return None

            def provider_name(self) -> str:
                return "concrete"

        cfg = make_config()
        p = ConcreteProvider(cfg)
        assert p._config is cfg
        assert p._config["api"]["key"] == "dummy-key"


# ---------------------------------------------------------------------------
# TestMoonshotProvider — 初始化
# ---------------------------------------------------------------------------


class TestMoonshotProviderInit:
    """MoonshotProvider.__init__ 初始化逻辑。"""

    def test_provider_name(self) -> None:
        """provider_name() 返回 'moonshot'。"""
        p = MoonshotProvider(make_config())
        assert p.provider_name() == "moonshot"

    def test_init_with_default_model(self) -> None:
        """不指定 api.model 时使用 _DEFAULT_MODEL。"""
        p = MoonshotProvider(make_config())
        assert p._model == _DEFAULT_MODEL

    def test_init_with_custom_model(self) -> None:
        """config 中指定 api.model 时正确读取。"""
        p = MoonshotProvider(make_config(model="custom-model-v1"))
        assert p._model == "custom-model-v1"


# ---------------------------------------------------------------------------
# TestMoonshotProvider — analyze_screenshot 顶层逻辑
# ---------------------------------------------------------------------------


class TestAnalyzeScreenshot:
    """MoonshotProvider.analyze_screenshot 顶层流程。"""

    def test_file_not_found_returns_none(self, tmp_path: Path) -> None:
        """文件不存在时返回 None，不发起 API 调用。"""
        p = MoonshotProvider(make_config())
        nonexistent = tmp_path / "does_not_exist.png"
        result = p.analyze_screenshot(nonexistent)
        assert result is None

    def test_api_success(self, tmp_path: Path) -> None:
        """_call_api 返回 dict 时，analyze_screenshot 正确返回结果。"""
        image_path = create_test_image(tmp_path)
        p = MoonshotProvider(make_config())
        expected = {"result": "ok"}

        with patch.object(p, "_call_api", return_value=expected) as mock_call:
            result = p.analyze_screenshot(image_path)

        assert result == expected
        mock_call.assert_called_once()

    def test_api_retry(self, tmp_path: Path) -> None:
        """首次 _call_api 失败，第二次成功，应重试并返回结果。"""
        image_path = create_test_image(tmp_path)
        p = MoonshotProvider(make_config())
        expected = {"result": "retry_ok"}

        with patch.object(
            p, "_call_api", side_effect=[ValueError("first fail"), expected],
        ) as mock_call:
            result = p.analyze_screenshot(image_path)

        assert result == expected
        assert mock_call.call_count == 2

    def test_api_all_fail(self, tmp_path: Path) -> None:
        """_call_api 始终失败，_MAX_RETRIES 次后返回 None。"""
        image_path = create_test_image(tmp_path)
        p = MoonshotProvider(make_config())

        with patch.object(
            p, "_call_api", side_effect=RuntimeError("always fail"),
        ) as mock_call:
            result = p.analyze_screenshot(image_path)

        assert result is None
        assert mock_call.call_count == _MAX_RETRIES

    def test_encode_image_failure_returns_none(self, tmp_path: Path) -> None:
        """_encode_image 抛异常时返回 None，不调用 _call_api。"""
        image_path = create_test_image(tmp_path)
        p = MoonshotProvider(make_config())

        with patch.object(p, "_encode_image", side_effect=OSError("encode fail")):
            with patch.object(p, "_call_api") as mock_call:
                result = p.analyze_screenshot(image_path)

        assert result is None
        mock_call.assert_not_called()


# ---------------------------------------------------------------------------
# TestMoonshotProvider — _call_api HTTP 级别
# ---------------------------------------------------------------------------


class TestCallApi:
    """MoonshotProvider._call_api 内部 HTTP 调用行为。"""

    def test_http_error_status_raises(self) -> None:
        """非 2xx 状态码应抛出 RuntimeError。"""
        p = MoonshotProvider(make_config())
        mock_resp = make_mock_response(status_code=500)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_resp

            with pytest.raises(RuntimeError, match="500"):
                p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)

    def test_invalid_json_response_raises(self) -> None:
        """响应的 content 不是有效 JSON 时应抛出 json.JSONDecodeError。"""
        p = MoonshotProvider(make_config())
        mock_resp = make_mock_response(content="not valid json {{{")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_resp

            with pytest.raises(json.JSONDecodeError):
                p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)

    def test_body_json_decode_error_raises(self) -> None:
        """HTTP 响应体本身不是合法 JSON 时 _call_api 应抛出异常。"""
        p = MoonshotProvider(make_config())
        mock_resp = make_mock_response(is_json_error=True)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_resp

            with pytest.raises(json.JSONDecodeError):
                p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)

    def test_no_choices_in_response_raises(self) -> None:
        """响应中无 choices 时应抛出 ValueError。"""
        p = MoonshotProvider(make_config())
        resp = MagicMock(spec=httpx.Response)
        resp.is_success = True
        resp.status_code = 200
        resp.json.return_value = {"choices": [], "usage": {}}

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = resp

            with pytest.raises(ValueError, match="choices"):
                p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)

    def test_empty_content_raises(self) -> None:
        """content 为空时 _call_api 应抛出 ValueError。"""
        p = MoonshotProvider(make_config())
        mock_resp = make_mock_response(content="")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_resp

            with pytest.raises(ValueError, match="content 为空"):
                p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)

    def test_content_is_dict_directly(self) -> None:
        """content 本身是 dict（非字符串）时直接使用。"""
        p = MoonshotProvider(make_config())
        expected = {"direct": "dict"}
        resp_body = {
            "choices": [{"message": {"content": expected}}],
            "usage": {},
        }
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.is_success = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = resp_body

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_resp

            result = p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)

        assert result == expected

    def test_token_usage_logged(self, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
        """token usage 正确记录到日志。"""
        caplog.set_level(logging.INFO, logger="tft_consider.vision.moonshot")
        p = MoonshotProvider(make_config())
        mock_resp = make_mock_response(
            usage={"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_resp

            p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)

        assert "token_usage" in caplog.text
        assert "prompt=200" in caplog.text
        assert "completion=80" in caplog.text
        assert "total=280" in caplog.text

    def test_http_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """HTTP 错误时记录包含 status_code 的日志。"""
        caplog.set_level(logging.ERROR, logger="tft_consider.vision.moonshot")
        p = MoonshotProvider(make_config())
        mock_resp = make_mock_response(status_code=401)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_resp

            try:
                p._call_api({}, {"Authorization": "Bearer xxx"}, attempt=1)
            except RuntimeError:
                pass

        assert "401" in caplog.text


# ---------------------------------------------------------------------------
# TestMoonshotProvider — _encode_image 降采样
# ---------------------------------------------------------------------------


class TestEncodeImage:
    """MoonshotProvider._encode_image 图片编码与降采样。"""

    def test_downscale_when_width_exceeds_threshold(self, tmp_path: Path) -> None:
        """宽度 > 3840 时降采样至 1920x1080。"""
        image_path = create_test_image(tmp_path, width=4000, height=2250)
        p = MoonshotProvider(make_config())

        result = p._encode_image(image_path)

        # 解码 base64 并读回尺寸
        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))
        assert img.width == _DOWNSCALE_WIDTH
        assert img.height == _DOWNSCALE_HEIGHT

    def test_no_downscale_when_width_within_threshold(self, tmp_path: Path) -> None:
        """宽度 <= 3840 时不降采样，保持原始尺寸。"""
        image_path = create_test_image(tmp_path, width=1920, height=1080)
        p = MoonshotProvider(make_config())

        result = p._encode_image(image_path)

        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))
        assert img.width == 1920
        assert img.height == 1080

    def test_no_downscale_exact_threshold(self, tmp_path: Path) -> None:
        """宽度恰好等于 3840 时不降采样（> 3840 才触发）。"""
        image_path = create_test_image(tmp_path, width=3840, height=2160)
        p = MoonshotProvider(make_config())

        result = p._encode_image(image_path)

        decoded = base64.b64decode(result)
        img = Image.open(io.BytesIO(decoded))
        assert img.width == 3840
        assert img.height == 2160

    def test_encode_returns_valid_base64_png(self, tmp_path: Path) -> None:
        """_encode_image 返回有效的 base64 编码 PNG 数据。"""
        image_path = create_test_image(tmp_path, width=100, height=200)
        p = MoonshotProvider(make_config())

        result = p._encode_image(image_path)

        # base64 可解码
        decoded = base64.b64decode(result)
        # 解码后的字节能作为 PNG 打开
        img = Image.open(io.BytesIO(decoded))
        assert img.format == "PNG"
        assert img.size == (100, 200)


# ---------------------------------------------------------------------------
# TestMoonshotProvider — API key 安全
# ---------------------------------------------------------------------------


class TestApiKeySecurity:
    """API key 读取与掩码安全。"""

    def test_get_api_key_base64_decoded(self) -> None:
        """base64 编码的 key 正确解码。"""
        raw_key = "my-secret-api-key-12345"
        encoded = base64.b64encode(raw_key.encode("utf-8")).decode("utf-8")
        config = make_config(api_key=encoded)
        result = get_api_key(config)
        assert result == raw_key

    def test_get_api_key_non_base64_passthrough(self) -> None:
        """非 base64 编码的 key 原样返回。"""
        config = make_config(api_key="plain-text-key")
        result = get_api_key(config)
        assert result == "plain-text-key"

    def test_get_api_key_empty_raises(self) -> None:
        """api.key 为空时抛出 ValueError。"""
        config = make_config(api_key="")
        with pytest.raises(ValueError, match="API key not configured"):
            get_api_key(config)

    def test_get_api_key_missing_raises(self) -> None:
        """api 下缺少 key 字段时抛出 ValueError。"""
        with pytest.raises(ValueError, match="API key not configured"):
            get_api_key({"api": {}})

    def test_mask_key_short(self) -> None:
        """短 key（<=8 字符）掩码返回 '****'。"""
        assert mask_key("12345678") == "****"
        assert mask_key("abc") == "****"

    def test_mask_key_normal(self) -> None:
        """正常 key 掩码：前 4 + **** + 后 4。"""
        masked = mask_key("abcdefghijklmnop")
        assert masked == "abcd****mnop"

    def test_provider_api_key_not_leaked_in_repr(self) -> None:
        """MoonshotProvider 的 repr/str 不应泄露原始 API key。"""
        raw_key = "secret-key-value-here"
        encoded = base64.b64encode(raw_key.encode("utf-8")).decode("utf-8")
        p = MoonshotProvider(make_config(api_key=encoded))

        repr_str = repr(p)
        str_str = str(p)
        assert raw_key not in repr_str
        assert raw_key not in str_str


# ---------------------------------------------------------------------------
# TestPrompts — SYSTEM_PROMPT 内容
# ---------------------------------------------------------------------------


class TestPrompts:
    """SYSTEM_PROMPT 内容完整性。"""

    def test_system_prompt_not_empty(self) -> None:
        """SYSTEM_PROMPT 非空字符串。"""
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_contains_key_fields(self) -> None:
        """SYSTEM_PROMPT 包含所有关键识别字段名。"""
        required_keywords = [
            "level",
            "gold",
            "hp",
            "board",
            "bench",
            "augments",
            "stage",
            "phase",
            "streak",
            "streak_count",
        ]
        for keyword in required_keywords:
            assert keyword in SYSTEM_PROMPT, f"SYSTEM_PROMPT 缺少字段: {keyword}"

    def test_system_prompt_mentions_json(self) -> None:
        """SYSTEM_PROMPT 应明确要求返回 JSON 格式。"""
        assert "JSON" in SYSTEM_PROMPT
        assert "json" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_tft(self) -> None:
        """SYSTEM_PROMPT 应提及云顶之弈。"""
        assert "云顶之弈" in SYSTEM_PROMPT or "TFT" in SYSTEM_PROMPT
