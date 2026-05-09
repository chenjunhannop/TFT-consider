# Spec 002: 截图内容的多模态 LLM 识别

**Priority:** HIGH
**Dependencies:** Spec 001

## Description
调用多模态 LLM API（默认 Kimi K2.6）对游戏截图进行内容识别，输出结构化 JSON，包含棋子、装备、海克斯、经济和血量等关键状态信息。设计 model provider 抽象接口，支持后续切换模型。

## Acceptance Criteria
- [ ] 支持调用 Kimi K2.6（Moonshot API）对单张截图进行内容识别
- [ ] 识别输出结构化 JSON：`{ level, gold, hp, board: [{name, star, position, items}], bench: [{name, star}], augments: [{name, tier, picked}], stage, phase, streak, streak_count }`
- [ ] 设计 `BaseProvider` 抽象接口，支持后续切换模型
- [ ] 首批实现 `MoonshotProvider`（Kimi K2.6）
- [ ] API key 从 `config.yaml` 读取，不硬编码
- [ ] 识别失败时自动重试 1 次，仍失败则跳过本回合并记录 ERROR 日志
- [ ] 每次 API 调用记录 `token_usage` 和 `latency_ms`
- [ ] 对 > 4K 分辨率的截图自动降采样到 1920×1080 后再发送
- [ ] 预留 `AnthropicProvider`、`OpenAIProvider` 接口规划（不实现）

## Status: PENDING

<!-- NR_OF_TRIES: 0 -->
