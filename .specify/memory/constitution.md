# TFT-Consider Constitution
> 云顶之弈 AI 对局分析助手 — 桌面端实时阵容建议工具。通过截屏 + 日志分析获取游戏状态，利用多模态 LLM（Kimi K2.6）识别棋盘信息，结合本地阵容数据库（SQLite）和外部 meta 数据，给出完整阵容推荐和运营建议。MIT 开源，面向 TFT 社区。

---
## Context Detection
**Ralph Loop Mode** (started by ralph-loop*.sh):
- Pick highest priority incomplete spec from `specs/`
- Implement, test, commit, push
- Output `DONE` only when 100% complete
- Output `ALL_DONE` when no work remains

**Interactive Mode** (normal conversation):
- Be helpful, guide decisions, create specs

---
## Core Principles
- 安全合规第一：不读取、不注入、不修改游戏进程内存，仅通过截屏 + 日志文件获取状态
- 纯粹建议工具：不进行任何游戏自动化操作（如自动买牌、自动 D 牌）
- 社区驱动：阵容数据开放维护，接受社区 PR 贡献
- 渐进式交付：MVP 先验证核心链路可行性，再逐步完善

---
## Technical Stack
- Language: Python 3.12+
- Desktop UI: PySide6 (Qt for Python)
- LLM API: Moonshot API (Kimi K2.6, model: kimi-k2-0719-preview)
- Database: SQLite + SQLAlchemy
- Screenshot: mss
- Image Processing: Pillow
- HTTP/Crawler: httpx + BeautifulSoup4
- Packaging: Nuitka / PyInstaller
- Package Manager: uv
- CI/CD: GitHub Actions (Windows runner)
- Lint: ruff
- Type Check: mypy
- Test: pytest

---
## Autonomy
YOLO Mode: ENABLED
Git Autonomy: ENABLED

---
## Quality Gates
Every user story must pass:
- `ruff check .` — Code style
- `mypy .` — Type checking
- `pytest` — Unit and integration tests

UI stories additionally require:
- Manual verification on Windows (start app, check rendering and interactions)

---
## Specs
Specs live in `specs/` as markdown files. Pick the highest priority incomplete spec (lower number = higher priority). A spec is incomplete if it lacks `## Status: COMPLETE`.

When all specs are complete, re-verify a random one before signaling done.

---
## NR_OF_TRIES
Track attempts per spec via `` at the bottom of the spec file. Increment each attempt. At 10+, the spec is too hard — split it into smaller specs.

---
## History
Append a 1-line summary to `history.md` after each spec completion. For details, create `history/YYYY-MM-DD--spec-name.md` with lessons learned, decisions made, and issues encountered. Check history before starting work on any spec.

---
## Completion Logs
After each spec, create `completion_log/YYYY-MM-DD--HH-MM-SS--spec-name.md` with a brief summary.

---
## Completion Signal
All acceptance criteria verified, tests pass, changes committed and pushed → output `DONE`. Never output this until truly complete.

---
## Scope Constraints
- Windows only (MVP, no macOS/Linux support)
- No overlay (standalone window only)
- No voice output
- No Riot Games API (external data sites + community data only)
- No game automation (suggestions only)
- Solo ranked/normal mode only (no duo/double-up)

---
Ralph Wiggum v0 (d205125cc33745116cce22d883417461174dcde5)
