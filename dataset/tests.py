from django.test import TestCase
from .models import Mentor, Paper


class SeparateMaintenanceTest(TestCase):
    def setUp(self):
        self.paper1 = Paper.objects.create(title="论文1")
        self.paper2 = Paper.objects.create(title="论文2")
        self.paper3 = Paper.objects.create(title="论文3")
        self.mentor = Mentor.objects.create(
            name="张老师",
            research_direction="自然语言处理",
            email="zhang@example.com",
        )

    def test_add_paper(self):
        self.mentor.add_paper(self.paper2.id)
        self.mentor.add_paper(self.paper1.id)
        self.assertEqual(self.mentor.get_paper_id_list(), [self.paper2.id, self.paper1.id])