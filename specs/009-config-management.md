# Spec 009: 配置管理与开箱体验

**Priority:** LOW
**Dependencies:** Spec 002 (needs API key config), Spec 008

## Description
首次启动引导、config.yaml 配置管理、CLI 配置验证命令。让新用户能快速配置 API key 并开始使用，无需手动编辑配置文件。

## Acceptance Criteria
- [ ] 首次启动时显示引导对话框：欢迎页 → 输入 API Key → 检查数据库 → 检测游戏客户端 → 完成
- [ ] 配置文件 `config.yaml` 存储在 `%APPDATA%/tft-consider/config.yaml`
- [ ] 可配置项：`api.provider`、`api.key`、`api.model`、`screenshot.interval_ms`、`screenshot.temp_dir`、`ui.theme`、`ui.opacity`、`data.sync_interval_hours`、`data.auto_sync`、`log.level`
- [ ] API key 写入时做简单 base64 编码，避免明文暴露
- [ ] API key 在日志中自动脱敏
- [ ] CLI 命令 `tft-consider check` 验证配置完整有效
- [ ] 配置文件缺失或格式错误时，给出清晰错误提示和恢复建议（重新运行引导向导）

## Status: COMPLETE

<!-- NR_OF_TRIES: 1 -->
