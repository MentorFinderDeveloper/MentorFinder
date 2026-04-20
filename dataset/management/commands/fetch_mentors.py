# mentor/backend/dataset/management/commands/import_mentors.py
from django.core.management.base import BaseCommand
from dataset.models import Mentor
from dataset.services.thu_crawler import parse_mentor_list

class Command(BaseCommand):
    help = "Import mentors from Tsinghua CS website"

    def handle(self, *args, **options):
        # 只需要中文 URL
        ch_url = "https://www.cs.tsinghua.edu.cn/szzk/jzgml.htm"
        
        # 1. 修改这里：删掉 en_url 参数
        self.stdout.write("开始从清华官网抓取导师信息...")
        mentors = parse_mentor_list(ch_url)

        # 2. 遍历保存
        for item in mentors:
            mentor, created = Mentor.objects.update_or_create(
                Chinese_name=item["Chinese_name"],
                owner=None,
                defaults={
                    "English_name": item["English_name"] or None,
                    "research_direction": item["research_direction"] or "未提供",
                    "email": item["email"] or None,
                    "profile": item["profile"] or None,
                    "owner": None,
                },
            )
            if created:
                self.stdout.write(f"  [新导师] {item['Chinese_name']}")

        self.stdout.write(self.style.SUCCESS(f"成功导入/更新 {len(mentors)} 位导师"))