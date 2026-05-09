"""阵容匹配算法。

根据当前游戏状态（已持有棋子、装备），从数据库检索最匹配的候选阵容。
"""

from __future__ import annotations

import json
from typing import Any

from tft_consider.database.models import (
    Champion,
    CompChampion,
    CompItem,
    Composition,
    Item,
    get_session,
)


def match_compositions(
    game_state: dict[str, Any], top_n: int = 5
) -> list[dict[str, Any]]:
    """根据当前游戏状态，从数据库检索最匹配的候选阵容。

    匹配算法：
    1. 从 game_state 提取已持有的棋子名称列表 (board + bench)
    2. 查询 comp_champions JOIN champions，计算每个阵容的匹配分数:
       - 核心棋子匹配: +3 分/个 (is_core=True)
       - 普通棋子匹配: +1 分/个
       - 装备匹配: 如果已持有的装备与阵容推荐装备一致 +2 分/件
    3. 按分数降序排列，取 Top N

    Args:
        game_state: Spec 002 输出的结构化 JSON，含 board, bench, items 等。
        top_n: 返回的候选阵容数量，默认 5。

    Returns:
        候选阵容列表，每个元素包含:
        {
            "composition_id": int,
            "name": str,
            "tier": str,
            "playstyle": str,
            "description": str,
            "match_score": int,
            "core_matched": int,
            "core_total": int,
            "champion_matched": int,
            "champion_total": int,
            "item_matched": int,
            "item_total": int,
            "core_champs_missing": [str],
            "positioning": list | None,
        }
    """
    # 1. 提取已持有的棋子名称集合（去重）
    held_champion_names: set[str] = set()
    for entry in game_state.get("board", []):
        if isinstance(entry, dict) and entry.get("name"):
            held_champion_names.add(entry["name"])
    for entry in game_state.get("bench", []):
        if isinstance(entry, dict) and entry.get("name"):
            held_champion_names.add(entry["name"])

    # 2. 提取已持有的装备名称集合
    held_item_names: set[str] = set()
    for entry in game_state.get("board", []):
        if isinstance(entry, dict):
            for item_name in entry.get("items", []):
                if item_name:
                    held_item_names.add(item_name)
    # 也检查顶层 items 字段（可能直接列在 game_state 中）
    for item_entry in game_state.get("items", []):
        if isinstance(item_entry, str) and item_entry:
            held_item_names.add(item_entry)
        elif isinstance(item_entry, dict) and item_entry.get("name"):
            held_item_names.add(item_entry["name"])

    # 3. 查询所有阵容
    session = get_session()
    try:
        compositions = session.query(Composition).all()

        if not compositions:
            return []

        # 预加载所有 comp_champions（含 champion 名称、is_core）按 composition_id 分组
        all_comp_champs = (
            session.query(CompChampion, Champion.name)
            .join(Champion, CompChampion.champion_id == Champion.id)
            .all()
        )

        # 预加载所有 comp_items（含 item 名称）按 composition_id 分组
        all_comp_items = (
            session.query(CompItem, Item.name)
            .join(Item, CompItem.item_id == Item.id)
            .all()
        )

        # 构建快速查找映射: composition_id -> {champion_name -> is_core}
        comp_champ_map: dict[int, dict[str, bool]] = {}
        for cc, champ_name in all_comp_champs:
            comp_champ_map.setdefault(cc.composition_id, {})[champ_name] = cc.is_core

        # 构建快速查找映射: composition_id -> set of item_names
        comp_item_map: dict[int, set[str]] = {}
        for ci, item_name in all_comp_items:
            comp_item_map.setdefault(ci.composition_id, set()).add(item_name)

        # 4. 计算每个阵容的匹配分数
        results: list[dict[str, Any]] = []

        for comp in compositions:
            champion_map = comp_champ_map.get(comp.id, {})
            item_set = comp_item_map.get(comp.id, set())

            core_total = sum(1 for is_core in champion_map.values() if is_core)
            champion_total = len(champion_map)
            item_total = len(item_set)

            # 计算棋子匹配
            core_matched = 0
            champion_matched = 0
            core_missing: list[str] = []

            for champ_name, is_core in champion_map.items():
                if champ_name in held_champion_names:
                    champion_matched += 1
                    if is_core:
                        core_matched += 1
                elif is_core:
                    core_missing.append(champ_name)

            # 计算装备匹配
            item_matched = len(item_set & held_item_names)

            match_score = (core_matched * 3) + (champion_matched * 1) + (item_matched * 2)

            # 解析站位 JSON
            positioning: list[dict[str, Any]] | None = None
            if comp.positioning:
                try:
                    positioning = json.loads(comp.positioning)
                except (json.JSONDecodeError, TypeError):
                    positioning = None

            results.append({
                "composition_id": comp.id,
                "name": comp.name,
                "tier": comp.tier,
                "playstyle": comp.playstyle,
                "description": comp.description or "",
                "match_score": match_score,
                "core_matched": core_matched,
                "core_total": core_total,
                "champion_matched": champion_matched,
                "champion_total": champion_total,
                "item_matched": item_matched,
                "item_total": item_total,
                "core_champs_missing": core_missing,
                "positioning": positioning,
            })

    finally:
        session.close()

    # 5. 按分数降序排序，取 Top N
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results[:top_n]
