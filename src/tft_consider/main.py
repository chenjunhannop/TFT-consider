"""TFT-Consider 应用入口。

支持命令：
    tft-consider           显示版本和使用说明
    tft-consider sync-data  从外部数据站同步 meta 数据
    tft-consider check      检查配置和环境
    tft-consider run        启动桌面应用主窗口
    tft-consider setup      强制运行配置向导（即使已配置过）
    tft-consider history    显示最近对局记录
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "sync-data":
        from tft_consider.config import load_config
        from tft_consider.crawler.scheduler import SyncScheduler
        from tft_consider.database.models import init_db

        config = load_config()
        init_db()
        scheduler = SyncScheduler(config)
        success = scheduler.sync_now()
        sys.exit(0 if success else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "check":
        print("TFT-Consider v0.1.0 — 配置检查")
        _cmd_check()
    elif len(sys.argv) > 1 and sys.argv[1] == "run":
        _cmd_run()
    elif len(sys.argv) > 1 and sys.argv[1] == "setup":
        _cmd_setup()
    elif len(sys.argv) > 1 and sys.argv[1] == "history":
        _cmd_history()
    else:
        print("TFT-Consider v0.1.0")
        print("Usage:")
        print("  tft-consider            显示帮助信息")
        print("  tft-consider sync-data   从外部数据站同步 meta 数据")
        print("  tft-consider check       检查配置和环境")
        print("  tft-consider run         启动桌面应用主窗口")
        print("  tft-consider setup       强制运行配置向导（即使已配置过）")
        print("  tft-consider history     显示最近对局记录")


def _cmd_run() -> None:
    """启动 TFT-Consider 桌面应用主窗口。"""
    from tft_consider.config import load_config
    from tft_consider.ui.app import run_app

    config = load_config()
    run_app(config)


def _cmd_check() -> None:
    """检查配置和基本环境。"""
    from tft_consider.config import _config_dir, _config_path, load_config

    config_dir = _config_dir()
    config_path = _config_path()

    print(f"  配置目录: {config_dir}")
    print(f"  配置文件: {config_path}")

    if config_path.exists():
        print("  [OK] 配置文件存在")
        try:
            config = load_config()
            api_cfg = config.get("api", {})
            api_key = api_cfg.get("key", "") if isinstance(api_cfg, dict) else ""
            print(f"  [OK] API provider: {api_cfg.get('provider', 'N/A')}")
            print(f"  [OK] API key: {'已配置' if api_key else '未配置'}")
            data_cfg = config.get("data", {})
            if isinstance(data_cfg, dict):
                print(f"  [OK] 同步间隔: {data_cfg.get('sync_interval_hours', 6)} 小时")
        except Exception as e:
            print(f"  [ERROR] 配置加载失败: {e}")
    else:
        print("  [WARN] 配置文件不存在，将使用默认配置")

    # 检查数据库
    try:
        from tft_consider.database.models import init_db

        init_db()
        print("  [OK] 数据库初始化成功")
    except Exception as e:
        print(f"  [WARN] 数据库检查失败: {e}")

    # 检查依赖
    deps: dict[str, str] = {
        "httpx": "HTTP 请求库 (数据爬取)",
        "bs4": "HTML 解析库 (数据爬取)",
        "sqlalchemy": "ORM (数据存储)",
        "PySide6": "GUI 框架",
        "PIL": "图像处理 (截图)",
        "mss": "屏幕截图",
        "yaml": "配置解析",
    }
    for mod_name, desc in deps.items():
        try:
            __import__(mod_name)
            print(f"  [OK] {mod_name} ({desc})")
        except ImportError:
            print(f"  [WARN] {mod_name} 未安装 ({desc})")


def _cmd_setup() -> None:
    """强制运行配置向导（即使已配置过）。"""
    from tft_consider.config import load_config, save_config

    config = load_config()
    print("TFT-Consider 配置向导")
    print("=" * 50)

    from PySide6.QtWidgets import QApplication, QWizard

    # 创建 QApplication（如果已存在则复用）
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        app = existing
    else:
        app = QApplication(["tft-consider", "setup"])

    from tft_consider.ui.setup_wizard import SetupWizard

    wizard = SetupWizard(config)
    result = wizard.exec()

    if result == QWizard.DialogCode.Accepted:
        config = wizard.get_config()
        try:
            save_config(config)
            print("\n配置已保存。")
            print("现在可以运行 tft-consider run 启动应用。")
        except OSError as exc:
            print(f"\n[错误] 配置保存失败: {exc}")
            sys.exit(1)
    else:
        print("\n已取消配置。")

    # 清理：只在本次创建的 QApplication 上退出
    if existing is None:
        app.quit()


def _cmd_history() -> None:
    """显示最近的对局记录。"""
    from tft_consider.database.models import init_db
    from tft_consider.tracker.replay import list_replays

    init_db()
    replays = list_replays(limit=20)

    if not replays:
        print("暂无对局记录。")
        return

    print(f"\n最近 {len(replays)} 条对局记录:")
    print("-" * 70)
    print(f"{'ID':<6} {'玩家':<12} {'开始时间':<22} {'排名':<6} {'回合数':<8}")
    print("-" * 70)

    for r in replays:
        rank = str(r["final_rank"]) if r["final_rank"] is not None else "-"
        started = r["started_at"][:19] if r["started_at"] else "-"
        print(
            f"{r['id']:<6} "
            f"{r['player_name']:<12} "
            f"{started:<22} "
            f"{rank:<6} "
            f"{r['total_rounds']:<8}"
        )
    print("-" * 70)


if __name__ == "__main__":
    main()
