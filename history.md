# TFT-Consider History

## 2026-05-09 — 项目初始化
- 完成 PRD 文档（workspace/2026-05-09/云顶之弈AI对局分析助手PRD.md）
- 配置 Ralph Wiggum 自治开发环境
- 创建 10 个 Spec，覆盖从截图采集到开源的完整链路
- Constitution v0 创建

## 2026-05-09 — Spec 001 完成
- 实现 log_parser (LogParser + PhaseEvent + 后台监控)
- 实现 screenshot capturer (mss 全屏 + ctypes 窗口 + 降采样 + pynput 快捷键)
- 61 个测试全部通过，ruff + mypy 零错误
- 子 agent: backend-implementer ×2 + test-writer ×1

## 2026-05-09 — Spec 002 + 003 完成
- Spec 002: vision 模块 (BaseProvider + MoonshotProvider + prompts), 34 tests
- Spec 003: database 模块 (8 SQLAlchemy models + JSON importer + example data), 22 tests
- 修复 get_api_key 非 dict api 配置的防御
- 修复 datetime.utcnow 弃用 → datetime.now(tz=UTC)
- 总计 117 tests passed, ruff + mypy 零错误
- 子 agent: backend-implementer ×2 + test-writer ×2
