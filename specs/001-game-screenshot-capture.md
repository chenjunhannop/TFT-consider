# Spec 001: 游戏状态截图采集 — 日志驱动的自动截屏

**Priority:** HIGH
**Dependencies:** None

## Description
通过分析 `League of Legends/Logs/GameLogs` 目录下的日志文件，检测回合阶段切换事件（准备阶段开始、战斗阶段结束），自动触发截图采集，完全不触碰游戏进程内存。同时支持手动快捷键作为兜底方案。

## Acceptance Criteria
- [ ] 解析 `League of Legends/Logs/GameLogs` 日志文件，识别回合阶段切换标志行
- [ ] 在准备阶段开始时（如 1-1, 2-1, 3-1...）自动触发截图
- [ ] 在战斗阶段结束后自动触发截图（获取战斗结果和血量变化）
- [ ] 截图保存为 PNG 格式到本地临时目录，按 `{stage}_{timestamp}.png` 命名
- [ ] 支持手动快捷键（Ctrl+Shift+S）作为兜底方案
- [ ] 日志解析失败时不影响游戏客户端运行，仅记录 WARNING 日志
- [ ] 只读取日志文件内容，不做任何进程注入或内存读取
- [ ] 支持全屏和窗口模式下的英雄联盟客户端截图

## Technical Risk
GameLogs 的日志格式和回合阶段标志行需要逆向分析验证，是 MVP 最高风险项。如果日志解析不可行，降级为固定间隔截屏 + LLM 判断阶段模式。

## Status: COMPLETE

<!-- NR_OF_TRIES: 1 -->
