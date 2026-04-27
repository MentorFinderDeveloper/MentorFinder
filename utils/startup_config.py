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


def _clone_default_startup_config() -> dict:
    return {
        "startup": dict(DEFAULT_STARTUP_CONFIG["startup"]),
    }


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default
