# TFT-Consider

云顶之弈 AI 对局分析助手。实时截取游戏画面，识别棋盘状态，结合 meta 数据推荐最优阵容和每回合行动建议。

[![CI](https://github.com/chenjunhan/tft-consider/actions/workflows/ci.yml/badge.svg)](https://github.com/chenjunhan/tft-consider/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 功能

- **实时截图分析** — 自动截取游戏画面，LLM 识别棋盘棋子、装备、海克斯、经济和血量
- **Meta 阵容推荐** — 从 Tactics.Tools 同步最新 meta 数据，结合当前来牌匹配最优阵容
- **行动建议** — 每回合给出升级时机、D 牌策略、变阵建议；关键决策点强化输出
- **对局追踪** — 记录每局完整数据，支持赛后复盘分析
- **桌面悬浮窗** — 置顶半透明窗口，不抢游戏焦点，系统托盘最小化

## 安装

```bash
# 克隆仓库
git clone https://github.com/chenjunhan/tft-consider.git
cd tft-consider

# 安装依赖
uv sync
pip install -e .

# 首次配置向导
tft-consider setup

# 启动应用
tft-consider run
```

## 使用

```bash
tft-consider setup        # 首次配置向导（输入 API Key）
tft-consider sync-data     # 同步最新 meta 阵容数据
tft-consider check         # 检查配置和环境
tft-consider run           # 启动桌面悬浮分析窗口
tft-consider history       # 查看历史对局记录
```

启动后，应用以半透明悬浮窗置顶显示在游戏窗口旁，实时展示推荐阵容和行动建议。

## 配置

配置文件位于 `%APPDATA%/tft-consider/config.yaml`：

```yaml
api:
  provider: "moonshot"
  key: ""        # base64 编码的 Moonshot (Kimi) API Key
  model: "kimi-k2.6"

ui:
  theme: "dark"    # dark / light
  opacity: 0.9

screenshot:
  interval_ms: 3000

data:
  sync_interval_hours: 6
  auto_sync: true
```

API Key 可在 [Moonshot 平台](https://platform.moonshot.cn) 获取。

## 技术栈

- **Python 3.12+**, PySide6, SQLAlchemy 2.0
- Moonshot (Kimi) Vision API
- mss 截图, pynput 快捷键监听
- ruff + mypy 代码质量
- pytest 测试 (544 tests)

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

MIT — 详见 [LICENSE](LICENSE)。
