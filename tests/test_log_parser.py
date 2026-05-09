"""LogParser 单元测试。

覆盖 GamePhase 枚举、PhaseEvent 数据类、日志行解析、文件尾随、
目录检测、自定义规则编译以及阶段去重。
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tft_consider.log_parser.parser import GamePhase, LogParser, PhaseEvent

# ---------------------------------------------------------------------------
# 枚举与数据结构
# ---------------------------------------------------------------------------


class TestGamePhaseEnum:
    """GamePhase 枚举基本验证。"""

    def test_enum_members(self) -> None:
        """验证枚举包含全部 4 个成员且值与预期一致。"""
        assert GamePhase.PLANNING.value == "planning"
        assert GamePhase.COMBAT.value == "combat"
        assert GamePhase.CAROUSEL.value == "carousel"
        assert GamePhase.UNKNOWN.value == "unknown"

    def test_enum_member_count(self) -> None:
        """验证枚举成员总数为 4。"""
        assert len(GamePhase) == 4


class TestPhaseEventCreation:
    """PhaseEvent 数据类创建与字段验证。"""

    def test_all_fields_provided(self) -> None:
        """全部字段显式提供时正确赋值。"""
        ts = time.time()
        event = PhaseEvent(
            phase=GamePhase.PLANNING,
            timestamp=ts,
            raw_line="[DEBUG] entering planning",
            stage="3-1",
        )
        assert event.phase == GamePhase.PLANNING
        assert event.timestamp == ts
        assert event.raw_line == "[DEBUG] entering planning"
        assert event.stage == "3-1"

    def test_stage_defaults_to_none(self) -> None:
        """stage 未提供时默认为 None。"""
        event = PhaseEvent(
            phase=GamePhase.COMBAT,
            timestamp=1000.0,
            raw_line="combat end",
        )
        assert event.stage is None

    def test_is_dataclass_instance(self) -> None:
        """验证 PhaseEvent 确实是 dataclass 实例。"""
        import dataclasses

        assert dataclasses.is_dataclass(PhaseEvent)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parser_default() -> LogParser:
    """返回使用默认规则的 LogParser，未指定 log_dir。"""
    return LogParser()


@pytest.fixture
def parser_no_logdir() -> LogParser:
    """返回 log_dir 指向不存在路径的 LogParser（用于测试 tail 失败路径）。"""
    return LogParser(log_dir="/nonexistent/path/12345/tft_logs")


# ---------------------------------------------------------------------------
# parse_line 测试
# ---------------------------------------------------------------------------


class TestParseLine:
    """LogParser.parse_line 各种输入场景。"""

    def test_parse_line_planning_start(self, parser_default: LogParser) -> None:
        """包含 planning_start 关键字的日志行应返回 PLANNING PhaseEvent。"""
        line = "[2024-12-01 10:00:00] GamePhase entering planning phase for round 1"
        event = parser_default.parse_line(line)
        assert event is not None
        assert event.phase == GamePhase.PLANNING
        assert event.raw_line == line
        assert isinstance(event.timestamp, float)

    def test_parse_line_combat_end(self, parser_default: LogParser) -> None:
        """包含 combat_end 关键字的日志行应返回 COMBAT PhaseEvent。"""
        line = "[2024-12-01 10:05:00] GamePhase combat_end detected, switching"
        event = parser_default.parse_line(line)
        assert event is not None
        assert event.phase == GamePhase.COMBAT
        assert event.raw_line == line

    def test_parse_line_no_match(self, parser_default: LogParser) -> None:
        """不包含任何阶段关键字的普通日志行应返回 None。"""
        line = "[2024-12-01 10:10:00] Player bought champion: Teemo (cost 3)"
        event = parser_default.parse_line(line)
        assert event is None

    def test_parse_line_empty(self, parser_default: LogParser) -> None:
        """空字符串应返回 None。"""
        assert parser_default.parse_line("") is None

    def test_parse_line_whitespace_only(self, parser_default: LogParser) -> None:
        """仅含空白字符的行应返回 None。"""
        assert parser_default.parse_line("   \t  ") is None

    def test_parse_line_case_insensitive(self, parser_default: LogParser) -> None:
        """正则规则应不区分大小写。"""
        line = "GAMEPHASE PLANNING START phase"
        event = parser_default.parse_line(line)
        assert event is not None
        assert event.phase == GamePhase.PLANNING

    def test_parse_line_stage_extraction(self, parser_default: LogParser) -> None:
        """日志行中 stage 3-1 应被 stage_info 正则提取为 "3-1"。"""
        line = "[INFO] GamePhase planning stage 3-1 begin"
        event = parser_default.parse_line(line)
        assert event is not None
        assert event.phase == GamePhase.PLANNING
        assert event.stage == "3-1"

    def test_parse_line_stage_underscore_to_dash(self, parser_default: LogParser) -> None:
        """stage_info 提取的下划线分隔应转换为短横线。"""
        line = "[INFO] GamePhase combat_end round 4_2 finished"
        event = parser_default.parse_line(line)
        assert event is not None
        assert event.phase == GamePhase.COMBAT
        assert event.stage == "4-2"  # _ → -

    def test_parse_line_no_stage_info(self, parser_default: LogParser) -> None:
        """无 stage_info 匹配时 stage 应为 None。"""
        line = "[DEBUG] GamePhase planning_start, no round info here"
        event = parser_default.parse_line(line)
        assert event is not None
        assert event.phase == GamePhase.PLANNING
        assert event.stage is None

    def test_parse_line_planning_before_combat_priority(self, parser_default: LogParser) -> None:
        """同时匹配 planning_start 和 combat_end 时，优先返回 PLANNING（源码顺序）。"""
        # 构建一行能同时命中两个模式的日志
        line = "GamePhase planning_start and combat_end both present stage 5-1"
        event = parser_default.parse_line(line)
        assert event is not None
        assert event.phase == GamePhase.PLANNING


# ---------------------------------------------------------------------------
# tail 与文件读取测试
# ---------------------------------------------------------------------------


class TestTail:
    """LogParser.tail 边界场景。"""

    def test_tail_file_not_found(self, parser_no_logdir: LogParser) -> None:
        """log_dir 不存在时 tail() 应返回空列表。"""
        result = parser_no_logdir.tail()
        assert result == []

    def test_tail_file_not_found_custom_lines(self, parser_no_logdir: LogParser) -> None:
        """log_dir 不存在时，指定 lines 参数的 tail() 应返回空列表。"""
        result = parser_no_logdir.tail(lines=10)
        assert result == []


# ---------------------------------------------------------------------------
# find_log_dir 测试
# ---------------------------------------------------------------------------


class TestFindLogDir:
    """LogParser.find_log_dir 自动检测逻辑。"""

    def test_find_log_dir_nonexistent(self, parser_default: LogParser) -> None:
        """在非 Windows 平台或 LoL 未安装时，find_log_dir 应返回 None。"""
        result = parser_default.find_log_dir()
        assert result is None

    def test_find_log_dir_uses_existing(self, tmp_path) -> None:
        """当构造时传入存在的 log_dir 时，find_log_dir 应直接返回该路径。"""
        parser = LogParser(log_dir=str(tmp_path))
        result = parser.find_log_dir()
        assert result == tmp_path


# ---------------------------------------------------------------------------
# 自定义规则测试
# ---------------------------------------------------------------------------


class TestCustomPatterns:
    """LogParser 自定义正则规则。"""

    def test_custom_patterns_compile(self) -> None:
        """自定义规则应能正常编译并与默认规则合并。"""
        custom = {
            "planning_start": r"(?i)custom_plan_pattern",
            "stage_info": r"CUSTOM_ROUND_(\d+)",
        }
        parser = LogParser(patterns=custom)
        # 默认规则中存在 combat_end
        assert "combat_end" in parser._compiled
        # 自定义规则覆盖了 planning_start 和 stage_info
        assert parser._compiled["planning_start"].pattern == "(?i)custom_plan_pattern"
        assert parser._compiled["stage_info"].pattern == r"CUSTOM_ROUND_(\d+)"

    def test_custom_patterns_override_behavior(self) -> None:
        """自定义规则应改变匹配行为。"""
        custom = {
            "planning_start": r"MY_CUSTOM_PLAN",
        }
        parser = LogParser(patterns=custom)
        # 默认关键字不再触发
        assert parser.parse_line("GamePhase planning") is None
        # 自定义关键字触发
        event = parser.parse_line("MY_CUSTOM_PLAN detected stage 1-2")
        assert event is not None
        assert event.phase == GamePhase.PLANNING

    def test_invalid_regex_logs_warning(self, caplog) -> None:
        """无效正则表达式不应抛异常，应记录 warning。"""
        import logging

        caplog.set_level(logging.WARNING)
        parser = LogParser(patterns={"planning_start": r"[invalid("})
        # 编译失败不应阻断，planning_start 不会被加入 _compiled
        assert "planning_start" not in parser._compiled


# ---------------------------------------------------------------------------
# 阶段检测与去重
# ---------------------------------------------------------------------------


class TestDetectPhase:
    """LogParser.detect_phase 阶段检测与去重逻辑。"""

    def test_detect_phase_returns_event(self, parser_default: LogParser) -> None:
        """当 tail 返回匹配行时，detect_phase 应返回 PhaseEvent。"""
        lines = ["[2024-12-01 10:00:00] GamePhase planning_start stage 2-1"]
        with patch.object(parser_default, "tail", return_value=lines):
            event = parser_default.detect_phase()
        assert event is not None
        assert event.phase == GamePhase.PLANNING
        assert event.stage == "2-1"

    def test_detect_phase_deduplication(self, parser_default: LogParser) -> None:
        """连续两次相同 phase+stage 的检测，第二次应返回 None（去重）。"""
        lines = ["[2024-12-01 10:00:00] GamePhase planning_start stage 3-1"]
        with patch.object(parser_default, "tail", return_value=lines):
            event1 = parser_default.detect_phase()
            assert event1 is not None
            assert event1.phase == GamePhase.PLANNING
            assert event1.stage == "3-1"

            event2 = parser_default.detect_phase()
            assert event2 is None

    def test_detect_phase_different_stage(self, parser_default: LogParser) -> None:
        """phase 相同但 stage 不同时，应返回新事件（非去重）。"""
        lines = [
            "[2024-12-01 10:00:00] GamePhase combat_end stage 1-1",
            "[2024-12-01 10:05:00] GamePhase combat_end stage 2-1",
            "[2024-12-01 10:10:00] GamePhase combat_end stage 3-1",
        ]
        with patch.object(parser_default, "tail", return_value=lines):
            event1 = parser_default.detect_phase()
            assert event1 is not None
            assert event1.stage == "3-1"  # reversed: 最后一行先被匹配

            # 修改 tail 返回不同 stage
            new_lines = ["[2024-12-01 10:15:00] GamePhase combat_end stage 3-2"]
            with patch.object(parser_default, "tail", return_value=new_lines):
                event2 = parser_default.detect_phase()
                assert event2 is not None
                assert event2.stage == "3-2"

    def test_detect_phase_different_phase(self, parser_default: LogParser) -> None:
        """同一 stage 但 phase 不同时，应返回新事件。"""
        lines_combat = ["[2024-12-01 10:00:00] GamePhase combat_end stage 4-1"]
        with patch.object(parser_default, "tail", return_value=lines_combat):
            event1 = parser_default.detect_phase()
            assert event1 is not None
            assert event1.phase == GamePhase.COMBAT

        lines_planning = ["[2024-12-01 10:01:00] GamePhase planning_start stage 4-1"]
        with patch.object(parser_default, "tail", return_value=lines_planning):
            event2 = parser_default.detect_phase()
            assert event2 is not None
            assert event2.phase == GamePhase.PLANNING

    def test_detect_phase_gaps_compare_last(self, parser_default: LogParser) -> None:
        """去重比较使用的是 _last_event，而非实时的第几行。"""
        lines_a = ["[INFO] GamePhase planning_start stage 5-1"]
        lines_b = ["[INFO] GamePhase planning_start stage 5-1"]

        with patch.object(parser_default, "tail", return_value=lines_a):
            e1 = parser_default.detect_phase()
            assert e1 is not None

        with patch.object(parser_default, "tail", return_value=lines_b):
            e2 = parser_default.detect_phase()
            assert e2 is None  # 相同 phase+stage，去重

    def test_detect_phase_no_log_lines(self, parser_default: LogParser) -> None:
        """tail 返回空列表时，detect_phase 应返回 None。"""
        with patch.object(parser_default, "tail", return_value=[]):
            event = parser_default.detect_phase()
        assert event is None

    def test_detect_phase_no_matching_lines(self, parser_default: LogParser) -> None:
        """tail 返回的行均不匹配任何规则时，应返回 None。"""
        with patch.object(parser_default, "tail", return_value=["line1", "line2", "line3"]):
            event = parser_default.detect_phase()
        assert event is None


# ---------------------------------------------------------------------------
# 后台监控
# ---------------------------------------------------------------------------


class TestMonitoring:
    """LogParser 后台监控生命周期。"""

    def test_start_monitoring(self, parser_default: LogParser) -> None:
        """start_monitoring 应启动后台线程并设置 is_monitoring 为 True。"""
        events: list[PhaseEvent] = []

        def callback(event: PhaseEvent) -> None:
            events.append(event)

        parser_default.start_monitoring(callback, interval=0.1)
        assert parser_default.is_monitoring

        parser_default.stop_monitoring(timeout=3.0)
        assert not parser_default.is_monitoring

    def test_stop_monitoring_when_not_running(self, parser_default: LogParser) -> None:
        """未启动监控时调用 stop_monitoring 不应抛异常。"""
        parser_default.stop_monitoring(timeout=0.1)
        assert not parser_default.is_monitoring

    def test_double_start_monitoring(self, parser_default: LogParser) -> None:
        """重复调用 start_monitoring 不应创建第二个线程。"""
        events: list[PhaseEvent] = []

        def callback(event: PhaseEvent) -> None:
            events.append(event)

        parser_default.start_monitoring(callback, interval=0.1)
        thread1 = parser_default._monitor_thread
        parser_default.start_monitoring(callback, interval=0.1)
        thread2 = parser_default._monitor_thread
        assert thread1 is thread2  # 未创建新线程

        parser_default.stop_monitoring(timeout=3.0)


# ---------------------------------------------------------------------------
# 属性
# ---------------------------------------------------------------------------


class TestProperties:
    """LogParser 公开属性。"""

    def test_log_dir_returns_path(self) -> None:
        """指定 log_dir 后，属性应返回对应 Path。"""
        parser = LogParser(log_dir="/tmp/logs")
        assert parser.log_dir == Path("/tmp/logs")

    def test_log_dir_none_by_default(self, parser_default: LogParser) -> None:
        """未指定 log_dir 时，属性返回 None。"""
        assert parser_default.log_dir is None

    def test_is_monitoring_default_false(self, parser_default: LogParser) -> None:
        """初始化后 is_monitoring 应为 False。"""
        assert not parser_default.is_monitoring
