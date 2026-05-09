"""配置管理模块。"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = {
    "api": {
        "provider": "moonshot",
        "key": "",
        "model": "kimi-k2-0719-preview",
    },
    "screenshot": {
        "interval_ms": 2000,
        "temp_dir": "",
    },
    "ui": {
        "theme": "dark",
        "opacity": 0.85,
    },
    "data": {
        "sync_interval_hours": 6,
        "auto_sync": True,
    },
    "log": {
        "level": "INFO",
    },
}


def _config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "tft-consider"


def _config_path() -> Path:
    return _config_dir() / "config.yaml"


def load_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    config = dict(DEFAULT_CONFIG)
    _deep_merge(config, loaded)
    return config


def save_config(config: dict[str, Any]) -> None:
    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(_config_path(), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)


def get_api_key(config: dict[str, Any]) -> str:
    api_cfg = config.get("api", {})
    if not isinstance(api_cfg, dict):
        raise ValueError("Invalid config: api section must be a dict")
    key: str = api_cfg.get("key", "")
    if not key:
        raise ValueError("API key not configured. Run setup wizard or set api.key in config.yaml")
    try:
        decoded = base64.b64decode(key).decode("utf-8")
        return str(decoded)
    except Exception:
        return str(key)


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
