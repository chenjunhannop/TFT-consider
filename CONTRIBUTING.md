# 贡献指南

欢迎为 TFT-Consider 贡献代码、数据或文档。

## 代码风格

- Python 3.12+ 语法，使用 `from __future__ import annotations`
- 类型注解: mypy strict 模式，公共 API 必须标注返回类型
- Lint: ruff (E, F, I, N, W, UP 规则)，行长度 120
- 命名: snake_case 函数/变量、PascalCase 类、CamelCase PySide6 覆盖方法加 `@override` 装饰器
- 不写无意义的注释，让代码自解释

## Pull Request 流程

1. Fork 仓库，创建 feature 分支 (`feat/spec-XXX-描述`)
2. 实现变更，确保新增功能有测试覆盖
3. 运行质量门禁：`ruff check . && mypy --strict src/tft_consider/ && pytest tests/`
4. 使用 Conventional Commits: `feat(scope): 描述` / `fix(scope): 描述`
5. 提交 PR，在描述中引用相关 issue/spec

## 阵容数据贡献

TFT-Consider 需要保持阵容数据库与当前版本同步。阵容数据可通过以下方式贡献：

### JSON 模板

```json
{
  "name": "阵容名称",
  "tier": "S",
  "difficulty": "medium",
  "playstyle": "运营",
  "champions": [
    {
      "name": "棋子名",
      "is_core": true,
      "position": "3,0",
      "star_target": 2
    }
  ],
  "items": [
    {
      "name": "装备名",
      "champion": "棋子名",
      "priority": 1
    }
  ],
  "positioning": "[[\"\",\"\",\"\",\"\",\"\",\"\",\"\"],...]"
}
```

### 提交步骤

1. 在 `data/compositions/` 下创建 JSON 文件，文件名为阵容名称（英文小写、连字符连接）
2. 运行 `tft-consider check` 验证数据可被正确加载
3. 提交 PR，标题格式: `feat(data): add <阵容名> composition`

## 项目结构

```
src/tft_consider/
  ui/            # PySide6 桌面 UI
  engine/        # 阵容匹配 + LLM 建议引擎
  vision/        # LLM 视觉识别
  tracker/       # 对局状态追踪 + 复盘
  crawler/       # Meta 数据爬虫
  database/      # SQLAlchemy ORM 模型
  log_parser/    # 游戏日志解析
  screenshot/    # 游戏截图采集
tests/           # pytest 测试
specs/           # Spec 定义
```

## 协议

贡献代码基于 MIT 协议开源。
