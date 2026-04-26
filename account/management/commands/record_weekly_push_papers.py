import json

from django.core.management.base import BaseCommand, CommandError

from account.models import WeeklyPushPaperBucket
from account.services.weekly_push_files import (
    DAY_KEYS,
    append_weekly_push_paper_ids,
)
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
            default="",
            help="Deprecated JSON file argument kept for backward compatibility and ignored by the database-backed implementation",
        )
        parser.add_argument(
            "--cycle",
            default=WeeklyPushPaperBucket.CYCLE_CURRENT,
            choices=[
                WeeklyPushPaperBucket.CYCLE_CURRENT,
                WeeklyPushPaperBucket.CYCLE_NEXT,
            ],
            help="Which cycle bucket to record into, defaults to current",
        )

    def handle(self, *args, **options):
        paper_ids = _parse_paper_ids(options["paper_ids"])
        _ensure_papers_exist(paper_ids)
        day_key = options["day"]
        added_count = append_weekly_push_paper_ids(
            cycle=options["cycle"],
            day_key=day_key,
            paper_ids=paper_ids,
        )
        self.stdout.write(
            f"Recorded {added_count} new paper ID(s) for {day_key} in cycle [{options['cycle']}]."
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
