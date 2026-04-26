from django.core.management.base import BaseCommand

from account.models import PushRecord


class Command(BaseCommand):
    help = "Show weekly push delivery records with optional filters"

    def add_arguments(self, parser):
        parser.add_argument("--period-key", help="Filter by weekly period key")
        parser.add_argument("--status", choices=[
            PushRecord.STATUS_PENDING,
            PushRecord.STATUS_SENT,
            PushRecord.STATUS_FAILED,
        ], help="Filter by push status")
        parser.add_argument("--username", help="Filter by username")
        parser.add_argument("--limit", type=int, default=20, help="Maximum number of records to display")

    def handle(self, *args, **options):
        queryset = PushRecord.objects.filter(type=PushRecord.TYPE_WEEKLY).select_related("user").order_by("-updated_at", "-id")

        period_key = options.get("period_key")
        if period_key:
            queryset = queryset.filter(period_key=period_key)

        status = options.get("status")
        if status:
            queryset = queryset.filter(status=status)

        username = options.get("username")
        if username:
            queryset = queryset.filter(user__username=username)

        records = list(queryset[: max(options["limit"], 1)])
        if not records:
            self.stdout.write(self.style.WARNING("No weekly push records found."))
            return

        for record in records:
            sent_at = record.sent_at.isoformat(sep=" ", timespec="seconds") if record.sent_at else "-"
            self.stdout.write(
                f"{record.user.username} | {record.period_key} | {record.status} | sent_at={sent_at}"
            )
            if record.error_message:
                self.stdout.write(f"  error={record.error_message}")
