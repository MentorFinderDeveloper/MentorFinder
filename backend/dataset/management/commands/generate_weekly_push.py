from django.core.management.base import BaseCommand

from dataset.models import Paper, WeeklyPaperPush
from dataset.services.weekly_push_summary import (
    build_weekly_push_payload,
    resolve_week_range,
)


class Command(BaseCommand):
    help = "Generate weekly homepage push for papers published in last week"

    def add_arguments(self, parser):
        parser.add_argument("--week-offset", type=int, default=0, help="0=上一周，1=上上周")
        parser.add_argument("--force", action="store_true", help="覆盖已有周推送")

    def handle(self, *args, **options):
        week_offset = int(options["week_offset"])
        force = bool(options["force"])

        week_start, week_end = resolve_week_range(week_offset)
        papers = list(
            Paper.objects.filter(
                publish_date__gte=week_start,
                publish_date__lte=week_end,
            ).order_by("-publish_date", "-id")
        )
        title = f"论文周报（{week_start.isoformat()} ~ {week_end.isoformat()}）"
        payload = build_weekly_push_payload(
            title=title,
            week_start=week_start,
            week_end=week_end,
            papers=papers,
            purpose_text="系统首页推送",
        )

        push_obj, created = WeeklyPaperPush.objects.update_or_create(
            week_start=week_start,
            defaults={
                "week_end": week_end,
                "paper_count": payload["paperCount"],
                "title": title,
                "fixed_summary": payload["fixedSummary"],
                "ai_summary": payload["aiSummary"],
                "content": payload["content"],
                "papers": payload["papers"],
                "generated_by": payload["generatedBy"],
            },
        )

        if not created and not force:
            self.stdout.write(self.style.WARNING("本周推送已存在，已按默认逻辑更新。可用 --force 显式覆盖。"))

        self.stdout.write(
            self.style.SUCCESS(
                f"周推送已生成：week={week_start}~{week_end}, papers={len(papers)}, mode={payload['generatedBy']}, id={push_obj.id}"
            )
        )
