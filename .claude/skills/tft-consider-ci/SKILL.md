---
name: tft-consider-ci
description: TFT-Consider CI 调试手册。当 GitHub Actions CI 失败、用户提供 CI run URL、或者需要排查 Windows runner 上的 ruff/mypy/pytest 错误时使用此 skill。涵盖跨平台 mypy type:ignore 差异、Windows 平台特定测试守卫、常见失败模式和修复策略。
---

# TFT-Consider CI 调试

## CI 概况

- **Runner:** `windows-latest` (GitHub Actions)
- **触发:** push/PR 到 `main` 分支
- **步骤:** checkout → setup-python (3.12) → install uv → install deps → ruff → mypy → pytest
- **配置文件:** `.github/workflows/ci.yml`

## 调试工作流

当 CI 失败时：

1. 用 `gh run view <run-id> --repo chenjunhannop/TFT-consider` 查看概况
2. 用 `gh run view <run-id> --repo chenjunhannop/TFT-consider --log-failed` 查看失败日志
3. 在本地重现（macOS 上 ruff/pytest 可重现，mypy 行为可能有差异）
4. 修复后 push，等待新 CI run 验证

## 常见失败模式

### 1. mypy: Unused "type: ignore" comment

**症状：** Windows CI 报 `error: Unused "type: ignore" comment [unused-ignore]`，但本地 macOS mypy 通过。

**根因：** 某些类型在 Windows mypy 中可解析，在 macOS mypy 中不可解析。典型例子是 `ctypes.windll` — Windows 上 mypy 认识它，macOS 上不认识。

**修复：** 用 `getattr()` 替代直接属性访问，消除对 `type: ignore` 的依赖：

```python
# ❌ 跨平台 mypy 不一致
user32 = ctypes.windll.user32  # type: ignore[attr-defined]

# ✅ 两个平台 mypy 都通过
windll = getattr(ctypes, "windll", None)
if windll is None:
    return None
user32 = windll.user32
```

### 2. pytest: 平台特定测试在错误平台运行

**症状：** Windows CI 上测试失败，测试名称含 `non_nt`、`macos` 等，或测试设置了 `XDG_CACHE_HOME`（仅非 Windows 使用）。

**根因：** 为非 Windows 平台设计的测试在 Windows runner 上执行了。

**修复：** 添加 `pytest.mark.skipif` 守卫：

```python
import os
import pytest

# 非 Windows 专用测试
@pytest.mark.skipif(os.name == "nt", reason="Windows 使用 TEMP 而非 XDG_CACHE_HOME")
def test_capturer_init_default_temp_dir(self, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    ...

# 或 Windows 专用测试
@pytest.mark.skipif(os.name != "nt", reason="需要 Windows API")
def test_windows_specific_behavior(self):
    ...
```

### 3. 路径比较失败 (WindowsPath vs PosixPath)

**症状：** `assert path1 == path2` 失败，两边路径格式不同。

**根因：** Windows 上 `tempfile.gettempdir()` 可能返回 8.3 短路径（如 `RUNNER~1`），与测试预期的长路径名不匹配。

**修复：** 使用 `Path.resolve()` 统一或添加 `skipif` 守卫。

### 4. CI 缓存问题

**症状：** `No file matched to [**/uv.lock,**/requirements*.txt]` annotation，但不影响执行。

**根因：** 项目用 `pip install -e .` 而非 `uv sync`，没有 `uv.lock` 文件。这是无害警告，可忽略；如需消除，在 CI workflow 的 `setup-uv` 步骤中添加 `cache-dependency-glob` 指向 `pyproject.toml`。

## 本地验证命令

推送前在本地验证（macOS 上运行这些可以预先发现大部分问题）：

```bash
python -m ruff check .
python -m mypy --strict src/tft_consider/
python -m pytest tests/ -v --tb=short
```

注意：mypy 在 macOS 上可能通过但 Windows 上失败（或反之），涉及平台特定 API 时需要特别注意。
