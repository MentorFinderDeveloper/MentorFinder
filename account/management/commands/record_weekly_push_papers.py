import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from account.services.weekly_push_files import DAY_KEYS, DEFAULT_PAPER_FILE
from dataset.models import Paper


class Command(BaseCommand):
    help = "Append daily crawler incremental paper IDs to a weekly push JSON file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--day",
            required=True,
            choices=DAY_KEYS,
            help="Target day key in the weekly push JSON file",
        )
        parser.add_argument(
            "--paper-ids",
            required=True,
            help="Comma-separated Paper.id values discovered by today's crawler run",
        )
        parser.add_argument(
            "--paper-file",
            default=DEFAULT_PAPER_FILE,
            help=f"Weekly push JSON file path, defaults to {DEFAULT_PAPER_FILE}",
        )

    def handle(self, *args, **options):
        paper_ids = _parse_paper_ids(options["paper_ids"])
        _ensure_papers_exist(paper_ids)

        file_path = Path(options["paper_file"])
        payload = _load_or_create_payload(file_path)
        day_key = options["day"]
        existing_ids = payload[day_key]
        payload[day_key] = _append_unique_ids(existing_ids, paper_ids)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
            fp.write("\n")

        added_count = len(payload[day_key]) - len(existing_ids)
        self.stdout.write(
            f"Recorded {added_count} new paper ID(s) for {day_key} in {file_path}."
        )


def _parse_paper_ids(raw_paper_ids: str) -> list[int]:
    paper_ids = []
    for raw_id in raw_paper_ids.split(","):
        normalized_id = raw_id.strip()
        if normalized_id == "":
            continue
        try:
            paper_ids.append(int(normalized_id))
        except ValueError as exc:
            raise CommandError(f"Invalid paper ID: {normalized_id}") from exc

    if not paper_ids:
        raise CommandError("At least one paper ID is required.")

    return paper_ids


def _ensure_papers_exist(paper_ids: list[int]):
    existing_ids = set(Paper.objects.filter(id__in=paper_ids).values_list("id", flat=True))
    missing_ids = [paper_id for paper_id in paper_ids if paper_id not in existing_ids]
    if missing_ids:
        raise CommandError(
            f"Paper IDs not found: {', '.join(str(paper_id) for paper_id in missing_ids)}"
        )


def _load_or_create_payload(file_path: Path) -> dict:
    if not file_path.exists():
        return {day_key: [] for day_key in DAY_KEYS}

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


def _append_unique_ids(existing_ids: list[int], new_ids: list[int]) -> list[int]:
    result = list(existing_ids)
    seen_ids = set(existing_ids)
    for paper_id in new_ids:
        if paper_id in seen_ids:
            continue
        result.append(paper_id)
        seen_ids.add(paper_id)
    return result
