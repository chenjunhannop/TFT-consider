"""追踪模块 (game_state + replay + pipeline) 单元测试。

覆盖 GameStateSnapshot、GameState、save_replay/list_replays、
AdvicePipeline 以及 GameReplay ORM 模型。
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Engine, event, inspect, select

from tft_consider.database import models
from tft_consider.database.models import GameReplay, get_session, init_db
from tft_consider.tracker.game_state import GameState, GameStateSnapshot, _extract_names
from tft_consider.tracker.replay import list_replays, save_replay
from tft_consider.vision.base import BaseProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Generator[models.Session, None, None]:
    """每个测试使用独立的 :memory: 数据库。"""
    event.listen(Engine, "connect", lambda dbapi_conn, _rec: dbapi_conn.execute("PRAGMA foreign_keys = ON"))
    init_db(":memory:")
    yield get_session()
    if models._engine is not None:
        models._engine.dispose()
    models._engine = None
    models._SessionLocal = None


@pytest.fixture
def sample_game_state_dict() -> dict[str, Any]:
    """构造一个标准的游戏状态字典。"""
    return {
        "level": 6,
        "gold": 45,
        "hp": 72,
        "stage": "3-2",
        "phase": "planning",
        "streak": "win",
        "streak_count": 3,
        "board": [
            {"name": "盖伦", "star": 2, "items": ["狂徒铠甲"]},
            {"name": "薇古丝", "star": 1, "items": []},
            {"name": "拉克丝", "star": 2, "items": ["蓝霸符"]},
            {"name": "安妮", "star": 1, "items": []},
        ],
        "bench": [
            {"name": "波比", "star": 1},
            {"name": "艾希", "star": 1},
        ],
        "items": ["无尽之刃"],
        "augments": [],
    }


@pytest.fixture
def suggestions_dict() -> dict[str, Any]:
    """构造一个标准的 LLM 建议字典。"""
    return {
        "recommended_comps": [
            {
                "name": "八法师",
                "confidence": 85,
                "reason": "持有多个法师棋子",
                "core_champs_missing": ["瑞兹", "辛德拉"],
            }
        ],
        "action_advice": {
            "level": "slow_level",
            "roll": "roll_interest",
            "positioning": "standard",
        },
        "next_steps": ["升级到8级", "搜索瑞兹"],
    }


@pytest.fixture
def mock_provider() -> MagicMock:
    """提供一个 mock 的 BaseProvider 实例。"""
    provider = MagicMock(spec=BaseProvider)
    provider.provider_name.return_value = "moonshot"
    return provider


@pytest.fixture
def pipeline_config() -> dict[str, Any]:
    """构造 AdvicePipeline 所需的最小配置。"""
    return {
        "api": {
            "provider": "moonshot",
            "key": "dummy-test-key",
            "model": "kimi-k2-0719-preview",
        },
    }


# ---------------------------------------------------------------------------
# _extract_names helper
# ---------------------------------------------------------------------------


class TestExtractNames:
    """_extract_names 辅助函数测试。"""

    def test_extract_names_from_list_of_dicts(self) -> None:
        """从包含 name 键的 dict 列表中提取名称。"""
        units: list[dict[str, Any]] = [
            {"name": "盖伦", "star": 2},
            {"name": "拉克丝", "star": 1},
            {"name": "", "star": 1},  # 空名称应被忽略
            {"star": 1},  # 没有 name 键
        ]
        names = _extract_names(units)
        assert names == ["盖伦", "拉克丝"]

    def test_extract_names_empty_list(self) -> None:
        """空列表返回空列表。"""
        assert _extract_names([]) == []

    def test_extract_names_ignores_non_dict(self) -> None:
        """非 dict 元素被跳过。"""
        units: list[Any] = ["string", 123, None, {"name": "盖伦"}]
        names = _extract_names(units)
        assert names == ["盖伦"]


# ---------------------------------------------------------------------------
# GameStateSnapshot
# ---------------------------------------------------------------------------


class TestGameStateSnapshot:
    """GameStateSnapshot dataclass 测试。"""

    def test_all_fields_exist_and_have_correct_types(self) -> None:
        """验证所有字段存在且类型正确。"""
        snapshot = GameStateSnapshot(
            stage="1-1",
            phase="planning",
            level=1,
            gold=0,
            hp=100,
            board=[],
            bench=[],
            augments=[],
            streak="none",
            streak_count=0,
            suggestions=None,
            created_at=datetime.now(UTC),
        )
        assert snapshot.stage == "1-1"
        assert snapshot.phase == "planning"
        assert isinstance(snapshot.level, int)
        assert isinstance(snapshot.gold, int)
        assert isinstance(snapshot.hp, int)
        assert isinstance(snapshot.board, list)
        assert isinstance(snapshot.bench, list)
        assert isinstance(snapshot.augments, list)
        assert isinstance(snapshot.streak, str)
        assert isinstance(snapshot.streak_count, int)
        assert snapshot.suggestions is None
        assert isinstance(snapshot.created_at, datetime)

    def test_created_at_is_utc_aware(self) -> None:
        """created_at 为 UTC aware datetime。"""
        snapshot = GameStateSnapshot(
            stage="1-1",
            phase="planning",
            level=1,
            gold=0,
            hp=100,
            board=[],
            bench=[],
            augments=[],
            streak="none",
            streak_count=0,
            suggestions=None,
            created_at=datetime.now(UTC),
        )
        assert snapshot.created_at.tzinfo is not None
        assert snapshot.created_at.tzinfo == UTC

    def test_board_and_bench_store_complex_data(self) -> None:
        """board 和 bench 可以存储复杂字典数据。"""
        board_data = [{"name": "盖伦", "star": 2, "items": ["狂徒铠甲"]}]
        bench_data = [{"name": "波比", "star": 1}]
        snapshot = GameStateSnapshot(
            stage="2-1",
            phase="combat",
            level=4,
            gold=20,
            hp=85,
            board=board_data,
            bench=bench_data,
            augments=[],
            streak="none",
            streak_count=0,
            suggestions=None,
            created_at=datetime.now(UTC),
        )
        assert snapshot.board == board_data
        assert snapshot.bench == bench_data

    def test_suggestions_can_be_none_or_dict(self) -> None:
        """suggestions 可以为 None 或包含建议数据的 dict。"""
        snapshot_none = GameStateSnapshot(
            stage="1-1",
            phase="planning",
            level=1,
            gold=0,
            hp=100,
            board=[],
            bench=[],
            augments=[],
            streak="none",
            streak_count=0,
            suggestions=None,
            created_at=datetime.now(UTC),
        )
        assert snapshot_none.suggestions is None

        suggestions = {"recommended_comps": [{"name": "八法师"}]}
        snapshot_with = GameStateSnapshot(
            stage="1-1",
            phase="planning",
            level=1,
            gold=0,
            hp=100,
            board=[],
            bench=[],
            augments=[],
            streak="none",
            streak_count=0,
            suggestions=suggestions,
            created_at=datetime.now(UTC),
        )
        assert snapshot_with.suggestions == suggestions


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------


class TestGameStateInit:
    """GameState.__init__ 测试。"""

    def test_default_player_name(self) -> None:
        """player_name 默认值为 'Player'。"""
        gs = GameState()
        assert gs.player_name == "Player"

    def test_custom_player_name(self) -> None:
        """可以传入自定义 player_name。"""
        gs = GameState(player_name="TestPlayer")
        assert gs.player_name == "TestPlayer"

    def test_init_history_is_empty(self) -> None:
        """初始化后 history 为空列表。"""
        gs = GameState()
        assert gs.history() == []

    def test_init_current_is_none(self) -> None:
        """初始化后 current 为 None。"""
        gs = GameState()
        assert gs.current() is None


class TestGameStateUpdate:
    """GameState.update() 测试。"""

    def test_first_update_returns_snapshot(self, sample_game_state_dict: dict[str, Any]) -> None:
        """首次 update 返回 GameStateSnapshot 实例。"""
        gs = GameState()
        snapshot = gs.update(sample_game_state_dict)
        assert isinstance(snapshot, GameStateSnapshot)
        assert snapshot.stage == "3-2"
        assert snapshot.phase == "planning"
        assert snapshot.level == 6
        assert snapshot.gold == 45
        assert snapshot.hp == 72
        assert snapshot.streak == "win"
        assert snapshot.streak_count == 3

    def test_multiple_updates_return_different_snapshots(self, sample_game_state_dict: dict[str, Any]) -> None:
        """多次 update 返回不同的 snapshot 对象。"""
        gs = GameState()
        snap1 = gs.update(sample_game_state_dict)

        state2 = dict(sample_game_state_dict, gold=50)
        snap2 = gs.update(state2)

        assert snap1 is not snap2
        assert snap1.gold == 45
        assert snap2.gold == 50

    def test_update_appends_to_history(self, sample_game_state_dict: dict[str, Any]) -> None:
        """每次 update 都将 snapshot 附加到 history。"""
        gs = GameState()
        gs.update(sample_game_state_dict)
        assert len(gs.history()) == 1

        gs.update(sample_game_state_dict)
        assert len(gs.history()) == 2

        gs.update(sample_game_state_dict)
        assert len(gs.history()) == 3

    def test_update_updates_current(self, sample_game_state_dict: dict[str, Any]) -> None:
        """每次 update 后 current 指向最新 snapshot。"""
        gs = GameState()
        snap1 = gs.update(sample_game_state_dict)
        assert gs.current() is snap1

        state2 = dict(sample_game_state_dict, gold=55)
        snap2 = gs.update(state2)
        assert gs.current() is snap2
        assert gs.current() is not snap1

    def test_update_with_suggestions(
        self, sample_game_state_dict: dict[str, Any], suggestions_dict: dict[str, Any]
    ) -> None:
        """update 可以附带 suggestions。"""
        gs = GameState()
        snapshot = gs.update(sample_game_state_dict, suggestions=suggestions_dict)
        assert snapshot.suggestions == suggestions_dict

    def test_update_defaults_for_missing_fields(self) -> None:
        """缺少字段时使用默认值。"""
        gs = GameState()
        snapshot = gs.update({})
        assert snapshot.stage == "1-1"
        assert snapshot.phase == "planning"
        assert snapshot.level == 1
        assert snapshot.gold == 0
        assert snapshot.hp == 100
        assert snapshot.board == []
        assert snapshot.bench == []
        assert snapshot.augments == []
        assert snapshot.streak == "none"
        assert snapshot.streak_count == 0
        assert snapshot.suggestions is None


class TestGameStateHistory:
    """GameState.history() 测试。"""

    def test_history_returns_copy(self, sample_game_state_dict: dict[str, Any]) -> None:
        """history() 返回列表副本，修改不影响内部状态。"""
        gs = GameState()
        gs.update(sample_game_state_dict)
        hist = gs.history()
        hist.pop()
        assert len(gs.history()) == 1  # 原列表未被修改

    def test_history_preserves_order(self, sample_game_state_dict: dict[str, Any]) -> None:
        """history 按时间先后顺序排列。"""
        gs = GameState()
        state1 = dict(sample_game_state_dict, gold=40)
        state2 = dict(sample_game_state_dict, gold=50)
        state3 = dict(sample_game_state_dict, gold=60)

        gs.update(state1)
        gs.update(state2)
        gs.update(state3)

        hist = gs.history()
        assert hist[0].gold == 40
        assert hist[1].gold == 50
        assert hist[2].gold == 60


class TestGameStateCurrent:
    """GameState.current() 测试。"""

    def test_current_returns_none_before_updates(self) -> None:
        """未调用 update 时 current() 返回 None。"""
        gs = GameState()
        assert gs.current() is None

    def test_current_returns_latest_snapshot(self, sample_game_state_dict: dict[str, Any]) -> None:
        """current() 返回最新快照。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, gold=10))
        gs.update(dict(sample_game_state_dict, gold=20))
        assert gs.current().gold == 20


class TestGameStateSummary:
    """GameState.summary() 测试。"""

    def test_summary_no_history_returns_zero_deltas(self) -> None:
        """无历史时返回全零增量。"""
        gs = GameState()
        summary = gs.summary()
        assert summary == {
            "new_champs": [],
            "gold_delta": 0,
            "hp_delta": 0,
            "phase_changed": False,
            "level_up": False,
        }

    def test_summary_single_snapshot_returns_zero_deltas(self, sample_game_state_dict: dict[str, Any]) -> None:
        """只有一个快照时返回全零增量。"""
        gs = GameState()
        gs.update(sample_game_state_dict)
        summary = gs.summary()
        assert summary == {
            "new_champs": [],
            "gold_delta": 0,
            "hp_delta": 0,
            "phase_changed": False,
            "level_up": False,
        }

    def test_summary_state_unchanged_zero_deltas(self, sample_game_state_dict: dict[str, Any]) -> None:
        """两次 update 相同状态时各 delta 为 0。"""
        gs = GameState()
        gs.update(sample_game_state_dict)
        gs.update(sample_game_state_dict)
        summary = gs.summary()
        assert summary["gold_delta"] == 0
        assert summary["hp_delta"] == 0
        assert summary["level_up"] is False
        assert summary["phase_changed"] is False
        assert summary["new_champs"] == []

    def test_summary_new_champs_detected(self, sample_game_state_dict: dict[str, Any]) -> None:
        """board 新增棋子时 new_champs 正确检测。"""
        gs = GameState()
        gs.update(sample_game_state_dict)

        state2 = dict(sample_game_state_dict)
        state2["board"] = sample_game_state_dict["board"] + [{"name": "瑞兹", "star": 1, "items": []}]

        gs.update(state2)
        summary = gs.summary()
        assert "瑞兹" in summary["new_champs"]

    def test_summary_new_champs_from_bench(self, sample_game_state_dict: dict[str, Any]) -> None:
        """bench 新增棋子时 new_champs 正确检测。"""
        gs = GameState()
        gs.update(sample_game_state_dict)

        state2 = dict(sample_game_state_dict)
        state2["bench"] = sample_game_state_dict["bench"] + [{"name": "辛德拉", "star": 1}]

        gs.update(state2)
        summary = gs.summary()
        assert "辛德拉" in summary["new_champs"]

    def test_summary_gold_delta_positive(self, sample_game_state_dict: dict[str, Any]) -> None:
        """gold 增加时 gold_delta 为正。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, gold=40))
        gs.update(dict(sample_game_state_dict, gold=50))
        summary = gs.summary()
        assert summary["gold_delta"] == 10

    def test_summary_gold_delta_negative(self, sample_game_state_dict: dict[str, Any]) -> None:
        """gold 减少时 gold_delta 为负。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, gold=50))
        gs.update(dict(sample_game_state_dict, gold=30))
        summary = gs.summary()
        assert summary["gold_delta"] == -20

    def test_summary_hp_delta(self, sample_game_state_dict: dict[str, Any]) -> None:
        """hp 变化时 hp_delta 正确。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, hp=80))
        gs.update(dict(sample_game_state_dict, hp=65))
        summary = gs.summary()
        assert summary["hp_delta"] == -15

    def test_summary_level_up_true(self, sample_game_state_dict: dict[str, Any]) -> None:
        """level 上升时 level_up 为 True。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, level=5))
        gs.update(dict(sample_game_state_dict, level=6))
        summary = gs.summary()
        assert summary["level_up"] is True

    def test_summary_level_same_not_level_up(self, sample_game_state_dict: dict[str, Any]) -> None:
        """level 不变时 level_up 为 False。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, level=6))
        gs.update(dict(sample_game_state_dict, level=6))
        summary = gs.summary()
        assert summary["level_up"] is False

    def test_summary_level_down_not_level_up(self, sample_game_state_dict: dict[str, Any]) -> None:
        """level 下降时 level_up 为 False。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, level=7))
        gs.update(dict(sample_game_state_dict, level=6))
        summary = gs.summary()
        assert summary["level_up"] is False

    def test_summary_phase_changed_stage(self, sample_game_state_dict: dict[str, Any]) -> None:
        """stage 变化时 phase_changed 为 True。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, stage="3-1"))
        gs.update(dict(sample_game_state_dict, stage="3-2"))
        summary = gs.summary()
        assert summary["phase_changed"] is True

    def test_summary_phase_changed_phase(self, sample_game_state_dict: dict[str, Any]) -> None:
        """phase 变化时 phase_changed 为 True。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, phase="planning"))
        gs.update(dict(sample_game_state_dict, phase="combat"))
        summary = gs.summary()
        assert summary["phase_changed"] is True

    def test_summary_new_champs_deduplicates_board_and_bench(self, sample_game_state_dict: dict[str, Any]) -> None:
        """同一棋子同时在 board 和 bench 中出现不重复计算。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, board=[{"name": "盖伦"}], bench=[{"name": "盖伦"}]))

        state2: dict[str, Any] = {
            "level": 1, "gold": 0, "hp": 100, "stage": "1-1", "phase": "planning",
            "streak": "none", "streak_count": 0,
            "board": [{"name": "盖伦"}, {"name": "拉克丝"}],
            "bench": [{"name": "盖伦"}, {"name": "拉克丝"}],
            "augments": [], "items": [],
        }
        gs.update(state2)
        summary = gs.summary()
        assert "拉克丝" in summary["new_champs"]
        assert "盖伦" not in summary["new_champs"]

    def test_summary_calculates_between_last_two_only(self, sample_game_state_dict: dict[str, Any]) -> None:
        """summary 只比较最近两个快照，不受更早快照影响。"""
        gs = GameState()
        gs.update(dict(sample_game_state_dict, gold=30))  # 第1个
        gs.update(dict(sample_game_state_dict, gold=50))  # 第2个, delta=+20
        gs.update(dict(sample_game_state_dict, gold=50))  # 第3个, delta=0
        summary = gs.summary()
        # 第2→第3 的 delta 应为 0
        assert summary["gold_delta"] == 0


class TestGameStateIsKeyDecisionPoint:
    """GameState.is_key_decision_point() 测试。"""

    def test_no_current_returns_false(self) -> None:
        """无快照时返回 False。"""
        gs = GameState()
        assert gs.is_key_decision_point() is False

    def test_stage_3_2_is_key(self) -> None:
        """stage 3-2 是关键决策点。"""
        gs = GameState()
        gs.update({"stage": "3-2", "phase": "planning"})
        assert gs.is_key_decision_point() is True

    def test_stage_4_1_is_key(self) -> None:
        """stage 4-1 是关键决策点。"""
        gs = GameState()
        gs.update({"stage": "4-1", "phase": "planning"})
        assert gs.is_key_decision_point() is True

    def test_stage_4_5_is_key(self) -> None:
        """stage 4-5 是关键决策点。"""
        gs = GameState()
        gs.update({"stage": "4-5", "phase": "planning"})
        assert gs.is_key_decision_point() is True

    def test_stage_2_1_is_not_key(self) -> None:
        """stage 2-1 不是关键决策点。"""
        gs = GameState()
        gs.update({"stage": "2-1", "phase": "planning"})
        assert gs.is_key_decision_point() is False

    def test_carousel_phase_is_key(self) -> None:
        """carousel 阶段是关键决策点。"""
        gs = GameState()
        gs.update({"stage": "2-4", "phase": "carousel"})
        assert gs.is_key_decision_point() is True

    def test_combat_phase_is_not_key(self) -> None:
        """combat 阶段不是关键决策点（非关键 stage）。"""
        gs = GameState()
        gs.update({"stage": "2-1", "phase": "combat"})
        assert gs.is_key_decision_point() is False

    def test_carousel_overrides_stage(self) -> None:
        """carousel 阶段即使不在关键 stage 上也返回 True。"""
        gs = GameState()
        gs.update({"stage": "1-4", "phase": "carousel"})
        assert gs.is_key_decision_point() is True

    def test_stage_6_1_is_not_key(self) -> None:
        """非关键 stage (6-1) 返回 False。"""
        gs = GameState()
        gs.update({"stage": "6-1", "phase": "planning"})
        assert gs.is_key_decision_point() is False


class TestGameStateShouldReconsider:
    """GameState.should_reconsider() 测试。"""

    def test_no_current_returns_false(self) -> None:
        """无快照时返回 (False, '')。"""
        gs = GameState()
        result = gs.should_reconsider()
        assert result == (False, "")

    def test_no_suggestions_returns_false(self) -> None:
        """无建议时返回 (False, '')。"""
        gs = GameState()
        gs.update({"stage": "3-2", "phase": "planning"})
        result = gs.should_reconsider()
        assert result == (False, "")

    def test_no_recommended_comps_returns_false(self) -> None:
        """suggestions 中无 recommended_comps 时返回 (False, '')。"""
        gs = GameState()
        gs.update({"stage": "3-2", "phase": "planning"}, suggestions={"other": "data"})
        result = gs.should_reconsider()
        assert result == (False, "")

    def test_empty_recommended_comps_returns_false(self) -> None:
        """recommended_comps 为空列表时返回 (False, '')。"""
        gs = GameState()
        gs.update({"stage": "3-2", "phase": "planning"}, suggestions={"recommended_comps": []})
        result = gs.should_reconsider()
        assert result == (False, "")

    def test_missing_core_not_appeared_returns_true(self) -> None:
        """推荐阵容缺少的核心棋子完全未出现时返回 True。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹", "辛德拉"],
                }
            ],
        }
        gs.update(
            {
                "stage": "3-5",
                "phase": "planning",
                "board": [{"name": "盖伦"}],
                "bench": [{"name": "波比"}],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        assert result[0] is True
        assert "未在棋盘" in result[1]

    def test_missing_core_appeared_does_not_trigger(self) -> None:
        """核心棋子出现时不触发转型建议（仅该检查不触发）。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
        }
        # 只有一个快照时，即便核心棋子出现也不触发（但此时 missing_core 出现在棋盘上，
        # 所以 last_missing & all_current 为真，不会触发 missing_core 检查）
        gs.update(
            {
                "stage": "3-5",
                "phase": "planning",
                "board": [{"name": "瑞兹"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        # 只有一个快照且核心棋子已出现 → 不触发
        result = gs.should_reconsider()
        assert result[0] is False

    def test_low_keep_ratio_returns_true(self) -> None:
        """连续两轮保留比例低于 40% 返回 True。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
        }
        # 第一轮: 4 个棋子
        gs.update(
            {
                "stage": "3-2",
                "phase": "planning",
                "board": [{"name": "盖伦"}, {"name": "拉克丝"}, {"name": "安妮"}, {"name": "波比"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        # 第二轮: 只保留了 1 个棋子 (keep_ratio = 1/4 = 0.25 < 0.4)
        gs.update(
            {
                "stage": "3-3",
                "phase": "planning",
                "board": [{"name": "盖伦"}, {"name": "瑞兹"}, {"name": "辛德拉"}, {"name": "艾希"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        assert result[0] is True
        assert "保留比例" in result[1]

    def test_normal_keep_ratio_returns_false(self) -> None:
        """保留比例正常时返回 False。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
        }
        # 第一轮: 4 个棋子
        gs.update(
            {
                "stage": "3-2",
                "phase": "planning",
                "board": [{"name": "盖伦"}, {"name": "拉克丝"}, {"name": "安妮"}, {"name": "波比"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        # 第二轮: 保留了 3 个棋子 (keep_ratio = 3/4 = 0.75 >= 0.4)
        gs.update(
            {
                "stage": "3-3",
                "phase": "planning",
                "board": [{"name": "盖伦"}, {"name": "拉克丝"}, {"name": "安妮"}, {"name": "瑞兹"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        assert result[0] is False

    def test_exactly_40_percent_keep_ratio_returns_false(self) -> None:
        """保留比例恰好等于 40% 时返回 False（因为条件是 < 0.4）。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
        }
        # 第一轮: 5 个棋子
        gs.update(
            {
                "stage": "3-2",
                "phase": "planning",
                "board": [
                    {"name": "盖伦"}, {"name": "拉克丝"}, {"name": "安妮"},
                    {"name": "波比"}, {"name": "艾希"},
                ],
                "bench": [],
            },
            suggestions=suggestions,
        )
        # 第二轮: 保留 2/5 = 40% → 不触发
        gs.update(
            {
                "stage": "3-3",
                "phase": "planning",
                "board": [
                    {"name": "盖伦"}, {"name": "拉克丝"}, {"name": "瑞兹"},
                    {"name": "辛德拉"}, {"name": "维克托"},
                ],
                "bench": [],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        assert result[0] is False

    def test_prev_board_empty_triggers_missing_core_check(self) -> None:
        """上一轮棋盘为空时，缺少核心棋子检查先触发（不依赖历史长度）。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
        }
        # 第一轮: 空棋盘（缺少的核心棋子未出现）
        gs.update(
            {
                "stage": "3-2",
                "phase": "planning",
                "board": [],
                "bench": [],
            },
            suggestions=suggestions,
        )
        # 第二轮: 缺少的核心棋子仍未出现 → missing_core 检查触发
        gs.update(
            {
                "stage": "3-3",
                "phase": "planning",
                "board": [{"name": "盖伦"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        # missing_core 检查先于 keep_ratio 检查，且不依赖 prev_board_names
        assert result[0] is True
        assert "未在棋盘" in result[1]

    def test_core_missing_appeared_no_complete_replacement_no_trigger(self) -> None:
        """核心棋子已出现，且保留比例正常时 should_reconsider 返回 False。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
        }
        # 第一轮: 有一些棋子
        gs.update(
            {
                "stage": "3-2",
                "phase": "planning",
                "board": [{"name": "盖伦"}, {"name": "拉克丝"}, {"name": "安妮"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        # 第二轮: 核心棋子"瑞兹"已出现，保留比例 3/3 = 100%
        gs.update(
            {
                "stage": "3-3",
                "phase": "planning",
                "board": [{"name": "盖伦"}, {"name": "拉克丝"}, {"name": "安妮"}, {"name": "瑞兹"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        assert result[0] is False

    def test_single_snapshot_does_not_trigger_keep_ratio(self) -> None:
        """只有一个快照时不触发保留比例检查（history < 2）。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹", "辛德拉"],
                }
            ],
        }
        gs.update(
            {
                "stage": "3-2",
                "phase": "planning",
                "board": [{"name": "盖伦"}],
                "bench": [{"name": "波比"}],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        assert result[0] is True  # 触发的是 missing_core 检查，不是 keep_ratio
        assert "未在棋盘" in result[1]

    def test_bench_champs_counted_in_keep_ratio(self) -> None:
        """备战席棋子也计入保留比例。"""
        gs = GameState()
        suggestions = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
        }
        # 第一轮: board 有 [A, B], bench 有 [C, D]
        gs.update(
            {
                "stage": "3-2",
                "phase": "planning",
                "board": [{"name": "A"}, {"name": "B"}],
                "bench": [{"name": "C"}, {"name": "D"}],
            },
            suggestions=suggestions,
        )
        # 第二轮: board [A, X], bench [] → all_current = {A, X}
        # prev_board_names = {A, B} (注意: 只看 prev.board，不看 prev.bench!)
        # kept = {A}, keep_ratio = 1/2 = 0.5 >= 0.4
        # 所以不会触发 keep_ratio
        gs.update(
            {
                "stage": "3-3",
                "phase": "planning",
                "board": [{"name": "A"}, {"name": "X"}],
                "bench": [],
            },
            suggestions=suggestions,
        )
        result = gs.should_reconsider()
        # keep_ratio = 1/2 = 0.5 >= 0.4 → 不触发
        # 同时 missing_core 中的 "瑞兹" 没有出现在 board/bench → 但 bench 为空，且上一轮 missing_core 触发了
        # 当前轮次的建议中 core_champs_missing 仍然是["瑞兹"]，而 all_current = {"A", "X"} 中没有瑞兹
        # 所以 missing_core 检查触发
        assert result[0] is True


# ---------------------------------------------------------------------------
# save_replay + list_replays
# ---------------------------------------------------------------------------


class TestSaveReplay:
    """save_replay 测试。"""

    def test_needs_init_db_first(self, sample_game_state_dict: dict[str, Any]) -> None:
        """未调用 init_db 时 save_replay 抛出 RuntimeError。"""
        # 确保全局状态清理
        models._engine = None
        models._SessionLocal = None
        gs = GameState()
        gs.update(sample_game_state_dict)
        with pytest.raises(RuntimeError, match="Database not initialized"):
            save_replay(gs)

    def test_empty_history_raises(self, db_session: models.Session) -> None:
        """没有快照数据时 save_replay 抛出 RuntimeError。"""
        gs = GameState()
        with pytest.raises(RuntimeError, match="没有对局快照数据"):
            save_replay(gs)

    def test_save_replay_returns_positive_id(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """save_replay 返回正整数 ID。"""
        gs = GameState()
        gs.update(sample_game_state_dict)
        gs.update(dict(sample_game_state_dict, gold=50))
        gs.update(dict(sample_game_state_dict, gold=60))

        replay_id = save_replay(gs)
        assert isinstance(replay_id, int)
        assert replay_id > 0

    def test_save_replay_writes_to_database(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """save_replay 正确写入 GameReplay 记录。"""
        gs = GameState(player_name="TestReplay")
        gs.update(sample_game_state_dict)
        gs.update(dict(sample_game_state_dict, gold=55))

        replay_id = save_replay(gs, final_rank=3)

        # 从数据库回读验证
        replay = db_session.execute(
            select(GameReplay).where(GameReplay.id == replay_id)
        ).scalar_one()

        assert replay.player_name == "TestReplay"
        assert replay.final_rank == 3
        assert replay.total_rounds == 2
        assert replay.snapshots is not None
        assert len(replay.snapshots) > 0
        assert replay.final_board is not None
        assert len(replay.final_board) > 0
        assert isinstance(replay.started_at, datetime)
        assert isinstance(replay.ended_at, datetime)

    def test_save_replay_without_final_rank(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """不传 final_rank 时字段为 None。"""
        gs = GameState()
        gs.update(sample_game_state_dict)

        replay_id = save_replay(gs)

        replay = db_session.execute(
            select(GameReplay).where(GameReplay.id == replay_id)
        ).scalar_one()

        assert replay.final_rank is None

    def test_save_replay_stores_valid_json_in_snapshots(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """snapshots 字段包含有效的 JSON 序列化数据。"""
        import json

        gs = GameState()
        gs.update(sample_game_state_dict)

        replay_id = save_replay(gs)

        replay = db_session.execute(
            select(GameReplay).where(GameReplay.id == replay_id)
        ).scalar_one()

        parsed = json.loads(replay.snapshots)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["stage"] == "3-2"


class TestListReplays:
    """list_replays 测试。"""

    def test_empty_database_returns_empty_list(self, db_session: models.Session) -> None:
        """空数据库返回空列表。"""
        result = list_replays(session=db_session)
        assert result == []
        assert isinstance(result, list)

    def test_list_replays_returns_all_records(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """有记录时返回列表，包含所有字段。"""
        # 插入两条记录
        gs1 = GameState(player_name="P1")
        gs1.update(dict(sample_game_state_dict, gold=10))
        gs1.update(dict(sample_game_state_dict, gold=20))
        save_replay(gs1, final_rank=2)

        gs2 = GameState(player_name="P2")
        gs2.update(dict(sample_game_state_dict, gold=30))
        save_replay(gs2, final_rank=5)

        result = list_replays(session=db_session)
        assert len(result) == 2

        required_keys = {"id", "player_name", "started_at", "ended_at", "final_rank", "total_rounds"}
        for record in result:
            assert required_keys.issubset(record.keys())
            assert isinstance(record["id"], int)
            assert isinstance(record["player_name"], str)
            assert isinstance(record["started_at"], str)
            assert isinstance(record["ended_at"], str)
            assert isinstance(record["total_rounds"], int)

    def test_list_replays_ordered_by_started_at_desc(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """返回的记录按 started_at 降序排列。"""
        gs1 = GameState(player_name="Older")
        gs1.update(sample_game_state_dict)
        save_replay(gs1)

        gs2 = GameState(player_name="Newer")
        gs2.update(sample_game_state_dict)
        save_replay(gs2)

        result = list_replays(session=db_session, limit=10)
        assert len(result) >= 2
        # 最新记录在前
        assert result[0]["player_name"] == "Newer"

    def test_list_replays_limit_respected(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """limit 参数生效。"""
        for i in range(5):
            gs = GameState(player_name=f"Player{i}")
            gs.update(dict(sample_game_state_dict, gold=i))
            save_replay(gs)

        result = list_replays(session=db_session, limit=3)
        assert len(result) == 3

    def test_list_replays_returns_iso_format_timestamps(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """started_at 和 ended_at 返回 ISO 格式字符串。"""
        gs = GameState()
        gs.update(sample_game_state_dict)
        save_replay(gs)

        result = list_replays(session=db_session)
        assert len(result) == 1
        # 验证 ISO 格式 (YYYY-MM-DDTHH:MM:SS)
        assert "T" in result[0]["started_at"]
        assert "T" in result[0]["ended_at"]

    def test_list_replays_default_session(
        self, db_session: models.Session, sample_game_state_dict: dict[str, Any]
    ) -> None:
        """不传 session 参数时自动获取会话。"""
        gs = GameState()
        gs.update(sample_game_state_dict)
        save_replay(gs)

        result = list_replays()  # 不传 session
        assert len(result) == 1


# ---------------------------------------------------------------------------
# GameReplay ORM 模型
# ---------------------------------------------------------------------------


class TestGameReplayModel:
    """GameReplay ORM 模型测试。"""

    def test_game_replay_table_exists(self, db_session: models.Session) -> None:
        """init_db(":memory:") 后 game_replays 表存在。"""
        inspector = inspect(db_session.get_bind())
        table_names = inspector.get_table_names()
        assert "game_replays" in table_names

    def test_game_replay_field_types(self, db_session: models.Session) -> None:
        """GameReplay 字段类型正确，nullable 字段可接受 None。"""
        from datetime import UTC

        now = datetime.now(UTC)
        replay = GameReplay(
            player_name="TestPlayer",
            started_at=now,
            ended_at=now,
            final_rank=None,
            total_rounds=10,
            snapshots=None,
            final_board=None,
        )
        db_session.add(replay)
        db_session.commit()

        result = db_session.execute(
            select(GameReplay).where(GameReplay.player_name == "TestPlayer")
        ).scalar_one()

        assert result.player_name == "TestPlayer"
        assert result.total_rounds == 10
        assert result.final_rank is None
        assert result.snapshots is None
        assert result.final_board is None
        assert isinstance(result.started_at, datetime)
        assert isinstance(result.ended_at, datetime)
        assert isinstance(result.id, int)

    def test_game_replay_autoincrement_id(self, db_session: models.Session) -> None:
        """GameReplay 的 id 字段自增。"""
        from datetime import UTC

        now = datetime.now(UTC)
        r1 = GameReplay(player_name="A", started_at=now, ended_at=now, total_rounds=1)
        r2 = GameReplay(player_name="B", started_at=now, ended_at=now, total_rounds=1)

        db_session.add(r1)
        db_session.commit()
        db_session.add(r2)
        db_session.commit()

        assert r1.id > 0
        assert r2.id > 0
        assert r2.id == r1.id + 1

    def test_game_replay_with_full_data(self, db_session: models.Session) -> None:
        """GameReplay 可以存储完整的 JSON 数据。"""
        from datetime import UTC

        snapshots_json = '[{"stage": "3-2", "gold": 45}]'
        final_board_json = '[{"name": "盖伦", "star": 2}]'

        now = datetime.now(UTC)
        replay = GameReplay(
            player_name="FullData",
            started_at=now,
            ended_at=now,
            final_rank=1,
            total_rounds=25,
            snapshots=snapshots_json,
            final_board=final_board_json,
        )
        db_session.add(replay)
        db_session.commit()

        result = db_session.execute(
            select(GameReplay).where(GameReplay.player_name == "FullData")
        ).scalar_one()

        assert result.final_rank == 1
        assert result.total_rounds == 25
        assert result.snapshots == snapshots_json
        assert result.final_board == final_board_json


# ---------------------------------------------------------------------------
# AdvicePipeline
# ---------------------------------------------------------------------------


class TestAdvicePipelineInit:
    """AdvicePipeline.__init__ 测试。"""

    def test_init_creates_game_state(self, mock_provider: MagicMock, pipeline_config: dict[str, Any]) -> None:
        """初始化后 _game_state 为 GameState 实例。"""
        # 延迟导入以避免 Advisor.__init__ 中的配置检查
        from tft_consider.tracker.pipeline import AdvicePipeline

        pipeline = AdvicePipeline(mock_provider, pipeline_config)
        assert isinstance(pipeline._game_state, GameState)

    def test_init_creates_advisor(self, mock_provider: MagicMock, pipeline_config: dict[str, Any]) -> None:
        """初始化后 _advisor 为 Advisor 实例。"""
        from tft_consider.engine.advisor import Advisor
        from tft_consider.tracker.pipeline import AdvicePipeline

        pipeline = AdvicePipeline(mock_provider, pipeline_config)
        assert isinstance(pipeline._advisor, Advisor)

    def test_init_default_player_name(self, mock_provider: MagicMock, pipeline_config: dict[str, Any]) -> None:
        """默认 player_name 为 'Player'。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        pipeline = AdvicePipeline(mock_provider, pipeline_config)
        assert pipeline._game_state.player_name == "Player"


class TestAdvicePipelineProcessFrame:
    """AdvicePipeline.process_frame() 测试。"""

    def test_process_frame_returns_required_fields(
        self, mock_provider: MagicMock, pipeline_config: dict[str, Any], sample_game_state_dict: dict[str, Any]
    ) -> None:
        """process_frame 返回结构包含 summary, is_key_point, candidates, suggestions, reconsider。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        mock_suggestions: dict[str, Any] = {
            "recommended_comps": [
                {"name": "八法师", "confidence": 80, "reason": "test", "core_champs_missing": ["瑞兹"]}
            ],
            "action_advice": {"level": "stay", "roll": "save", "positioning": "standard"},
            "next_steps": ["step1"],
        }
        mock_candidates: list[dict[str, Any]] = [
            {"name": "八法师", "tier": "S", "match_score": 15, "core_champs_missing": ["瑞兹"]}
        ]

        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=mock_candidates):
            pipeline = AdvicePipeline(mock_provider, pipeline_config)
            with patch.object(pipeline._advisor, "analyze", return_value=mock_suggestions):
                result = pipeline.process_frame(sample_game_state_dict)

        assert "summary" in result
        assert "is_key_point" in result
        assert "candidates" in result
        assert "suggestions" in result
        assert "reconsider" in result

    def test_process_frame_is_key_decision_point(
        self, mock_provider: MagicMock, pipeline_config: dict[str, Any]
    ) -> None:
        """关键决策点时 is_key_point 为 True。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        mock_suggestions: dict[str, Any] = {
            "recommended_comps": [],
            "action_advice": {"level": "stay", "roll": "save", "positioning": "standard"},
            "next_steps": [],
        }

        key_game_state: dict[str, Any] = {
            "level": 6, "gold": 45, "hp": 72, "stage": "3-2", "phase": "planning",
            "streak": "win", "streak_count": 3, "board": [], "bench": [], "items": [], "augments": [],
        }

        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=[]):
            pipeline = AdvicePipeline(mock_provider, pipeline_config)
            with patch.object(pipeline._advisor, "analyze", return_value=mock_suggestions):
                result = pipeline.process_frame(key_game_state)

        assert result["is_key_point"] is True

    def test_process_frame_updates_game_state(
        self, mock_provider: MagicMock, pipeline_config: dict[str, Any], sample_game_state_dict: dict[str, Any]
    ) -> None:
        """process_frame 调用后 GameState 历史增加。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        mock_suggestions: dict[str, Any] = {
            "recommended_comps": [],
            "action_advice": {"level": "stay", "roll": "save", "positioning": "standard"},
            "next_steps": [],
        }

        pipeline = AdvicePipeline(mock_provider, pipeline_config)
        assert len(pipeline._game_state.history()) == 0

        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=[]):
            with patch.object(pipeline._advisor, "analyze", return_value=mock_suggestions):
                pipeline.process_frame(sample_game_state_dict)

        assert len(pipeline._game_state.history()) == 1

    def test_process_frame_reconsider_when_low_keep_ratio(
        self, mock_provider: MagicMock, pipeline_config: dict[str, Any]
    ) -> None:
        """棋盘大量替换时 reconsider[0] 为 True。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        mock_suggestions: dict[str, Any] = {
            "recommended_comps": [
                {"name": "八法师", "confidence": 80, "reason": "test", "core_champs_missing": ["瑞兹"]}
            ],
            "action_advice": {"level": "stay", "roll": "save", "positioning": "standard"},
            "next_steps": ["step1"],
        }

        # 第一帧: 4 个棋子
        state1: dict[str, Any] = {
            "level": 6, "gold": 50, "hp": 72, "stage": "3-2", "phase": "planning",
            "streak": "win", "streak_count": 3,
            "board": [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
            "bench": [], "items": [], "augments": [],
        }
        # 第二帧: 只保留 1 个棋子 from 4 (keep_ratio = 25% < 40%)
        state2: dict[str, Any] = {
            "level": 6, "gold": 55, "hp": 72, "stage": "3-3", "phase": "planning",
            "streak": "win", "streak_count": 3,
            "board": [{"name": "A"}, {"name": "X"}, {"name": "Y"}, {"name": "Z"}],
            "bench": [], "items": [], "augments": [],
        }

        pipeline = AdvicePipeline(mock_provider, pipeline_config)

        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=[]):
            with patch.object(pipeline._advisor, "analyze", return_value=mock_suggestions):
                pipeline.process_frame(state1)
                result = pipeline.process_frame(state2)

        assert result["reconsider"][0] is True


class TestAdvicePipelineProcessAugments:
    """AdvicePipeline.process_augments() 测试。"""

    def test_process_augments_returns_analysis(
        self, mock_provider: MagicMock, pipeline_config: dict[str, Any], sample_game_state_dict: dict[str, Any]
    ) -> None:
        """process_augments 返回海克斯分析结果。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        mock_augment_result: dict[str, Any] = {
            "augments": [{"name": "法力流系带", "score": 90, "reason": "完美适配"}],
            "recommendation": "法力流系带",
        }

        augment_options = ["法力流系带", "护卫之心"]

        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=[]):
            pipeline = AdvicePipeline(mock_provider, pipeline_config)
            with patch.object(pipeline._advisor, "analyze_augments", return_value=mock_augment_result):
                result = pipeline.process_augments(sample_game_state_dict, augment_options)

        assert result == mock_augment_result
        assert "augments" in result
        assert "recommendation" in result

    def test_process_augments_passes_candidates_to_advisor(
        self, mock_provider: MagicMock, pipeline_config: dict[str, Any], sample_game_state_dict: dict[str, Any]
    ) -> None:
        """process_augments 将 match_compositions 的结果传给 advisor。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        mock_candidates: list[dict[str, Any]] = [
            {"name": "八法师", "tier": "S", "match_score": 15}
        ]
        mock_augment_result: dict[str, Any] = {
            "augments": [{"name": "test", "score": 50, "reason": "test"}],
            "recommendation": "test",
        }
        augment_options = ["法力流系带"]

        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=mock_candidates):
            pipeline = AdvicePipeline(mock_provider, pipeline_config)
            with patch.object(pipeline._advisor, "analyze_augments", return_value=mock_augment_result) as mock_analyze:
                pipeline.process_augments(sample_game_state_dict, augment_options)

        # 验证传给 analyze_augments 的 candidates 参数正确
        mock_analyze.assert_called_once()
        call_kwargs = mock_analyze.call_args
        assert call_kwargs[0][1] == augment_options  # 第二个位置参数
        assert call_kwargs[0][2] == mock_candidates  # 第三个位置参数


class TestAdvicePipelineProperties:
    """AdvicePipeline 属性测试。"""

    def test_game_state_property_accessible(self, mock_provider: MagicMock, pipeline_config: dict[str, Any]) -> None:
        """game_state 属性可访问内部 GameState。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        pipeline = AdvicePipeline(mock_provider, pipeline_config)
        assert pipeline.game_state is pipeline._game_state
        assert isinstance(pipeline.game_state, GameState)


class TestAdvicePipelineOnGameEnd:
    """AdvicePipeline.on_game_end() 测试。"""

    def test_on_game_end_returns_replay_id(
        self,
        db_session: models.Session,
        mock_provider: MagicMock,
        pipeline_config: dict[str, Any],
        sample_game_state_dict: dict[str, Any],
    ) -> None:
        """on_game_end 调用 save_replay 返回 ID。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        pipeline = AdvicePipeline(mock_provider, pipeline_config)

        # 需要先通过 process_frame 添加快照数据
        mock_suggestions: dict[str, Any] = {
            "recommended_comps": [],
            "action_advice": {"level": "stay", "roll": "save", "positioning": "standard"},
            "next_steps": [],
        }
        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=[]):
            with patch.object(pipeline._advisor, "analyze", return_value=mock_suggestions):
                pipeline.process_frame(sample_game_state_dict)

        replay_id = pipeline.on_game_end(final_rank=4)
        assert isinstance(replay_id, int)
        assert replay_id > 0

        # 验证数据库中有记录
        replay = db_session.execute(
            select(GameReplay).where(GameReplay.id == replay_id)
        ).scalar_one()
        assert replay.final_rank == 4

    def test_on_game_end_without_final_rank(
        self,
        db_session: models.Session,
        mock_provider: MagicMock,
        pipeline_config: dict[str, Any],
        sample_game_state_dict: dict[str, Any],
    ) -> None:
        """不传 final_rank 时 on_game_end 正常工作。"""
        from tft_consider.tracker.pipeline import AdvicePipeline

        pipeline = AdvicePipeline(mock_provider, pipeline_config)

        mock_suggestions: dict[str, Any] = {
            "recommended_comps": [],
            "action_advice": {"level": "stay", "roll": "save", "positioning": "standard"},
            "next_steps": [],
        }
        with patch("tft_consider.tracker.pipeline.match_compositions", return_value=[]):
            with patch.object(pipeline._advisor, "analyze", return_value=mock_suggestions):
                pipeline.process_frame(sample_game_state_dict)

        replay_id = pipeline.on_game_end()
        assert replay_id > 0

        replay = db_session.execute(
            select(GameReplay).where(GameReplay.id == replay_id)
        ).scalar_one()
        assert replay.final_rank is None
