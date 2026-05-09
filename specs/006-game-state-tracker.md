# Spec 006: 对局持续追踪与建议更新

**Priority:** MEDIUM
**Dependencies:** Spec 002, Spec 005

## Description
维护 `GameState` 对象持续追踪对局状态变化，每回合输出增量变化摘要。在关键决策点强化建议，状态偏离时提示转型。对局结束后保存完整复盘数据到 SQLite。

## Acceptance Criteria
- [ ] 维护 `GameState` 数据对象，每次新截图识别后更新状态并保留历史快照
- [ ] 每回合输出增量变化摘要：新来的关键牌、经济变化（+/-）、血量变化
- [ ] 当前阵容方向明显偏离上一回合建议时，自动提示是否考虑转型
- [ ] 关键决策点强化输出：3-2（升 6）、4-1（升 7）、4-5（升 8）、选秀阶段
- [ ] 对局结束时自动保存完整复盘数据到 SQLite 对局历史表
- [ ] 复盘包含：每回合状态快照、当时建议、最终阵容和排名
- [ ] 支持 CLI 命令 `tft-consider history` 查看历史对局记录

## Status: PENDING

<!-- NR_OF_TRIES: 0 -->
