import logging
import sys
import threading
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.db.models import Q
from django.utils import timezone as django_timezone

from utils.startup_config import load_startup_config


logger = logging.getLogger(__name__)

_scheduler = None
_scheduler_lock = threading.Lock()

# 心跳停滞超过该阈值仍处于 running 的记录，视为已被重启/重新部署杀死的孤儿任务。
# 一次完整同步会每处理一位导师就更新一次心跳（间隔通常几十秒），15 分钟无心跳即可判死。
STALE_RUNNING_THRESHOLD = timedelta(minutes=15)


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

        # 进程（重新部署/重启）启动时，先把上一轮残留、卡在 running 的孤儿任务判死，
        # 避免状态永远停在 running，也便于排查“又被部署打断了”。
        _mark_orphaned_running_tasks_failed()

        timezone = ZoneInfo(settings.TIME_ZONE)
        scheduler = BackgroundScheduler(timezone=timezone)

        if config["run_daily_sync_scheduler"]:
            scheduler.add_job(
                _run_sync_dataset_job,
                trigger=CronTrigger(hour=18, minute=0, timezone=timezone),
                id="daily_sync_dataset",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                _run_weekly_home_push_job,
                trigger=CronTrigger(day_of_week="sun", hour=15, minute=15, timezone=timezone),
                id="weekly_home_push",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )

        if config["run_weekly_push_scheduler"]:
            scheduler.add_job(
                _run_weekly_email_push_job,
                trigger=CronTrigger(day_of_week="sun", hour=15, minute=15, timezone=timezone),
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


def _mark_orphaned_running_tasks_failed() -> int:
    """把上一轮进程残留、卡在 running 的任务判死。

    进程被 SIGKILL（重新部署 / 重启 / 被杀）时，``_run_recorded_task`` 的 except 来不及
    执行，记录会永远停在 running。调度器启动时清理这些孤儿：心跳为空、或心跳停滞超过
    ``STALE_RUNNING_THRESHOLD`` 的 running 记录全部标记为 failed。心跳仍新鲜的（极少数
    滚动升级期间另一实例正在跑）会被保留，不会误杀。
    """
    from dataset.models import ScheduledTaskRun

    now = django_timezone.now()
    stale_before = now - STALE_RUNNING_THRESHOLD
    updated = (
        ScheduledTaskRun.objects
        .filter(status=ScheduledTaskRun.STATUS_RUNNING)
        .filter(Q(last_heartbeat_at__isnull=True) | Q(last_heartbeat_at__lt=stale_before))
        .update(
            status=ScheduledTaskRun.STATUS_FAILED,
            finished_at=now,
            error_message="进程中断（疑似重新部署/重启/被杀），由调度器启动时清理。",
        )
    )
    if updated:
        logger.warning("启动时清理了 %s 条卡在 running 的孤儿定时任务记录。", updated)
    return updated


def _has_fresh_running_task(task_name: str) -> bool:
    """判断是否已有同名任务正在运行（心跳新鲜），用于避免重复触发。"""
    from dataset.models import ScheduledTaskRun

    fresh_after = django_timezone.now() - STALE_RUNNING_THRESHOLD
    return (
        ScheduledTaskRun.objects
        .filter(
            task_name=task_name,
            status=ScheduledTaskRun.STATUS_RUNNING,
            last_heartbeat_at__gte=fresh_after,
        )
        .exists()
    )


def _run_recorded_task(*, task_name: str, runner, error_log_message: str, pass_record: bool = False):
    from dataset.models import ScheduledTaskRun

    # 去重守卫：若已有同名任务正在运行（如滚动升级期间新旧实例并存），跳过本次触发，
    # 避免出现重复爬取（历史记录里出现过同一秒两条 daily_sync_dataset 的情况）。
    if _has_fresh_running_task(task_name):
        logger.warning("任务 %s 已有正在运行的实例，跳过本次触发以避免重复。", task_name)
        return

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
