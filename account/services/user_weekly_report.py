"""用户周报服务：生成、查询并持久化用户专属周报。"""

from collections import defaultdict

from django.db import transaction

from account.models import User, UserWeeklyReport
from account.services.weekly_push import (
    build_weekly_push_digest,
    collect_target_mentors,
    collect_target_subjects,
)
from dataset.models import Paper
from dataset.services.weekly_push_summary import (
    build_weekly_push_payload,
    resolve_week_range,
)


def generate_user_weekly_report(
    user: User,
    week_offset: int = 0,
    generated_by_kind: str = UserWeeklyReport.GENERATED_BY_USER,
) -> UserWeeklyReport:
    """Generate and persist a per-user weekly report for the target week.

    The same routine is used both by the user-triggered "regenerate" button
    and by the scheduled weekly job, so the stored row always reflects the
    most recent generation regardless of trigger.
    """
    week_start, week_end = resolve_week_range(week_offset)
    weekly_papers = list(
        Paper.objects.filter(
            publish_date__gte=week_start,
            publish_date__lte=week_end,
        ).order_by("-publish_date", "-id")
    )

    digest = build_weekly_push_digest(user, [weekly_papers])

    mentor_names_by_paper_id = defaultdict(list)
    for group in digest.get("mentorGroups", []):
        mentor_name = str(group.get("mentorName") or "").strip()
        if mentor_name == "":
            continue
        for paper in group.get("papers", []):
            paper_id = int(paper.get("id") or 0)
            if paper_id == 0 or mentor_name in mentor_names_by_paper_id[paper_id]:
                continue
            mentor_names_by_paper_id[paper_id].append(mentor_name)

    subject_names_by_paper_id = defaultdict(list)
    for group in digest.get("subjectGroups", []):
        subject = str(group.get("subject") or "").strip()
        if subject == "":
            continue
        for paper in group.get("papers", []):
            paper_id = int(paper.get("id") or 0)
            if paper_id == 0 or subject in subject_names_by_paper_id[paper_id]:
                continue
            subject_names_by_paper_id[paper_id].append(subject)

    matched_paper_ids = set(mentor_names_by_paper_id) | set(subject_names_by_paper_id)
    matched_papers = [paper for paper in weekly_papers if paper.id in matched_paper_ids]

    title = f"专属周报（{week_start.isoformat()} ~ {week_end.isoformat()}）"
    tracked_mentors = collect_target_mentors(user)
    tracked_subjects = collect_target_subjects(user)

    payload = build_weekly_push_payload(
        title=title,
        week_start=week_start,
        week_end=week_end,
        papers=matched_papers,
        purpose_text="用户专属周报",
        mentor_names_by_paper_id=dict(mentor_names_by_paper_id),
        extra_fields={
            "mentorGroups": digest.get("mentorGroups", []),
            "subjectGroups": digest.get("subjectGroups", []),
            "subjectDistribution": digest.get("subjectDistribution", []),
            "trackedMentorCount": len(tracked_mentors),
            "activeMentorCount": len(digest.get("mentorGroups", [])),
            "trackedSubjectCount": len(tracked_subjects),
            "activeSubjectCount": len(digest.get("subjectGroups", [])),
        },
    )

    total_paper_count = int(digest.get("totalPaperCount") or 0)
    has_updates = bool(digest.get("hasUpdates"))

    with transaction.atomic():
        report, _ = UserWeeklyReport.objects.update_or_create(
            user=user,
            week_start=week_start,
            defaults={
                "week_end": week_end,
                "title": title,
                "payload": payload,
                "digest": digest,
                "has_updates": has_updates,
                "total_paper_count": total_paper_count,
                "generated_by_kind": generated_by_kind,
            },
        )
    return report


def get_latest_user_weekly_report(user: User) -> UserWeeklyReport | None:
    return (
        UserWeeklyReport.objects
        .filter(user=user)
        .order_by("-week_start", "-id")
        .first()
    )


def get_user_weekly_report_by_week(user: User, week_start) -> UserWeeklyReport | None:
    return (
        UserWeeklyReport.objects
        .filter(user=user, week_start=week_start)
        .order_by("-id")
        .first()
    )


def list_user_weekly_reports(user: User):
    return (
        UserWeeklyReport.objects
        .filter(user=user)
        .order_by("-week_start", "-id")
    )


def build_period_key_from_week_start(week_start) -> str:
    """Stable period_key string used by PushRecord dedup, derived from week_start.

    Format: `weekly_YYYYMMDD`. Different from the legacy bucket-based
    `YYYYMMDD_YYYYMMDD` format on purpose, so old and new PushRecord rows
    do not collide on the (user, type, period_key) uniqueness constraint.
    """
    return f"weekly_{week_start.strftime('%Y%m%d')}"
