"""多模态 LLM provider 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseProvider(ABC):
    """多模态 LLM provider 抽象基类。"""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    @abstractmethod
    def analyze_screenshot(self, image_path: Path) -> dict[str, Any] | None:
        """分析截图，返回结构化 JSON 或 None（失败时）。

        Args:
            image_path: 截图文件的本地路径。

        Returns:
            结构化识别结果 dict，或 None（识别失败时）。
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """返回 provider 名称，如 'moonshot'。

        Returns:
            Provider 名称字符串。
        """
        ...
