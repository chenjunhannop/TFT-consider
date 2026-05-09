"""建议流水线模块。

整合截图识别 -> 阵容匹配 -> LLM 建议的完整流水线。
"""

from __future__ import annotations

import logging
from typing import Any

from tft_consider.engine.advisor import Advisor
from tft_consider.engine.matcher import match_compositions
from tft_consider.tracker.game_state import GameState
from tft_consider.tracker.replay import save_replay
from tft_consider.vision.base import BaseProvider

logger = logging.getLogger(__name__)


class AdvicePipeline:
    """整合截图识别 -> 阵容匹配 -> LLM 建议的完整流水线。

    每个回合调用 process_frame() 完成：
    1. 更新对局状态
    2. 关键决策点检测
    3. 阵容匹配
    4. LLM 建议生成
    5. 转型检测
    """

    def __init__(
        self,
        provider: BaseProvider,
        config: dict[str, Any],
    ) -> None:
        """初始化建议流水线。

        Args:
            provider: 多模态 LLM provider 实例。
            config: 应用配置字典。
        """
        self._provider = provider
        self._config = config
        self._advisor = Advisor(provider, config)
        self._game_state = GameState()

    def process_frame(self, game_state: dict[str, Any]) -> dict[str, Any]:
        """处理一帧游戏状态，生成完整建议。

        完整流程：
        1. 更新 GameState 并获取增量变化摘要
        2. 判断是否处于关键决策点
        3. 调用阵容匹配获取候选阵容
        4. 调用 Advisor 生成 LLM 建议
        5. 检查是否需要转型
        6. 将建议关联到当前快照

        Args:
            game_state: Spec 002 输出的结构化 JSON，含 board, bench, items,
                        stage, phase, level, gold, hp, streak, augments 等。

        Returns:
            {
                "summary": dict,          # 增量变化摘要
                "is_key_point": bool,     # 是否关键决策点
                "candidates": list,       # 候选阵容 Top 5
                "suggestions": dict,      # LLM 建议
                "reconsider": [bool, str],  # 转型检测结果
            }
        """
        # 1. 先进行阵容匹配（在更新状态之前，因为需要当前状态的棋子信息）
        candidates = match_compositions(game_state, top_n=5)

        # 2. 调用 Advisor 生成建议
        suggestions = self._advisor.analyze(game_state, candidates)

        # 3. 更新 GameState（附带建议）
        self._game_state.update(game_state, suggestions)

        # 4. 获取增量变化
        summary = self._game_state.summary()

        # 5. 判断关键决策点
        is_key = self._game_state.is_key_decision_point()

        # 6. 转型检测
        reconsider = self._game_state.should_reconsider()

        result: dict[str, Any] = {
            "summary": summary,
            "is_key_point": is_key,
            "candidates": candidates,
            "suggestions": suggestions,
            "reconsider": reconsider,
        }

        logger.debug(
            "process_frame: stage=%s phase=%s key=%s reconsider=%s",
            game_state.get("stage"),
            game_state.get("phase"),
            is_key,
            reconsider[0],
        )

        return result

    def process_augments(
        self,
        game_state: dict[str, Any],
        augment_options: list[str],
    ) -> dict[str, Any]:
        """处理海克斯强化选择。

        在海克斯选择阶段调用，分析各选项与候选阵容的适配度。

        Args:
            game_state: 当前游戏状态。
            augment_options: 可选的海克斯强化名称列表。

        Returns:
            海克斯分析结果 dict，包含 augments 列表和 recommendation。
        """
        candidates = match_compositions(game_state, top_n=3)
        result = self._advisor.analyze_augments(game_state, augment_options, candidates)
        logger.debug("process_augments: options=%d recommendation=%s",
                     len(augment_options), result.get("recommendation"))
        return result

    def on_game_end(self, final_rank: int | None = None) -> int:
        """对局结束时调用，保存完整复盘记录。

        Args:
            final_rank: 最终排名 (1-8)，None 表示未知。

        Returns:
            新创建的 GameReplay 记录 ID。
        """
        logger.info("对局结束，保存复盘记录: final_rank=%s", final_rank)
        return save_replay(self._game_state, final_rank)

    @property
    def game_state(self) -> GameState:
        """返回内部 GameState 实例。"""
        return self._game_state
