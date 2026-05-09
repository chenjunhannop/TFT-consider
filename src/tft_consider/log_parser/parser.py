"""TFT 游戏日志解析器。

通过读取英雄联盟客户端生成的 GameLogs 日志文件，检测回合阶段切换事件。
如果日志格式不可解析，所有方法安全返回 None/空列表，
调用方应降级为固定间隔截屏 + LLM 判断阶段。
"""

from __future__ import annotations

import dataclasses
import enum
import logging
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# 常见 LoL 安装盘符（Windows）
_COMMON_DRIVES: Final[tuple[str, ...]] = ("C:", "D:", "E:", "F:", "G:")

# LoL 安装路径下 GameLogs 的相对路径
_LOL_LOG_SUFFIX: Final[str] = "Riot Games/League of Legends/Logs/GameLogs"


# ---------------------------------------------------------------------------
# 枚举与数据结构
# ---------------------------------------------------------------------------

class GamePhase(enum.Enum):
    """游戏回合阶段。"""

    PLANNING = "planning"
    COMBAT = "combat"
    CAROUSEL = "carousel"
    UNKNOWN = "unknown"


@dataclasses.dataclass
class PhaseEvent:
    """阶段切换事件。

    Attributes:
        phase: 检测到的游戏阶段。
        timestamp: 检测时的 Unix 时间戳。
        raw_line: 匹配的原始日志行（调试用）。
        stage: 回合编号，如 "3-1"。
    """

    phase: GamePhase
    timestamp: float
    raw_line: str
    stage: str | None = None


# ---------------------------------------------------------------------------
# 默认正则规则
# ---------------------------------------------------------------------------

DEFAULT_PATTERNS: Final[dict[str, str]] = {
    "planning_start": (
        r"(?i).*?(?:GamePhase|phase|stage)"
        r".*?(?:planning|prep|ready|planning_start).*"
    ),
    "combat_end": (
        r"(?i).*?(?:GamePhase|phase|stage)"
        r".*?(?:combat_end|fight_end|battle_end|combat.*end).*"
    ),
    "stage_info": (
        r"(?i).*?(?:stage|round).*?(\d+[-_]\d+).*"
    ),
}

# ---------------------------------------------------------------------------
# LogParser
# ---------------------------------------------------------------------------


class LogParser:
    """游戏日志解析器。

    尾随 LoL GameLogs 目录下的日志文件，通过正则匹配检测回合阶段切换。
    所有公开方法在出错时安全返回，不抛异常。
    """

    def __init__(
        self,
        log_dir: str | None = None,
        patterns: dict[str, str] | None = None,
    ) -> None:
        """初始化解析器。

        Args:
            log_dir: 显式指定日志目录路径；为 None 时自动检测。
            patterns: 覆写或扩展默认正则规则。键与 DEFAULT_PATTERNS 相同。
        """
        self._log_dir: Path | None = Path(log_dir) if log_dir else None
        merged = {**DEFAULT_PATTERNS, **(patterns or {})}
        self._patterns: dict[str, str] = merged
        self._compiled: dict[str, re.Pattern[str]] = {}
        self._last_event: PhaseEvent | None = None
        self._monitor_thread: threading.Thread | None = None
        self._stop_monitor = threading.Event()

        for name, pattern in self._patterns.items():
            try:
                self._compiled[name] = re.compile(pattern)
            except re.error as exc:
                logger.warning("Invalid regex for '%s': %s", name, exc)

    # ---- 公开属性 ----

    @property
    def log_dir(self) -> Path | None:
        """当前使用的日志目录。"""
        return self._log_dir

    @property
    def is_monitoring(self) -> bool:
        """后台监控是否正在运行。"""
        return self._monitor_thread is not None and self._monitor_thread.is_alive()

    # ---- 日志目录检测 ----

    def find_log_dir(self) -> Path | None:
        """自动检测 LoL GameLogs 目录。

        扫描常见 Windows 盘符，查找 ``Riot Games/League of Legends/Logs/GameLogs``，
        返回其中最新修改的目录。支持中英文路径。

        Returns:
            GameLogs 目录路径，未找到则返回 None。
        """
        if self._log_dir is not None and self._log_dir.exists():
            return self._log_dir

        candidates: list[tuple[Path, float]] = []

        for drive in _COMMON_DRIVES:
            candidate = Path(drive) / _LOL_LOG_SUFFIX
            if not candidate.is_dir():
                continue
            try:
                newest = 0.0
                for entry in candidate.iterdir():
                    if entry.is_file():
                        mtime = entry.stat().st_mtime
                        if mtime > newest:
                            newest = mtime
                if newest > 0:
                    candidates.append((candidate, newest))
            except OSError:
                continue

        if not candidates:
            logger.debug("No LoL GameLogs directory found on common drives.")
            return None

        candidates.sort(key=lambda item: item[1], reverse=True)
        found = candidates[0][0]
        logger.info("Found GameLogs directory: %s", found)
        self._log_dir = found
        return found

    # ---- 文件读取 ----

    def _latest_log_file(self) -> Path | None:
        """返回日志目录下最新修改的 .txt 文件。"""
        log_dir = self._log_dir or self.find_log_dir()
        if log_dir is None or not log_dir.is_dir():
            return None
        try:
            files = [f for f in log_dir.iterdir() if f.is_file() and f.suffix == ".txt"]
            if not files:
                logger.debug("No .txt files in %s", log_dir)
                return None
            return max(files, key=lambda f: f.stat().st_mtime)
        except OSError as exc:
            logger.warning("Failed to list log files in %s: %s", log_dir, exc)
            return None

    def tail(self, lines: int = 50) -> list[str]:
        """读取日志文件最近 N 行。

        自动定位最新日志文件，读取末尾指定行数。

        Args:
            lines: 要读取的行数，默认 50。

        Returns:
            日志行列表（按文件顺序）；无法读取时返回空列表。
        """
        log_file = self._latest_log_file()
        if log_file is None:
            return []
        try:
            with open(log_file, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:
            logger.warning("Failed to read log file %s: %s", log_file, exc)
            return []

        all_lines = content.splitlines()
        if len(all_lines) <= lines:
            return all_lines
        return all_lines[-lines:]

    # ---- 行解析 ----

    def parse_line(self, line: str) -> PhaseEvent | None:
        """解析单行日志，检测阶段事件。

        依次尝试 compiled patterns 中的 "planning_start" 和 "combat_end"。
        匹配成功时附带 stage_info 提取的回合编号（如 "3-1"）。

        Args:
            line: 单行日志文本。

        Returns:
            匹配到的 PhaseEvent，否则 None。
        """
        stripped = line.strip()
        if not stripped:
            return None

        # 提取回合信息
        stage: str | None = None
        stage_re = self._compiled.get("stage_info")
        if stage_re is not None:
            m = stage_re.search(stripped)
            if m:
                stage = m.group(1).replace("_", "-")

        # 准备阶段开始
        plan_re = self._compiled.get("planning_start")
        if plan_re is not None and plan_re.search(stripped):
            event = PhaseEvent(
                phase=GamePhase.PLANNING,
                timestamp=time.time(),
                raw_line=stripped,
                stage=stage,
            )
            logger.debug("Detected planning start, stage=%s", stage)
            return event

        # 战斗阶段结束
        combat_re = self._compiled.get("combat_end")
        if combat_re is not None and combat_re.search(stripped):
            event = PhaseEvent(
                phase=GamePhase.COMBAT,
                timestamp=time.time(),
                raw_line=stripped,
                stage=stage,
            )
            logger.debug("Detected combat end, stage=%s", stage)
            return event

        return None

    # ---- 阶段检测 ----

    def detect_phase(self) -> PhaseEvent | None:
        """尾随日志文件并返回最新阶段事件。

        从最新到最旧扫描最近 N 行日志，返回第一个匹配的事件。
        如果匹配到的事件与上次相同（同 phase、同 stage），返回 None
        以支持去重轮询。

        Returns:
            新的 PhaseEvent；无新事件或无匹配时返回 None。
        """
        log_lines = self.tail(lines=50)
        if not log_lines:
            logger.debug("No log lines available for phase detection.")
            return None

        for line in reversed(log_lines):
            event = self.parse_line(line)
            if event is None:
                continue
            # 与上次事件比较：phase 或 stage 变化时才返回
            if self._last_event is None:
                self._last_event = event
                return event
            if event.phase != self._last_event.phase or event.stage != self._last_event.stage:
                self._last_event = event
                return event
            return None

        return None

    # ---- 后台监控 ----

    def start_monitoring(
        self,
        callback: Callable[[PhaseEvent], None],
        interval: float = 2.0,
    ) -> None:
        """启动后台监控线程。

        定期尾随日志文件，检测到阶段变化时调用 *callback*。
        线程为 daemon，随主进程退出而终止。

        Args:
            callback: 接收 PhaseEvent 的回调函数。
            interval: 轮询间隔（秒），默认 2.0。
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            logger.warning("Monitor thread is already running.")
            return

        self._stop_monitor.clear()

        def _loop() -> None:
            logger.info("Log monitor started, interval=%.1fs", interval)
            while not self._stop_monitor.is_set():
                try:
                    event = self.detect_phase()
                    if event is not None:
                        callback(event)
                except Exception:
                    logger.exception("Unexpected error in monitor loop.")
                self._stop_monitor.wait(interval)
            logger.info("Log monitor stopped.")

        self._monitor_thread = threading.Thread(
            target=_loop,
            daemon=True,
            name="tft-log-monitor",
        )
        self._monitor_thread.start()

    def stop_monitoring(self, timeout: float = 5.0) -> None:
        """停止后台监控线程。

        Args:
            timeout: 等待线程退出的最大秒数，默认 5.0。
        """
        if self._monitor_thread is None:
            return
        self._stop_monitor.set()
        self._monitor_thread.join(timeout=timeout)
        if self._monitor_thread.is_alive():
            logger.warning("Monitor thread did not stop within %.1fs.", timeout)
        self._monitor_thread = None
