import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def run_sync_dataset_job():
    try:
        call_command("sync_dataset")
    except Exception:
        logger.exception("每日定时同步任务执行失败")


def run_weekly_push_job():
    try:
        call_command("generate_weekly_push")
    except Exception:
        logger.exception("每周主页推送生成任务执行失败")


class Command(BaseCommand):
    help = "每天定时执行 sync_dataset，默认在 Asia/Shanghai 时区 04:00 运行"

    def add_arguments(self, parser):
        parser.add_argument("--hour", type=int, default=4, help="每日执行小时，默认 4")
        parser.add_argument("--minute", type=int, default=0, help="每日执行分钟，默认 0")

    def handle(self, *args, **options):
        hour = options["hour"]
        minute = options["minute"]
        timezone = ZoneInfo(settings.TIME_ZONE)

        scheduler = BlockingScheduler(timezone=timezone)
        scheduler.add_job(
            run_sync_dataset_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
            id="daily_sync_dataset",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            run_weekly_push_job,
            trigger=CronTrigger(day_of_week="mon", hour=7, minute=0, timezone=timezone),
            id="weekly_home_push",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"已启动定时任务：每天 {hour:02d}:{minute:02d} 同步数据；每周一 07:00 生成主页推送 ({settings.TIME_ZONE})"
            )
        )

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING("定时同步任务已停止"))
