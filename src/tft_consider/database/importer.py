"""JSON 数据导入器。

从 JSON 文件读取 TFT 阵容数据并导入 SQLite 数据库。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from tft_consider.database.models import (
    Champion,
    CompChampion,
    CompItem,
    Composition,
    Item,
    Meta,
    Synergy,
    get_session,
)


def import_from_json(json_path: str | Path) -> dict[str, Any]:
    """从 JSON 文件导入阵容数据到 SQLite。

    导入逻辑：
    - champions/items/synergies: 如果 name 已存在则跳过，否则 INSERT
    - compositions: 总是 INSERT，并创建对应的 comp_champions 和 comp_items 关联
    - 更新 meta 表记录当前 set 和 patch 信息

    Args:
        json_path: JSON 数据文件路径。

    Returns:
        dict: 导入统计，格式为 {
            "imported": {
                "compositions": int,
                "champions": int,
                "items": int,
                "synergies": int,
            },
            "skipped": {
                "champions": int,
                "items": int,
                "synergies": int,
            },
        }
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    session = get_session()

    stats: dict[str, Any] = {
        "imported": {
            "compositions": 0,
            "champions": 0,
            "items": 0,
            "synergies": 0,
        },
        "skipped": {
            "champions": 0,
            "items": 0,
            "synergies": 0,
        },
    }

    # --- 1. 导入 champions ---
    champion_name_to_id: dict[str, int] = {}
    for champ_data in data.get("champions", []):
        name = champ_data["name"]
        existing = session.execute(
            select(Champion.id).where(Champion.name == name)
        ).scalar_one_or_none()

        if existing is not None:
            champion_name_to_id[name] = existing
            stats["skipped"]["champions"] += 1
            continue

        champion = Champion(
            name=name,
            cost=champ_data["cost"],
            traits=json.dumps(champ_data.get("traits", []), ensure_ascii=False),
            image_url=champ_data.get("image_url"),
        )
        session.add(champion)
        session.flush()  # 获取 auto-increment id
        champion_name_to_id[name] = champion.id
        stats["imported"]["champions"] += 1

    # --- 2. 导入 items ---
    item_name_to_id: dict[str, int] = {}
    for item_data in data.get("items", []):
        name = item_data["name"]
        existing = session.execute(
            select(Item.id).where(Item.name == name)
        ).scalar_one_or_none()

        if existing is not None:
            item_name_to_id[name] = existing
            stats["skipped"]["items"] += 1
            continue

        raw_components = item_data.get("components")
        components_json = json.dumps(raw_components, ensure_ascii=False) if raw_components else None

        item = Item(
            name=name,
            components=components_json,
            effect=item_data.get("effect"),
        )
        session.add(item)
        session.flush()
        item_name_to_id[name] = item.id
        stats["imported"]["items"] += 1

    # --- 3. 导入 synergies ---
    for synergy_data in data.get("synergies", []):
        name = synergy_data["name"]
        existing = session.execute(
            select(Synergy.id).where(Synergy.name == name)
        ).scalar_one_or_none()

        if existing is not None:
            stats["skipped"]["synergies"] += 1
            continue

        synergy = Synergy(
            name=name,
            breakpoints=json.dumps(synergy_data.get("breakpoints", []), ensure_ascii=False),
            effect_per_level=json.dumps(synergy_data.get("effect_per_level"), ensure_ascii=False)
            if synergy_data.get("effect_per_level")
            else None,
        )
        session.add(synergy)
        stats["imported"]["synergies"] += 1

    # --- 4. 导入 compositions ---
    for comp_data in data.get("compositions", []):
        composition = Composition(
            name=comp_data["name"],
            tier=comp_data.get("tier", "B"),
            difficulty=comp_data.get("difficulty", "medium"),
            playstyle=comp_data.get("playstyle", "运营"),
            description=comp_data.get("description"),
            source=comp_data.get("source", "manual"),
            synced_at=datetime.now(tz=UTC).replace(tzinfo=None),
            positioning=json.dumps(comp_data.get("positioning"), ensure_ascii=False)
            if comp_data.get("positioning")
            else None,
        )
        session.add(composition)
        session.flush()

        # 关联棋子
        for cc_data in comp_data.get("champions", []):
            champ_name = cc_data["name"]
            champion_id = champion_name_to_id.get(champ_name)
            if champion_id is None:
                # champions JSON 中不存在的棋子，跳过并记录
                continue

            comp_champion = CompChampion(
                composition_id=composition.id,
                champion_id=champion_id,
                is_core=cc_data.get("is_core", False),
                star_target=cc_data.get("star_target", 2),
                position=cc_data.get("position"),
            )
            session.add(comp_champion)

        # 关联装备
        for ci_data in comp_data.get("items", []):
            item_name = ci_data["item"]
            item_id = item_name_to_id.get(item_name)
            if item_id is None:
                continue

            champ_name = ci_data.get("champion")
            champion_id = champion_name_to_id.get(champ_name) if champ_name else None

            comp_item = CompItem(
                composition_id=composition.id,
                item_id=item_id,
                champion_id=champion_id,
                priority=ci_data.get("priority", 1),
            )
            session.add(comp_item)

        stats["imported"]["compositions"] += 1

    # --- 5. 更新 meta 表 ---
    set_value = data.get("set")
    if set_value is not None:
        _upsert_meta(session, "set", str(set_value))

    patch_value = data.get("patch")
    if patch_value is not None:
        _upsert_meta(session, "patch", str(patch_value))

    session.commit()
    session.close()

    return stats


def _upsert_meta(session: Any, key: str, value: str) -> None:
    """更新或插入 meta 表记录。"""
    existing = session.execute(
        select(Meta).where(Meta.key == key)
    ).scalar_one_or_none()

    if existing is not None:
        existing.value = value
    else:
        session.add(Meta(key=key, value=value))
