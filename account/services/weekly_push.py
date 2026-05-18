from collections import Counter
from collections.abc import Iterable

from django.conf import settings
from django.core.mail import send_mail

from account.models import MentorFollow, SubjectFollow, User
from dataset.models import Mentor, Paper


DEFAULT_ABSTRACT_PREVIEW_LINES = 3


def build_weekly_push_digest(
    user: User,
    daily_paper_lists: Iterable[Iterable[Paper]],
) -> dict:
    """Build one user's weekly paper digest from mocked crawler increments."""
    weekly_papers = _collect_unique_papers(daily_paper_lists)
    mentor_groups = []
    subject_groups = []
    matched_papers_by_id = {}

    for mentor in collect_target_mentors(user):
        mentor_papers = _match_mentor_papers(mentor, weekly_papers)
        if not mentor_papers:
            continue

        for paper in mentor_papers:
            matched_papers_by_id[paper.id] = paper

        mentor_groups.append(
            {
                "mentorId": mentor.id,
                "mentorName": mentor.Chinese_name,
                "mentorEnglishName": mentor.English_name,
                "mentorResearchDirection": mentor.research_direction,
                "isPrivate": mentor.is_private,
                "paperCount": len(mentor_papers),
                "papers": [
                    _serialize_digest_paper(paper, mentor)
                    for paper in mentor_papers
                ],
            }
        )

    for subject in collect_target_subjects(user):
        subject_papers = _match_subject_papers(subject, weekly_papers)
        if not subject_papers:
            continue

        for paper in subject_papers:
            matched_papers_by_id[paper.id] = paper

        subject_groups.append(
            {
                "subject": subject,
                "paperCount": len(subject_papers),
                "papers": [
                    _serialize_subject_digest_paper(paper, subject)
                    for paper in subject_papers
                ],
            }
        )

    total_paper_count = len(matched_papers_by_id)
    has_updates = total_paper_count > 0

    return {
        "userId": user.id,
        "userEmail": user.email,
        "hasUpdates": has_updates,
        "title": _build_digest_title(total_paper_count),
        "summary": _build_digest_summary(total_paper_count),
        "totalPaperCount": total_paper_count,
        "mentorGroups": mentor_groups,
        "subjectGroups": subject_groups,
        "subjectDistribution": _build_subject_distribution(matched_papers_by_id.values()),
    }


def render_weekly_push_email(digest: dict) -> dict:
    subject = str(digest.get("title") or "[MentorFinder]本周无论文更新")
    if not digest.get("hasUpdates"):
        body = "\n".join(
            [
                subject,
                "",
                str(digest.get("summary") or "本周无论文更新"),
                "",
                "系统当前未检测到你关注的导师或私有导师有新增论文。",
                "你关注的板块本周也暂无新增论文。",
            ]
        )
        return {
            "subject": subject,
            "body": body,
        }

    body_lines = [
        subject,
        "",
        str(digest.get("summary") or ""),
        f"本周共发现 {digest.get('totalPaperCount', 0)} 篇新增论文。",
        "",
    ]

    if digest.get("mentorGroups"):
        body_lines.extend(["按导师分组："])
        for group in digest.get("mentorGroups", []):
            mentor_name = str(group.get("mentorName") or "未命名导师")
            if group.get("isPrivate"):
                mentor_name = f"{mentor_name}（私有导师）"

            body_lines.append(f"- {mentor_name}：{group.get('paperCount', 0)} 篇")
            body_lines.append(
                f"  研究方向：{group.get('mentorResearchDirection') or '未提供'}"
            )

            for index, paper in enumerate(group.get("papers", []), start=1):
                body_lines.extend(
                    [
                        f"  {index}. {paper.get('title') or '未命名论文'}",
                        f"     发表时间：{paper.get('publishDate') or '未知日期'}",
                        f"     作者：{paper.get('authorNames') or '未提供'}",
                        f"     所属导师：{paper.get('mentorName') or mentor_name}",
                        f"     研究方向：{paper.get('researchDirection') or '未提供'}",
                        f"     分类：{_format_subjects_for_email(paper.get('subjects', []))}",
                        f"     摘要简述：{paper.get('abstractPreview') or '暂无摘要'}",
                    ]
                )

            body_lines.append("")

    if digest.get("subjectGroups"):
        body_lines.extend(["按关注板块分组："])
        for group in digest.get("subjectGroups", []):
            # 不要复用外层的 subject 变量名——那是邮件标题，被覆盖会让 return 把学科名当邮件 subject 发出去。
            group_subject = str(group.get("subject") or "未命名板块")
            body_lines.append(f"- {group_subject}：{group.get('paperCount', 0)} 篇")
            for index, paper in enumerate(group.get("papers", []), start=1):
                body_lines.extend(
                    [
                        f"  {index}. {paper.get('title') or '未命名论文'}",
                        f"     发表时间：{paper.get('publishDate') or '未知日期'}",
                        f"     作者：{paper.get('authorNames') or '未提供'}",
                        f"     分类：{_format_subjects_for_email(paper.get('subjects', []))}",
                        f"     摘要简述：{paper.get('abstractPreview') or '暂无摘要'}",
                    ]
                )
            body_lines.append("")

    body_lines.extend(
        _build_subject_distribution_lines(digest.get("subjectDistribution", []))
    )

    return {
        "subject": subject,
        "body": "\n".join(body_lines).rstrip(),
    }


def send_weekly_push_email(
    user: User,
    daily_paper_lists: Iterable[Iterable[Paper]],
) -> dict:
    digest = build_weekly_push_digest(user, daily_paper_lists)
    return send_weekly_push_email_from_digest(user, digest)


def send_weekly_push_email_from_digest(user: User, digest: dict) -> dict:
    """Send a weekly push email using a pre-built digest payload.

    This is the primary entry point for the new storage-backed delivery
    flow: the digest is loaded from UserWeeklyReport, not recomputed.
    """
    email_content = render_weekly_push_email(digest)

    # 仅在用户个人周报有内容（匹配到关注/私有导师的新论文）时才真正发送邮件，
    # 通用空白周报不发邮件，避免打扰用户。
    if not digest.get("hasUpdates"):
        return {
            "digest": digest,
            "email": email_content,
            "sent": False,
            "sentCount": 0,
            "errorMessage": "",
            "skipped": True,
            "skipReason": "no_personal_updates",
        }

    sent_count = 0
    error_message = ""
    try:
        sent_count = send_mail(
            subject=email_content["subject"],
            message=email_content["body"],
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:
        error_message = _format_email_send_error(exc)

    if sent_count == 0 and error_message == "":
        error_message = "Email backend reported zero successful deliveries."

    return {
        "digest": digest,
        "email": email_content,
        "sent": sent_count > 0,
        "sentCount": sent_count,
        "errorMessage": error_message,
        "skipped": False,
        "skipReason": "",
    }


def _format_email_send_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__


def _collect_unique_papers(daily_paper_lists: Iterable[Iterable[Paper]]) -> dict[int, Paper]:
    papers_by_id = {}
    for paper_list in daily_paper_lists:
        for paper in paper_list:
            if paper.id is None:
                continue
            papers_by_id.setdefault(paper.id, paper)
    return papers_by_id


def collect_target_mentors(user: User) -> list[Mentor]:
    followed_mentors = (
        MentorFollow.objects
        .filter(student=user)
        .select_related("mentor")
        .order_by("mentor_id")
    )
    private_mentors = Mentor.objects.filter(owner=user).order_by("id")

    mentors = []
    seen_mentor_ids = set()
    for follow in followed_mentors:
        mentor = follow.mentor
        if mentor.id in seen_mentor_ids:
            continue
        mentors.append(mentor)
        seen_mentor_ids.add(mentor.id)

    for mentor in private_mentors:
        if mentor.id in seen_mentor_ids:
            continue
        mentors.append(mentor)
        seen_mentor_ids.add(mentor.id)

    return mentors


def collect_target_subjects(user: User) -> list[str]:
    return list(
        SubjectFollow.objects
        .filter(user=user)
        .order_by("subject")
        .values_list("subject", flat=True)
    )


def _match_mentor_papers(mentor: Mentor, weekly_papers: dict[int, Paper]) -> list[Paper]:
    papers = []
    seen_paper_ids = set()
    for paper_id in mentor.get_paper_id_list():
        if paper_id in seen_paper_ids or paper_id not in weekly_papers:
            continue
        papers.append(weekly_papers[paper_id])
        seen_paper_ids.add(paper_id)
    return papers


def _match_subject_papers(subject: str, weekly_papers: dict[int, Paper]) -> list[Paper]:
    return [
        paper
        for paper in weekly_papers.values()
        if subject in _split_subjects(paper.subjects)
    ]


def _serialize_digest_paper(paper: Paper, mentor: Mentor) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "publishDate": paper.publish_date.isoformat() if paper.publish_date else None,
        "authorNames": paper.author_names,
        "mentorId": mentor.id,
        "mentorName": mentor.Chinese_name,
        "researchDirection": mentor.research_direction,
        "subjects": _split_subjects(paper.subjects),
        "abstractPreview": _build_abstract_preview(paper.abstract),
    }


def _serialize_subject_digest_paper(paper: Paper, subject: str) -> dict:
    return {
        "id": paper.id,
        "title": paper.title,
        "publishDate": paper.publish_date.isoformat() if paper.publish_date else None,
        "authorNames": paper.author_names,
        "subject": subject,
        "subjects": _split_subjects(paper.subjects),
        "abstractPreview": _build_abstract_preview(paper.abstract),
    }


def _split_subjects(subjects: str) -> list[str]:
    if not subjects:
        return []
    return [subject.strip() for subject in subjects.split(",") if subject.strip()]


def _format_subjects_for_email(subjects: list[str]) -> str:
    if not subjects:
        return "未分类"
    return ", ".join(subjects)


def _build_abstract_preview(abstract: str | None) -> str:
    if not abstract:
        return ""
    lines = [
        line.strip()
        for line in abstract.splitlines()
        if line.strip()
    ]
    return "\n".join(lines[:DEFAULT_ABSTRACT_PREVIEW_LINES])


def _build_subject_distribution(papers: Iterable[Paper]) -> list[dict]:
    counter = Counter()
    for paper in papers:
        counter.update(_split_subjects(paper.subjects))

    return [
        {
            "subject": subject,
            "count": count,
        }
        for subject, count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _build_subject_distribution_lines(subject_distribution: list[dict]) -> list[str]:
    if not subject_distribution:
        return [
            "研究方向分布：",
            "- 本周暂无可统计的研究方向分布",
        ]

    lines = ["研究方向分布："]
    for item in subject_distribution:
        lines.append(f"- {item['subject']}：{item['count']} 篇")
    return lines


def _build_digest_title(total_paper_count: int) -> str:
    if total_paper_count == 0:
        return "[MentorFinder]本周无论文更新"
    return f"[MentorFinder]你关注的导师或板块本周有 {total_paper_count} 篇新论文"


def _build_digest_summary(total_paper_count: int) -> str:
    if total_paper_count == 0:
        return "本周无论文更新"
    return f"你关注的导师或板块本周有 {total_paper_count} 篇新论文"
