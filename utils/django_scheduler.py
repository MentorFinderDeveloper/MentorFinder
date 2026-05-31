import logging
import sys
import threading
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.db.models import F, Q
from django.utils import timezone as django_timezone

from utils.startup_config import load_startup_config


logger = logging.getLogger(__name__)

_scheduler = None
_scheduler_lock = threading.Lock()

# 心跳停滞超过该阈值仍处于 running 的记录，视为已被重启/重新部署杀死的孤儿任务。
# 一次完整同步会每处理一位导师就更新一次心跳（间隔通常几十秒），15 分钟无心跳即可判死。
STALE_RUNNING_THRESHOLD = timedelta(minutes=15)

# 只续跑最近这么久内被中断的同步任务，避免把很久以前的失败任务又拉起来。
RESUME_MAX_AGE = timedelta(hours=24)

# 区分 progress_current 含义的阈值：逐位抓论文阶段 progress_total=导师数（≥3），
# 而导师抓取/包装阶段 progress_total=2。≥该值才把 progress_current 当作“导师序号”用于续跑。
RESUME_PAPERS_PHASE_MIN_TOTAL = 3

# 进程启动后延迟这么久再触发续跑，给应用/数据库连接初始化留出时间。
RESUME_DELAY_SECONDS = 10


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

        # 进程（重新部署/重启）启动时：先找出被中断、可从断点续跑的同步任务，
        # 其余卡在 running 的孤儿全部判死（但保留要续跑的那条）。
        resumable_run = _find_resumable_sync_run()
        resume_id = resumable_run.id if resumable_run is not None else None
        _mark_orphaned_running_tasks_failed(exclude_id=resume_id)

        timezone = ZoneInfo(settings.TIME_ZONE)
        scheduler = BackgroundScheduler(timezone=timezone)

        if config["run_daily_sync_scheduler"]:
            scheduler.add_job(
                _run_sync_dataset_job,
                trigger=CronTrigger(hour=4, minute=0, timezone=timezone),
                id="daily_sync_dataset",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                _run_sync_dataset_job,
                trigger=CronTrigger(hour=12, minute=0, timezone=timezone),
                id="daily_sync_dataset",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                _run_sync_dataset_job,
                trigger=CronTrigger(hour=20, minute=0, timezone=timezone),
                id="daily_sync_dataset",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            scheduler.add_job(
                _run_weekly_home_push_job,
                trigger=CronTrigger(day_of_week="mon", hour=5, minute=0, timezone=timezone),
                id="weekly_home_push",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )

        if config["run_weekly_push_scheduler"]:
            scheduler.add_job(
                _run_weekly_email_push_job,
                trigger=CronTrigger(day_of_week="mon", hour=5, minute=0, timezone=timezone),
                id="weekly_email_push",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )

        # 若上一轮同步被部署/重启打断，进程一起来就排一个一次性任务，从断点继续抓取，
        # 而不是等到明天的定时时间。这样“部署中断”对爬虫只是暂停几秒、随后自动续跑。
        if resumable_run is not None:
            in_papers_phase = (resumable_run.progress_total or 0) >= RESUME_PAPERS_PHASE_MIN_TOTAL
            start_index = (resumable_run.progress_current or 0) if in_papers_phase else 0
            skip_mentors = in_papers_phase
            run_date = django_timezone.now() + timedelta(seconds=RESUME_DELAY_SECONDS)
            scheduler.add_job(
                _resume_sync_dataset_job,
                trigger="date",
                run_date=run_date,
                args=[resumable_run.id, start_index, skip_mentors],
                id="resume_sync_dataset",
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=600,
            )
            logger.warning(
                "检测到被中断的同步任务 #%s，%s秒后从第 %s 位导师之后续跑（skip_mentors=%s）。",
                resumable_run.id, RESUME_DELAY_SECONDS, start_index, skip_mentors,
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


def _mark_orphaned_running_tasks_failed(exclude_id=None) -> int:
    """把上一轮进程残留、卡在 running 的任务判死。

    进程被 SIGKILL（重新部署 / 重启 / 被杀）时，``_run_recorded_task`` 的 except 来不及
    执行，记录会永远停在 running。调度器启动时清理这些孤儿：心跳为空、或心跳停滞超过
    ``STALE_RUNNING_THRESHOLD`` 的 running 记录全部标记为 failed。心跳仍新鲜的（极少数
    滚动升级期间另一实例正在跑）会被保留，不会误杀。

    ``exclude_id``：要保留用于断点续跑的那条记录，不在此处判死。
    """
    from dataset.models import ScheduledTaskRun

    now = django_timezone.now()
    stale_before = now - STALE_RUNNING_THRESHOLD
    queryset = (
        ScheduledTaskRun.objects
        .filter(status=ScheduledTaskRun.STATUS_RUNNING)
        .filter(Q(last_heartbeat_at__isnull=True) | Q(last_heartbeat_at__lt=stale_before))
    )
    if exclude_id is not None:
        queryset = queryset.exclude(id=exclude_id)
    updated = queryset.update(
        status=ScheduledTaskRun.STATUS_FAILED,
        finished_at=now,
        error_message="进程中断（疑似重新部署/重启/被杀），由调度器启动时清理。",
    )
    if updated:
        logger.warning("启动时清理了 %s 条卡在 running 的孤儿定时任务记录。", updated)
    return updated


def _find_resumable_sync_run():
    """找出最近一次被中断、可从断点续跑的 daily_sync 记录。

    条件：daily_sync、状态仍是 running（被 SIGKILL 残留）、在 RESUME_MAX_AGE 时间窗内、
    且未完成（progress_current < progress_total）。不要求心跳停滞——因为进程刚启动意味着
    上一实例（单 pod + RWO 卷，二者不会同时持有数据库）已经死亡，残留的 running 必然是孤儿。
    返回最近的一条，没有则返回 None。
    """
    from dataset.models import ScheduledTaskRun

    started_after = django_timezone.now() - RESUME_MAX_AGE
    return (
        ScheduledTaskRun.objects
        .filter(task_name="daily_sync_dataset", status=ScheduledTaskRun.STATUS_RUNNING)
        .filter(started_at__gte=started_after)
        .filter(progress_total__gt=0)
        .filter(Q(progress_current__isnull=True) | Q(progress_current__lt=F("progress_total")))
        .order_by("-id")
        .first()
    )


def _resume_sync_dataset_job(record_id: int, start_index: int, skip_mentors: bool):
    """复用既有记录，从断点继续跑 sync_dataset（不新建记录，进度连续）。"""
    from dataset.models import ScheduledTaskRun

    record = ScheduledTaskRun.objects.filter(id=record_id).first()
    if record is None:
        return

    now = django_timezone.now()
    record.status = ScheduledTaskRun.STATUS_RUNNING
    record.finished_at = None
    record.error_message = ""
    record.last_heartbeat_at = now
    record.save(update_fields=["status", "finished_at", "error_message", "last_heartbeat_at"])

    try:
        call_command(
            "sync_dataset",
            scheduled_run_id=record.id,
            start_index=start_index,
            skip_mentors=skip_mentors,
        )
    except Exception as exc:
        record.status = ScheduledTaskRun.STATUS_FAILED
        record.finished_at = django_timezone.now()
        record.error_message = _format_exception(exc)
        record.save(update_fields=["status", "finished_at", "error_message"])
        logger.exception("Django 定时同步任务断点续跑失败")
        return

    record.status = ScheduledTaskRun.STATUS_SUCCESS
    record.finished_at = django_timezone.now()
    record.error_message = ""
    record.save(update_fields=["status", "finished_at", "error_message"])


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
