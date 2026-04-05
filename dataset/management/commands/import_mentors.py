# mentor/backend/dataset/management/commands/import_mentors.py
from django.core.management.base import BaseCommand
from dataset.models import Mentor
from dataset.services.thu_crawler import parse_mentor_list

class Command(BaseCommand):
    help = "Import mentors from Tsinghua CS website"

    def handle(self, *args, **options):
        ch_url = "https://www.cs.tsinghua.edu.cn/szzk/jzgml.htm"
        en_url = "https://www.cs.tsinghua.edu.cn/csen/Faculty/Full_time_Faculty.htm"
        mentors = parse_mentor_list(ch_url,en_url)

        for item in mentors:
            Mentor.objects.update_or_create(
                Chinese_name=item["Chinese_name"],
                defaults={
                    "English_name": item["English_name"] or None,
                    "research_direction": item["research_direction"] or "未提供",
                    "email": item["email"] or None,
                    "profile": item["profile"] or None,
                },
            )

        self.stdout.write(self.style.SUCCESS(f"Imported {len(mentors)} mentors"))
