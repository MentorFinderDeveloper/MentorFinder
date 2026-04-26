from datetime import datetime

from django.db import transaction
from django.utils import timezone

from account.models import WeeklyPushPaperBucket
from dataset.models import Paper


DAY_KEYS = [
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
]

WEEKLY_PUSH_CUTOFF_WEEKDAY = 3
WEEKLY_PUSH_CUTOFF_HOUR = 12
WEEKLY_PUSH_CUTOFF_MINUTE = 0


def create_empty_weekly_push_payload() -> dict:
    return {day_key: [] for day_key in DAY_KEYS}


def load_weekly_push_payload(cycle: str = WeeklyPushPaperBucket.CYCLE_CURRENT) -> dict:
    payload = create_empty_weekly_push_payload()
    bucket_rows = (
        WeeklyPushPaperBucket.objects
        .filter(cycle=cycle)
        .select_related("paper")
        .order_by("day_key", "id")
    )
    for bucket in bucket_rows:
        payload[bucket.day_key].append(bucket.paper_id)
    return payload


def append_unique_paper_ids(existing_ids: list[int], new_ids: list[int]) -> list[int]:
    result = list(existing_ids)
    seen_ids = set(existing_ids)
    for paper_id in new_ids:
        if paper_id in seen_ids:
            continue
        result.append(paper_id)
        seen_ids.add(paper_id)
    return result


def append_weekly_push_paper_ids(
    cycle: str,
    day_key: str,
    paper_ids: list[int],
) -> int:
    existing_ids = list(
        WeeklyPushPaperBucket.objects
        .filter(cycle=cycle, day_key=day_key, paper_id__in=paper_ids)
        .values_list("paper_id", flat=True)
    )
    missing_ids = [paper_id for paper_id in paper_ids if paper_id not in set(existing_ids)]
    bucket_rows = [
        WeeklyPushPaperBucket(
            cycle=cycle,
            day_key=day_key,
            paper_id=paper_id,
        )
        for paper_id in missing_ids
    ]
    WeeklyPushPaperBucket.objects.bulk_create(bucket_rows)
    return len(bucket_rows)


def get_weekly_push_day_key(now: datetime | None = None) -> str:
    local_now = _normalize_local_datetime(now)
    day_key_by_weekday = {
        3: "thursday",
        4: "friday",
        5: "saturday",
        6: "sunday",
        0: "monday",
        1: "tuesday",
        2: "wednesday",
    }
    return day_key_by_weekday[local_now.weekday()]


def should_stage_next_cycle_payload(now: datetime | None = None) -> bool:
    local_now = _normalize_local_datetime(now)
    if local_now.weekday() != WEEKLY_PUSH_CUTOFF_WEEKDAY:
        return False
    current_minutes = local_now.hour * 60 + local_now.minute
    cutoff_minutes = WEEKLY_PUSH_CUTOFF_HOUR * 60 + WEEKLY_PUSH_CUTOFF_MINUTE
    return current_minutes < cutoff_minutes


def resolve_weekly_push_record_target_cycle(now: datetime | None = None) -> str:
    if should_stage_next_cycle_payload(now):
        return WeeklyPushPaperBucket.CYCLE_NEXT
    return WeeklyPushPaperBucket.CYCLE_CURRENT


def archive_weekly_push_payload(archive_batch: str) -> int:
    with transaction.atomic():
        archived_rows = list(
            WeeklyPushPaperBucket.objects
            .filter(cycle=WeeklyPushPaperBucket.CYCLE_CURRENT)
            .values("day_key", "paper_id")
        )
        WeeklyPushPaperBucket.objects.bulk_create(
            [
                WeeklyPushPaperBucket(
                    cycle=WeeklyPushPaperBucket.CYCLE_ARCHIVED,
                    day_key=row["day_key"],
                    paper_id=row["paper_id"],
                    archive_batch=archive_batch,
                )
                for row in archived_rows
            ]
        )
        WeeklyPushPaperBucket.objects.filter(cycle=WeeklyPushPaperBucket.CYCLE_CURRENT).delete()
    return len(archived_rows)


def promote_staged_weekly_push_payload() -> bool:
    with transaction.atomic():
        next_rows = list(
            WeeklyPushPaperBucket.objects
            .filter(cycle=WeeklyPushPaperBucket.CYCLE_NEXT)
            .values("day_key", "paper_id")
        )
        if not next_rows:
            return False

        WeeklyPushPaperBucket.objects.filter(cycle=WeeklyPushPaperBucket.CYCLE_CURRENT).delete()
        WeeklyPushPaperBucket.objects.bulk_create(
            [
                WeeklyPushPaperBucket(
                    cycle=WeeklyPushPaperBucket.CYCLE_CURRENT,
                    day_key=row["day_key"],
                    paper_id=row["paper_id"],
                )
                for row in next_rows
            ]
        )
        WeeklyPushPaperBucket.objects.filter(cycle=WeeklyPushPaperBucket.CYCLE_NEXT).delete()
    return True


def clear_weekly_push_cycle(cycle: str = WeeklyPushPaperBucket.CYCLE_CURRENT):
    WeeklyPushPaperBucket.objects.filter(cycle=cycle).delete()


def load_daily_paper_lists_from_cycle(cycle: str = WeeklyPushPaperBucket.CYCLE_CURRENT) -> list[list[Paper]]:
    payload = load_weekly_push_payload(cycle)
    daily_paper_lists = []
    for day_key in DAY_KEYS:
        paper_ids = payload[day_key]
        papers = list(Paper.objects.filter(id__in=paper_ids))
        paper_map = {paper.id: paper for paper in papers}
        daily_paper_lists.append([paper_map[paper_id] for paper_id in paper_ids if paper_id in paper_map])
    return daily_paper_lists


def _normalize_local_datetime(now: datetime | None) -> datetime:
    if now is None:
        return timezone.localtime()
    if timezone.is_naive(now):
        return timezone.make_aware(now, timezone.get_current_timezone())
    return timezone.localtime(now)
