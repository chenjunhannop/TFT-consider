"""引擎模块 (matcher + advisor) 单元测试。

覆盖 match_compositions 阵容匹配算法和 Advisor LLM 建议引擎。
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Engine, event

from tft_consider.database import importer, models
from tft_consider.engine.advisor import Advisor
from tft_consider.engine.matcher import match_compositions
from tft_consider.vision.base import BaseProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Generator[models.Session, None, None]:
    """每个测试使用独立的 :memory: 数据库。"""
    event.listen(Engine, "connect", lambda dbapi_conn, _rec: dbapi_conn.execute("PRAGMA foreign_keys = ON"))
    models.init_db(":memory:")
    yield models.get_session()
    if models._engine is not None:
        models._engine.dispose()
    models._engine = None
    models._SessionLocal = None


@pytest.fixture
def populated_db(db_session: models.Session, tmp_path: Path) -> None:
    """在 :memory: 数据库中导入 example_comps.json 数据。"""
    src = Path(__file__).parent.parent / "data" / "templates" / "example_comps.json"
    dest = tmp_path / "example_comps.json"
    shutil.copy(src, dest)
    importer.import_from_json(dest)


@pytest.fixture
def sample_game_state() -> dict[str, Any]:
    """构造一个持有部分棋子和装备的游戏状态。"""
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
def empty_game_state() -> dict[str, Any]:
    """构造一个 board/bench 均为空的游戏状态。"""
    return {
        "level": 4,
        "gold": 10,
        "hp": 100,
        "stage": "1-3",
        "phase": "planning",
        "streak": "none",
        "streak_count": 0,
        "board": [],
        "bench": [],
        "items": [],
        "augments": [],
    }


@pytest.fixture
def mock_provider() -> MagicMock:
    """提供一个 mock 的 BaseProvider 实例。"""
    return MagicMock(spec=BaseProvider)


@pytest.fixture
def advisor_config() -> dict[str, Any]:
    """构造 Advisor 所需的最小配置。"""
    return {
        "api": {
            "provider": "moonshot",
            "key": "dummy-test-key",
            "model": "kimi-k2-0719-preview",
        },
    }


@pytest.fixture
def sample_candidates() -> list[dict[str, Any]]:
    """构造候选阵容列表，模拟 match_compositions 的输出格式。"""
    return [
        {
            "composition_id": 1,
            "name": "八法师",
            "tier": "S",
            "playstyle": "运营",
            "description": "八法师阵容描述",
            "match_score": 15,
            "core_matched": 3,
            "core_total": 4,
            "champion_matched": 4,
            "champion_total": 9,
            "item_matched": 2,
            "item_total": 9,
            "core_champs_missing": ["瑞兹"],
            "positioning": None,
        },
        {
            "composition_id": 2,
            "name": "六护卫",
            "tier": "A",
            "playstyle": "连胜",
            "description": "六护卫阵容描述",
            "match_score": 10,
            "core_matched": 2,
            "core_total": 5,
            "champion_matched": 3,
            "champion_total": 8,
            "item_matched": 1,
            "item_total": 8,
            "core_champs_missing": ["雷欧娜", "维克托"],
            "positioning": None,
        },
    ]


# ---------------------------------------------------------------------------
# TestMatcher: match_compositions
# ---------------------------------------------------------------------------


class TestMatcherEmpty:
    """空数据库场景。"""

    def test_empty_database_returns_empty_list(self, db_session: models.Session) -> None:
        """未导入任何数据时，match_compositions 返回空列表。"""
        game_state: dict[str, Any] = {"board": [], "bench": [], "items": []}
        result = match_compositions(game_state)
        assert result == []
        assert isinstance(result, list)

    def test_empty_database_with_top_n(self, db_session: models.Session) -> None:
        """空数据库下 top_n 参数不影响结果（仍返回空列表）。"""
        game_state: dict[str, Any] = {"board": [], "bench": [], "items": []}
        result = match_compositions(game_state, top_n=3)
        assert result == []


class TestMatcherNormal:
    """正常匹配场景（数据库已导入数据）。"""

    def test_returns_correct_structure(
        self, populated_db: None, sample_game_state: dict[str, Any]
    ) -> None:
        """返回的每个候选阵容包含所有必要字段。"""
        result = match_compositions(sample_game_state, top_n=5)
        assert len(result) > 0
        required_keys = {
            "composition_id", "name", "tier", "playstyle", "description",
            "match_score", "core_matched", "core_total",
            "champion_matched", "champion_total",
            "item_matched", "item_total",
            "core_champs_missing", "positioning",
        }
        for candidate in result:
            assert required_keys.issubset(candidate.keys())

    def test_match_score_positive(
        self, populated_db: None, sample_game_state: dict[str, Any]
    ) -> None:
        """持有棋子与阵容有重叠时，match_score > 0。"""
        result = match_compositions(sample_game_state, top_n=5)
        assert len(result) > 0
        for candidate in result:
            assert candidate["match_score"] >= 0
        assert any(c["match_score"] > 0 for c in result)

    def test_sorted_by_score_desc(
        self, populated_db: None, sample_game_state: dict[str, Any]
    ) -> None:
        """结果按 match_score 降序排列。"""
        result = match_compositions(sample_game_state, top_n=5)
        scores = [c["match_score"] for c in result]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_limit(
        self, populated_db: None, sample_game_state: dict[str, Any]
    ) -> None:
        """top_n 参数生效，返回数量不超过 top_n。"""
        for top_n in [1, 2]:
            result = match_compositions(sample_game_state, top_n=top_n)
            assert len(result) <= top_n

    def test_top_n_zero_returns_empty(
        self, populated_db: None, sample_game_state: dict[str, Any]
    ) -> None:
        """top_n=0 时返回空列表。"""
        result = match_compositions(sample_game_state, top_n=0)
        assert result == []


class TestMatcherEdge:
    """边界和特殊场景。"""

    def test_empty_board_and_bench(
        self, populated_db: None, empty_game_state: dict[str, Any]
    ) -> None:
        """board 和 bench 均为空时仍能返回结果。"""
        result = match_compositions(empty_game_state, top_n=5)
        assert len(result) > 0
        assert len(result) <= 5

    def test_item_matching_increases_score(
        self, populated_db: None, tmp_path: Path
    ) -> None:
        """持有装备时，装备匹配会计入 match_score。"""
        game_state: dict[str, Any] = {
            "level": 5,
            "gold": 20,
            "hp": 80,
            "stage": "2-1",
            "phase": "planning",
            "streak": "none",
            "streak_count": 0,
            "board": [{"name": "盖伦", "star": 1, "items": ["狂徒铠甲"]}],
            "bench": [],
            "items": [],
            "augments": [],
        }
        result = match_compositions(game_state, top_n=5)
        assert any(c["item_matched"] > 0 for c in result)

    def test_core_champs_missing_field(
        self, populated_db: None, sample_game_state: dict[str, Any]
    ) -> None:
        """core_champs_missing 字段包含未持有的核心棋子。"""
        result = match_compositions(sample_game_state, top_n=5)
        for candidate in result:
            assert isinstance(candidate["core_champs_missing"], list)
            held_names = {
                c["name"] for c in sample_game_state.get("board", [])
            } | {
                c["name"] for c in sample_game_state.get("bench", [])
            }
            for missing_name in candidate["core_champs_missing"]:
                assert missing_name not in held_names

    def test_no_champions_held(self, populated_db: None) -> None:
        """不持有任何数据库中的棋子时，match_score 为 0 但仍返回结果。"""
        game_state: dict[str, Any] = {
            "level": 4,
            "gold": 10,
            "hp": 100,
            "stage": "1-3",
            "phase": "planning",
            "streak": "none",
            "streak_count": 0,
            "board": [{"name": "完全不存在的棋子名", "star": 1, "items": []}],
            "bench": [],
            "items": [],
            "augments": [],
        }
        result = match_compositions(game_state, top_n=5)
        assert len(result) > 0
        for candidate in result:
            assert candidate["match_score"] == 0
            assert candidate["champion_matched"] == 0
            assert candidate["core_matched"] == 0

    def test_items_from_board_entries(self, populated_db: None) -> None:
        """装备从 board 条目的 items 字段中提取。"""
        game_state: dict[str, Any] = {
            "level": 5,
            "gold": 30,
            "hp": 80,
            "stage": "2-3",
            "phase": "planning",
            "streak": "none",
            "streak_count": 0,
            "board": [
                {"name": "盖伦", "star": 2, "items": ["狂徒铠甲", "棘刺背心"]},
            ],
            "bench": [],
            "items": [],
            "augments": [],
        }
        result = match_compositions(game_state, top_n=5)
        eight_mage = [c for c in result if c["name"] == "八法师"]
        if eight_mage:
            assert eight_mage[0]["item_matched"] >= 2

    def test_items_from_top_level_field(self, populated_db: None) -> None:
        """装备也从顶层 items 字段（字符串列表）中提取。"""
        game_state: dict[str, Any] = {
            "level": 5,
            "gold": 30,
            "hp": 80,
            "stage": "2-3",
            "phase": "planning",
            "streak": "none",
            "streak_count": 0,
            "board": [],
            "bench": [],
            "items": ["蓝霸符", "珠光护手"],
            "augments": [],
        }
        result = match_compositions(game_state, top_n=5)
        assert any(c["item_matched"] >= 2 for c in result)

    def test_items_from_top_level_dict_field(self, populated_db: None) -> None:
        """装备也从顶层 items 字段（dict 列表含 name 键）中提取。"""
        game_state: dict[str, Any] = {
            "level": 5,
            "gold": 30,
            "hp": 80,
            "stage": "2-3",
            "phase": "planning",
            "streak": "none",
            "streak_count": 0,
            "board": [],
            "bench": [],
            "items": [{"name": "蓝霸符"}, {"name": "珠光护手"}],
            "augments": [],
        }
        result = match_compositions(game_state, top_n=5)
        assert any(c["item_matched"] >= 2 for c in result)

    def test_positioning_parsed_correctly(
        self, populated_db: None, sample_game_state: dict[str, Any]
    ) -> None:
        """positioning 字段被正确解析为 list 或 None。"""
        result = match_compositions(sample_game_state, top_n=5)
        for candidate in result:
            positioning = candidate.get("positioning")
            assert positioning is None or isinstance(positioning, list)
            if isinstance(positioning, list):
                for pos_item in positioning:
                    assert isinstance(pos_item, dict)
                    assert "champion" in pos_item
                    assert "row" in pos_item
                    assert "col" in pos_item


# ---------------------------------------------------------------------------
# TestAdvisor: Advisor
# ---------------------------------------------------------------------------


class TestAdvisorInit:
    """Advisor 初始化。"""

    def test_init_sets_attributes(
        self, mock_provider: MagicMock, advisor_config: dict[str, Any]
    ) -> None:
        """__init__ 正确设置 provider、config、api_key、model。"""
        advisor = Advisor(mock_provider, advisor_config)
        assert advisor._provider is mock_provider
        assert advisor._config is advisor_config
        assert advisor._api_key == "dummy-test-key"
        assert advisor._model == "kimi-k2-0719-preview"

    def test_init_default_model(
        self, mock_provider: MagicMock
    ) -> None:
        """api 段中未指定 model 时使用默认模型。"""
        config: dict[str, Any] = {
            "api": {
                "provider": "moonshot",
                "key": "dummy-key",
            },
        }
        advisor = Advisor(mock_provider, config)
        assert advisor._model == "kimi-k2-0719-preview"

    def test_init_config_without_model_field(
        self, mock_provider: MagicMock
    ) -> None:
        """config 中 api 段不包含 model 字段时使用默认 model。"""
        config: dict[str, Any] = {
            "api": {
                "provider": "moonshot",
                "key": "dummy-key",
            },
        }
        advisor = Advisor(mock_provider, config)
        assert advisor._model == "kimi-k2-0719-preview"


class TestAdvisorAnalyze:
    """analyze 方法。"""

    def test_analyze_no_llm_returns_fallback(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """use_llm=False 时返回 fallback 建议。"""
        advisor = Advisor(mock_provider, advisor_config)
        result = advisor.analyze(sample_game_state, sample_candidates, use_llm=False)
        assert result["fallback"] is True
        assert "recommended_comps" in result
        assert "action_advice" in result
        assert "next_steps" in result
        assert isinstance(result["recommended_comps"], list)
        assert isinstance(result["action_advice"], dict)
        assert isinstance(result["next_steps"], list)

    def test_analyze_llm_success(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """LLM 调用成功时返回结构化建议。"""
        mock_llm_response: dict[str, Any] = {
            "recommended_comps": [
                {
                    "name": "八法师",
                    "confidence": 85,
                    "reason": "持有多个法师棋子，核心棋子齐全",
                    "core_champs_missing": ["瑞兹"],
                }
            ],
            "action_advice": {
                "level": "slow_level",
                "roll": "roll_interest",
                "positioning": "standard",
            },
            "next_steps": ["优先升级到8级搜索瑞兹", "保留蓝霸符给瑞兹"],
        }
        advisor = Advisor(mock_provider, advisor_config)
        with patch.object(advisor, "_call_llm", return_value=mock_llm_response):
            result = advisor.analyze(sample_game_state, sample_candidates, use_llm=True)
        assert result == mock_llm_response
        assert "fallback" not in result

    def test_analyze_llm_returns_none_fallback(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """LLM 调用返回 None 时回退到规则引擎。"""
        advisor = Advisor(mock_provider, advisor_config)
        with patch.object(advisor, "_call_llm", return_value=None):
            result = advisor.analyze(sample_game_state, sample_candidates, use_llm=True)
        assert result["fallback"] is True
        assert "recommended_comps" in result
        assert "action_advice" in result

    def test_analyze_llm_raises_exception_fallback(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """LLM 调用抛出异常时回退到规则引擎。"""
        advisor = Advisor(mock_provider, advisor_config)
        with patch.object(advisor, "_call_llm", side_effect=RuntimeError("API error")):
            result = advisor.analyze(sample_game_state, sample_candidates, use_llm=True)
        assert result["fallback"] is True
        assert "recommended_comps" in result

    def test_analyze_empty_candidates_skips_llm(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
    ) -> None:
        """candidates 为空时直接走 fallback，不调用 LLM。"""
        advisor = Advisor(mock_provider, advisor_config)
        with patch.object(advisor, "_call_llm") as mock_call:
            result = advisor.analyze(sample_game_state, [], use_llm=True)
        mock_call.assert_not_called()
        assert result["fallback"] is True

    def test_analyze_fallback_includes_confidence(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """fallback 结果中 recommended_comps 包含 confidence 字段。"""
        advisor = Advisor(mock_provider, advisor_config)
        result = advisor.analyze(sample_game_state, sample_candidates, use_llm=False)
        if result["recommended_comps"]:
            comp = result["recommended_comps"][0]
            assert "confidence" in comp
            assert comp["confidence"] == 60


class TestAdvisorAnalyzeAugments:
    """analyze_augments 方法。"""

    def test_analyze_augments_llm_success(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """LLM 调用成功时返回海克斯分析结果。"""
        mock_llm_response: dict[str, Any] = {
            "augments": [
                {"name": "法力流系带", "score": 90, "reason": "完美适配法师阵容"},
                {"name": "护卫之心", "score": 70, "reason": "增强前排坦度"},
            ],
            "recommendation": "法力流系带",
        }
        advisor = Advisor(mock_provider, advisor_config)
        augment_options = ["法力流系带", "护卫之心"]
        with patch.object(advisor, "_call_llm", return_value=mock_llm_response):
            result = advisor.analyze_augments(
                sample_game_state, augment_options, sample_candidates
            )
        assert result == mock_llm_response
        assert "fallback" not in result

    def test_analyze_augments_llm_failure_fallback(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """LLM 调用失败时回退到规则引擎。"""
        advisor = Advisor(mock_provider, advisor_config)
        augment_options = ["法力流系带", "护卫之心"]
        with patch.object(advisor, "_call_llm", return_value=None):
            result = advisor.analyze_augments(
                sample_game_state, augment_options, sample_candidates
            )
        assert result["fallback"] is True
        assert "augments" in result
        assert "recommendation" in result

    def test_analyze_augments_empty_options_skips_llm(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """augment_options 为空时不调用 LLM 直接 fallback。"""
        advisor = Advisor(mock_provider, advisor_config)
        with patch.object(advisor, "_call_llm") as mock_call:
            result = advisor.analyze_augments(sample_game_state, [], sample_candidates)
        mock_call.assert_not_called()
        assert result["fallback"] is True
        assert result["augments"] == []
        assert result["recommendation"] == ""


class TestAdvisorFallbackAdvice:
    """_fallback_advice 静态方法。"""

    def test_low_hp_all_in(self) -> None:
        """HP < 30 时 roll = 'all_in'。"""
        game_state: dict[str, Any] = {"hp": 20, "gold": 30}
        result = Advisor._fallback_advice(game_state, [])
        assert result["action_advice"]["level"] == "stay"
        assert result["action_advice"]["roll"] == "all_in"
        assert result["fallback"] is True

    def test_high_gold_roll_interest(self) -> None:
        """gold >= 50 时 roll = 'roll_interest'。"""
        game_state: dict[str, Any] = {"hp": 80, "gold": 60}
        result = Advisor._fallback_advice(game_state, [])
        assert result["action_advice"]["roll"] == "roll_interest"

    def test_low_gold_save(self) -> None:
        """gold < 20 时 roll = 'save'。"""
        game_state: dict[str, Any] = {"hp": 80, "gold": 10}
        result = Advisor._fallback_advice(game_state, [])
        assert result["action_advice"]["roll"] == "save"
        assert result["action_advice"]["level"] == "stay"

    def test_low_hp_takes_priority_over_gold(self) -> None:
        """HP < 30 优先于 gold >= 50。"""
        game_state: dict[str, Any] = {"hp": 15, "gold": 70}
        result = Advisor._fallback_advice(game_state, [])
        assert result["action_advice"]["roll"] == "all_in"
        assert result["action_advice"]["level"] == "stay"

    def test_with_candidates_recommended_comps_non_empty(
        self,
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """有候选阵容时 recommended_comps 不为空。"""
        result = Advisor._fallback_advice(sample_game_state, sample_candidates)
        assert len(result["recommended_comps"]) > 0
        assert result["recommended_comps"][0]["name"] == "八法师"

    def test_with_candidates_next_steps_contains_info(
        self,
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """有候选阵容时 next_steps 包含阵容名。"""
        result = Advisor._fallback_advice(sample_game_state, sample_candidates)
        assert len(result["next_steps"]) > 0
        assert any("八法师" in step for step in result["next_steps"])

    def test_with_candidate_missing_core_next_steps(
        self, sample_game_state: dict[str, Any]
    ) -> None:
        """最佳阵容有缺少的核心棋子时 next_steps 包含提示。"""
        candidates: list[dict[str, Any]] = [
            {
                "composition_id": 1,
                "name": "八法师",
                "tier": "S",
                "playstyle": "运营",
                "description": "",
                "match_score": 15,
                "core_matched": 2,
                "core_total": 4,
                "champion_matched": 4,
                "champion_total": 9,
                "item_matched": 0,
                "item_total": 0,
                "core_champs_missing": ["瑞兹", "辛德拉"],
                "positioning": None,
            },
        ]
        result = Advisor._fallback_advice(sample_game_state, candidates)
        assert any("瑞兹" in step or "辛德拉" in step for step in result["next_steps"])

    def test_no_candidates_default_next_steps(self) -> None:
        """无候选阵容时 next_steps 包含默认建议。"""
        game_state: dict[str, Any] = {"hp": 80, "gold": 30}
        result = Advisor._fallback_advice(game_state, [])
        assert len(result["next_steps"]) > 0

    def test_action_advice_positioning_is_standard(self) -> None:
        """fallback 中 positioning 始终为 'standard'。"""
        game_state: dict[str, Any] = {"hp": 80, "gold": 30}
        result = Advisor._fallback_advice(game_state, [])
        assert result["action_advice"]["positioning"] == "standard"


class TestAdvisorFallbackAugment:
    """_fallback_augment_advice 静态方法。"""

    def test_empty_options_returns_empty(self) -> None:
        """空选项返回空结果。"""
        result = Advisor._fallback_augment_advice([], [])
        assert result["augments"] == []
        assert result["recommendation"] == ""
        assert result["fallback"] is True

    def test_with_options_each_has_name_score_reason(self) -> None:
        """有选项时每个选项都有 name/score/reason。"""
        options = ["经济类强化A", "战力类强化B"]
        result = Advisor._fallback_augment_advice(options, [])
        assert len(result["augments"]) == 2
        for aug in result["augments"]:
            assert "name" in aug
            assert "score" in aug
            assert "reason" in aug
            assert isinstance(aug["score"], int)

    def test_recommendation_is_first_option(self) -> None:
        """推荐为第一个选项。"""
        options = ["经济类强化A", "战力类强化B"]
        result = Advisor._fallback_augment_advice(options, [])
        assert result["recommendation"] == options[0]

    def test_economy_keyword_boosts_score_with_matching_playstyle(self) -> None:
        """经济类海克斯 + 运营型阵容 -> score 提高。"""
        options = ["经济类强化A"]
        candidates: list[dict[str, Any]] = [
            {"name": "八法师", "playstyle": "运营", "tier": "S"},
        ]
        result = Advisor._fallback_augment_advice(options, candidates)
        assert result["augments"][0]["score"] == 80

    def test_combat_keyword_boosts_score_with_matching_playstyle(self) -> None:
        """战力类海克斯 + 连胜型阵容 -> score 提高。"""
        options = ["战力类强化A"]
        candidates: list[dict[str, Any]] = [
            {"name": "六护卫", "playstyle": "连胜", "tier": "A"},
        ]
        result = Advisor._fallback_augment_advice(options, candidates)
        assert result["augments"][0]["score"] == 80

    def test_no_match_uses_default_score(self) -> None:
        """无关键词匹配时使用基准分 50。"""
        options = ["未知强化A"]
        result = Advisor._fallback_augment_advice(options, [])
        assert result["augments"][0]["score"] == 50


class TestAdvisorPromptBuilding:
    """_build_analysis_prompt 和 _build_augment_prompt。"""

    def test_build_analysis_prompt_non_empty(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """_build_analysis_prompt 返回非空字符串，包含关键信息。"""
        advisor = Advisor(mock_provider, advisor_config)
        prompt = advisor._build_analysis_prompt(sample_game_state, sample_candidates)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "八法师" in prompt

    def test_build_analysis_prompt_handles_empty_candidates(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
    ) -> None:
        """空候选阵容时 prompt 仍正常生成。"""
        advisor = Advisor(mock_provider, advisor_config)
        prompt = advisor._build_analysis_prompt(sample_game_state, [])
        assert len(prompt) > 0
        assert "候选阵容" in prompt

    def test_build_analysis_prompt_truncates_to_top_5(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
    ) -> None:
        """候选阵容超过 5 个时只取前 5 个。"""
        advisor = Advisor(mock_provider, advisor_config)
        many_candidates: list[dict[str, Any]] = [
            {
                "composition_id": i,
                "name": f"阵容{i}",
                "tier": "B",
                "playstyle": "运营",
                "match_score": 10 - i,
                "core_champs_missing": [],
            }
            for i in range(10)
        ]
        prompt = advisor._build_analysis_prompt(sample_game_state, many_candidates)
        assert "阵容0" in prompt
        assert "阵容4" in prompt
        assert "阵容5" not in prompt

    def test_build_augment_prompt_non_empty(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
        sample_candidates: list[dict[str, Any]],
    ) -> None:
        """_build_augment_prompt 返回非空字符串，包含关键信息。"""
        advisor = Advisor(mock_provider, advisor_config)
        augment_options = ["法力流系带", "护卫之心", "战力强化"]
        prompt = advisor._build_augment_prompt(
            sample_game_state, augment_options, sample_candidates
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "法力流系带" in prompt
        assert "八法师" in prompt

    def test_build_augment_prompt_candidates_truncated(
        self,
        mock_provider: MagicMock,
        advisor_config: dict[str, Any],
        sample_game_state: dict[str, Any],
    ) -> None:
        """候选阵容超过 3 个时只取前 3 个的阵容名。"""
        advisor = Advisor(mock_provider, advisor_config)
        many_candidates: list[dict[str, Any]] = [
            {"name": f"阵容{i}"} for i in range(5)
        ]
        prompt = advisor._build_augment_prompt(
            sample_game_state, ["选项A"], many_candidates
        )
        assert "阵容0" in prompt
        assert "阵容2" in prompt
        assert "阵容3" not in prompt
