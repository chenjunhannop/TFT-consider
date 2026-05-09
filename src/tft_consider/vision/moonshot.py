"""Moonshot (Kimi K2.6) 多模态识别 provider。

通过 Moonshot API 的 OpenAI 兼容接口调用 Kimi K2.6 vision 模型，
对云顶之弈游戏截图进行结构化内容识别。
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from tft_consider.config import get_api_key
from tft_consider.vision.base import BaseProvider
from tft_consider.vision.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MOONSHOT_API_URL = "https://api.moonshot.cn/v1/chat/completions"
_4K_WIDTH_THRESHOLD = 3840
_DOWNSCALE_WIDTH = 1920
_DOWNSCALE_HEIGHT = 1080
_DEFAULT_MODEL = "kimi-k2-0719-preview"
_MAX_RETRIES = 2  # 首次 + 1 次重试


class MoonshotProvider(BaseProvider):
    """Moonshot (Kimi K2.6) 多模态识别 provider。

    通过 HTTP POST 向 Moonshot API 发送 base64 编码的截图，
    获取结构化的云顶之弈游戏状态 JSON。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化 Moonshot provider。

        Args:
            config: 应用配置字典，需包含 api.key 和 api.model 项。
        """
        super().__init__(config)
        self._api_key = get_api_key(config)
        api_cfg = config.get("api", {})
        if isinstance(api_cfg, dict):
            self._model: str = str(api_cfg.get("model", _DEFAULT_MODEL))
        else:
            self._model = _DEFAULT_MODEL

    def provider_name(self) -> str:
        """返回 provider 名称。

        Returns:
            固定返回 'moonshot'。
        """
        return "moonshot"

    def analyze_screenshot(self, image_path: Path) -> dict[str, Any] | None:
        """分析截图，调用 Moonshot API 进行多模态识别。

        流程：
        1. 读取图片，若宽度超过 4K 阈值则降采样。
        2. 将图片编码为 base64 data URI。
        3. 发送 HTTP POST 请求到 Moonshot API。
        4. 解析响应中的 JSON 内容。
        5. 失败时自动重试 1 次。

        Args:
            image_path: 截图文件的本地路径。

        Returns:
            结构化识别结果 dict，失败时返回 None。
        """
        if not image_path.exists():
            logger.error("截图文件不存在: %s", image_path)
            return None

        # 1. 读取并预处理图片
        try:
            b64_data = self._encode_image(image_path)
        except Exception:
            logger.exception("图片编码失败: %s", image_path)
            return None

        # 2. 构建请求体
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_data}"},
                        },
                        {
                            "type": "text",
                            "text": "请分析这张云顶之弈游戏截图，提取所有关键信息。",
                        },
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # 3. 发送请求（含重试）
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self._call_api(payload, headers, attempt)
            except Exception as exc:
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "Moonshot API 调用失败 (attempt %d/%d)，准备重试: %s",
                        attempt, _MAX_RETRIES, exc,
                    )
                else:
                    logger.error(
                        "Moonshot API 调用失败，已达最大重试次数 (%d): %s",
                        _MAX_RETRIES, exc,
                    )

        return None

    # --- 内部实现 ------------------------------------------------------------

    def _encode_image(self, image_path: Path) -> str:
        """读取图片并编码为 base64 字符串。

        若图片宽度超过 4K 阈值 (3840px)，先降采样到 1920x1080。

        Args:
            image_path: 图片文件路径。

        Returns:
            base64 编码的图片数据字符串。
        """
        img: Image.Image = Image.open(image_path)
        if img.width > _4K_WIDTH_THRESHOLD:
            logger.info(
                "图片宽度 %d 超过 4K 阈值，降采样到 %dx%d",
                img.width, _DOWNSCALE_WIDTH, _DOWNSCALE_HEIGHT,
            )
            img = img.resize((_DOWNSCALE_WIDTH, _DOWNSCALE_HEIGHT), Image.LANCZOS)  # type: ignore[attr-defined]

        # 将图片转为 PNG 字节流再 base64 编码
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()
        return base64.b64encode(img_bytes).decode("utf-8")

    def _call_api(
        self, payload: dict[str, Any], headers: dict[str, str], attempt: int,
    ) -> dict[str, Any] | None:
        """发送 HTTP 请求并解析响应。

        Args:
            payload: JSON 请求体。
            headers: HTTP 请求头。
            attempt: 当前尝试次数（用于日志）。

        Returns:
            解析后的识别结果 dict，失败时抛出异常。
        """
        start_time = time.monotonic()

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(MOONSHOT_API_URL, json=payload, headers=headers)
        except httpx.HTTPError:
            logger.exception("Moonshot API HTTP 请求失败 (attempt %d)", attempt)
            raise

        elapsed_ms = (time.monotonic() - start_time) * 1000

        if not response.is_success:
            logger.error(
                "Moonshot API 返回非成功状态码: %d (attempt %d), body=%s",
                response.status_code, attempt, response.text[:500],
            )
            raise RuntimeError(f"Moonshot API 返回 {response.status_code}")

        # 解析 JSON 响应
        try:
            resp_data: dict[str, Any] = response.json()
        except json.JSONDecodeError:
            logger.exception("Moonshot API 响应 JSON 解析失败 (attempt %d)", attempt)
            raise

        # 提取 token usage
        usage = resp_data.get("usage", {})
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            logger.info(
                "Moonshot token_usage: prompt=%d, completion=%d, total=%d, latency_ms=%.0f",
                prompt_tokens, completion_tokens, total_tokens, elapsed_ms,
            )

        # 提取 choices[0].message.content
        choices = resp_data.get("choices", [])
        if not choices:
            logger.error("Moonshot API 响应中没有 choices (attempt %d)", attempt)
            raise ValueError("API 响应中没有 choices")

        choice = choices[0]
        message = choice.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", "")
        else:
            content = ""

        if not content:
            logger.error("Moonshot API 响应 content 为空 (attempt %d)", attempt)
            raise ValueError("API 响应 content 为空")

        # 将 content 文本解析为 dict
        if isinstance(content, str):
            try:
                result: dict[str, Any] = json.loads(content)
            except json.JSONDecodeError:
                logger.exception("Moonshot 返回的 content 不是有效 JSON (attempt %d): %s", attempt, content[:500])
                raise
        elif isinstance(content, dict):
            result = content
        else:
            logger.error("Moonshot content 类型异常: %s (attempt %d)", type(content), attempt)
            raise TypeError(f"content 类型异常: {type(content)}")

        logger.info("Moonshot 识别完成, latency_ms=%.0f", elapsed_ms)
        return result
