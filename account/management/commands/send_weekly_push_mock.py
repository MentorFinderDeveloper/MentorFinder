from django.core.management.base import BaseCommand

from account.models import User
from account.services.weekly_push import build_weekly_push_digest, send_weekly_push_email
from dataset.models import Paper


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

    def handle(self, *args, **options):
        daily_paper_lists = _build_mock_daily_paper_lists(options["paper_limit"])
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

            result = send_weekly_push_email(user, daily_paper_lists)
            status = "sent" if result["sent"] else "failed"
            self.stdout.write(
                f"{user.username}: {status}, "
                f"{result['digest']['totalPaperCount']} matched paper(s)."
            )


def _build_mock_daily_paper_lists(paper_limit: int) -> list[list[Paper]]:
    daily_paper_lists = [[] for _ in range(7)]
    if paper_limit <= 0:
        return daily_paper_lists

    papers = Paper.objects.order_by("-publish_date", "-id")[:paper_limit]
    for index, paper in enumerate(papers):
        daily_paper_lists[index % 7].append(paper)

    return daily_paper_lists


def _get_target_users(username: str | None):
    users = User.objects.exclude(email="")
    if username:
        users = users.filter(username=username)
    return users.order_by("id")
