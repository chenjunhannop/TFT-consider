"""对局复盘模块。

将完整对局历史保存到 SQLite 并提供查询接口。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from tft_consider.database.models import GameReplay, get_session
from tft_consider.tracker.game_state import GameState


def save_replay(
    game_state: GameState,
    final_rank: int | None = None,
) -> int:
    """将完整对局历史保存到 SQLite。

    将 GameState 中的所有快照序列化为 JSON 存入 GameReplay 表。

    Args:
        game_state: 对局状态追踪器实例，含完整快照历史。
        final_rank: 最终排名 (1-8)，None 表示未知。

    Returns:
        新创建的 GameReplay 记录 ID。

    Raises:
        RuntimeError: 如果数据库尚未初始化或没有快照数据。
    """
    history = game_state.history()
    if not history:
        raise RuntimeError("没有对局快照数据，无法保存复盘")

    started_at = history[0].created_at
    ended_at = history[-1].created_at

    # 序列化所有快照
    snapshots_json = json.dumps(
        [_snapshot_to_dict(s) for s in history],
        ensure_ascii=False,
        default=str,
    )

    # 序列化最终棋盘
    final_snapshot = history[-1]
    final_board_json = json.dumps(
        final_snapshot.board,
        ensure_ascii=False,
        default=str,
    )

    session = get_session()
    try:
        replay = GameReplay(
            player_name=game_state.player_name,
            started_at=started_at,
            ended_at=ended_at,
            final_rank=final_rank,
            total_rounds=len(history),
            snapshots=snapshots_json,
            final_board=final_board_json,
        )
        session.add(replay)
        session.commit()
        replay_id: int = replay.id
        return replay_id
    finally:
        session.close()


def list_replays(
    session: Any = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """查询历史对局记录列表。

    Args:
        session: 可选的外部数据库会话。为 None 时自动获取。
        limit: 返回的最大记录数，默认 20。

    Returns:
        对局记录列表，按 started_at 降序排列。每条记录包含:
        {
            "id": int,
            "player_name": str,
            "started_at": str,
            "ended_at": str,
            "final_rank": int | None,
            "total_rounds": int,
        }
    """
    close_after = session is None
    if session is None:
        session = get_session()

    try:
        replays = (
            session.query(GameReplay)
            .order_by(GameReplay.started_at.desc())
            .limit(limit)
            .all()
        )

        result: list[dict[str, Any]] = []
        for r in replays:
            result.append({
                "id": r.id,
                "player_name": r.player_name,
                "started_at": r.started_at.isoformat() if r.started_at else "",
                "ended_at": r.ended_at.isoformat() if r.ended_at else "",
                "final_rank": r.final_rank,
                "total_rounds": r.total_rounds,
            })
        return result
    finally:
        if close_after:
            session.close()


def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
    """将 GameStateSnapshot 转换为可 JSON 序列化的 dict。"""
    d = asdict(snapshot)
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d
