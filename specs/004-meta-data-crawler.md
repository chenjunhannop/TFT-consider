# Spec 004: 外部数据站 Meta 数据爬取与合并

**Priority:** MEDIUM
**Dependencies:** Spec 003

## Description
从 tactics.tools 或类似公开 TFT 数据站爬取当前版本的 meta 阵容胜率、登场率、平均排名数据，自动合并到本地 SQLite 数据库。支持定期同步和手动触发。

## Acceptance Criteria
- [ ] 爬取 tactics.tools 或类似数据站的阵容胜率、登场率、平均排名数据
- [ ] 爬取频率默认每 6 小时一次（可配置）
- [ ] 下载的 meta 数据自动合并到本地 SQLite，标记 `source='auto_crawled'` 和 `synced_at` 时间戳
- [ ] 爬取失败时不影响工具正常启动，回退使用已有本地数据
- [ ] 爬虫使用合法的 User-Agent，请求间隔 > 2s
- [ ] 支持 CLI 命令 `tft-consider sync-data` 手动触发同步
- [ ] 爬取逻辑独立模块，方便后续添加新数据源

## Status: PENDING

<!-- NR_OF_TRIES: 0 -->
