from django.core.management.base import BaseCommand, CommandError

from account.management.commands.send_weekly_push import _deliver_weekly_push_for_user, _load_weekly_delivery_context
from account.models import PushRecord


class Command(BaseCommand):
    help = "Retry failed weekly push deliveries for one weekly period"

    def add_arguments(self, parser):
        parser.add_argument(
            "--period-key",
            required=True,
            help="Weekly push period key to retry, for example 20260416_20260422",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show which failed users would be retried",
        )

    def handle(self, *args, **options):
        period_key = options["period_key"]
        failed_records = list(
            PushRecord.objects
            .filter(type=PushRecord.TYPE_WEEKLY, period_key=period_key, status=PushRecord.STATUS_FAILED)
            .select_related("user")
            .order_by("user__username")
        )

        if not failed_records:
            self.stdout.write(self.style.WARNING(f"No failed weekly push records found for {period_key}."))
            return

        usernames = [record.user.username for record in failed_records]
        if options["dry_run"]:
            self.stdout.write(
                f"[DRY RUN] Would retry {len(usernames)} failed weekly push user(s) for {period_key}: {', '.join(usernames)}"
            )
            return

        _, daily_paper_lists, _, _, _ = _load_weekly_delivery_context("current")
        for username in usernames:
            self.stdout.write(f"Retrying weekly push for {username} in period {period_key}...")
            record = next(record for record in failed_records if record.user.username == username)
            _deliver_weekly_push_for_user(
                user=record.user,
                daily_paper_lists=daily_paper_lists,
                period_key=record.period_key,
                period_start=record.period_start,
                period_end=record.period_end,
                stdout=self.stdout,
            )

        refreshed_failed_count = PushRecord.objects.filter(
            type=PushRecord.TYPE_WEEKLY,
            period_key=period_key,
            status=PushRecord.STATUS_FAILED,
        ).count()
        if refreshed_failed_count > 0:
            raise CommandError(f"Still have {refreshed_failed_count} failed weekly push record(s) in {period_key}.")

        self.stdout.write(self.style.SUCCESS(f"Retried {len(usernames)} failed weekly push user(s) for {period_key}."))
