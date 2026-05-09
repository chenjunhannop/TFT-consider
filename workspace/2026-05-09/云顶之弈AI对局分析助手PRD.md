# PRD: 云顶之弈 AI 对局分析助手 (TFT-Consider)

## 1. Overview

TFT-Consider 是一款桌面 AI 助手，为云顶之弈（Teamfight Tactics）玩家提供实时的对局分析与阵容建议。通过自动截取游戏画面并结合游戏日志分析，利用多模态大模型识别棋子、装备、海克斯、经济和血量等关键状态信息，对比本地阵容数据库和外部数据站 meta 数据，给出完整的阵容推荐、D 牌阶段建议、经济运营策略，并随对局推进持续更新建议。

项目以 MIT 协议开源，面向 TFT 社区，接受社区贡献和阵容数据维护。

**核心原则：**
- 不读取、不注入、不修改游戏进程内存，完全通过截屏 + 日志文件获取状态
- 不进行任何游戏自动化操作（如自动买牌、自动 D 牌），仅提供建议
- 保持独立窗口运行，不与游戏客户端产生任何交互

## 2. Goals

- 在 Windows 平台上提供一款桌面应用，安全合规地获取游戏状态
- 每个回合开始和战斗结束后自动识别游戏状态，无需用户手动操作
- 结合多模态 LLM 视觉理解和外部 TFT 数据，给出可信、可解释的阵容和运营建议
- 支持阵容可视化展示（棋子站位图、装备合成路径、羁绊效果）
- 构建可维护的本地阵容数据库（SQLite），支持手动维护、自动爬取和社区贡献三重数据来源
- 建立完整的开源协作体系（MIT License、CI/CD、贡献指南）

## 3. Quality Gates

以下命令必须在每个 User Story 完成后通过：

- `ruff check .` — 代码风格检查
- `mypy .` — 类型检查
- `pytest` — 单元测试和集成测试

涉及 UI 的 Story，额外要求：
- 在 Windows 上启动应用，手动验证界面渲染和交互行为

## 4. User Stories

### US-001: 游戏状态截图采集 — 日志驱动的自动截屏

**Description:** 作为玩家，我希望工具能自动在每回合开始时和战斗结束后截取游戏画面，以便分析当前对局状态。

**Acceptance Criteria:**
- [ ] 通过分析 `League of Legends/Logs/GameLogs` 目录下的日志文件，检测回合阶段切换事件（准备阶段开始、战斗阶段结束）
- [ ] 在准备阶段开始时（如 1-1, 2-1, 3-1...）自动触发截图
- [ ] 在战斗阶段结束后触发截图（获取战斗结果和剩余血量变化）
- [ ] 截图保存为 PNG 格式到本地临时目录，按 `{stage}_{timestamp}.png` 命名
- [ ] 支持手动快捷键（Ctrl+Shift+S）作为自动截图的兜底方式
- [ ] 日志解析失败时不影响游戏客户端运行，仅记录 WARNING 日志
- [ ] 只读取日志文件内容，不做任何进程注入或内存读取
- [ ] 截图工具支持全屏模式和窗口模式下的英雄联盟客户端

**技术不确定性：** GameLogs 的日志格式和回合阶段标志行需要逆向分析验证，这是 MVP 最高风险项。

---

### US-002: 截图内容的多模态 LLM 识别

**Description:** 作为玩家，我希望工具能理解截图中的游戏内容，识别出我的棋子、装备、海克斯、经济和血量。

**Acceptance Criteria:**
- [ ] 支持调用 Kimi K2.6（Moonshot API）对单张截图进行内容识别
- [ ] 识别输出结构化 JSON，包含字段：
  ```
  {
    level: int, gold: int, hp: int,
    board: [{name: str, star: int, position: [row, col], items: [str]}],
    bench: [{name: str, star: int}],
    augments: [{name: str, tier: 1|2|3, picked: bool}],
    stage: "1-1"|...|"7-1", phase: "planning"|"fighting"|"carousel",
    streak: "win"|"lose"|"mixed", streak_count: int
  }
  ```
- [ ] 设计 model provider 抽象接口（`BaseProvider`），支持后续切换模型
- [ ] 首批实现 `MoonshotProvider`（Kimi K2.6）
- [ ] 预留 `AnthropicProvider`、`OpenAIProvider` 接口规划
- [ ] API key 从 `config.yaml` 读取，不硬编码
- [ ] 识别失败时自动重试 1 次，仍失败则跳过本回合并记录 ERROR 日志
- [ ] 每次 API 调用记录 `token_usage` 和 `latency_ms` 到本地日志
- [ ] 对过大的截图（> 4K 分辨率），自动降采样到 1920×1080 后再发送

---

### US-003: 本地阵容数据库构建 (SQLite)

**Description:** 作为玩家，我希望工具内置当前赛季的阵容数据，以便将我的状态与已知强势阵容进行匹配。

**Acceptance Criteria:**
- [ ] SQLite 数据库文件独立于应用代码，存储在 `%APPDATA%/tft-consider/data/`，可热更新
- [ ] 核心表结构：
  - `compositions`（阵容）：name, tier, difficulty, playstyle, description
  - `champions`（棋子）：name, cost, traits
  - `items`（装备）：name, components, effect
  - `synergies`（羁绊）：name, breakpoints
  - `comp_champions`：composition_id, champion_id, is_core, star_target, position
  - `comp_items`：composition_id, item_id, champion_id, priority
- [ ] 数据库包含版本号 `meta` 表，记录 TFT set 和 patch 版本
- [ ] 提供 `import_from_json` 脚本，支持从 JSON 文件批量导入阵容数据
- [ ] 手动维护一个赛季 JSON 数据模板作为初始基础数据
- [ ] 每个阵容记录包含：名称、难度、核心棋子（含目标星级）、装备优先级、运营节奏（连胜/连败/赌狗/速八）、标准站位
- [ ] 数据库 schema 支持迁移（`schema_version` 表），便于赛季更替

---

### US-004: 外部数据站 Meta 数据爬取与合并

**Description:** 作为玩家，我希望工具能自动获取当前版本的 meta 阵容和胜率数据，使阵容建议更加准确。

**Acceptance Criteria:**
- [ ] 爬取 tactics.tools 或类似公开数据站当前版本的阵容胜率、登场率、平均排名数据
- [ ] 爬取频率默认每 6 小时一次（可配置），尊重目标站点的服务器负载
- [ ] 下载的 meta 数据自动合并到本地 SQLite，字段标记 `source='auto_crawled'` 和 `synced_at` 时间戳
- [ ] 爬取失败时不影响工具正常启动，回退使用本地已有数据
- [ ] 爬虫使用合法的 User-Agent 和合理的请求间隔（> 2s/请求）
- [ ] 支持 CLI 命令 `tft-consider sync-data` 手动触发数据同步
- [ ] 爬取逻辑独立模块，方便后续添加新数据源

---

### US-005: LLM 阵容匹配与建议引擎

**Description:** 作为玩家，我希望工具根据当前状态分析，告诉我该玩什么阵容、是否该 D 牌、是否该升人口。

**Acceptance Criteria:**
- [ ] 构建结构化的 LLM prompt，包含以下上下文信息：
  - 当前棋盘状态（US-002 的 JSON 输出）
  - 候选阵容 Top 5（从 SQLite 检索，基于已持有棋子和装备的匹配度排序）
  - 当前阶段、经济、血量、连胜/连败状态
- [ ] 候选阵容初筛算法：
  - 从 SQLite 查询 `comp_champions` 与当前棋盘/banc 棋子有交集的阵容
  - 按交集棋子数和核心棋子匹配数加权排序
  - 取 Top 5 作为 LLM 候选输入
- [ ] LLM 输出结构化建议 JSON：
  ```
  {
    recommended_comps: [{name, confidence: 0-100, reason, core_champs_missing}],
    action_advice: {
      level: "stay"|"slow_level"|"rush_level",
      roll: "save"|"roll_interest"|"roll_down"|"all_in",
      positioning: "standard"|"anti_assassin"|"anti_aoe"
    },
    next_steps: ["3-2 升 6 小 D 找二星前排", ...]
  }
  ```
- [ ] 当处于海克斯选择阶段时，额外分析每个海克斯选项与候选阵容的适配度
- [ ] 建议内容全部中文输出
- [ ] LLM 调用失败时有 fallback：降级为纯数据库匹配建议（无 LLM 推理）

---

### US-006: 对局持续追踪与建议更新

**Description:** 作为玩家，我希望在整局游戏中，工具能持续追踪我的状态变化，并在每次新信息到来时更新建议。

**Acceptance Criteria:**
- [ ] 维护 `GameState` 数据对象，每次新截图识别后更新状态并保留历史快照
- [ ] 每回合输出增量变化摘要：新来的关键牌、经济变化（+/-）、血量变化
- [ ] 如果当前阵容方向明显偏离上一回合建议（如核心棋子被同行抢光），自动提示是否考虑转型
- [ ] 在关键决策点强化输出：
  - **3-2（升 6）**: D 牌/升人口建议
  - **4-1（升 7）**: 阵容锁定确认或转型窗口
  - **4-5（升 8）**: 最终阵容冲刺建议
  - **选秀阶段**: 目标棋子/装备推荐
- [ ] 对局结束（游戏结算画面）时，自动保存完整复盘数据到 SQLite 的对局历史表
- [ ] 复盘包含：每回合状态快照、当时给出的建议、用户的最终阵容和排名
- [ ] 支持 CLI `tft-consider history` 查看历史对局记录

---

### US-007: 阵容可视化展示

**Description:** 作为玩家，我希望看到推荐阵容的完整可视化（棋子站位、装备分配、羁绊效果），而不仅是文字建议。

**Acceptance Criteria:**
- [ ] 使用 PySide6 自定义绘制 4×7 棋盘站位图
- [ ] 棋盘格子中显示：棋子图标（或首字母替代）、名称、星级（★）、携带装备小图标
- [ ] 棋盘旁显示羁绊激活列表（如 "8 法师 / 2 护卫"），已激活的高亮、未激活的灰色
- [ ] 显示装备合成路径：当前已有散件 → 推荐合成装备的树状图
- [ ] 站位图支持鼠标拖拽调整棋子位置（用户实验不同站位布局）
- [ ] 存在多个推荐阵容时，支持 Tab 或下拉切换不同阵容的可视化
- [ ] 核心棋子与自由位棋子有视觉区分（如不同边框颜色）

---

### US-008: PyQt 桌面应用主框架

**Description:** 作为玩家，我希望有一个桌面应用集中展示所有分析信息，且以不干扰游戏的方式呈现。

**Acceptance Criteria:**
- [ ] 使用 PySide6 构建主窗口，默认：置顶、半透明背景、无边框、不可聚焦（避免抢游戏焦点）
- [ ] 窗口布局分三栏：
  - **左侧面板**：当前状态摘要（等级、经济、血量、连胜/连败、当前回合）
  - **中间面板**：推荐阵容可视化（站位图 + 羁绊，来自 US-007）
  - **右侧面板**：行动建议文字（来自 US-005） + 关键决策高亮
- [ ] 底部状态栏显示：截图状态（等待中/处理中/完成）、LLM 调用次数、当前对局阶段
- [ ] 窗口支持最小化到系统托盘，托盘图标显示当前回合编号
- [ ] 支持深色/浅色主题切换，通过设置持久化
- [ ] 应用启动时检测英雄联盟客户端是否在运行，若未运行则显示友好提示
- [ ] 窗口大小可调节，面板比例可拖拽分割线调整
- [ ] 应用关闭时自动清理临时截图文件

---

### US-009: 配置管理与开箱体验

**Description:** 作为新用户，我希望能快速配置 API key 并开始使用，而不需要手动编辑配置文件。

**Acceptance Criteria:**
- [ ] 首次启动时显示引导对话框：
  1. 欢迎页 → 2. 输入 Moonshot API Key → 3. 检查数据库 → 4. 检测游戏客户端 → 5. 完成
- [ ] 配置文件 `config.yaml` 存储在 `%APPDATA%/tft-consider/config.yaml`
- [ ] 可配置项完整列表：
  - `api.provider`: "moonshot" | "anthropic" | "openai"
  - `api.key`: API key（写入时做简单的 base64 编码，避免明文暴露）
  - `api.model`: 模型名称（默认 `kimi-k2-0719-preview`）
  - `screenshot.interval_ms`: 截屏间隔（默认 2000ms）
  - `screenshot.temp_dir`: 临时截图目录
  - `ui.theme`: "dark" | "light"
  - `ui.opacity`: 窗口透明度（0.3-1.0，默认 0.85）
  - `data.sync_interval_hours`: 数据同步间隔（默认 6）
  - `data.auto_sync`: 是否启用自动数据同步
  - `log.level`: 日志级别（默认 INFO）
- [ ] CLI 命令 `tft-consider check` 验证配置是否完整有效
- [ ] 配置文件缺失或格式错误时，给出清晰的错误提示和恢复建议（如重新运行引导向导）
- [ ] 所有 API key 相关字段在日志中自动脱敏

---

### US-010: 开源项目基础设施

**Description:** 作为开源维护者，我希望项目具备完整的 CI/CD 和贡献流程，让社区能参与。

**Acceptance Criteria:**
- [ ] GitHub Actions CI 工作流（`.github/workflows/ci.yml`）：
  - 使用 Windows runner（`windows-latest`）
  - 步骤：checkout → setup python → install → ruff check → mypy . → pytest
- [ ] `README.md` 包含：
  - 项目介绍与核心能力说明
  - 安装步骤（`git clone` → `pip install -r requirements.txt` 或 `uv sync`）
  - 首次配置引导说明
  - 使用截图或录制 GIF
  - 贡献指南入口链接
  - MIT License badge
- [ ] `CONTRIBUTING.md` 说明：
  - 代码风格规范（ruff 配置）
  - PR 提交流程
  - 阵容数据贡献方式（JSON 格式模板 + PR 示例）
  - Commit message 约定（Conventional Commits）
- [ ] `pyproject.toml` 统一管理：
  - 项目元数据与依赖
  - `[tool.ruff]` 配置
  - `[tool.mypy]` 配置
  - `[tool.pytest.ini_options]` 配置
- [ ] `LICENSE` 文件（MIT）
- [ ] `.gitignore` 配置：排除 `config.yaml`（含 API key）、临时截图、`__pycache__`、数据库文件
- [ ] 提供 `uv sync` 或 `pip install -e .` 一键安装依赖并启动

## 5. Functional Requirements

每个功能需求对应至少一个 User Story。

- **FR-1**: 系统必须通过读取 `League of Legends/Logs/GameLogs` 目录下的日志文件检测游戏回合阶段切换（→ US-001）
- **FR-2**: 系统必须在准备阶段开始和战斗阶段结束时自动触发截图（→ US-001）
- **FR-3**: 系统不得以任何方式读取、注入或修改英雄联盟游戏进程内存（→ US-001）
- **FR-4**: 系统必须支持手动快捷键截图作为自动截图的兜底方案（→ US-001）
- **FR-5**: 系统必须调用多模态 LLM API（默认 Kimi K2.6）对截图进行结构化识别（→ US-002）
- **FR-6**: 系统必须维护 SQLite 本地阵容数据库，支持手动维护、自动爬取和社区贡献三种数据来源（→ US-003, US-004）
- **FR-7**: 系统必须从外部 TFT 数据站爬取 meta 阵容和胜率数据，默认每 6 小时更新一次，频率可配置（→ US-004）
- **FR-8**: 系统必须根据当前棋盘状态从数据库初筛候选阵容，结合 LLM 推理输出最终建议（→ US-005）
- **FR-9**: 系统必须持续追踪对局状态，在关键阶段强化建议，状态偏离时提示转型（→ US-006）
- **FR-10**: 系统必须提供阵容可视化（站位图、羁绊、装备合成路径）（→ US-007）
- **FR-11**: 系统必须提供 PySide6 桌面窗口，支持置顶、半透明、可最小化到系统托盘（→ US-008）
- **FR-12**: 系统必须在 Windows 平台运行，首版仅支持 Windows（→ US-008）
- **FR-13**: 系统必须保存每局完整复盘数据，包含历史状态和建议记录（→ US-006）
- **FR-14**: 系统必须通过配置文件管理所有设置，首次启动提供引导流程（→ US-009）

## 6. Non-Goals (Out of Scope for MVP)

以下内容明确不在首版范围内：

- **跨平台支持**：不支持 Windows 以外的操作系统（macOS/Linux 不在首版范围）
- **Overlay 叠加层**：不在游戏内显示任何叠加层，保持独立窗口以避免可能的反作弊误判
- **语音播报**：不提供语音播报建议，仅文字 + 可视化
- **模型训练/微调**：不训练自己的模型，完全依赖外部 LLM API
- **实时视频流分析**：不支持 OBS/采集卡推流分析
- **游戏自动化操作**：不提供任何游戏客户端修改或自动化功能（如自动购买棋子、自动 D 牌），纯粹的建议工具
- **Riot Games 官方 API**：不接入 Riot API（申请周期长且非必需）
- **规则引擎**：阵容推荐规则引擎不在首版实现，首版完全依赖 LLM 推理，后续可逐步沉淀规则
- **移动端**：不提供手机版或远程查看
- **团队/双人模式**：仅支持单人排位/匹配模式

## 7. Technical Considerations

### 7.1 日志解析（最高风险）

- 需逆向分析 TFT GameLogs 的日志格式，找到回合阶段切换的标志行
- 日志格式可能随补丁或赛季变更，需设计为可适配的正则/规则配置
- 此项技术不确定性最高，需在 US-001 中优先验证
- 如果日志解析不可行，可降级为固定间隔截屏 + LLM 判断阶段的模式

### 7.2 截图性能

- 推荐使用 `mss` 库进行高性能窗口截图（优于 PySide6 的 `QScreen.grabWindow`）
- 需注意在高分辨率（4K）下的截图文件大小和传输延迟
- 截图前可自动降采样到 1920×1080

### 7.3 LLM 延迟

- Kimi K2.6 API 调用预计延迟 3-10 秒/次
- 需在 UI 中用状态指示器体现处理进度
- 截图采集和 LLM 调用必须异步处理，不能阻塞 UI 线程
- 一局游戏约 30-40 回合，每回合 2 次截图，总计 60-80 次 API 调用/局

### 7.4 模型切换架构

- Model provider 使用抽象基类设计：
  ```
  BaseProvider
    ├── MoonshotProvider (Kimi K2.6)
    ├── AnthropicProvider (Claude API)
    └── OpenAIProvider (GPT-4V)
  ```
- 通过 `config.yaml` 的 `api.provider` 字段切换

### 7.5 SQLite 版本管理

- `meta` 表记录 `set_version` 和 `patch_version`
- `schema_version` 表支持数据库迁移
- TFT 每个 set 约 3-4 个月更新一次，阵容结构相对稳定

### 7.6 打包分发

- 使用 `Nuitka` 或 `PyInstaller` 打包为 Windows 独立 .exe
- 免除用户安装 Python 环境的需求
- 打包大小预估：80-150MB（含 PySide6 依赖）

### 7.7 安全与合规

- 所有截屏行为只是调用系统截屏 API，不触碰游戏进程
- 日志读取仅使用标准文件 I/O
- 不使用任何 DLL 注入、内存扫描、hook 等技术
- 完全合规，不存在被反作弊系统检测的风险

## 8. Success Metrics

| 指标 | 目标值 | 测量方式 |
|------|--------|---------|
| 端到端延迟（截图 → 建议显示） | < 15 秒 | 日志打点 |
| LLM 对棋子/装备/血量的识别准确率 | > 90% | 人工标定 50 张截图验证 |
| 阵容建议与当前 meta S/A 级阵容重叠率 | > 70% | 抽样 20 局对比 |
| 应用 CPU 占用 | < 5% | Windows 任务管理器 |
| 应用内存占用 | < 300MB | Windows 任务管理器（不含 LLM API 调用） |
| GitHub stars（发布 1 个月内） | > 100 | GitHub |
| 社区阵容数据贡献 PR/赛季 | > 3 | GitHub |

## 9. Open Questions

1. **Kimi K2.6 的视觉识别能力**：在 TFT 截图上的表现如何？棋子头像小、装备多层叠加、三星/四星棋子视觉差异等场景需要实际测试验证
2. **GameLogs 格式稳定性**：TFT GameLogs 的格式是否有社区文档？回合阶段切换的标志行在不同语言客户端下是否一致？
3. **API 调用成本**：每局 60-80 次 Kimi K2.6 API 调用的成本是否在可接受范围内？需要关注 Moonshot 平台的价格策略
4. **全屏游戏下的窗口行为**：PySide6 置顶半透明窗口在 DX12/Vulkan 全屏模式下是否能正常显示？无边框窗口模式（游戏设置）可能是推荐的运行环境
5. **tactics.tools 反爬策略**：是否有 robots.txt 限制或反爬机制？是否有更友好的数据获取方式（如官方数据 API、社区维护的数据集）？
6. **LLM 幻觉问题**：当 LLM 无法准确识别某些棋子或装备时，可能会给出错误的阵容建议。需要衡量错误建议的容错机制
7. **TFT 赛季更新节奏**：每个新赛季/set 发布时，需要重新收集阵容数据、更新棋子-装备映射，这部分工作的自动化程度能有多高？

## 10. Appendix

### A. 项目目录结构（规划）

```
tft-consider/
├── src/tft_consider/
│   ├── __init__.py
│   ├── main.py              # 应用入口
│   ├── config.py            # 配置管理
│   ├── screenshot/
│   │   ├── __init__.py
│   │   ├── capturer.py      # 自动截屏（日志驱动）
│   │   └── manual.py        # 手动快捷键截屏
│   ├── log_parser/
│   │   ├── __init__.py
│   │   └── parser.py        # GameLogs 解析
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── base.py          # BaseProvider 抽象
│   │   ├── moonshot.py      # Kimi K2.6 provider
│   │   └── prompts.py       # Prompt 模板
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py        # SQLAlchemy/SQLite 模型
│   │   ├── importer.py      # JSON → SQLite 导入
│   │   └── queries.py       # 阵容查询逻辑
│   ├── crawler/
│   │   ├── __init__.py
│   │   └── tactics_tools.py # 数据站爬虫
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── matcher.py       # 阵容匹配算法
│   │   └── advisor.py       # LLM 建议引擎
│   ├── state/
│   │   ├── __init__.py
│   │   └── tracker.py       # 对局状态追踪
│   └── ui/
│       ├── __init__.py
│       ├── main_window.py   # 主窗口
│       ├── status_panel.py  # 状态面板
│       ├── comp_view.py     # 阵容可视化
│       ├── advice_panel.py  # 建议面板
│       └── tray.py          # 系统托盘
├── data/
│   ├── templates/           # 阵容 JSON 模板
│   └── tft_consider.db      # SQLite 数据库（gitignore）
├── tests/
├── workspace/               # 计划文档
├── pyproject.toml
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── .github/workflows/ci.yml
```

### B. 技术栈一览

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.12+ | |
| 桌面 UI | PySide6 | Qt for Python |
| LLM API | Moonshot API (Kimi K2.6) | 默认 provider |
| 数据库 | SQLite + SQLAlchemy | 本地数据 |
| 截图 | mss | 高性能屏幕截图 |
| 图像处理 | Pillow | 截图降采样/格式转换 |
| 爬虫 | httpx + BeautifulSoup4 | 数据站爬取 |
| 打包 | Nuitka / PyInstaller | Windows .exe |
| 包管理 | uv | 快速依赖管理 |
| CI/CD | GitHub Actions (Windows runner) | |
| Lint | ruff | |
| 类型检查 | mypy | |
| 测试 | pytest | |

### C. 数据流概览

```
[Game Client] ──截屏──→ [Screenshot Module] ──PNG──→ [LLM Vision API]
                              ↑                              ↓
                     [Log Parser]                    [Structured JSON]
                     (检测回合切换)                          ↓
                                              [Engine: Matcher + Advisor]
                                                      ↓         ↓
                                          [SQLite DB]    [LLM Reasoning]
                                              ↓               ↓
                                        候选阵容 Top 5 ──→ 建议生成
                                                              ↓
                                                     [UI 展示]
                                              ├── 状态摘要
                                              ├── 阵容可视化
                                              └── 行动建议
```


