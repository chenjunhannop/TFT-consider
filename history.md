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

## 2026-05-09 — Spec 004 + 005 完成
- Spec 004: crawler 模块 (TacticsToolsCrawler + SyncScheduler + CLI), 63 tests
- Spec 005: engine 模块 (matcher + Advisor + fallback), 47 tests
- main.py 更新: `tft-consider sync-data` 和 `tft-consider check` CLI 命令
- 总计 227 tests passed, ruff + mypy 零错误
- 子 agent: backend-implementer ×2 + test-writer ×2

## 2026-05-09 — Spec 006 + 008 完成
- Spec 006: tracker 模块 (GameState + AdvicePipeline + GameReplay + replay), 86 tests
- Spec 008: UI 模块 (MainWindow + TftConsiderApp + 系统托盘 + 主题), 77 tests
- main.py 更新: `tft-consider run` 和 `tft-consider history` CLI 命令
- 修复 QApplication 单例复用问题
- 总计 390 tests passed, ruff + mypy 零错误
- 子 agent: backend-implementer ×2 + test-writer ×2

## 2026-05-09 — Spec 007 + 009 完成
- Spec 007: comp_widget 模块 (CompositionWidget + BoardArea + BoardCell), 棋盘 QPainter 绘制, 4×7 站位图, 羁绊/装备展示, 拖拽交换, 多阵容 Tab 切换
- Spec 009: setup_wizard 模块 (SetupWizard 4 页引导), app.py 首次启动检测, CLI `tft-consider setup` 命令
- 新增 tests/test_comp_widget.py (85 tests) + tests/test_setup_wizard.py (69 tests)
- 新增 tests/conftest.py 提取共享 qapp fixture
- 总计 544 tests passed, ruff + mypy 零错误
- 子 agent: frontend-implementer ×2 + test-writer ×2
