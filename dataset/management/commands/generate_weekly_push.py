from collections import Counter
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from dataset.models import Paper, WeeklyPaperPush


class Command(BaseCommand):
    help = "Generate weekly homepage push for papers published in last week"

    def add_arguments(self, parser):
        parser.add_argument("--week-offset", type=int, default=0, help="0=上一周，1=上上周")
        parser.add_argument("--force", action="store_true", help="覆盖已有周推送")

    def handle(self, *args, **options):
        week_offset = int(options["week_offset"])
        force = bool(options["force"])

        week_start, week_end = self._resolve_week_range(week_offset)
        papers = list(
            Paper.objects.filter(
                publish_date__gte=week_start,
                publish_date__lte=week_end,
            ).order_by("-publish_date", "-id")
        )

        fixed_summary = self._build_fixed_summary(week_start, week_end, papers)
        ai_summary, generated_by = self._build_ai_summary_with_fallback(week_start, week_end, papers, fixed_summary)
        final_content = self._compose_content(fixed_summary, ai_summary)
        title = f"论文周报（{week_start.isoformat()} ~ {week_end.isoformat()}）"

        push_obj, created = WeeklyPaperPush.objects.update_or_create(
            week_start=week_start,
            defaults={
                "week_end": week_end,
                "paper_count": len(papers),
                "title": title,
                "fixed_summary": fixed_summary,
                "ai_summary": ai_summary,
                "content": final_content,
                "generated_by": generated_by,
            },
        )

        if not created and not force:
            self.stdout.write(self.style.WARNING("本周推送已存在，已按默认逻辑更新。可用 --force 显式覆盖。"))

        self.stdout.write(
            self.style.SUCCESS(
                f"周推送已生成：week={week_start}~{week_end}, papers={len(papers)}, mode={generated_by}, id={push_obj.id}"
            )
        )

    def _resolve_week_range(self, week_offset: int):
        today = timezone.localdate()
        this_week_monday = today - timedelta(days=today.weekday())
        target_start = this_week_monday - timedelta(days=7 * (week_offset + 1))
        target_end = target_start + timedelta(days=6)
        return target_start, target_end

    def _build_fixed_summary(self, week_start, week_end, papers):
        if not papers:
            return f"{week_start.isoformat()} 到 {week_end.isoformat()} 无新增论文。"

        subject_counter = Counter()
        for paper in papers:
            subjects = [item.strip() for item in (paper.subjects or "").split(",") if item.strip()]
            if subjects:
                subject_counter.update(subjects)
            else:
                subject_counter.update(["其他/未分类"])

        top_subjects = ", ".join(
            f"{subject}({count})"
            for subject, count in subject_counter.most_common(5)
        )
        newest_date = papers[0].publish_date.isoformat() if papers[0].publish_date else "未知"
        oldest_date = papers[-1].publish_date.isoformat() if papers[-1].publish_date else "未知"

        return (
            f"{week_start.isoformat()} 到 {week_end.isoformat()} 共收录 {len(papers)} 篇论文。"
            f" 时间范围覆盖 {oldest_date} 至 {newest_date}。"
            f" 热门方向：{top_subjects}。"
        )

    def _build_ai_summary_with_fallback(self, week_start, week_end, papers, fixed_summary):
        api_key = str(getattr(settings, "THUCS_API_KEY", "") or "").strip()
        api_base_url = str(getattr(settings, "THUCS_API_BASE_URL", "https://api-ai.thucs.cn") or "https://api-ai.thucs.cn").rstrip("/")
        model_name = str(getattr(settings, "THUCS_MODEL_NAME", "qwen-plus") or "qwen-plus").strip()
        if api_key == "":
            return fixed_summary, "rule"

        sample_lines = []
        for paper in papers[:20]:
            sample_lines.append(
                f"- 标题: {paper.title}\n  作者: {paper.author_names or '未知'}\n  摘要: {(paper.tldr or paper.abstract or '暂无').strip()[:400]}"
            )

        prompt = (
            "你是高校科研信息助手。请基于以下论文信息，写一段 200-350 字中文周报，"
            "用于系统首页推送。要求：\n"
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

    def _compose_content(self, fixed_summary: str, ai_summary: str):
        if ai_summary == fixed_summary:
            return fixed_summary
        return f"{fixed_summary}\n\n【AI总结】\n{ai_summary}"
