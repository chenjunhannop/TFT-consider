"""对局状态追踪模块。

持续追踪对局状态变化，维护历史快照并检测关键决策点。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class GameStateSnapshot:
    """一回合的快照。"""

    stage: str
    phase: str
    level: int
    gold: int
    hp: int
    board: list[dict[str, Any]]
    bench: list[dict[str, Any]]
    augments: list[dict[str, Any]]
    streak: str
    streak_count: int
    suggestions: dict[str, Any] | None  # 当时的建议
    created_at: datetime


def _extract_names(units: list[dict[str, Any]]) -> list[str]:
    """从棋子列表中提取名称列表，忽略空名。"""
    names: list[str] = []
    for u in units:
        if isinstance(u, dict):
            name = u.get("name")
            if name:
                names.append(str(name))
    return names


class GameState:
    """对局状态追踪器。

    维护当前状态并保留历史快照，全部存储在内存中（不持久化到数据库）。
    """

    def __init__(self, player_name: str = "Player") -> None:
        """初始化对局状态追踪器。

        Args:
            player_name: 玩家名称，用于日志标识。
        """
        self.player_name: str = player_name
        self._history: list[GameStateSnapshot] = []
        self._current: GameStateSnapshot | None = None
        self._started_at: datetime | None = None

    def update(
        self,
        game_state: dict[str, Any],
        suggestions: dict[str, Any] | None = None,
    ) -> GameStateSnapshot:
        """更新当前对局状态并生成快照。

        比较新旧状态，计算增量变化（新棋子、经济变化、血量变化），
        将快照附加到历史列表。

        Args:
            game_state: Spec 002 输出的结构化 JSON。
            suggestions: 当前回合的建议 dict。

        Returns:
            新创建的游戏状态快照。
        """
        now = datetime.now(UTC)

        snapshot = GameStateSnapshot(
            stage=str(game_state.get("stage", "1-1")),
            phase=str(game_state.get("phase", "planning")),
            level=int(game_state.get("level", 1)),
            gold=int(game_state.get("gold", 0)),
            hp=int(game_state.get("hp", 100)),
            board=list(game_state.get("board", [])),
            bench=list(game_state.get("bench", [])),
            augments=list(game_state.get("augments", [])),
            streak=str(game_state.get("streak", "none")),
            streak_count=int(game_state.get("streak_count", 0)),
            suggestions=suggestions,
            created_at=now,
        )

        if self._started_at is None:
            self._started_at = now

        self._history.append(snapshot)
        self._current = snapshot
        return snapshot

    def history(self) -> list[GameStateSnapshot]:
        """返回完整历史快照列表。

        Returns:
            按时间先后顺序排列的所有快照。
        """
        return list(self._history)

    def current(self) -> GameStateSnapshot | None:
        """返回最近一次更新时的快照。

        Returns:
            当前快照，如果没有更新过则返回 None。
        """
        return self._current

    def summary(self) -> dict[str, Any]:
        """生成增量变化摘要。

        比较最近两个快照，计算 new_champs、gold_delta、hp_delta、
        phase_changed、level_up 等增量信息。

        Returns:
            {
                "new_champs": [str],
                "gold_delta": int,
                "hp_delta": int,
                "phase_changed": bool,
                "level_up": bool,
            }
        """
        if len(self._history) < 2:
            return {
                "new_champs": [],
                "gold_delta": 0,
                "hp_delta": 0,
                "phase_changed": False,
                "level_up": False,
            }

        prev = self._history[-2]
        curr = self._history[-1]

        # 新上场的棋子
        prev_names = set(_extract_names(prev.board) + _extract_names(prev.bench))
        curr_names = set(_extract_names(curr.board) + _extract_names(curr.bench))
        new_champs = sorted(curr_names - prev_names)

        gold_delta = curr.gold - prev.gold
        hp_delta = curr.hp - prev.hp
        phase_changed = prev.stage != curr.stage or prev.phase != curr.phase
        level_up = curr.level > prev.level

        return {
            "new_champs": new_champs,
            "gold_delta": gold_delta,
            "hp_delta": hp_delta,
            "phase_changed": phase_changed,
            "level_up": level_up,
        }

    def is_key_decision_point(self) -> bool:
        """检测当前是否处于关键决策点。

        关键决策点包括：
        - 3-2: 升 6 级节点
        - 4-1: 升 7 级节点
        - 4-5: 升 8 级节点
        - 选秀阶段（carousel）

        Returns:
            是否为关键决策点。
        """
        if self._current is None:
            return False

        stage = self._current.stage
        phase = self._current.phase

        if phase == "carousel":
            return True

        # 回合关键节点：stage-phase 组合
        key_stages = {"3-2", "4-1", "4-5"}
        if stage in key_stages:
            return True

        return False

    def should_reconsider(self) -> tuple[bool, str]:
        """检测是否建议转型。

        规则：如果当前最新快照的建议阵容与上一快照的建议阵容不同，
        且当前棋盘的核心棋子与上一轮建议阵容匹配度大幅下降，则表示
        玩家可能偏离了原计划。

        更具体的判断：
        1. 检查上一轮是否有建议阵容
        2. 收集当前棋盘上所有棋子名称
        3. 如果上一轮推荐阵容的核心缺失棋子中，当前棋盘没有新增任何
           原推荐阵容的棋子，且新增了其他阵容的棋子，则建议转型

        Returns:
            (是否建议转型, 转型原因描述)
        """
        if self._current is None or self._current.suggestions is None:
            return (False, "")

        suggestions = self._current.suggestions
        rec_comps = suggestions.get("recommended_comps", [])
        if not rec_comps:
            return (False, "")

        # 获取上一轮推荐阵容的核心缺失棋子
        last_rec = rec_comps[0] if rec_comps else {}
        last_missing = set(last_rec.get("core_champs_missing", []))

        # 当前棋盘上的棋子
        current_board_names = set(_extract_names(self._current.board))
        current_bench_names = set(_extract_names(self._current.bench))
        all_current = current_board_names | current_bench_names

        # 如果上一轮缺少的核心棋子现在都没有，且当前棋盘棋子与推荐阵容差异大
        if last_missing and not (last_missing & all_current):
            # 进一步检查：上一轮推荐阵容的核心缺失棋子完全没有出现
            # 说明玩家可能选了其他方向
            reason = "未在棋盘/备战席上发现推荐阵容缺少的核心棋子，可能已转向其他阵容"
            return (True, reason)

        # 如果没有发生快照更新（只有一个快照），不需要转型
        if len(self._history) < 2:
            return (False, "")

        # 比较连续两轮的棋盘：如果核心棋子大量替换
        prev_snapshot = self._history[-2]
        prev_board_names = set(_extract_names(prev_snapshot.board))
        current_board_champs = all_current

        # 计算保留比例
        if prev_board_names:
            kept = current_board_champs & prev_board_names
            keep_ratio = len(kept) / len(prev_board_names)
            if keep_ratio < 0.4 and len(current_board_champs) > 0:
                reason = f"棋盘棋子大量替换（保留比例 {keep_ratio:.0%}），可能需要重新评估阵容"
                return (True, reason)

        return (False, "")
