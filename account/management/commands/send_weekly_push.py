from datetime import datetime, time

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from account.models import PushRecord, UserWeeklyReport
from account.management.commands.send_weekly_push_mock import _get_target_users
from account.services.user_weekly_report import (
    build_period_key_from_week_start,
    get_latest_user_weekly_report,
)
from account.services.weekly_push import send_weekly_push_email_from_digest


class Command(BaseCommand):
    help = (
        "Send weekly push emails from each user's most recent stored weekly "
        "report (UserWeeklyReport). The stored report is what the homepage "
        "shows, so the email and the homepage always agree."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="username",
            help="Only send the weekly push email to this username",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build email content without actually sending or recording delivery",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Force-resend even to users already marked as sent for this report's week. "
                "Failures only log without aborting. Users whose latest report has no "
                "personal updates are still skipped."
            ),
        )

    def handle(self, *args, **options):
        users = _get_target_users(options.get("username"))
        if not users.exists():
            self.stdout.write(self.style.WARNING("No target users found."))
            return

        force = bool(options.get("force"))
        dry_run = bool(options.get("dry_run"))
        sent_count = 0
        skipped_count = 0
        failed_count = 0

        for user in users:
            report = get_latest_user_weekly_report(user)
            if report is None:
                self.stdout.write(
                    f"{user.username}: skipped, no stored weekly report yet. "
                    "Run generate_user_weekly_reports first."
                )
                skipped_count += 1
                continue

            if not report.has_updates:
                self.stdout.write(
                    f"{user.username}: skipped, latest report ({report.week_start.isoformat()}) "
                    f"has no personal updates ({report.total_paper_count} matched paper(s))."
                )
                skipped_count += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] {user.username}: would send report for "
                    f"{report.week_start.isoformat()} with {report.total_paper_count} paper(s)."
                )
                continue

            try:
                result = _deliver_email_for_user(
                    user=user,
                    report=report,
                    stdout=self.stdout,
                    force=force,
                )
            except CommandError:
                failed_count += 1
                continue

            if result == "sent":
                sent_count += 1
            elif result == "skipped":
                skipped_count += 1
            else:
                failed_count += 1

        if dry_run:
            return

        self.stdout.write(
            f"Weekly push delivery summary: sent={sent_count}, "
            f"skipped={skipped_count}, failed={failed_count}."
        )


def _deliver_email_for_user(
    *,
    user,
    report: UserWeeklyReport,
    stdout,
    force: bool,
) -> str:
    """Returns one of "sent", "skipped", "failed"."""
    period_key = build_period_key_from_week_start(report.week_start)
    period_start, period_end = _bounds_for_week(report.week_start, report.week_end)
    push_record = _get_or_create_weekly_push_record(
        user=user,
        period_key=period_key,
        period_start=period_start,
        period_end=period_end,
    )

    if not force and push_record.status == PushRecord.STATUS_SENT:
        stdout.write(
            f"{user.username}: skipped, already sent for week {report.week_start.isoformat()}."
        )
        return "skipped"

    try:
        result = send_weekly_push_email_from_digest(user, report.digest or {})
    except Exception as exc:
        error_message = _format_email_failure_reason(exc)
        _mark_push_record_failed(push_record, error_message)
        stdout.write(f"{user.username}: failed before email delivery completed.")
        stdout.write(f"{user.username}: failure reason: {error_message}")
        if force:
            return "failed"
        raise CommandError(
            f"Weekly push email failed for user {user.username}: {error_message}"
        ) from exc

    # 即使 digest.hasUpdates 为 False，service 也会返回 skipped=True。
    # 这里把它当成"本周无更新"处理：PushRecord 标为 sent，避免重试任务反复处理。
    if result.get("skipped"):
        _mark_push_record_sent(push_record)
        stdout.write(
            f"{user.username}: skipped, no personal updates "
            f"({result['digest'].get('totalPaperCount', 0)} matched paper(s))."
        )
        return "skipped"

    if result["sent"]:
        _mark_push_record_sent(push_record)
        stdout.write(
            f"{user.username}: sent, {result['digest'].get('totalPaperCount', 0)} matched paper(s)."
        )
        return "sent"

    error_message = (
        str(result.get("errorMessage") or "").strip()
        or "Weekly push email failed"
    )
    _mark_push_record_failed(push_record, error_message)
    stdout.write(f"{user.username}: failed.")
    stdout.write(f"{user.username}: failure reason: {error_message}")
    return "failed"


def _bounds_for_week(week_start, week_end):
    """Build aware datetime bounds for PushRecord.period_start/period_end."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(week_start, time.min), tz)
    end = timezone.make_aware(datetime.combine(week_end, time.max), tz)
    return start, end


def _get_or_create_weekly_push_record(user, period_key, period_start, period_end):
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


def _mark_push_record_sent(push_record: PushRecord):
    push_record.status = PushRecord.STATUS_SENT
    push_record.sent_at = timezone.now()
    push_record.error_message = ""
    push_record.save(update_fields=["status", "sent_at", "error_message", "updated_at"])


def _mark_push_record_failed(push_record: PushRecord, error_message: str):
    push_record.status = PushRecord.STATUS_FAILED
    push_record.error_message = error_message
    push_record.save(update_fields=["status", "error_message", "updated_at"])


def _format_email_failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__
