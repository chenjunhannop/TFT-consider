# Spec 010: 开源项目基础设施

**Priority:** LOW
**Dependencies:** All other specs (infrastructure wraps around)

## Description
建立完整的开源协作体系：GitHub Actions CI/CD、README、CONTRIBUTING、pyproject.toml、LICENSE、.gitignore。

## Acceptance Criteria
- [ ] GitHub Actions CI 工作流（`.github/workflows/ci.yml`）：Windows runner, checkout → setup python → install → ruff check → mypy . → pytest
- [ ] `README.md` 包含：项目介绍、安装步骤（git clone → uv sync）、首次配置引导、使用截图占位、贡献指南入口、MIT License badge
- [ ] `CONTRIBUTING.md` 包含：代码风格规范、PR 流程、阵容数据贡献方式（JSON 模板 + PR 示例）、Conventional Commits 约定
- [ ] `pyproject.toml` 统一管理：项目元数据、依赖、`[tool.ruff]`、`[tool.mypy]`、`[tool.pytest.ini_options]`
- [ ] `LICENSE` 文件（MIT）
- [ ] `.gitignore`：排除 `config.yaml`、临时截图、`__pycache__`、`*.db`、`dist/`、`build/`
- [ ] 一键安装依赖并启动：`uv sync && tft-consider` 或 `pip install -e . && tft-consider`

## Status: COMPLETE

<!-- NR_OF_TRIES: 1 -->
