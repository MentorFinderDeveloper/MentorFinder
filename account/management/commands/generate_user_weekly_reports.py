from django.core.management.base import BaseCommand

from account.models import UserWeeklyReport
from account.management.commands.send_weekly_push_mock import _get_target_users
from account.services.user_weekly_report import generate_user_weekly_report


class Command(BaseCommand):
    help = (
        "Generate (or refresh) per-user weekly reports and persist them into "
        "UserWeeklyReport. Intended to run on the weekly schedule right before "
        "send_weekly_push, so every eligible user has an up-to-date stored report."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="username",
            help="Only generate the weekly report for this username",
        )
        parser.add_argument(
            "--week-offset",
            type=int,
            default=0,
            help="0=上一周（与 send_weekly_push 默认对齐），1=上上周，依此类推",
        )

    def handle(self, *args, **options):
        users = _get_target_users(options.get("username"))
        if not users.exists():
            self.stdout.write(self.style.WARNING("No target users found."))
            return

        week_offset = int(options.get("week_offset") or 0)
        updated = 0
        empty = 0
        for user in users:
            report = generate_user_weekly_report(
                user,
                week_offset=week_offset,
                generated_by_kind=UserWeeklyReport.GENERATED_BY_SCHEDULED,
            )
            updated += 1
            tag = "has updates" if report.has_updates else "no updates"
            if not report.has_updates:
                empty += 1
            self.stdout.write(
                f"{user.username}: week {report.week_start.isoformat()} ~ "
                f"{report.week_end.isoformat()}, {report.total_paper_count} paper(s) "
                f"({tag})."
            )

        self.stdout.write(
            f"User weekly report refresh complete: total={updated}, empty={empty}."
        )
