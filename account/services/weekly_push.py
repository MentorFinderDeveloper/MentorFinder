from collections import Counter
from collections.abc import Iterable

from account.models import MentorFollow, User
from dataset.models import Mentor, Paper


DEFAULT_ABSTRACT_PREVIEW_LINES = 3


def build_weekly_push_digest(
    user: User,
    daily_paper_lists: Iterable[Iterable[Paper]],
) -> dict:
    """Build one user's weekly paper digest from mocked crawler increments."""
    weekly_papers = _collect_unique_papers(daily_paper_lists)
    mentor_groups = []
    matched_papers_by_id = {}

    for mentor in _collect_target_mentors(user):
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
        "subjectDistribution": _build_subject_distribution(matched_papers_by_id.values()),
    }


def _collect_unique_papers(daily_paper_lists: Iterable[Iterable[Paper]]) -> dict[int, Paper]:
    papers_by_id = {}
    for paper_list in daily_paper_lists:
        for paper in paper_list:
            if paper.id is None:
                continue
            papers_by_id.setdefault(paper.id, paper)
    return papers_by_id


def _collect_target_mentors(user: User) -> list[Mentor]:
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


def _match_mentor_papers(mentor: Mentor, weekly_papers: dict[int, Paper]) -> list[Paper]:
    papers = []
    seen_paper_ids = set()
    for paper_id in mentor.get_paper_id_list():
        if paper_id in seen_paper_ids or paper_id not in weekly_papers:
            continue
        papers.append(weekly_papers[paper_id])
        seen_paper_ids.add(paper_id)
    return papers


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


def _split_subjects(subjects: str) -> list[str]:
    if not subjects:
        return []
    return [subject.strip() for subject in subjects.split(",") if subject.strip()]


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


def _build_digest_title(total_paper_count: int) -> str:
    if total_paper_count == 0:
        return "[MentorFinder]本周无论文更新"
    return f"[MentorFinder]你关注的导师本周有 {total_paper_count} 篇新论文"


def _build_digest_summary(total_paper_count: int) -> str:
    if total_paper_count == 0:
        return "本周无论文更新"
    return f"你关注的导师本周有 {total_paper_count} 篇新论文"
