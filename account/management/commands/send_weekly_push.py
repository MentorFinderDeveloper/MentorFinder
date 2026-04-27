from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from account.models import PushRecord, WeeklyPushPaperBucket
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
        payload, daily_paper_lists, period_key, period_start, period_end = _load_weekly_delivery_context(options["cycle"])
        users = _get_target_users(options.get("username"))

        if not users.exists():
            self.stdout.write(self.style.WARNING("No target users found."))
            return

        total_recorded_paper_count = sum(len(paper_ids) for paper_ids in payload.values())
        self.stdout.write(
            f"Loaded 7 recorded daily paper lists with {total_recorded_paper_count} paper ID(s)."
        )

        pending_users = []
        for user in users:
            if options["dry_run"]:
                digest = build_weekly_push_digest(user, daily_paper_lists)
                self.stdout.write(
                    f"[DRY RUN] {user.username}: "
                    f"{digest['totalPaperCount']} matched paper(s)."
                )
                continue

            skipped = _deliver_weekly_push_for_user(
                user=user,
                daily_paper_lists=daily_paper_lists,
                period_key=period_key,
                period_start=period_start,
                period_end=period_end,
                stdout=self.stdout,
            )
            if skipped:
                continue
            pending_users.append(user.username)

        if options["dry_run"]:
            return

        if pending_users:
            self.stdout.write(
                f"Weekly push period {period_key}: completed delivery attempts for {len(pending_users)} user(s)."
            )

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


def _load_weekly_delivery_context(cycle: str) -> tuple[dict, list, str, datetime, datetime]:
    payload = load_weekly_push_payload(cycle)
    daily_paper_lists = load_daily_paper_lists_from_cycle(cycle)
    period_key, period_start, period_end = _build_weekly_period_metadata()
    return payload, daily_paper_lists, period_key, period_start, period_end


def _build_weekly_period_metadata(now: datetime | None = None) -> tuple[str, datetime, datetime]:
    local_now = timezone.localtime(now) if now is not None else timezone.localtime()
    start_of_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = start_of_today - timedelta(seconds=1)
    period_start = (start_of_today - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    period_key = f"{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}"
    return period_key, period_start, period_end


def _get_or_create_weekly_push_record(user, period_key: str, period_start: datetime, period_end: datetime) -> PushRecord:
    push_record, created = PushRecord.objects.get_or_create(
        user=user,
        type=PushRecord.TYPE_WEEKLY,
        period_key=period_key,
        defaults={
            "period_start": period_start,
            "period_end": period_end,
            "status": PushRecord.STATUS_PENDING,
        },
    )
    if not created:
        fields_to_update = []
        if push_record.period_start != period_start:
            push_record.period_start = period_start
            fields_to_update.append("period_start")
        if push_record.period_end != period_end:
            push_record.period_end = period_end
            fields_to_update.append("period_end")
        if fields_to_update:
            push_record.save(update_fields=fields_to_update + ["updated_at"])
    return push_record


def _deliver_weekly_push_for_user(
    user,
    daily_paper_lists,
    period_key: str,
    period_start: datetime,
    period_end: datetime,
    stdout,
) -> bool:
    push_record = _get_or_create_weekly_push_record(
        user=user,
        period_key=period_key,
        period_start=period_start,
        period_end=period_end,
    )

    if push_record.status == PushRecord.STATUS_SENT:
        stdout.write(
            f"{user.username}: skipped, already sent for weekly period {period_key}."
        )
        return True

    result = send_weekly_push_email(user, daily_paper_lists)
    status = "sent" if result["sent"] else "failed"
    if result["sent"]:
        _mark_push_record_sent(push_record)
    else:
        _mark_push_record_failed(push_record, "Weekly push email failed")
    stdout.write(
        f"{user.username}: {status}, "
        f"{result['digest']['totalPaperCount']} matched paper(s)."
    )
    if not result["sent"]:
        raise CommandError(f"Weekly push email failed for user {user.username}")

    return False


def _mark_push_record_sent(push_record: PushRecord):
    push_record.status = PushRecord.STATUS_SENT
    push_record.sent_at = timezone.now()
    push_record.error_message = ""
    push_record.save(update_fields=["status", "sent_at", "error_message", "updated_at"])


def _mark_push_record_failed(push_record: PushRecord, error_message: str):
    push_record.status = PushRecord.STATUS_FAILED
    push_record.error_message = error_message
    push_record.save(update_fields=["status", "error_message", "updated_at"])
