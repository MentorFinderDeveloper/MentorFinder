from django.core.management.base import BaseCommand

from account.models import WeeklyPushPaperBucket
from account.services.weekly_push_files import DAY_KEYS, clear_weekly_push_cycle


class Command(BaseCommand):
    help = "Reset the weekly push paper bucket table for one cycle"

    def add_arguments(self, parser):
        parser.add_argument(
            "--paper-file",
            default="",
            help="Deprecated JSON file argument kept for backward compatibility and ignored by the database-backed implementation",
        )
        parser.add_argument(
            "--cycle",
            default=WeeklyPushPaperBucket.CYCLE_CURRENT,
            choices=[
                WeeklyPushPaperBucket.CYCLE_CURRENT,
                WeeklyPushPaperBucket.CYCLE_NEXT,
            ],
            help="Which cycle bucket to reset, defaults to current",
        )

    def handle(self, *args, **options):
        clear_weekly_push_cycle(options["cycle"])
        self.stdout.write(f"Reset weekly push paper records in cycle [{options['cycle']}].")
