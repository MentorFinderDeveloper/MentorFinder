import logging
import sys
import threading
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone as django_timezone

from utils.startup_config import load_startup_config


logger = logging.getLogger(__name__)

_scheduler = None
_scheduler_lock = threading.Lock()


def start_django_scheduler() -> bool:
    """Start the in-process scheduler once for the Django web process."""
    if not _should_start_scheduler():
        return False

    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return False

        config = load_startup_config()["startup"]
        if not (
            config["run_daily_sync_scheduler"]
            or config["run_weekly_push_scheduler"]
        ):
            logger.info("Django scheduler disabled by startup config.")
            return False

        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        timezone = ZoneInfo(settings.TIME_ZONE)
        scheduler = BackgroundScheduler(timezone=timezone)

        if config["run_daily_sync_scheduler"]:
            scheduler.add_job(
                _run_sync_dataset_job,
                trigger=CronTrigger(hour=14, minute=20, timezone=timezone),
                id="daily_sync_dataset",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                _run_weekly_home_push_job,
                trigger=CronTrigger(day_of_week="sun", hour=14, minute=30, timezone=timezone),
                id="weekly_home_push",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )

        if config["run_weekly_push_scheduler"]:
            scheduler.add_job(
                _run_weekly_email_push_job,
                trigger=CronTrigger(day_of_week="sun", hour=14, minute=30, timezone=timezone),
                id="weekly_email_push",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )

        scheduler.start()
        _scheduler = scheduler
        logger.info("Django in-process scheduler started.")
        return True


def _should_start_scheduler() -> bool:
    argv = set(sys.argv[1:])
    management_commands_without_scheduler = {
        "check",
        "collectstatic",
        "createsuperuser",
        "makemigrations",
        "migrate",
        "shell",
        "showmigrations",
        "test",
    }
    if argv & management_commands_without_scheduler:
        return False

    if "runserver" in argv:
        return sys.argv[0].endswith("manage.py") and _is_runserver_main_process()

    return True


def _is_runserver_main_process() -> bool:
    import os

    return os.environ.get("RUN_MAIN") == "true"


def _run_sync_dataset_job():
    _run_recorded_task(
        task_name="daily_sync_dataset",
        runner=lambda record: call_command("sync_dataset", scheduled_run_id=record.id),
        error_log_message="Django 定时同步任务执行失败",
        pass_record=True,
    )


def _run_weekly_home_push_job():
    _run_recorded_task(
        task_name="weekly_home_push",
        runner=lambda: call_command("generate_weekly_push"),
        error_log_message="Django 定时首页周推送生成任务执行失败",
    )


def _run_weekly_email_push_job():
    def runner():
        call_command("generate_user_weekly_reports")
        call_command("send_weekly_push")

    _run_recorded_task(
        task_name="weekly_email_push",
        runner=runner,
        error_log_message="Django 定时周报邮件推送任务执行失败",
    )


def _run_recorded_task(*, task_name: str, runner, error_log_message: str, pass_record: bool = False):
    from dataset.models import ScheduledTaskRun

    record = ScheduledTaskRun.objects.create(
        task_name=task_name,
        status=ScheduledTaskRun.STATUS_RUNNING,
    )
    try:
        if pass_record:
            runner(record)
        else:
            runner()
    except Exception as exc:
        record.status = ScheduledTaskRun.STATUS_FAILED
        record.finished_at = django_timezone.now()
        record.error_message = _format_exception(exc)
        record.save(update_fields=["status", "finished_at", "error_message"])
        logger.exception(error_log_message)
        return

    record.status = ScheduledTaskRun.STATUS_SUCCESS
    record.finished_at = django_timezone.now()
    record.error_message = ""
    record.save(update_fields=["status", "finished_at", "error_message"])


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__
