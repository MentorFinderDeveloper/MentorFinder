from django.core.management import call_command
from django.core.management.base import BaseCommand

from dataset.services.scheduled_task_progress import update_scheduled_task_progress


class Command(BaseCommand):
    help = "Fetch mentors first, then fetch papers"

    def add_arguments(self, parser):
        parser.add_argument("--scheduled-run-id", type=int, default=None)
        parser.add_argument(
            "--start-index",
            type=int,
            default=0,
            help="论文抓取从第 N 位导师之后开始（断点续跑用）",
        )
        parser.add_argument(
            "--skip-mentors",
            action="store_true",
            help="跳过导师抓取阶段，直接抓论文（断点续跑用）",
        )

    def handle(self, *args, **options):
        scheduled_run_id = options["scheduled_run_id"]
        start_index = max(0, options.get("start_index") or 0)
        skip_mentors = options.get("skip_mentors", False)
        self.stdout.write("开始同步导师与论文数据...")
        update_scheduled_task_progress(
            scheduled_run_id,
            "开始同步导师与论文数据",
            current=0,
            total=2,
        )

        if not skip_mentors:
            self.stdout.write("[1/2] 执行 fetch_mentors")
            update_scheduled_task_progress(scheduled_run_id, "[1/2] 正在抓取导师数据", current=0, total=2)
            call_command("fetch_mentors")
            update_scheduled_task_progress(scheduled_run_id, "[1/2] 导师数据抓取完成", current=1, total=2)
        else:
            self.stdout.write(f"[续跑] 跳过导师抓取，从第 {start_index} 位导师之后开始抓论文")
            update_scheduled_task_progress(
                scheduled_run_id,
                f"[续跑] 跳过导师抓取，从第 {start_index} 位之后继续",
                current=1,
                total=2,
            )

        self.stdout.write("[2/2] 执行 fetch_papers")
        update_scheduled_task_progress(scheduled_run_id, "[2/2] 正在抓取论文数据", current=1, total=2)
        call_command("fetch_papers", scheduled_run_id=scheduled_run_id, start_index=start_index)

        self.stdout.write(self.style.SUCCESS("同步完成"))
        update_scheduled_task_progress(scheduled_run_id, "导师与论文数据同步完成", current=2, total=2)
