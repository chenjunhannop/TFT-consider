"""定时同步调度器。

管理 meta 数据的自动同步计划，使用 threading.Timer 实现定时调度。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from tft_consider.crawler.tactics_tools import TacticsToolsCrawler

logger = logging.getLogger(__name__)


class SyncScheduler:
    """定时同步调度器。

    使用 threading.Timer 按配置的间隔自动同步外部 meta 数据到本地数据库。
    同步采用 best-effort 策略：失败时记录 ERROR 日志但不崩溃。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """初始化调度器。

        Args:
            config: 应用配置字典。
        """
        self._config = config
        self._crawler = TacticsToolsCrawler(config)
        data_cfg = config.get("data", {})
        if isinstance(data_cfg, dict):
            self._interval_hours: float = float(data_cfg.get("sync_interval_hours", 6))
        else:
            self._interval_hours = 6.0
        self._timer: threading.Timer | None = None
        self._running = False

    def sync_now(self) -> bool:
        """立即执行一次完整同步。

        Returns:
            True 表示同步成功（至少有一个阵容被合并），False 表示同步失败。
        """
        logger.info("开始手动同步 meta 数据...")
        try:
            comps = self._crawler.fetch_meta_comps()
            if comps is None:
                logger.warning("爬取 meta 数据失败：未获取到阵容数据")
                return False

            merged = self._crawler.merge_to_database(comps)
            logger.info("同步完成：合并 %d 个阵容", merged)
            return merged > 0
        except Exception:
            logger.exception("同步过程中发生未预期错误")
            return False

    def start(self) -> None:
        """启动定时同步。

        设置定时器，按 data.sync_interval_hours 配置的间隔自动同步。
        如果 interval_hours <= 0，则不启动定时器。
        """
        if self._running:
            return

        if self._interval_hours <= 0:
            logger.info("sync_interval_hours <= 0，跳过定时同步")
            return

        self._running = True
        self._schedule_next()
        logger.info("定时同步已启动，间隔 %.1f 小时", self._interval_hours)

    def stop(self) -> None:
        """停止定时同步，取消待执行的定时器。"""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
            logger.info("定时同步已停止")

    def _schedule_next(self) -> None:
        """安排下一次同步。"""
        if not self._running:
            return

        interval_seconds = self._interval_hours * 3600
        self._timer = threading.Timer(interval_seconds, self._on_timer)
        self._timer.daemon = True
        self._timer.start()

    def _on_timer(self) -> None:
        """定时器回调：执行同步并安排下一次。"""
        try:
            self.sync_now()
        finally:
            if self._running:
                self._schedule_next()
