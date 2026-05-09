# Spec 003: 本地阵容数据库构建 (SQLite)

**Priority:** HIGH
**Dependencies:** None

## Description
构建 SQLite 本地阵容数据库，存储当前赛季的棋子、装备、羁绊和阵容数据。提供 JSON 导入脚本，支持数据库 schema 版本管理和热更新。

## Acceptance Criteria
- [ ] SQLite 数据库文件存储在 `%APPDATA%/tft-consider/data/`，独立于应用代码，可热更新
- [ ] 核心表：`compositions`, `champions`, `items`, `synergies`, `comp_champions`, `comp_items`
- [ ] `compositions` 表包含：name, tier, difficulty, playstyle, description
- [ ] `comp_champions` 包含：composition_id, champion_id, is_core, star_target, position
- [ ] `comp_items` 包含：composition_id, item_id, champion_id, priority
- [ ] 数据库包含 `meta` 表记录 TFT set 和 patch 版本
- [ ] 数据库包含 `schema_version` 表支持迁移
- [ ] 提供 `import_from_json` 脚本，从 JSON 文件批量导入阵容
- [ ] 手动维护一个赛季 JSON 数据模板作为初始基础数据
- [ ] 每个阵容包含：名称、难度、核心棋子（含目标星级）、装备优先级、运营节奏、标准站位

## Status: COMPLETE

<!-- NR_OF_TRIES: 1 -->
