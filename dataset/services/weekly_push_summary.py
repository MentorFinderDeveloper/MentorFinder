from collections import Counter
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone


def resolve_week_range(week_offset: int, today=None):
    resolved_today = today or timezone.localdate()
    this_week_monday = resolved_today - timedelta(days=resolved_today.weekday())
    target_start = this_week_monday - timedelta(days=7 * (week_offset + 1))
    target_end = target_start + timedelta(days=6)
    return target_start, target_end


def build_fixed_summary(week_start, week_end, papers):
    paper_list = list(papers)
    if not paper_list:
        return f"{week_start.isoformat()} 到 {week_end.isoformat()} 无新增论文。"

    subject_counter = Counter()
    for paper in paper_list:
        subjects = [item.strip() for item in (paper.subjects or "").split(",") if item.strip()]
        if subjects:
            subject_counter.update(subjects)
        else:
            subject_counter.update(["其他/未分类"])

    top_subjects = ", ".join(
        f"{subject}({count})"
        for subject, count in subject_counter.most_common(5)
    )
    newest_date = paper_list[0].publish_date.isoformat() if paper_list[0].publish_date else "未知"
    oldest_date = paper_list[-1].publish_date.isoformat() if paper_list[-1].publish_date else "未知"

    return (
        f"{week_start.isoformat()} 到 {week_end.isoformat()} 共收录 {len(paper_list)} 篇论文。"
        f" 时间范围覆盖 {oldest_date} 至 {newest_date}。"
        f" 热门方向：{top_subjects}。"
    )


def build_ai_summary_with_fallback(
    week_start,
    week_end,
    papers,
    fixed_summary: str,
    purpose_text: str = "系统首页推送",
    mentor_names_by_paper_id: dict[int, list[str]] | None = None,
):
    api_key = str(getattr(settings, "THUCS_API_KEY", "") or "").strip()
    api_base_url = str(getattr(settings, "THUCS_API_BASE_URL", "https://api-ai.thucs.cn") or "https://api-ai.thucs.cn").rstrip("/")
    model_name = str(getattr(settings, "THUCS_MODEL_NAME", "qwen-plus") or "qwen-plus").strip()
    if api_key == "":
        return fixed_summary, "rule"

    sample_lines = []
    for paper in list(papers)[:20]:
        mentor_names = []
        if mentor_names_by_paper_id is not None:
            mentor_names = mentor_names_by_paper_id.get(paper.id or 0, [])
        mentor_line = f"\n  相关导师: {'、'.join(mentor_names)}" if mentor_names else ""
        sample_lines.append(
            f"- 标题: {paper.title}\n  作者: {paper.author_names or '未知'}{mentor_line}\n  摘要: {(paper.tldr or paper.abstract or '暂无').strip()[:400]}"
        )

    prompt = (
        "你是高校科研信息助手。请基于以下论文信息，写一段 200-350 字中文周报，"
        f"用于{purpose_text}。要求：\n"
        "1) 先概览趋势，再点名2-3个亮点方向；\n"
        "2) 用客观表述，不夸张；\n"
        "3) 不要编造不存在的数据。\n\n"
        f"周范围: {week_start.isoformat()} ~ {week_end.isoformat()}\n"
        f"固定摘要: {fixed_summary}\n\n"
        "论文样本:\n"
        + ("\n".join(sample_lines) if sample_lines else "- 本周暂无论文")
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "你是高校科研周报助手，输出中文且内容准确克制。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }

    try:
        response = requests.post(
            f"{api_base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if text == "":
            return fixed_summary, "rule"
        return text, "thucs-openai"
    except Exception:
        return fixed_summary, "rule"


def compose_weekly_push_content(fixed_summary: str, ai_summary: str):
    if ai_summary == fixed_summary:
        return fixed_summary
    return f"{fixed_summary}\n\n【AI总结】\n{ai_summary}"


def serialize_weekly_push_paper(paper, mentor_names: list[str] | None = None):
    arxiv_url = paper.arxiv_url
    if not arxiv_url and paper.arxiv_id:
        arxiv_url = f"https://arxiv.org/abs/{paper.arxiv_id}"

    item = {
        "id": paper.id,
        "title": paper.title,
        "publishDate": paper.publish_date.isoformat() if paper.publish_date else None,
        "authorNames": paper.author_names,
        "arxivUrl": arxiv_url,
        "arxivId": paper.arxiv_id,
        "abstract": paper.abstract,
        "tldr": paper.tldr,
    }
    if mentor_names is not None:
        item["mentorNames"] = mentor_names
    return item


def build_weekly_push_payload(
    *,
    title: str,
    week_start,
    week_end,
    papers,
    purpose_text: str = "系统首页推送",
    mentor_names_by_paper_id: dict[int, list[str]] | None = None,
    extra_fields: dict | None = None,
):
    paper_list = list(papers)
    fixed_summary = build_fixed_summary(week_start, week_end, paper_list)
    ai_summary, generated_by = build_ai_summary_with_fallback(
        week_start,
        week_end,
        paper_list,
        fixed_summary,
        purpose_text=purpose_text,
        mentor_names_by_paper_id=mentor_names_by_paper_id,
    )
    payload = {
        "weekStart": week_start.isoformat(),
        "weekEnd": week_end.isoformat(),
        "paperCount": len(paper_list),
        "title": title,
        "fixedSummary": fixed_summary,
        "aiSummary": ai_summary,
        "content": compose_weekly_push_content(fixed_summary, ai_summary),
        "papers": [
            serialize_weekly_push_paper(
                paper,
                mentor_names=(mentor_names_by_paper_id or {}).get(paper.id or 0),
            )
            for paper in paper_list
        ],
        "generatedBy": generated_by,
        "updatedAt": timezone.localtime(timezone.now()).isoformat(sep=" ", timespec="seconds"),
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload
