from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from account.models import WeeklyPushPaperBucket
from account.management.commands.send_weekly_push_mock import _get_target_users
from account.services.weekly_push import build_weekly_push_digest, send_weekly_push_email
from account.services.weekly_push_files import (
    archive_weekly_push_payload,
    load_weekly_push_payload,
    load_daily_paper_lists_from_cycle,
    promote_staged_weekly_push_payload,
)


class Command(BaseCommand):
    help = "Send weekly push emails from the database-backed weekly push buckets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="username",
            help="Only send the weekly push email to this username",
        )
        parser.add_argument(
            "--cycle",
            default=WeeklyPushPaperBucket.CYCLE_CURRENT,
            choices=[WeeklyPushPaperBucket.CYCLE_CURRENT],
            help="Which cycle bucket to send, defaults to current",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build weekly push digests without sending emails or updating weekly push buckets",
        )
    def handle(self, *args, **options):
        payload = load_weekly_push_payload(options["cycle"])
        daily_paper_lists = load_daily_paper_lists_from_cycle(options["cycle"])
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

        archive_batch = _build_archive_batch()
        archived_count = archive_weekly_push_payload(archive_batch)
        promoted = promote_staged_weekly_push_payload()
        if not promoted:
            self.stdout.write(
                f"Archived {archived_count} weekly push paper record(s) into batch {archive_batch} and reset current cycle."
            )
            return
        self.stdout.write(
            f"Archived {archived_count} weekly push paper record(s) into batch {archive_batch} and promoted staged next-cycle records."
        )


def _build_archive_batch() -> str:
    return timezone.localtime().strftime("%Y%m%d_%H%M%S")
