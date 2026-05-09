"""LLM 阵容建议引擎。

组合 matcher + LLM provider，将游戏状态 + 候选阵容发给 LLM，
生成最终的阵容建议和操作指导。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from tft_consider.config import get_api_key
from tft_consider.vision.base import BaseProvider

logger = logging.getLogger(__name__)

MOONSHOT_API_URL = "https://api.moonshot.cn/v1/chat/completions"
_DEFAULT_MODEL = "kimi-k2-0719-preview"
_MAX_RETRIES = 2

_ADVISOR_SYSTEM_PROMPT = """你是一位云顶之弈（TFT）顶级教练。
根据当前游戏状态和候选阵容数据，给出最优的阵容选择和操作建议。

返回严格的 JSON 格式，结构如下：
{
  "recommended_comps": [
    {
      "name": "阵容名称",
      "confidence": 85,
      "reason": "推荐理由（中文，简洁）",
      "core_champs_missing": ["缺少的核心棋子名"]
    }
  ],
  "action_advice": {
    "level": "stay | slow_level | rush_level",
    "roll": "save | roll_interest | roll_down | all_in",
    "positioning": "standard | anti_assassin | anti_aoe"
  },
  "next_steps": ["具体下一步操作建议1", "具体下一步操作建议2"]
}

操作建议规则：
- level: stay(停等级), slow_level(慢升), rush_level(速升)
- roll: save(存钱), roll_interest(吃利息D), roll_down(大D到一定经济), all_in(梭哈)
- positioning: standard(标准站位), anti_assassin(防刺客), anti_aoe(防AOE)

只返回 JSON，不要其他内容。"""


class Advisor:
    """LLM 阵容建议引擎。

    组合 matcher 匹配结果，通过 LLM（Moonshot API 文本模式）生成
    最终的阵容建议、操作指导和海克斯分析。
    """

    def __init__(self, provider: BaseProvider, config: dict[str, Any]) -> None:
        """初始化 Advisor。

        Args:
            provider: 多模态 provider 实例（保留接口，当前 advisor 不直接使用）。
            config: 应用配置字典，需包含 api.key 和 api.model 项。
        """
        self._provider = provider
        self._config = config
        self._api_key = get_api_key(config)
        api_cfg = config.get("api", {})
        if isinstance(api_cfg, dict):
            self._model: str = str(api_cfg.get("model", _DEFAULT_MODEL))
        else:
            self._model = _DEFAULT_MODEL

    def analyze(
        self,
        game_state: dict[str, Any],
        candidates: list[dict[str, Any]],
        use_llm: bool = True,
    ) -> dict[str, Any]:
        """分析游戏状态并给出阵容建议。

        1. 构建中文 prompt，包含当前游戏状态和候选阵容 Top 5。
        2. 如果 use_llm=True 且 LLM 调用成功，返回结构化 JSON 建议。
        3. 如果 use_llm=False 或 LLM 调用失败，使用 fallback 规则。

        Args:
            game_state: Spec 002 输出的结构化 JSON。
            candidates: match_compositions() 返回的候选阵容列表。
            use_llm: 是否使用 LLM 推理，默认 True。

        Returns:
            {
                "recommended_comps": [{"name", "confidence", "reason", "core_champs_missing"}],
                "action_advice": {"level", "roll", "positioning"},
                "next_steps": [str],
                "fallback": bool,  # 仅 fallback 模式下出现
            }
        """
        if use_llm and candidates:
            try:
                prompt = self._build_analysis_prompt(game_state, candidates)
                result = self._call_llm(prompt)
                if result is not None:
                    return result
            except Exception:
                logger.exception("LLM 分析失败，回退到规则引擎")

        return self._fallback_advice(game_state, candidates)

    def analyze_augments(
        self,
        game_state: dict[str, Any],
        augment_options: list[str],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """分析海克斯强化选项与候选阵容的适配度。

        Args:
            game_state: 当前游戏状态。
            augment_options: 海克斯强化选项列表（中文名称）。
            candidates: match_compositions() 返回的候选阵容列表。

        Returns:
            {
                "augments": [
                    {"name": str, "score": int, "reason": str},
                ],
                "recommendation": str,  # 推荐的海克斯名称
                "fallback": bool,  # 仅 fallback 模式下出现
            }
        """
        if candidates and augment_options:
            try:
                prompt = self._build_augment_prompt(
                    game_state, augment_options, candidates
                )
                result = self._call_llm(prompt)
                if result is not None:
                    return result
            except Exception:
                logger.exception("LLM 海克斯分析失败，回退到规则引擎")

        return self._fallback_augment_advice(augment_options, candidates)

    # --- 内部方法 -------------------------------------------------------------

    def _build_analysis_prompt(
        self,
        game_state: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> str:
        """构建阵容分析 prompt。"""
        # 精简 game_state：只保留 LLM 决策所需的关键字段
        summary = {
            "level": game_state.get("level", 1),
            "gold": game_state.get("gold", 0),
            "hp": game_state.get("hp", 100),
            "stage": game_state.get("stage", "1-1"),
            "phase": game_state.get("phase", "planning"),
            "streak": game_state.get("streak", "none"),
            "streak_count": game_state.get("streak_count", 0),
            "board": [
                {
                    "name": c.get("name", ""),
                    "star": c.get("star", 1),
                    "items": c.get("items", []),
                }
                for c in game_state.get("board", [])
            ],
            "bench": [
                {"name": c.get("name", ""), "star": c.get("star", 1)}
                for c in game_state.get("bench", [])
            ],
            "augments": [
                a.get("name", "") for a in game_state.get("augments", []) if a.get("picked")
            ],
        }

        # 精简 candidates
        cand_summary = []
        for c in candidates[:5]:
            cand_summary.append({
                "name": c.get("name", ""),
                "tier": c.get("tier", ""),
                "playstyle": c.get("playstyle", ""),
                "match_score": c.get("match_score", 0),
                "core_champs_missing": c.get("core_champs_missing", []),
            })

        prompt = f"""当前游戏状态：
{json.dumps(summary, ensure_ascii=False, indent=2)}

候选阵容（按匹配分数排序）：
{json.dumps(cand_summary, ensure_ascii=False, indent=2)}

请根据以上信息，给出最优的阵容选择和操作建议。只返回 JSON。"""
        return prompt

    def _build_augment_prompt(
        self,
        game_state: dict[str, Any],
        augment_options: list[str],
        candidates: list[dict[str, Any]],
    ) -> str:
        """构建海克斯分析 prompt。"""
        summary = {
            "level": game_state.get("level", 1),
            "stage": game_state.get("stage", "1-1"),
            "streak": game_state.get("streak", "none"),
        }
        cand_names = [c.get("name", "") for c in candidates[:3]]

        prompt = f"""当前游戏状态：
{json.dumps(summary, ensure_ascii=False, indent=2)}

可选海克斯强化：
{json.dumps(augment_options, ensure_ascii=False)}

候选阵容：{", ".join(cand_names)}

请分析每个海克斯强化与候选阵容的适配度，为每个海克斯打分（0-100分），并给出最终推荐。
返回 JSON 格式：
{{
  "augments": [
    {{"name": "海克斯名称", "score": 85, "reason": "适配理由"}}
  ],
  "recommendation": "推荐的海克斯名称"
}}
只返回 JSON。"""
        return prompt

    def _call_llm(self, prompt: str) -> dict[str, Any] | None:
        """调用 Moonshot API 文本模式。

        Args:
            prompt: 用户提示词文本。

        Returns:
            解析后的 JSON dict，失败时返回 None。
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _ADVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self._call_api(payload, headers, attempt)
            except Exception as exc:
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "Advisor LLM 调用失败 (attempt %d/%d)，准备重试: %s",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )
                else:
                    logger.error(
                        "Advisor LLM 调用失败，已达最大重试次数 (%d): %s",
                        _MAX_RETRIES,
                        exc,
                    )
        return None

    def _call_api(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        attempt: int,
    ) -> dict[str, Any] | None:
        """发送 HTTP 请求并解析响应。

        Args:
            payload: JSON 请求体。
            headers: HTTP 请求头。
            attempt: 当前尝试次数。

        Returns:
            解析后的结果 dict，失败时抛出异常。
        """
        start_time = time.monotonic()

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(MOONSHOT_API_URL, json=payload, headers=headers)
        except httpx.HTTPError:
            logger.exception("Advisor HTTP 请求失败 (attempt %d)", attempt)
            raise

        elapsed_ms = (time.monotonic() - start_time) * 1000

        if not response.is_success:
            logger.error(
                "Advisor API 返回非成功状态码: %d (attempt %d), body=%s",
                response.status_code,
                attempt,
                response.text[:500],
            )
            raise RuntimeError(f"Moonshot API 返回 {response.status_code}")

        try:
            resp_data: dict[str, Any] = response.json()
        except json.JSONDecodeError:
            logger.exception("Advisor API 响应 JSON 解析失败 (attempt %d)", attempt)
            raise

        usage = resp_data.get("usage", {})
        if isinstance(usage, dict):
            logger.info(
                "Advisor token_usage: prompt=%d, completion=%d, total=%d, latency_ms=%.0f",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
                elapsed_ms,
            )

        choices = resp_data.get("choices", [])
        if not choices:
            logger.error("Advisor API 响应中没有 choices (attempt %d)", attempt)
            raise ValueError("API 响应中没有 choices")

        message = choices[0].get("message", {})
        content: str = ""
        if isinstance(message, dict):
            content = message.get("content", "")
        else:
            content = ""

        if not content:
            logger.error("Advisor API 响应 content 为空 (attempt %d)", attempt)
            raise ValueError("API 响应 content 为空")

        if isinstance(content, str):
            try:
                result: dict[str, Any] = json.loads(content)
            except json.JSONDecodeError:
                logger.exception(
                    "Advisor LLM 返回的 content 不是有效 JSON (attempt %d): %s",
                    attempt,
                    content[:500],
                )
                raise
        elif isinstance(content, dict):
            result = content
        else:
            logger.error(
                "Advisor content 类型异常: %s (attempt %d)", type(content), attempt
            )
            raise TypeError(f"content 类型异常: {type(content)}")

        logger.info("Advisor LLM 分析完成, latency_ms=%.0f", elapsed_ms)
        return result

    # --- Fallback 逻辑 ---------------------------------------------------------

    @staticmethod
    def _fallback_advice(
        game_state: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """纯规则 fallback——不依赖 LLM 的阵容建议。

        Args:
            game_state: 当前游戏状态。
            candidates: 候选阵容列表。

        Returns:
            结构化建议 dict，包含 fallback=True 标记。
        """
        gold = game_state.get("gold", 0)
        hp = game_state.get("hp", 100)

        # 简单规则
        if hp < 30:
            level_action = "stay"
            roll_action = "all_in"
        elif gold >= 50:
            level_action = "slow_level"
            roll_action = "roll_interest"
        elif gold < 20:
            level_action = "stay"
            roll_action = "save"
        else:
            level_action = "slow_level"
            roll_action = "roll_interest"

        recommended_comps: list[dict[str, Any]] = []
        next_steps: list[str] = []

        if candidates:
            best = candidates[0]
            recommended_comps.append({
                "name": best.get("name", "未知"),
                "confidence": 60,
                "reason": f"基于{best.get('champion_matched', 0)}/{best.get('champion_total', 0)}棋子匹配的自动推荐",
                "core_champs_missing": best.get("core_champs_missing", []),
            })
            next_steps.append(f"优先收集{best.get('name', '推荐阵容')}所需棋子")
            if best.get("core_champs_missing"):
                missing = "、".join(best["core_champs_missing"])
                next_steps.append(f"重点关注缺少的核心棋子: {missing}")
        else:
            next_steps.append("根据当前状态自动判断")

        return {
            "recommended_comps": recommended_comps,
            "action_advice": {
                "level": level_action,
                "roll": roll_action,
                "positioning": "standard",
            },
            "next_steps": next_steps,
            "fallback": True,
        }

    @staticmethod
    def _fallback_augment_advice(
        augment_options: list[str],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """纯规则 fallback——不依赖 LLM 的海克斯分析。

        Args:
            augment_options: 海克斯选项列表。
            candidates: 候选阵容列表。

        Returns:
            结构化建议 dict，包含 fallback=True 标记。
        """
        augments: list[dict[str, Any]] = []
        if not augment_options:
            return {
                "augments": [],
                "recommendation": "",
                "fallback": True,
            }

        # 简单启发式：如果候选阵容有 playstyle 信息，略作匹配
        playstyle = candidates[0].get("playstyle", "") if candidates else ""

        for name in augment_options:
            score = 50  # 基准分
            reason = "无法精确分析，给予基准评分"
            # 简单的关键词匹配启发
            if "经济" in name or "金币" in name or "利息" in name:
                if playstyle in ("运营", "速八"):
                    score = 80
                    reason = "适合经济运营型阵容"
            elif "战力" in name or "战斗" in name or "攻击" in name:
                if playstyle in ("连胜", "赌狗"):
                    score = 80
                    reason = "适合前期压制型阵容"
            augments.append({"name": name, "score": score, "reason": reason})

        recommendation = augments[0]["name"] if augments else ""

        return {
            "augments": augments,
            "recommendation": recommendation,
            "fallback": True,
        }
