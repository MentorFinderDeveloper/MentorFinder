import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from account.models import User
from account.services.weekly_push import build_weekly_push_digest, send_weekly_push_email
from dataset.models import Paper

DAY_KEYS = [
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
]


class Command(BaseCommand):
    help = "Send weekly push emails with mocked seven-day crawler paper lists"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="username",
            help="Only send the mock weekly push email to this username",
        )
        parser.add_argument(
            "--paper-limit",
            type=int,
            default=20,
            help="Number of recent papers used to build the mocked seven-day lists",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build weekly push digests without sending emails",
        )
        parser.add_argument(
            "--paper-file",
            help="Load mocked seven-day paper lists from a JSON file",
        )

    def handle(self, *args, **options):
        daily_paper_lists = _resolve_mock_daily_paper_lists(
            options.get("paper_file"),
            options["paper_limit"],
        )
        users = _get_target_users(options.get("username"))

        if not users.exists():
            self.stdout.write(self.style.WARNING("No target users found."))
            return

        self.stdout.write(
            f"Prepared 7 mocked daily paper lists with "
            f"{sum(len(papers) for papers in daily_paper_lists)} papers."
        )

        for user in users:
            if options["dry_run"]:
                digest = build_weekly_push_digest(user, daily_paper_lists)
                self.stdout.write(
                    f"[DRY RUN] {user.username}: "
                    f"{digest['totalPaperCount']} matched paper(s)."
                )
                continue

            try:
                result = send_weekly_push_email(user, daily_paper_lists)
            except Exception as exc:
                error_message = _format_mock_weekly_push_failure_reason(exc)
                self.stdout.write(f"{user.username}: failed before email delivery completed.")
                self.stdout.write(f"{user.username}: failure reason: {error_message}")
                continue

            status = "sent" if result["sent"] else "failed"
            self.stdout.write(
                f"{user.username}: {status}, "
                f"{result['digest']['totalPaperCount']} matched paper(s)."
            )
            if not result["sent"] and result.get("errorMessage"):
                self.stdout.write(
                    f"{user.username}: failure reason: {result['errorMessage']}"
                )


def _build_mock_daily_paper_lists(paper_limit: int) -> list[list[Paper]]:
    daily_paper_lists = [[] for _ in range(7)]
    if paper_limit <= 0:
        return daily_paper_lists

    papers = Paper.objects.order_by("-publish_date", "-id")[:paper_limit]
    for index, paper in enumerate(papers):
        daily_paper_lists[index % 7].append(paper)

    return daily_paper_lists


def _resolve_mock_daily_paper_lists(paper_file: str | None, paper_limit: int) -> list[list[Paper]]:
    if paper_file:
        return _load_mock_daily_paper_lists_from_file(paper_file)
    return _build_mock_daily_paper_lists(paper_limit)


def _load_mock_daily_paper_lists_from_file(paper_file: str) -> list[list[Paper]]:
    file_path = Path(paper_file)
    if not file_path.exists():
        raise CommandError(f"Paper file does not exist: {paper_file}")

    try:
        with file_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Invalid JSON in paper file: {paper_file}") from exc

    if not isinstance(payload, dict):
        raise CommandError("Paper file must contain a JSON object.")

    daily_paper_lists = []
    for day_key in DAY_KEYS:
        paper_ids = payload.get(day_key, [])
        if not isinstance(paper_ids, list):
            raise CommandError(f"Paper IDs for [{day_key}] must be a list.")
        if not all(isinstance(paper_id, int) for paper_id in paper_ids):
            raise CommandError(f"Paper IDs for [{day_key}] must be integers.")

        papers = list(Paper.objects.filter(id__in=paper_ids))
        paper_map = {paper.id: paper for paper in papers}

        missing_ids = [paper_id for paper_id in paper_ids if paper_id not in paper_map]
        if missing_ids:
            raise CommandError(
                f"Paper IDs not found for [{day_key}]: {', '.join(str(pid) for pid in missing_ids)}"
            )

        daily_paper_lists.append([paper_map[paper_id] for paper_id in paper_ids])

    return daily_paper_lists


def _get_target_users(username: str | None):
    users = User.objects.exclude(email="")
    if username:
        users = users.filter(username=username)
    return users.order_by("id")


def _format_mock_weekly_push_failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__
