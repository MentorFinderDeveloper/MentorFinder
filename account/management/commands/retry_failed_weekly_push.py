from django.core.management.base import BaseCommand, CommandError

from account.management.commands.send_weekly_push import _deliver_email_for_user
from account.models import PushRecord
from account.services.user_weekly_report import get_latest_user_weekly_report


class Command(BaseCommand):
    help = "Retry failed weekly push deliveries by re-sending each user's latest stored weekly report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--period-key",
            help=(
                "Optional. Filter retry by PushRecord.period_key (e.g. weekly_20260511 "
                "for new-style records, or legacy 20260416_20260422 for older bucket-era records)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show which failed users would be retried",
        )

    def handle(self, *args, **options):
        period_key = options.get("period_key") or ""
        failed_qs = PushRecord.objects.filter(
            type=PushRecord.TYPE_WEEKLY,
            status=PushRecord.STATUS_FAILED,
        )
        if period_key:
            failed_qs = failed_qs.filter(period_key=period_key)
        failed_records = list(
            failed_qs.select_related("user").order_by("user__username")
        )

        if not failed_records:
            scope = f"period {period_key}" if period_key else "any period"
            self.stdout.write(self.style.WARNING(f"No failed weekly push records found for {scope}."))
            return

        usernames = [record.user.username for record in failed_records]
        if options["dry_run"]:
            self.stdout.write(
                f"[DRY RUN] Would retry {len(usernames)} failed weekly push user(s): {', '.join(usernames)}"
            )
            return

        for record in failed_records:
            user = record.user
            report = get_latest_user_weekly_report(user)
            if report is None:
                self.stdout.write(
                    f"{user.username}: skipped retry, no stored weekly report. "
                    "Run generate_user_weekly_reports first."
                )
                continue
            self.stdout.write(
                f"Retrying weekly push for {user.username} (latest report "
                f"{report.week_start.isoformat()})..."
            )
            _deliver_email_for_user(
                user=user,
                report=report,
                stdout=self.stdout,
                force=True,
            )

        refreshed_failed_count = PushRecord.objects.filter(
            type=PushRecord.TYPE_WEEKLY,
            status=PushRecord.STATUS_FAILED,
            **({"period_key": period_key} if period_key else {}),
        ).count()
        if refreshed_failed_count > 0:
            raise CommandError(
                f"Still have {refreshed_failed_count} failed weekly push record(s) after retry."
            )

        self.stdout.write(self.style.SUCCESS(f"Retried {len(usernames)} failed weekly push user(s)."))
