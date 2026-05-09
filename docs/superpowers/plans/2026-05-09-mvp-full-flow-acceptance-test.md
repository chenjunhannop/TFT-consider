# MVP 全流程验收测试计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 编写端到端验收测试，覆盖从数据库初始化→阵容匹配→LLM建议→流水线编排→对局追踪→复盘保存的完整 MVP 链路。

**Architecture:** 采用 mock LLM provider 替代真实 Moonshot API，在内存 SQLite 中验证全链路数据流。测试文件 `tests/test_acceptance.py` 独立于现有单元测试，聚焦集成行为而非单模块细节。

**Tech Stack:** Python 3.12+, pytest, SQLAlchemy (in-memory SQLite), unittest.mock, PySide6 (QApplication offscreen)

---

## 待测模块全景

```
ScreenshotCapturer ──→ MoonshotProvider.analyze_screenshot() ──→ game_state (dict)
                                                                      │
                                     ┌────────────────────────────────┘
                                     ▼
                          match_compositions() ──→ candidates (list[dict])
                                     │
                                     ▼
                          Advisor.analyze() ──→ suggestions (dict)
                                     │
                                     ▼
                          GameState.update() ──→ snapshot + summary
                                     │
                                     ▼
                          save_replay() ──→ SQLite GameReplay
```

全流程关键数据流：
1. `game_state` dict 从 LLM 识别输出 → 包含 board, bench, items, level, gold, hp, stage, phase, streak, augments
2. `candidates` list 从 `match_compositions()` 输出 → 每个含 composition_id, name, tier, match_score, core_matched, core_champs_missing, positioning 等
3. `suggestions` dict 从 `Advisor.analyze()` 输出 → 含 recommended_comps, action_advice, next_steps
4. `result` dict 从 `AdvicePipeline.process_frame()` 输出 → 含 summary, is_key_point, candidates, suggestions, reconsider
5. `GameStateSnapshot` → board, bench, level, gold, hp, stage, phase, streak, suggestions, created_at

---




### Task 1: 测试骨架 — 创建文件 + fixtures

**Files:**
- Create: `tests/test_acceptance.py`

- [ ] **Step 1: 创建测试文件骨架 + 全部 fixtures**

```python
"""MVP 全流程验收测试。

覆盖完整链路：
  数据库初始化 → 阵容匹配 → LLM 建议 → 流水线编排 → 对局追踪 → 复盘保存
使用 mock MoonshotProvider 替代真实 API，在 :memory: SQLite 中运行。
"""

from __future__ import annotations

import json
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
from tft_consider.tracker.game_state import GameState, GameStateSnapshot
from tft_consider.tracker.pipeline import AdvicePipeline
from tft_consider.tracker.replay import list_replays, save_replay
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
def mock_config() -> dict[str, Any]:
    """构造最小有效配置，含假 API key。"""
    return {
        "api": {
            "provider": "moonshot",
            "key": "ZmFrZS1hcGkta2V5LWZvci10ZXN0aW5n",
            "model": "kimi-k2-0719-preview",
        },
        "ui": {"theme": "dark", "opacity": 0.85},
        "data": {"sync_interval_hours": 6, "auto_sync": False},
        "screenshot": {"interval_ms": 2000, "temp_dir": ""},
        "log": {"level": "DEBUG"},
    }


# ---------------------------------------------------------------------------
# Mock LLM Provider
# ---------------------------------------------------------------------------


class MockVisionProvider(BaseProvider):
    """模拟视觉识别 provider，返回预置 game_state。"""

    def __init__(self, config: dict[str, Any], fixed_result: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._fixed_result = fixed_result or {}
        self.analyze_screenshot_calls: list[Path] = []

    def analyze_screenshot(self, image_path: Path) -> dict[str, Any] | None:
        self.analyze_screenshot_calls.append(image_path)
        return dict(self._fixed_result)

    def provider_name(self) -> str:
        return "mock-vision"
```

- [ ] **Step 2: 验证文件可被 pytest 收集**

```bash
python -m pytest tests/test_acceptance.py --collect-only -q
```
预期: `no tests ran` (0 tests — fixtures 不含 test_ 前缀不会被收集)

- [ ] **Step 3: 提交**

```bash
git add tests/test_acceptance.py
git commit -m "test: add acceptance test skeleton with fixtures and MockVisionProvider"
```

---

### Task 2: 场景一 — 数据库初始化 + 数据导入 + 阵容匹配

**Files:**
- Modify: `tests/test_acceptance.py` (追加测试类)

- [ ] **Step 1: 编写测试**

```python
class TestScenario1DatabaseAndMatch:
    """场景一：数据库就位 → 阵容匹配可返回候选。"""

    def test_import_populates_compositions(self, db_session: models.Session, populated_db: None) -> None:
        """验证导入后 compositions 表有数据。"""
        comps = db_session.query(models.Composition).all()
        assert len(comps) > 0, "导入后应有至少 1 条阵容数据"

    def test_match_compositions_returns_candidates(
        self, db_session: models.Session, populated_db: None
    ) -> None:
        """给定含已知棋子的 game_state，match_compositions 应返回非空候选列表。"""
        game_state: dict[str, Any] = {
            "level": 6, "gold": 50, "hp": 80,
            "stage": "3-2", "phase": "planning",
            "streak": "win", "streak_count": 2,
            "board": [
                {"name": "盖伦", "star": 2, "items": ["狂徒铠甲"]},
                {"name": "拉克丝", "star": 2, "items": []},
            ],
            "bench": [{"name": "波比", "star": 1}],
            "items": ["反曲之弓"], "augments": [],
        }

        candidates = match_compositions(game_state, top_n=5)
        assert isinstance(candidates, list), "应返回 list"
        for c in candidates:
            assert "composition_id" in c
            assert "name" in c
            assert "tier" in c
            assert "match_score" in c
            assert "core_matched" in c
            assert "core_total" in c
            assert "champion_matched" in c
            assert "champion_total" in c
            assert "core_champs_missing" in c
            assert "positioning" in c

    def test_match_compositions_empty_state_returns_results(
        self, db_session: models.Session, populated_db: None
    ) -> None:
        """空棋盘也应返回阵容列表（只是匹配分低）。"""
        empty_state: dict[str, Any] = {
            "level": 1, "gold": 0, "hp": 100,
            "stage": "1-1", "phase": "planning",
            "streak": "none", "streak_count": 0,
            "board": [], "bench": [], "items": [], "augments": [],
        }
        candidates = match_compositions(empty_state, top_n=3)
        assert isinstance(candidates, list)

    def test_match_compositions_db_not_initialized_returns_empty(self) -> None:
        """数据库未初始化时不应抛异常，返回空列表。"""
        if models._engine is not None:
            models._engine.dispose()
        models._engine = None
        models._SessionLocal = None
        try:
            empty_state: dict[str, Any] = {
                "level": 1, "gold": 0, "hp": 100,
                "stage": "1-1", "phase": "planning",
                "streak": "none", "streak_count": 0,
                "board": [], "bench": [], "items": [], "augments": [],
            }
            candidates = match_compositions(empty_state, top_n=3)
            assert candidates == []
        finally:
            pass
```

- [ ] **Step 2: 运行测试验证通过**

```bash
pytest tests/test_acceptance.py::TestScenario1DatabaseAndMatch -v --tb=short
```
预期: 4 passed

- [ ] **Step 3: 提交**

```bash
git add tests/test_acceptance.py
git commit -m "test: add Scenario 1 — database init + composition matching"
```

---

### Task 3: 场景二 — Advisor 生成 LLM 建议 (mock API)

**Files:**
- Modify: `tests/test_acceptance.py` (追加测试类)

- [ ] **Step 1: 编写测试 — mock httpx 调用 Moonshot API 文本模式**

```python
class TestScenario2AdvisorAdvice:
    """场景二：Advisor 基于候选阵容 + 游戏状态生成建议。"""

    def test_advisor_analyze_returns_structured_suggestions(
        self, db_session: models.Session, populated_db: None, mock_config: dict[str, Any]
    ) -> None:
        """mock Moonshot API 响应，验证 Advisor.analyze 返回完整建议结构。"""
        game_state: dict[str, Any] = {
            "level": 7, "gold": 32, "hp": 45,
            "stage": "4-1", "phase": "planning",
            "streak": "loss", "streak_count": 2,
            "board": [
                {"name": "盖伦", "star": 2, "items": ["狂徒铠甲", "荆棘背心"]},
                {"name": "拉克丝", "star": 2, "items": ["蓝霸符"]},
                {"name": "薇古丝", "star": 1, "items": []},
            ],
            "bench": [],
            "items": ["无用大棒"],
            "augments": [{"name": "星界赐福", "tier": "silver"}],
        }

        candidates = match_compositions(game_state, top_n=3)
        assert len(candidates) > 0, "需要有候选阵容才能测试 Advisor"

        mock_response = {
            "recommended_comps": [
                {
                    "name": candidates[0]["name"],
                    "confidence": 85,
                    "reason": "核心棋子到位，装备匹配度高",
                    "core_champs_missing": [],
                }
            ],
            "action_advice": {
                "level": "rush_level",
                "roll": "roll_interest",
                "positioning": "standard",
            },
            "next_steps": [
                "速升 7 级补充阵容深度",
                "保留盖伦核心装备",
            ],
        }

        mock_httpx_response = MagicMock()
        mock_httpx_response.status_code = 200
        mock_httpx_response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps(mock_response, ensure_ascii=False)}}
            ]
        }

        mock_provider = MockVisionProvider(mock_config)
        advisor = Advisor(mock_provider, mock_config)

        with patch("httpx.Client.post", return_value=mock_httpx_response):
            result = advisor.analyze(game_state, candidates)

        assert "recommended_comps" in result
        assert "action_advice" in result
        assert "next_steps" in result
        rec = result["recommended_comps"]
        assert isinstance(rec, list)
        if rec:
            assert "name" in rec[0]
            assert "confidence" in rec[0]
            assert "reason" in rec[0]

    def test_advisor_llm_failure_falls_back_to_rules(
        self, db_session: models.Session, populated_db: None, mock_config: dict[str, Any]
    ) -> None:
        """LLM 调用失败时，应降级到规则引擎返回合理建议。"""
        game_state: dict[str, Any] = {
            "level": 5, "gold": 15, "hp": 22,
            "stage": "4-1", "phase": "planning",
            "streak": "loss", "streak_count": 5,
            "board": [{"name": "盖伦", "star": 1, "items": []}],
            "bench": [], "items": [], "augments": [],
        }

        candidates = match_compositions(game_state, top_n=3)
        mock_provider = MockVisionProvider(mock_config)
        advisor = Advisor(mock_provider, mock_config)

        with patch("httpx.Client.post", side_effect=Exception("network error")):
            result = advisor.analyze(game_state, candidates)

        assert "recommended_comps" in result
        assert "action_advice" in result
        assert "next_steps" in result
        # 低血量应触发 all_in 建议
        assert result["action_advice"]["roll"] == "all_in"
```

- [ ] **Step 2: 运行测试验证通过**

```bash
pytest tests/test_acceptance.py::TestScenario2AdvisorAdvice -v --tb=short
```
预期: 2 passed

- [ ] **Step 3: 提交**

```bash
git add tests/test_acceptance.py
git commit -m "test: add Scenario 2 — Advisor LLM advice with mock API"
```

---

### Task 4: 场景三 — GameState 多回合对局追踪

**Files:**
- Modify: `tests/test_acceptance.py` (追加测试类)

- [ ] **Step 1: 编写测试 — 模拟完整 6 回合对局流程**

```python
class TestScenario3GameStateTracking:
    """场景三：多回合对局追踪 — 增量变化、关键决策点、转型检测。"""

    @staticmethod
    def _make_state(
        stage: str = "2-1",
        phase: str = "planning",
        level: int = 4,
        gold: int = 30,
        hp: int = 100,
        board: list[dict[str, Any]] | None = None,
        bench: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "stage": stage, "phase": phase,
            "level": level, "gold": gold, "hp": hp,
            "streak": "none", "streak_count": 0,
            "board": board or [], "bench": bench or [],
            "items": [], "augments": [],
        }

    def test_full_6_round_simulation(self) -> None:
        """模拟 6 回合完整对局，验证 state 追踪的每个环节。"""
        gs = GameState(player_name="TestPlayer")

        # R1: 初始
        s1 = gs.update(self._make_state("2-1", "planning", level=4, gold=10, hp=100))
        assert isinstance(s1, GameStateSnapshot)
        assert s1.level == 4
        assert len(gs.history()) == 1

        # R2: 升 5 级，金币增加
        s2 = gs.update(self._make_state(
            "2-3", "planning", level=5, gold=22, hp=98,
            board=[{"name": "盖伦", "star": 2, "items": []}],
        ))
        summary = gs.summary()
        assert summary["level_up"] is True
        assert summary["gold_delta"] == 12
        assert summary["hp_delta"] == -2
        assert "盖伦" in summary["new_champs"]

        # R3: 3-2 关键决策点
        gs.update(self._make_state(
            "3-2", "planning", level=6, gold=45, hp=85,
            board=[{"name": "盖伦", "star": 2, "items": ["狂徒铠甲"]}],
            bench=[{"name": "拉克丝", "star": 1, "items": []}],
        ))
        assert gs.is_key_decision_point() is True

        # R4: 选秀阶段
        gs.update(self._make_state("3-4", "carousel", level=6, gold=47, hp=83))
        assert gs.is_key_decision_point() is True

        # R5: 普通回合
        gs.update(self._make_state("3-5", "planning", level=6, gold=50, hp=78))
        assert gs.is_key_decision_point() is False

        # R6: 4-1 关键节点
        gs.update(self._make_state("4-1", "planning", level=7, gold=48, hp=52))
        assert gs.is_key_decision_point() is True

        history = gs.history()
        assert len(history) == 6
        assert history[0].hp == 100
        assert history[-1].hp == 52

    def test_summary_new_champs_detected(self) -> None:
        """新棋子上场应被增量摘要检测到。"""
        gs = GameState()
        gs.update(self._make_state("2-1", board=[{"name": "盖伦", "star": 1, "items": []}]))
        gs.update(self._make_state(
            "2-2",
            board=[{"name": "盖伦", "star": 1, "items": []}],
            bench=[{"name": "薇古丝", "star": 1, "items": []}],
        ))
        assert "薇古丝" in gs.summary()["new_champs"]

    def test_reconsider_when_board_changes_radically(self) -> None:
        """棋盘棋子大量替换时应触发转型检测。"""
        gs = GameState()
        suggestions: dict[str, Any] = {
            "recommended_comps": [
                {"name": "法师阵容", "confidence": 80, "core_champs_missing": ["拉克丝"]}
            ],
            "action_advice": {"level": "slow_level", "roll": "roll_interest", "positioning": "standard"},
            "next_steps": ["等拉克丝"],
        }
        gs.update(self._make_state(
            "3-2",
            board=[
                {"name": "盖伦", "star": 2, "items": []},
                {"name": "薇古丝", "star": 2, "items": []},
                {"name": "安妮", "star": 2, "items": []},
            ],
        ), suggestions=suggestions)
        gs.update(self._make_state(
            "3-3",
            board=[
                {"name": "艾希", "star": 2, "items": []},
                {"name": "瑟庄妮", "star": 2, "items": []},
                {"name": "猪妹", "star": 1, "items": []},
            ],
        ))
        should, reason = gs.should_reconsider()
        assert should is True
        assert len(reason) > 0
```

- [ ] **Step 2: 运行测试验证通过**

```bash
pytest tests/test_acceptance.py::TestScenario3GameStateTracking -v --tb=short
```
预期: 3 passed

- [ ] **Step 3: 提交**

```bash
git add tests/test_acceptance.py
git commit -m "test: add Scenario 3 — multi-round game state tracking"
```

---

### Task 5: 场景四 — AdvicePipeline 全流程编排

**Files:**
- Modify: `tests/test_acceptance.py` (追加测试类)

- [ ] **Step 1: 编写测试 — 验证 Pipeline 串联 match → advisor → state → summary**

```python
class TestScenario4AdvicePipeline:
    """场景四：AdvicePipeline.process_frame() 全流程编排。"""

    def test_pipeline_process_frame_returns_complete_result(
        self, db_session: models.Session, populated_db: None, mock_config: dict[str, Any]
    ) -> None:
        """单帧处理应返回 summary, is_key_point, candidates, suggestions, reconsider。"""
        mock_response = {
            "recommended_comps": [
                {"name": "法师阵容", "confidence": 80, "reason": "装备和经济支持", "core_champs_missing": ["拉克丝"]}
            ],
            "action_advice": {"level": "rush_level", "roll": "roll_interest", "positioning": "standard"},
            "next_steps": ["速升 7", "找拉克丝"],
        }
        mock_http = MagicMock()
        mock_http.status_code = 200
        mock_http.json.return_value = {
            "choices": [{"message": {"content": json.dumps(mock_response, ensure_ascii=False)}}]
        }

        provider = MockVisionProvider(mock_config)
        pipeline = AdvicePipeline(provider, mock_config)

        game_state: dict[str, Any] = {
            "level": 6, "gold": 45, "hp": 72,
            "stage": "3-2", "phase": "planning",
            "streak": "win", "streak_count": 3,
            "board": [
                {"name": "盖伦", "star": 2, "items": ["狂徒铠甲"]},
                {"name": "薇古丝", "star": 2, "items": []},
            ],
            "bench": [{"name": "安妮", "star": 1, "items": []}],
            "items": ["反曲之弓"], "augments": [],
        }

        with patch("httpx.Client.post", return_value=mock_http):
            result = pipeline.process_frame(game_state)

        assert "summary" in result
        assert "is_key_point" in result
        assert "candidates" in result
        assert "suggestions" in result
        assert "reconsider" in result
        assert result["is_key_point"] is True
        assert isinstance(result["candidates"], list)
        suggestions = result["suggestions"]
        assert "recommended_comps" in suggestions
        assert "action_advice" in suggestions
        assert "next_steps" in suggestions

    def test_pipeline_multiple_frames_build_history(
        self, db_session: models.Session, populated_db: None, mock_config: dict[str, Any]
    ) -> None:
        """多次调用 process_frame 应在内部 GameState 中累积历史。"""
        mock_response = {
            "recommended_comps": [
                {"name": "法师", "confidence": 80, "reason": "测试", "core_champs_missing": []}
            ],
            "action_advice": {"level": "slow_level", "roll": "save", "positioning": "standard"},
            "next_steps": ["存钱"],
        }
        mock_http = MagicMock()
        mock_http.status_code = 200
        mock_http.json.return_value = {
            "choices": [{"message": {"content": json.dumps(mock_response, ensure_ascii=False)}}]
        }

        provider = MockVisionProvider(mock_config)
        pipeline = AdvicePipeline(provider, mock_config)

        base_state: dict[str, Any] = {
            "level": 4, "gold": 20, "hp": 100, "stage": "2-1",
            "phase": "planning", "streak": "none", "streak_count": 0,
            "board": [{"name": "盖伦", "star": 1, "items": []}],
            "bench": [], "items": [], "augments": [],
        }

        with patch("httpx.Client.post", return_value=mock_http):
            pipeline.process_frame(dict(base_state))
            state2 = dict(base_state)
            state2["stage"] = "2-2"
            state2["gold"] = 28
            state2["hp"] = 95
            state2["board"] = [{"name": "盖伦", "star": 2, "items": []}]
            r2 = pipeline.process_frame(state2)

        assert r2["summary"]["gold_delta"] == 8
        assert r2["summary"]["hp_delta"] == -5

    def test_pipeline_empty_board_no_crash(
        self, db_session: models.Session, populated_db: None, mock_config: dict[str, Any]
    ) -> None:
        """空棋盘/空 bench 不应导致 pipeline 崩溃。"""
        mock_response = {
            "recommended_comps": [],
            "action_advice": {"level": "slow_level", "roll": "save", "positioning": "standard"},
            "next_steps": ["先攒经济，观察来牌"],
        }
        mock_http = MagicMock()
        mock_http.status_code = 200
        mock_http.json.return_value = {
            "choices": [{"message": {"content": json.dumps(mock_response, ensure_ascii=False)}}]
        }

        provider = MockVisionProvider(mock_config)
        pipeline = AdvicePipeline(provider, mock_config)

        empty_state: dict[str, Any] = {
            "level": 1, "gold": 0, "hp": 100, "stage": "1-1",
            "phase": "planning", "streak": "none", "streak_count": 0,
            "board": [], "bench": [], "items": [], "augments": [],
        }

        with patch("httpx.Client.post", return_value=mock_http):
            result = pipeline.process_frame(empty_state)

        assert result["is_key_point"] is False
        assert isinstance(result["candidates"], list)
        assert "suggestions" in result
```

- [ ] **Step 2: 运行测试验证通过**

```bash
pytest tests/test_acceptance.py::TestScenario4AdvicePipeline -v --tb=short
```
预期: 3 passed

- [ ] **Step 3: 提交**

```bash
git add tests/test_acceptance.py
git commit -m "test: add Scenario 4 — AdvicePipeline full orchestration"
```

---

### Task 6: 场景五 — 复盘保存 + 历史查询

**Files:**
- Modify: `tests/test_acceptance.py` (追加测试类)

- [ ] **Step 1: 编写测试 — save_replay 持久化 + list_replays 查询**

```python
class TestScenario5ReplayPersistence:
    """场景五：对局结束后复盘保存到 SQLite + 历史查询。"""

    def test_save_and_list_replay(self, db_session: models.Session) -> None:
        """模拟完整对局后保存复盘，验证可查询。"""
        gs = GameState(player_name="TestPlayer")
        for stage, level, gold, hp in [
            ("2-1", 4, 10, 100),
            ("2-3", 5, 22, 98),
            ("3-1", 6, 35, 90),
            ("3-4", 6, 38, 85),
            ("4-1", 7, 45, 60),
        ]:
            gs.update({
                "stage": stage, "phase": "planning",
                "level": level, "gold": gold, "hp": hp,
                "streak": "none", "streak_count": 0,
                "board": [{"name": "盖伦", "star": 2, "items": ["狂徒铠甲"]}],
                "bench": [], "items": [], "augments": [],
            })

        assert len(gs.history()) == 5
        replay_id = save_replay(gs, final_rank=3)
        assert replay_id > 0

        replays = list_replays(limit=10)
        assert len(replays) >= 1
        latest = replays[0]
        assert latest["player_name"] == "TestPlayer"
        assert latest["final_rank"] == 3
        assert latest["total_rounds"] == 5
        assert latest["started_at"] != ""
        assert latest["ended_at"] != ""

    def test_save_replay_no_snapshots_raises(self) -> None:
        """无快照时 save_replay 应抛出 RuntimeError。"""
        gs = GameState()
        with pytest.raises(RuntimeError, match="没有对局快照数据"):
            save_replay(gs)

    def test_list_replays_empty_returns_empty_list(self, db_session: models.Session) -> None:
        """全新数据库 list_replays 应返回空列表。"""
        replays = list_replays(limit=5)
        assert replays == []
```

- [ ] **Step 2: 运行测试验证通过**

```bash
pytest tests/test_acceptance.py::TestScenario5ReplayPersistence -v --tb=short
```
预期: 3 passed

- [ ] **Step 3: 提交**

```bash
git add tests/test_acceptance.py
git commit -m "test: add Scenario 5 — replay persistence and history query"
```

---

### Task 7: 全量验证 + 质量门禁

**Files:**
- Modify: 无 (验证阶段)

- [ ] **Step 1: 运行全量测试**

```bash
pytest tests/ -v --tb=short
```
预期: 原有 544 + 新增 16 = 560 passed

- [ ] **Step 2: 运行 ruff + mypy**

```bash
python -m ruff check tests/test_acceptance.py
python -m mypy --strict tests/test_acceptance.py
```
预期: All checks passed, Success: no issues found

- [ ] **Step 3: 提交 (如有 lint 修复)**

```bash
git add tests/test_acceptance.py
git commit -m "chore: final quality gate fixes for acceptance tests"
```

---

## 验证清单

- [ ] 场景一：数据库初始化 + 阵容匹配 (4 tests)
- [ ] 场景二：Advisor LLM 建议 + mock API (2 tests)
- [ ] 场景三：6 回合对局追踪 + 增量变化 + 关键节点 + 转型检测 (3 tests)
- [ ] 场景四：AdvicePipeline 全流程编排 (3 tests)
- [ ] 场景五：复盘保存 + 历史查询 (3 tests)
- [ ] ruff + mypy + pytest 全量 560 passed

## 自审查

### 1. Spec 覆盖检查

原 Spec 001-010 的 MVP 链路均已覆盖：
- Spec 003 (数据库): 场景一 — import + match
- Spec 005 (引擎): 场景二 — Advisor LLM
- Spec 006 (追踪): 场景三 — GameState
- Spec 006 + 002 + 005: 场景四 — Pipeline 串联
- Spec 006 (复盘): 场景五 — save_replay

### 2. Placeholder 扫描

无 TBD/TODO/占位符。

### 3. 类型一致性

- `game_state: dict[str, Any]` — 全场景统一使用
- `candidates: list[dict[str, Any]]` — 与 `match_compositions` 返回类型一致
- `GameStateSnapshot` — 字段名与 `game_state.py:17-29` 一致
- `mock_config` — 与 `config.py:DEFAULT_CONFIG` 结构一致
