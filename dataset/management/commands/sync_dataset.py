from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Fetch mentors first, then fetch papers"

    def handle(self, *args, **options):
        self.stdout.write("开始同步导师与论文数据...")

        self.stdout.write("[1/2] 执行 fetch_mentors")
        call_command("fetch_mentors")

        self.stdout.write("[2/2] 执行 fetch_papers")
        call_command("fetch_papers")

        self.stdout.write(self.style.SUCCESS("同步完成"))
