from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import patch, MagicMock
from datetime import date, datetime
from pathlib import Path
import json
import tempfile

from dataset.models import Paper, Mentor
from dataset.management.commands.fetch_papers import Command as FetchPapersCommand
from dataset.services.thu_crawler import get_english_name, parse_mentor_detail, parse_mentor_list
from account.models import User as AccountUser, WeeklyPushPaperBucket
from account.services.weekly_push_files import build_weekly_push_bucket_period_key
from utils.utils_jwt import generate_jwt_token


class PaperModelTest(TestCase):
    """测试Paper模型"""

    def setUp(self):
        self.paper = Paper.objects.create(
            title="测试论文",
            abstract="这是一个测试摘要",
            publish_date=date(2023, 1, 1),
            author_names="张三, 李四, Wang Wu"
        )

    def test_paper_creation(self):
        """测试论文创建"""
        self.assertEqual(self.paper.title, "测试论文")
        self.assertEqual(self.paper.abstract, "这是一个测试摘要")
        self.assertEqual(self.paper.publish_date, date(2023, 1, 1))
        self.assertEqual(self.paper.author_names, "张三, 李四, Wang Wu")

    def test_subjects_field(self):
        """测试论文学科字段"""
        paper = Paper.objects.create(title="分类论文", subjects="cs.LG, cs.AI")
        self.assertEqual(paper.subjects, "cs.LG, cs.AI")

    def test_get_author_list(self):
        """测试获取作者列表"""
        authors = self.paper.get_author_list()
        self.assertEqual(len(authors), 3)
        self.assertEqual(authors[0], "张三")
        self.assertEqual(authors[1], "李四")
        self.assertEqual(authors[2], "Wang Wu")

    def test_get_author_list_empty(self):
        """测试空作者列表"""
        paper = Paper.objects.create(title="无作者论文", author_names="")
        authors = paper.get_author_list()
        self.assertEqual(len(authors), 0)

    def test_str_representation(self):
        """测试字符串表示"""
        self.assertEqual(str(self.paper), "测试论文")


class MentorModelTest(TestCase):
    """测试Mentor模型"""

    def setUp(self):
        self.mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能",
            email="zhangsan@example.com",
            profile="测试画像"
        )

        self.paper1 = Paper.objects.create(
            title="论文1",
            author_names="张三, 李四"
        )
        self.paper2 = Paper.objects.create(
            title="论文2",
            author_names="Wang Wu, San Zhang"
        )

    def test_mentor_creation(self):
        """测试导师创建"""
        self.assertEqual(self.mentor.Chinese_name, "张三")
        self.assertEqual(self.mentor.English_name, "San Zhang")
        self.assertEqual(self.mentor.research_direction, "人工智能")
        self.assertEqual(self.mentor.email, "zhangsan@example.com")
        self.assertEqual(self.mentor.profile, "测试画像")

    def test_get_paper_id_list(self):
        """测试获取论文ID列表"""
        self.mentor.set_paper_id_list([1, 2, 3])
        paper_ids = self.mentor.get_paper_id_list()
        self.assertEqual(paper_ids, [1, 2, 3])

    def test_set_paper_id_list(self):
        """测试设置论文ID列表"""
        self.mentor.set_paper_id_list([4, 5, 6])
        self.assertEqual(self.mentor.paper_ids, "4,5,6")

    def test_get_papers(self):
        """测试获取关联论文"""
        self.mentor.set_paper_id_list([self.paper1.id, self.paper2.id])
        papers = self.mentor.get_papers()
        self.assertEqual(len(papers), 2)
        self.assertEqual(papers[0].title, "论文1")
        self.assertEqual(papers[1].title, "论文2")

    def test_add_paper(self):
        """测试添加论文"""
        self.mentor.add_paper(self.paper1.id)
        self.assertIn(self.paper1.id, self.mentor.get_paper_id_list())

    def test_remove_paper(self):
        """测试移除论文"""
        self.mentor.add_paper(self.paper1.id)
        self.mentor.add_paper(self.paper2.id)
        self.mentor.remove_paper(self.paper1.id)
        self.assertNotIn(self.paper1.id, self.mentor.get_paper_id_list())
        self.assertIn(self.paper2.id, self.mentor.get_paper_id_list())

    def test_str_representation(self):
        """测试字符串表示"""
        self.assertEqual(str(self.mentor), "张三")


class PaperMentorBindingTest(TestCase):
    """测试论文与导师的绑定"""

    def setUp(self):
        self.mentor1 = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能"
        )
        self.mentor2 = Mentor.objects.create(
            Chinese_name="李四",
            English_name="Si Li",
            research_direction="机器学习"
        )

        self.paper1 = Paper.objects.create(
            title="论文1",
            author_names="张三, Wang Wu"
        )
        self.paper2 = Paper.objects.create(
            title="论文2",
            author_names="Si Li, Wang Liu"
        )
        self.paper3 = Paper.objects.create(
            title="论文3",
            author_names="Wang Wu, Wang Liu"
        )

    def test_bind_to_mentors_by_chinese_name(self):
        """测试通过中文名绑定导师"""
        self.paper1.bind_to_mentors_by_authors()
        self.mentor1.refresh_from_db()
        self.assertIn(self.paper1.id, self.mentor1.get_paper_id_list())

    def test_bind_to_mentors_by_english_name(self):
        """测试通过英文名绑定导师"""
        self.paper2.bind_to_mentors_by_authors()
        self.mentor2.refresh_from_db()
        self.assertIn(self.paper2.id, self.mentor2.get_paper_id_list())

    def test_bind_to_mentors_case_insensitive(self):
        """测试英文名不区分大小写绑定"""
        paper = Paper.objects.create(
            title="测试论文",
            author_names="SAN ZHANG, Wang Wu"
        )
        paper.bind_to_mentors_by_authors()
        self.mentor1.refresh_from_db()
        self.assertIn(paper.id, self.mentor1.get_paper_id_list())

    def test_bind_to_mentors_reversed_name(self):
        """测试英文名颠倒顺序绑定"""
        paper = Paper.objects.create(
            title="测试论文",
            author_names="Zhang San, Wang Wu"
        )
        paper.bind_to_mentors_by_authors()
        self.mentor1.refresh_from_db()
        self.assertIn(paper.id, self.mentor1.get_paper_id_list())


class PaperViewTest(TestCase):
    """测试论文相关视图"""
    
    def setUp(self):
        self.client = Client()
        
        # 创建管理员用户
        self.admin_user = AccountUser.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="admin123",
            role="admin"
        )
        self.admin_token = generate_jwt_token("admin")
        
        # 创建普通用户
        self.normal_user = AccountUser.objects.create_user(
            username="user",
            email="user@test.com",
            password="user123",
            role="student"
        )
        self.normal_token = generate_jwt_token("user")
        
        # 创建测试论文
        self.paper = Paper.objects.create(
            title="测试论文",
            abstract="测试摘要",
            author_names="张三"
        )
    
    def test_create_paper_as_admin(self):
        """测试管理员创建论文"""
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "新论文",
                "abstract": "新摘要",
                "author_names": "张三, 李四"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Paper.objects.count(), 2)
    
    def test_create_paper_as_user(self):
        """测试普通用户创建论文（应失败）"""
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "新论文",
                "abstract": "新摘要",
                "author_names": "张三, 李四"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}"
        )
        self.assertEqual(response.status_code, 403)
    
    def test_create_paper_without_auth(self):
        """测试未授权创建论文（应失败）"""
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "新论文",
                "abstract": "新摘要",
                "author_names": "张三, 李四"
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)
    
    def test_create_paper_invalid_title(self):
        """测试创建论文时标题为空（应失败）"""
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "",
                "abstract": "新摘要",
                "author_names": "张三, 李四"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 400)
    
    def test_update_paper_as_admin(self):
        """测试管理员更新论文"""
        response = self.client.put(
            f"/dataset/papers/{self.paper.id}",
            data=json.dumps({
                "title": "更新后的论文",
                "abstract": "更新后的摘要",
                "author_names": "李四"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 200)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.title, "更新后的论文")
    
    def test_delete_paper_as_admin(self):
        """测试管理员删除论文"""
        response = self.client.delete(
            f"/dataset/papers/{self.paper.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Paper.objects.count(), 0)


class MentorViewTest(TestCase):
    """测试导师相关视图"""
    
    def setUp(self):
        self.client = Client()
        
        # 创建管理员用户
        self.admin_user = AccountUser.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="admin123",
            role="admin"
        )
        self.admin_token = generate_jwt_token("admin")
        
        # 创建普通用户
        self.normal_user = AccountUser.objects.create_user(
            username="user",
            email="user@test.com",
            password="user123",
            role="student"
        )
        self.normal_token = generate_jwt_token("user")

        self.other_user = AccountUser.objects.create_user(
            username="other",
            email="other@test.com",
            password="other123",
            role="student"
        )
        self.other_token = generate_jwt_token("other")
        
        # 创建测试导师
        self.mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能",
            email="zhangsan@example.com"
        )
    
    def test_create_mentor_as_admin(self):
        """测试管理员创建导师"""
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "李四",
                "English_name": "Si Li",
                "research_direction": "机器学习",
                "email": "lisi@example.com"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Mentor.objects.count(), 2)
    
    def test_create_mentor_as_user(self):
        """测试普通用户创建导师（应失败）"""
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "李四",
                "English_name": "Si Li",
                "research_direction": "机器学习",
                "email": "lisi@example.com"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}"
        )
        self.assertEqual(response.status_code, 403)
    
    def test_create_mentor_without_auth(self):
        """测试未授权创建导师（应失败）"""
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "李四",
                "English_name": "Si Li",
                "research_direction": "机器学习",
                "email": "lisi@example.com"
            }),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)
    
    def test_create_mentor_invalid_chinese_name(self):
        """测试创建导师时中文名为空（应失败）"""
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "",
                "English_name": "Si Li",
                "research_direction": "机器学习",
                "email": "lisi@example.com"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 400)
    
    def test_create_mentor_invalid_email(self):
        """测试创建导师时邮箱格式不正确（应失败）"""
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "李四",
                "English_name": "Si Li",
                "research_direction": "机器学习",
                "email": "invalid_email"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 400)

    @patch("dataset.views.crawl_mentor_by_name")
    def test_create_custom_mentor_success(self, mock_crawler):
        mock_crawler.return_value = {
            "Chinese_name": "王五",
            "English_name": "Wang Wu",
            "research_direction": "强化学习",
            "email": "wangwu@example.com",
            "profile": "测试私有导师",
        }

        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "王五",
                "English_name": "Wang Wu",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        created = Mentor.objects.filter(owner=self.normal_user, Chinese_name="王五").first()
        self.assertIsNotNone(created)
        self.assertEqual(response.json()["mentor"]["Chinese_name"], "王五")
        self.assertEqual(response.json()["mentor"]["is_private"], True)

    @patch("dataset.views.crawl_mentor_by_name")
    def test_create_custom_mentor_prefers_english_name_for_crawler(self, mock_crawler):
        mock_crawler.return_value = {
            "Chinese_name": "王五",
            "English_name": "Wang Wu",
            "research_direction": "强化学习",
            "email": "wangwu@example.com",
            "profile": "测试私有导师",
        }

        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "错误中文名",
                "English_name": "Wang Wu",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        mock_crawler.assert_called_once_with(chinese_name="", english_name="Wang Wu")

    @patch("dataset.views.crawl_mentor_by_name")
    def test_create_custom_mentor_uses_pinyin_name_surname_when_english_missing(self, mock_crawler):
        mock_crawler.return_value = {
            "Chinese_name": "唐杰",
            "English_name": "Jie Tang",
            "research_direction": "知识图谱",
            "email": "jietang@example.com",
            "profile": "测试私有导师",
        }

        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "唐杰",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        mock_crawler.assert_called_once_with(chinese_name="", english_name="jie-tang")

    def test_create_custom_mentor_requires_login(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "王五",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    @patch("dataset.views.crawl_mentor_by_name")
    def test_create_custom_mentor_rejects_when_reaching_limit(self, mock_crawler):
        for idx in range(10):
            Mentor.objects.create(
                Chinese_name=f"私有导师{idx}",
                English_name=f"Private Mentor {idx}",
                research_direction="测试方向",
                owner=self.normal_user,
            )

        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "王五",
                "English_name": "Wang Wu",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["info"], "Private mentor limit reached (max 10)")
        self.assertEqual(Mentor.objects.filter(owner=self.normal_user).count(), 10)
        mock_crawler.assert_not_called()

    @patch("dataset.views.crawl_mentor_by_name")
    def test_my_custom_mentors_only_returns_current_user_records(self, mock_crawler):
        mock_crawler.return_value = {
            "Chinese_name": "王五",
            "English_name": "Wang Wu",
            "research_direction": "强化学习",
            "email": "wangwu@example.com",
            "profile": "测试私有导师",
        }

        self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({"Chinese_name": "王五"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        Mentor.objects.create(
            Chinese_name="赵六",
            English_name="Zhao Liu",
            research_direction="数据库",
            owner=self.other_user,
        )

        response = self.client.get(
            "/dataset/mentors/mine",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        names = {mentor["Chinese_name"] for mentor in response.json()["mentors"]}
        self.assertEqual(names, {"王五"})

    def test_private_mentor_detail_only_visible_to_owner(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="系统安全",
            owner=self.normal_user,
        )

        anonymous_res = self.client.get(f"/dataset/mentors/{private_mentor.id}")
        self.assertEqual(anonymous_res.status_code, 404)

        other_res = self.client.get(
            f"/dataset/mentors/{private_mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.other_token}",
        )
        self.assertEqual(other_res.status_code, 404)

        owner_res = self.client.get(
            f"/dataset/mentors/{private_mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )
        self.assertEqual(owner_res.status_code, 200)

    def test_owner_can_update_private_mentor(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="系统安全",
            owner=self.normal_user,
        )

        response = self.client.put(
            f"/dataset/mentors/{private_mentor.id}",
            data=json.dumps({
                "Chinese_name": "私有导师",
                "English_name": "Private Mentor",
                "research_direction": "可信人工智能",
                "email": "private@example.com",
                "profile": "用户维护的私有导师档案",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        private_mentor.refresh_from_db()
        self.assertEqual(private_mentor.research_direction, "可信人工智能")
        self.assertEqual(private_mentor.email, "private@example.com")
        self.assertEqual(response.json()["mentor"]["is_private"], True)

    def test_non_owner_cannot_update_private_mentor(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="系统安全",
            owner=self.normal_user,
        )

        response = self.client.put(
            f"/dataset/mentors/{private_mentor.id}",
            data=json.dumps({
                "Chinese_name": "私有导师",
                "English_name": "Private Mentor",
                "research_direction": "不应被写入",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.other_token}",
        )

        self.assertEqual(response.status_code, 404)
        private_mentor.refresh_from_db()
        self.assertEqual(private_mentor.research_direction, "系统安全")

    def test_admin_can_delete_private_mentor(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="系统安全",
            owner=self.normal_user,
        )

        response = self.client.delete(
            f"/dataset/mentors/{private_mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Mentor.objects.filter(id=private_mentor.id).exists())

    def test_get_mentor_without_auth(self):
        """测试未登录也可以获取导师详情"""
        response = self.client.get(f"/dataset/mentors/{self.mentor.id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["mentor"]["id"], self.mentor.id)
        self.assertEqual(data["mentor"]["Chinese_name"], "张三")
        self.assertEqual(data["mentor"]["English_name"], "San Zhang")
        self.assertEqual(data["mentor"]["research_direction"], "人工智能")
        self.assertEqual(data["mentor"]["email"], "zhangsan@example.com")

    def test_update_mentor_without_auth(self):
        """测试未登录不能修改导师"""
        response = self.client.put(
            f"/dataset/mentors/{self.mentor.id}",
            data=json.dumps({
                "Chinese_name": "张三",
                "English_name": "San Zhang",
                "research_direction": "深度学习",
                "email": "zhangsan_new@example.com"
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
    
    def test_update_mentor_as_admin(self):
        """测试管理员更新导师"""
        response = self.client.put(
            f"/dataset/mentors/{self.mentor.id}",
            data=json.dumps({
                "Chinese_name": "张三",
                "English_name": "San Zhang",
                "research_direction": "深度学习",
                "email": "zhangsan_new@example.com"
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 200)
        self.mentor.refresh_from_db()
        self.assertEqual(self.mentor.research_direction, "深度学习")
        self.assertEqual(self.mentor.email, "zhangsan_new@example.com")
    
    def test_delete_mentor_as_admin(self):
        """测试管理员删除导师"""
        response = self.client.delete(
            f"/dataset/mentors/{self.mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Mentor.objects.count(), 0)


class FetchPapersCommandTest(TestCase):
    """测试 fetch_papers 命令中的语义分类增强逻辑"""

    def setUp(self):
        self.command = FetchPapersCommand()

    @patch.object(FetchPapersCommand, "_fetch_s2_metadata")
    @patch("dataset.management.commands.fetch_papers.arxiv.Client")
    def test_fetch_from_arxiv_tracks_created_paper_ids(self, mock_arxiv_client_cls, mock_fetch_s2_metadata):
        mentor = Mentor.objects.create(
            Chinese_name="测试导师",
            English_name="Test Mentor",
            research_direction="人工智能",
        )
        result = MagicMock()
        result.title = "测试新增论文"
        result.summary = "测试摘要"
        result.published = datetime(2026, 4, 25, 12, 0, 0)
        author_1 = MagicMock()
        author_1.name = "Test Mentor"
        author_2 = MagicMock()
        author_2.name = "Other Author"
        result.authors = [author_1, author_2]
        result.entry_id = "http://arxiv.org/abs/2504.12345v1"
        result.categories = ["cs.AI"]
        mock_arxiv_client_cls.return_value.results.return_value = [result]
        mock_fetch_s2_metadata.return_value = ("cs.AI", "TLDR")

        self.command.fetch_from_arxiv(mentor)

        self.assertEqual(Paper.objects.count(), 1)
        self.assertEqual(len(self.command.created_paper_ids), 1)
        self.assertEqual(list(self.command.created_paper_ids)[0], Paper.objects.first().id)

    def test_record_new_papers_for_weekly_push_writes_to_current_cycle_file(self):
        paper = Paper.objects.create(
            title="周报当前周期论文",
            abstract="摘要",
            publish_date=date(2026, 4, 24),
            author_names="Author",
            subjects="cs.AI",
        )

        self.command._record_new_papers_for_weekly_push(
            paper_ids=[paper.id],
            now=datetime(2026, 4, 24, 13, 0, 0),
        )

        self.assertEqual(
            WeeklyPushPaperBucket.objects.filter(
                cycle=WeeklyPushPaperBucket.CYCLE_CURRENT,
                period_key="20260423_20260429",
                day_key="friday",
                paper=paper,
            ).count(),
            1,
        )

    def test_record_new_papers_for_weekly_push_routes_thursday_morning_to_next_cycle(self):
        paper = Paper.objects.create(
            title="周报下周期论文",
            abstract="摘要",
            publish_date=date(2026, 4, 23),
            author_names="Author",
            subjects="cs.CL",
        )

        self.command._record_new_papers_for_weekly_push(
            paper_ids=[paper.id],
            now=datetime(2026, 4, 23, 4, 0, 0),
        )

        self.assertEqual(
            WeeklyPushPaperBucket.objects.filter(
                cycle=WeeklyPushPaperBucket.CYCLE_NEXT,
                period_key="20260423_20260429",
                day_key="thursday",
                paper=paper,
            ).count(),
            1,
        )

    def test_record_new_papers_for_weekly_push_skips_empty_increment(self):
        self.command._record_new_papers_for_weekly_push(
            paper_ids=[],
            now=datetime(2026, 4, 22, 4, 0, 0),
        )

        self.assertEqual(WeeklyPushPaperBucket.objects.count(), 0)


class TimelineViewTest(TestCase):
    """测试时间线接口的方向概览与分页加载"""

    def setUp(self):
        self.client = Client()

        self.paper_ai_old = Paper.objects.create(
            title="AI 早期论文",
            abstract="摘要1",
            publish_date=date(2024, 1, 10),
            author_names="张三",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/1111.1111",
            tldr="tldr1",
        )
        self.paper_ai_new = Paper.objects.create(
            title="AI 最新论文",
            abstract="摘要2",
            publish_date=date(2024, 2, 12),
            author_names="李四",
            subjects="cs.AI, cs.LG",
            arxiv_url="https://arxiv.org/abs/2222.2222",
            tldr="tldr2",
        )
        self.paper_other = Paper.objects.create(
            title="未分类论文",
            abstract="摘要3",
            publish_date=date(2024, 3, 18),
            author_names="王五",
            subjects="",
            arxiv_url="https://arxiv.org/abs/3333.3333",
            tldr="tldr3",
        )
        Paper.objects.create(
            title="无发表日期论文",
            abstract="摘要4",
            publish_date=None,
            author_names="赵六",
            subjects="cs.AI",
        )

    def test_timeline_overview_returns_direction_counts(self):
        response = self.client.get("/timeline/")

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("directions", data)
        self.assertIn("default_direction", data)
        self.assertIn("page_size_default", data)
        self.assertIn("page_size_max", data)

        directions = data["directions"]
        direction_counts = {
            item["direction"]: item["paper_count"]
            for item in directions
        }

        self.assertEqual(direction_counts["人工智能 (Artificial Intelligence)"], 2)
        self.assertEqual(direction_counts["机器学习 (Machine Learning)"], 1)
        self.assertEqual(direction_counts["其他/未分类"], 1)
        self.assertEqual(data["default_direction"], "人工智能 (Artificial Intelligence)")

    def test_timeline_direction_response_is_paginated(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "page": 1,
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["direction"], "人工智能 (Artificial Intelligence)")
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 1)
        self.assertEqual(data["total_papers"], 2)
        self.assertEqual(data["total_pages"], 2)
        self.assertFalse(data["has_previous"])
        self.assertTrue(data["has_next"])
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(data["papers"][0]["id"], self.paper_ai_new.id)

    def test_timeline_page_size_has_upper_bound(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "其他/未分类",
                "page": 1,
                "page_size": 999,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page_size"], 100)
        self.assertEqual(data["total_papers"], 1)
        self.assertEqual(data["papers"][0]["id"], self.paper_other.id)


    
   
