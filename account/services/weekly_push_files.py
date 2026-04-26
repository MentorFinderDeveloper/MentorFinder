import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import CommandError
from django.utils import timezone


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
DEFAULT_NEXT_PAPER_FILE = "data/mock_weekly_papers_next.json"
DEFAULT_ARCHIVE_DIR = "data/weekly_push_archive"
WEEKLY_PUSH_CUTOFF_WEEKDAY = 3
WEEKLY_PUSH_CUTOFF_HOUR = 12
WEEKLY_PUSH_CUTOFF_MINUTE = 0


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


def load_or_create_weekly_push_payload(file_path: Path) -> dict:
    if not file_path.exists():
        return create_empty_weekly_push_payload()
    return load_weekly_push_payload(file_path)


def create_empty_weekly_push_payload() -> dict:
    return {day_key: [] for day_key in DAY_KEYS}


def write_weekly_push_payload(file_path: Path, payload: dict):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def append_unique_paper_ids(existing_ids: list[int], new_ids: list[int]) -> list[int]:
    result = list(existing_ids)
    seen_ids = set(existing_ids)
    for paper_id in new_ids:
        if paper_id in seen_ids:
            continue
        result.append(paper_id)
        seen_ids.add(paper_id)
    return result


def append_weekly_push_paper_ids(
    file_path: Path,
    day_key: str,
    paper_ids: list[int],
) -> int:
    payload = load_or_create_weekly_push_payload(file_path)
    existing_ids = payload[day_key]
    payload[day_key] = append_unique_paper_ids(existing_ids, paper_ids)
    write_weekly_push_payload(file_path, payload)
    return len(payload[day_key]) - len(existing_ids)


def get_weekly_push_day_key(now: datetime | None = None) -> str:
    local_now = _normalize_local_datetime(now)
    day_key_by_weekday = {
        3: "thursday",
        4: "friday",
        5: "saturday",
        6: "sunday",
        0: "monday",
        1: "tuesday",
        2: "wednesday",
    }
    return day_key_by_weekday[local_now.weekday()]


def should_stage_next_cycle_payload(now: datetime | None = None) -> bool:
    local_now = _normalize_local_datetime(now)
    if local_now.weekday() != WEEKLY_PUSH_CUTOFF_WEEKDAY:
        return False
    current_minutes = local_now.hour * 60 + local_now.minute
    cutoff_minutes = WEEKLY_PUSH_CUTOFF_HOUR * 60 + WEEKLY_PUSH_CUTOFF_MINUTE
    return current_minutes < cutoff_minutes


def resolve_weekly_push_record_target_path(
    paper_file: Path,
    next_paper_file: Path,
    now: datetime | None = None,
) -> Path:
    if should_stage_next_cycle_payload(now):
        return next_paper_file
    return paper_file


def archive_weekly_push_payload(
    payload: dict,
    archive_dir: Path,
    archive_name: str,
) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / archive_name
    write_weekly_push_payload(archive_path, payload)
    return archive_path


def promote_staged_weekly_push_payload(
    paper_file: Path,
    next_paper_file: Path,
) -> bool:
    if not next_paper_file.exists():
        return False

    payload = load_weekly_push_payload(next_paper_file)
    write_weekly_push_payload(paper_file, payload)
    next_paper_file.unlink()
    return True


def _normalize_local_datetime(now: datetime | None) -> datetime:
    if now is None:
        return timezone.localtime()
    if timezone.is_naive(now):
        return timezone.make_aware(now, timezone.get_current_timezone())
    return timezone.localtime(now)
