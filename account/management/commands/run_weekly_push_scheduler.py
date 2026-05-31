import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)


def run_weekly_push_job():
    try:
        call_command("generate_user_weekly_reports")
        call_command("send_weekly_push")
    except Exception:
        logger.exception("每周定时周报推送任务执行失败")


class Command(BaseCommand):
    help = "每周定时执行 send_weekly_push，默认在 Asia/Shanghai 时区周日 15:15 运行"

    def add_arguments(self, parser):
        parser.add_argument(
            "--day-of-week",
            default="sun",
            help="每周执行日期，默认 sun",
        )
        parser.add_argument("--hour", type=int, default=15, help="每周执行小时，默认 15")
        parser.add_argument("--minute", type=int, default=15, help="每周执行分钟，默认 15")

    def handle(self, *args, **options):
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        hour = options["hour"]
        minute = options["minute"]
        day_of_week = options["day_of_week"]
        timezone = ZoneInfo(settings.TIME_ZONE)

        scheduler = BlockingScheduler(timezone=timezone)
        scheduler.add_job(
            run_weekly_push_job,
            trigger=CronTrigger(
                day_of_week=day_of_week,
                hour=hour,
                minute=minute,
                timezone=timezone,
            ),
            id="weekly_push_job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"已启动每周周报推送任务：每周 {day_of_week} {hour:02d}:{minute:02d} ({settings.TIME_ZONE})"
            )
        )

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING("每周周报推送任务已停止"))
