from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from account.management.commands.send_weekly_push_mock import _get_target_users, _load_mock_daily_paper_lists_from_file
from account.services.weekly_push import build_weekly_push_digest, send_weekly_push_email
from account.services.weekly_push_files import (
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_PAPER_FILE,
    archive_weekly_push_payload,
    create_empty_weekly_push_payload,
    load_weekly_push_payload,
    write_weekly_push_payload,
)


class Command(BaseCommand):
    help = "Send weekly push emails from the recorded seven-day paper JSON file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="username",
            help="Only send the weekly push email to this username",
        )
        parser.add_argument(
            "--paper-file",
            default=DEFAULT_PAPER_FILE,
            help=f"Weekly push JSON file path, defaults to {DEFAULT_PAPER_FILE}",
        )
        parser.add_argument(
            "--archive-dir",
            default=DEFAULT_ARCHIVE_DIR,
            help=f"Archive directory for sent weekly push paper files, defaults to {DEFAULT_ARCHIVE_DIR}",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build weekly push digests without sending emails or resetting the weekly paper file",
        )
    def handle(self, *args, **options):
        paper_file_path = Path(options["paper_file"])
        payload = load_weekly_push_payload(paper_file_path)
        daily_paper_lists = _load_mock_daily_paper_lists_from_file(str(paper_file_path))
        users = _get_target_users(options.get("username"))

        if not users.exists():
            self.stdout.write(self.style.WARNING("No target users found."))
            return

        total_recorded_paper_count = sum(len(paper_ids) for paper_ids in payload.values())
        self.stdout.write(
            f"Loaded 7 recorded daily paper lists with {total_recorded_paper_count} paper ID(s)."
        )

        for user in users:
            if options["dry_run"]:
                digest = build_weekly_push_digest(user, daily_paper_lists)
                self.stdout.write(
                    f"[DRY RUN] {user.username}: "
                    f"{digest['totalPaperCount']} matched paper(s)."
                )
                continue

            result = send_weekly_push_email(user, daily_paper_lists)
            status = "sent" if result["sent"] else "failed"
            self.stdout.write(
                f"{user.username}: {status}, "
                f"{result['digest']['totalPaperCount']} matched paper(s)."
            )
            if not result["sent"]:
                raise CommandError(f"Weekly push email failed for user {user.username}")

        if options["dry_run"]:
            return

        archive_path = archive_weekly_push_payload(
            payload=payload,
            archive_dir=Path(options["archive_dir"]),
            archive_name=_build_archive_file_name(),
        )
        write_weekly_push_payload(
            paper_file_path,
            create_empty_weekly_push_payload(),
        )
        self.stdout.write(
            f"Archived weekly push paper records to {archive_path} and reset {paper_file_path}."
        )


def _build_archive_file_name() -> str:
    timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    return f"weekly_push_{timestamp}.json"
