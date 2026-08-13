from pathlib import Path

import yaml


CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yaml"

DEFAULT_STARTUP_CONFIG = {
    "startup": {
        "run_initial_sync": True,
        "run_daily_sync_scheduler": True,
        "run_weekly_push_scheduler": True,
    }
}


# 加载启动配置文件，并对缺省值和类型做兜底处理。
def load_startup_config(config_path: Path | None = None) -> dict:
    target_path = config_path or CONFIG_FILE
    if not target_path.exists():
        return _clone_default_startup_config()

    with target_path.open("r", encoding="utf-8") as fp:
        payload = yaml.safe_load(fp) or {}

    if not isinstance(payload, dict):
        return _clone_default_startup_config()

    startup_payload = payload.get("startup") or {}
    if not isinstance(startup_payload, dict):
        startup_payload = {}

    return {
        "startup": {
            "run_initial_sync": _coerce_bool(
                startup_payload.get("run_initial_sync"),
                DEFAULT_STARTUP_CONFIG["startup"]["run_initial_sync"],
            ),
            "run_daily_sync_scheduler": _coerce_bool(
                startup_payload.get("run_daily_sync_scheduler"),
                DEFAULT_STARTUP_CONFIG["startup"]["run_daily_sync_scheduler"],
            ),
            "run_weekly_push_scheduler": _coerce_bool(
                startup_payload.get("run_weekly_push_scheduler"),
                DEFAULT_STARTUP_CONFIG["startup"]["run_weekly_push_scheduler"],
            ),
        }
    }


# 返回一份默认启动配置的独立副本。
def _clone_default_startup_config() -> dict:
    return {
        "startup": dict(DEFAULT_STARTUP_CONFIG["startup"]),
    }


# 在配置值为布尔类型时直接返回，否则回退到默认值。
def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default
