import json
from pathlib import Path

from django.core.management.base import BaseCommand

from account.services.weekly_push_files import DAY_KEYS, DEFAULT_PAPER_FILE


class Command(BaseCommand):
    help = "Reset the weekly push paper JSON file to empty seven-day lists"

    def add_arguments(self, parser):
        parser.add_argument(
            "--paper-file",
            default=DEFAULT_PAPER_FILE,
            help=f"Weekly push JSON file path, defaults to {DEFAULT_PAPER_FILE}",
        )

    def handle(self, *args, **options):
        file_path = Path(options["paper_file"])
        payload = {day_key: [] for day_key in DAY_KEYS}

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
            fp.write("\n")

        self.stdout.write(f"Reset weekly push paper records in {file_path}.")
