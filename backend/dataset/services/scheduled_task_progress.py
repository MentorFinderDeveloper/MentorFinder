"""更新定时任务进度日志的轻量工具。

适用于长时间运行的后台任务向数据库写入进度与心跳，限制日志字段长度。
"""

from django.utils import timezone


MAX_PROGRESS_LOG_LENGTH = 12000


def update_scheduled_task_progress(
    scheduled_run_id: int | None,
    message: str,
    *,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if scheduled_run_id is None:
        return

    from dataset.models import ScheduledTaskRun

    run = ScheduledTaskRun.objects.filter(id=scheduled_run_id).first()
    if run is None:
        return

    now = timezone.now()
    timestamp = timezone.localtime(now).isoformat(sep=" ", timespec="seconds")
    log_line = f"[{timestamp}] {message}"
    progress_log = f"{run.progress_log}\n{log_line}".strip()
    if len(progress_log) > MAX_PROGRESS_LOG_LENGTH:
        progress_log = progress_log[-MAX_PROGRESS_LOG_LENGTH:]

    run.progress_message = message[:255]
    run.last_heartbeat_at = now
    run.progress_log = progress_log
    update_fields = ["progress_message", "last_heartbeat_at", "progress_log"]

    if current is not None:
        run.progress_current = max(0, current)
        update_fields.append("progress_current")
    if total is not None:
        run.progress_total = max(0, total)
        update_fields.append("progress_total")

    run.save(update_fields=update_fields)
