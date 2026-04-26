import json
from pathlib import Path

from django.core.management.base import CommandError


DAY_KEYS = [
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
]

DEFAULT_PAPER_FILE = "data/mock_weekly_papers.json"
DEFAULT_ARCHIVE_DIR = "data/weekly_push_archive"


def load_weekly_push_payload(file_path: Path) -> dict:
    if not file_path.exists():
        raise CommandError(f"Paper file does not exist: {file_path}")

    try:
        with file_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Invalid JSON in paper file: {file_path}") from exc

    if not isinstance(payload, dict):
        raise CommandError("Paper file must contain a JSON object.")

    normalized_payload = {}
    for day_key in DAY_KEYS:
        paper_ids = payload.get(day_key, [])
        if not isinstance(paper_ids, list):
            raise CommandError(f"Paper IDs for [{day_key}] must be a list.")
        if not all(isinstance(paper_id, int) for paper_id in paper_ids):
            raise CommandError(f"Paper IDs for [{day_key}] must be integers.")
        normalized_payload[day_key] = paper_ids

    return normalized_payload


def create_empty_weekly_push_payload() -> dict:
    return {day_key: [] for day_key in DAY_KEYS}


def write_weekly_push_payload(file_path: Path, payload: dict):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def archive_weekly_push_payload(
    payload: dict,
    archive_dir: Path,
    archive_name: str,
) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / archive_name
    write_weekly_push_payload(archive_path, payload)
    return archive_path
