---
name: tft-consider-dev
description: TFT-Consider 项目核心开发工作流。当用户需要新增功能、编写测试、实现 spec、调试代码、运行质量门禁，或进行任何代码变更时使用此 skill。涵盖 spec 驱动开发、测试模式（mock provider + 内存 SQLite + QApplication offscreen）、subagent 分派模式、质量门禁命令。项目使用 Python 3.12+、PySide6、SQLAlchemy、ruff、mypy、pytest。
---

# TFT-Consider 开发工作流

## 项目概览

云顶之弈 AI 对局分析助手。桌面端应用，通过截屏 + LLM 识别棋盘状态，匹配本地阵容数据库给出运营建议。

**核心原则：** 只读分析，不操作游戏进程；Windows only (MVP)；MIT 开源。

## 质量门禁

每次代码变更后必须全部通过：

```bash
# 代码风格（零错误）
python -m ruff check .

# 类型检查（仅检查 src/，不检查 tests/）
python -m mypy --strict src/tft_consider/

# 全量测试
python -m pytest tests/ -v --tb=short
```

CI 只对 `src/tft_consider/` 做 mypy 检查，tests/ 不在 mypy 范围内。

## 测试模式

### Mock Provider 模式

涉及 LLM API 调用的测试使用 mock provider，不发起真实网络请求：

```python
class MockVisionProvider(BaseProvider):
    """模拟视觉识别，返回预置 game_state。"""
    def __init__(self, config, fixed_result=None):
        super().__init__(config)
        self._fixed_result = fixed_result or {}
        self.analyze_screenshot_calls: list[Path] = []

    def analyze_screenshot(self, image_path: Path) -> dict[str, Any] | None:
        self.analyze_screenshot_calls.append(image_path)
        return dict(self._fixed_result)

    def provider_name(self) -> str:
        return "mock-vision"
```

### 内存 SQLite 模式

数据库测试使用 `:memory:` 隔离：

```python
@pytest.fixture
def db_session() -> Generator[models.Session, None, None]:
    event.listen(Engine, "connect", lambda dbapi_conn, _rec:
        dbapi_conn.execute("PRAGMA foreign_keys = ON"))
    models.init_db(":memory:")
    yield models.get_session()
    if models._engine is not None:
        models._engine.dispose()
    models._engine = None
    models._SessionLocal = None
```

### QApplication Fixture

GUI 测试共享 session-scoped offscreen QApplication（定义在 `tests/conftest.py`）：

```python
@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    app = QApplication.instance()
    if app is None:
        app = QApplication([sys.argv[0], "-platform", "offscreen"])
    yield app
```

### Mock HTTP 模式

拦截 `httpx.Client.post` 模拟 LLM API 响应：

```python
mock_http = MagicMock()
mock_http.status_code = 200
mock_http.json.return_value = {
    "choices": [{"message": {"content": json.dumps(mock_response)}}]
}
with patch("httpx.Client.post", return_value=mock_http):
    result = advisor.analyze(game_state, candidates)
```

## Subagent 分派模式

大任务拆成独立的 subagent，每个修改聚焦文件的一部分。

**适用场景：** 向已有文件追加测试类、多模块并行开发。

**关键原则：**
- 每个 subagent 的 prompt 必须自包含：完整背景、精确文件路径、完整代码、预期输出
- prompt 中写明 "先读取源码理解实际接口，如果与预期不一致以实际源码为准"
- subagent 结束后验证输出：运行测试、ruff、检查 diff

**示例 prompt 结构：**
```
你的任务是在 xxx 文件中追加测试类。

## 背景
TFT-Consider 项目，xxx.py 已有 xxx。

## 你的任务
先读取 xxx.py 最后 30 行确认当前末尾内容，然后用 Edit 在末尾追加...

## 质量门禁
追加后运行：pytest xxx -v --tb=short
预期: N passed

## 重要
- 使用 Edit 在末尾追加
- 不要做 git commit
- 如果测试失败，分析原因并修复
```

## 文件组织

```
src/tft_consider/
  ui/            # PySide6 桌面 UI (MainWindow, CompositionWidget, SetupWizard)
  engine/        # 阵容匹配 (matcher) + LLM 建议引擎 (Advisor)
  vision/        # LLM 视觉识别 (BaseProvider, MoonshotProvider)
  tracker/       # 对局状态追踪 (GameState, AdvicePipeline) + 复盘 (replay)
  crawler/       # Meta 数据爬虫 (TacticsToolsCrawler, SyncScheduler)
  database/      # SQLAlchemy ORM 模型 + JSON importer
  log_parser/    # 游戏日志解析
  screenshot/    # 游戏截图采集 (ScreenshotCapturer)
tests/           # pytest 测试 (命名: test_<module>.py)
specs/           # Spec 定义 (命名: NNN-description.md)
docs/superpowers/plans/  # 实施计划
```

## 关键模块接口

- `match_compositions(game_state, top_n) → list[dict]` — 阵容匹配
- `Advisor.analyze(game_state, candidates) → dict` — LLM 建议（含 recommended_comps, action_advice, next_steps）
- `AdvicePipeline.process_frame(game_state) → dict` — 全流程编排（含 summary, is_key_point, candidates, suggestions, reconsider）
- `GameState.update(state, suggestions) → GameStateSnapshot` — 对局状态更新
- `save_replay(gs, final_rank) → int` — 复盘持久化
- `list_replays(limit) → list[dict]` — 历史查询
