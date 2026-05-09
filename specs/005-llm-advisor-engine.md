# Spec 005: LLM 阵容匹配与建议引擎

**Priority:** HIGH
**Dependencies:** Spec 002, Spec 003

## Description
构建 LLM 阵容匹配与建议引擎：从 SQLite 数据库初筛候选阵容（基于已持有棋子和装备），通过 LLM 推理输出最终建议（推荐阵容、D 牌时机、升人口策略、海克斯选择分析）。建议全部中文输出。

## Acceptance Criteria
- [ ] 构建结构化 LLM prompt，包含：当前棋盘状态（Spec 002 JSON）、候选阵容 Top 5（从 SQLite 检索）、当前阶段/经济/血量/连胜连败状态
- [ ] 候选阵容初筛算法：按已持有棋子与 `comp_champions` 的交集数 + 核心棋子匹配数加权排序，取 Top 5
- [ ] LLM 输出结构化建议 JSON：`{ recommended_comps: [{name, confidence, reason, core_champs_missing}], action_advice: { level, roll, positioning }, next_steps: [...] }`
- [ ] 海克斯选择阶段时，额外分析每个海克斯选项与候选阵容的适配度
- [ ] 建议内容全部中文输出
- [ ] LLM 调用失败时有 fallback：降级为纯数据库匹配建议（无 LLM 推理）
- [ ] 支持 `level`（stay/slow_level/rush_level）、`roll`（save/roll_interest/roll_down/all_in）、`positioning`（standard/anti_assassin/anti_aoe）等建议类型

## Status: PENDING

<!-- NR_OF_TRIES: 0 -->
