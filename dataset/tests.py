from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import tempfile

from dataset.models import Paper, Mentor
from dataset.management.commands.fetch_papers import Command as FetchPapersCommand
from dataset.services.thu_crawler import (
    _english_name_variants,
    _normalize_name,
    build_given_name_surname_pinyin,
    crawl_mentor_by_name,
    get_english_name,
    parse_mentor_detail,
    parse_mentor_list,
)
from dataset.services.author_matching import (
    english_name_variants,
    has_exact_english_author_match,
    is_exact_english_author_match,
    normalize_english_name,
)
from dataset.services.weekly_push_summary import (
    build_fixed_summary,
    compose_weekly_push_content,
    resolve_week_range,
    serialize_weekly_push_paper,
)
from account.models import MentorFollow, SubjectFollow, User as AccountUser, WeeklyPushPaperBucket
from account.services.weekly_push_files import build_weekly_push_bucket_period_key
from utils.utils_jwt import generate_jwt_token
from utils.utils_request import return_field
from utils.utils_time import get_timestamp


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

    def test_bind_to_mentors_updates_paper_mentor_ids(self):
        """测试绑定导师时同步记录到论文侧"""
        self.paper1.bind_to_mentors_by_authors()
        self.paper1.refresh_from_db()
        self.assertIn(self.mentor1.id, self.paper1.get_mentor_id_list())

    def test_bind_to_mentors_does_not_match_partial_english_name(self):
        mentor = Mentor.objects.create(
            Chinese_name="陈宇",
            English_name="Yu Chen",
            research_direction="人工智能",
        )
        paper = Paper.objects.create(
            title="误匹配论文",
            author_names="Wei Yu Chen, Other Author",
        )

        paper.bind_to_mentors_by_authors()
        mentor.refresh_from_db()
        paper.refresh_from_db()

        self.assertNotIn(mentor.id, paper.get_mentor_id_list())
        self.assertNotIn(paper.id, mentor.get_paper_id_list())


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

    def test_create_paper_binds_existing_mentor_by_author_name(self):
        mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能",
        )

        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "导师绑定论文",
                "abstract": "摘要",
                "author_names": "张三, 其他作者",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 200)
        mentor.refresh_from_db()
        created_paper_id = response.json()["paper"]["id"]
        self.assertIn(created_paper_id, mentor.get_paper_id_list())

    def test_create_paper_rejects_title_that_is_too_long(self):
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "x" * 256,
                "abstract": "摘要",
                "author_names": "张三",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid parameters. [title] is too long")

    def test_create_paper_rejects_abstract_that_is_too_long(self):
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "摘要过长论文",
                "abstract": "x" * 5001,
                "author_names": "张三",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid parameters. [abstract] is too long")

    def test_create_paper_rejects_author_names_that_are_too_long(self):
        response = self.client.post(
            "/dataset/papers",
            data=json.dumps({
                "title": "作者过长论文",
                "abstract": "摘要",
                "author_names": "x" * 5001,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid parameters. [author_names] is too long")
    
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

    def test_update_paper_rebinds_mentor_paper_ids(self):
        zhang_mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能",
        )
        li_mentor = Mentor.objects.create(
            Chinese_name="李四",
            English_name="Si Li",
            research_direction="机器学习",
        )
        self.paper.bind_to_mentors_by_authors()
        zhang_mentor.refresh_from_db()
        self.assertIn(self.paper.id, zhang_mentor.get_paper_id_list())

        response = self.client.put(
            f"/dataset/papers/{self.paper.id}",
            data=json.dumps({
                "title": "更新后的论文",
                "abstract": "更新后的摘要",
                "author_names": "李四",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 200)
        zhang_mentor.refresh_from_db()
        li_mentor.refresh_from_db()
        self.assertNotIn(self.paper.id, zhang_mentor.get_paper_id_list())
        self.assertIn(self.paper.id, li_mentor.get_paper_id_list())

    def test_delete_paper_detaches_from_mentor_paper_ids(self):
        zhang_mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能",
        )
        self.paper.bind_to_mentors_by_authors()
        zhang_mentor.refresh_from_db()
        self.assertIn(self.paper.id, zhang_mentor.get_paper_id_list())

        response = self.client.delete(
            f"/dataset/papers/{self.paper.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 200)
        zhang_mentor.refresh_from_db()
        self.assertNotIn(self.paper.id, zhang_mentor.get_paper_id_list())

    def test_update_paper_requires_admin(self):
        response = self.client.put(
            f"/dataset/papers/{self.paper.id}",
            data=json.dumps({
                "title": "普通用户修改",
                "abstract": "摘要",
                "author_names": "张三",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 403)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.title, "测试论文")

    def test_update_paper_returns_404_for_missing_paper(self):
        response = self.client.put(
            "/dataset/papers/999999",
            data=json.dumps({
                "title": "不存在论文",
                "abstract": "摘要",
                "author_names": "张三",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "Paper not found")

    def test_delete_paper_requires_admin(self):
        response = self.client.delete(
            f"/dataset/papers/{self.paper.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Paper.objects.filter(id=self.paper.id).exists())

    def test_delete_paper_returns_404_for_missing_paper(self):
        response = self.client.delete(
            "/dataset/papers/999999",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "Paper not found")

    def test_paper_detail_rejects_bad_method(self):
        response = self.client.get(
            f"/dataset/papers/{self.paper.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)
    
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

    def test_create_custom_mentor_success(self):
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
        self.assertEqual(response.json()["mentor"]["English_name"], "Wang Wu")
        self.assertEqual(response.json()["mentor"]["research_direction"], "待补充")
        self.assertEqual(response.json()["mentor"]["email"], None)
        self.assertEqual(response.json()["mentor"]["is_private"], True)

    def test_create_custom_mentor_uses_provided_english_name(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "赵六",
                "English_name": "Six Zhao",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mentor"]["English_name"], "Six Zhao")

    def test_create_custom_mentor_generates_pinyin_when_english_missing(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "唐杰",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mentor"]["English_name"], "Jie Tang")

    def test_create_custom_mentor_requires_login(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "王五",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_create_custom_mentor_creates_directly_without_crawler(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({"Chinese_name": "独立导师"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        mentor = Mentor.objects.get(owner=self.normal_user, Chinese_name="独立导师")
        self.assertEqual(mentor.research_direction, "待补充")
        self.assertEqual(mentor.email, None)
        self.assertEqual(mentor.profile, None)

    def test_create_custom_mentor_requires_at_least_one_name(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({"Chinese_name": "   ", "English_name": "   "}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(
            response.json()["info"],
            "Invalid parameters. [Chinese_name] or [English_name] is required",
        )

    def test_create_custom_mentor_rejects_english_name_that_is_too_long(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({"Chinese_name": "", "English_name": "x" * 101}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid parameters. [English_name] is too long")

    def test_create_custom_mentor_rejects_duplicate_private_mentor(self):
        Mentor.objects.create(
            Chinese_name="王五",
            English_name="Wang Wu",
            research_direction="强化学习",
            owner=self.normal_user,
        )

        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({
                "Chinese_name": "王五",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], 3)
        self.assertEqual(response.json()["info"], "Mentor already exists in your private library")

    def test_create_custom_mentor_rejects_when_reaching_limit(self):
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

    def test_my_custom_mentors_only_returns_current_user_records(self):
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

    def test_my_custom_mentors_rejects_bad_method(self):
        response = self.client.post(
            "/dataset/mentors/mine",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)

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

    def test_admin_can_view_private_mentor_detail(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="后台可见私有导师",
            English_name="Admin Visible",
            research_direction="机器学习",
            owner=self.normal_user,
        )

        response = self.client.get(
            f"/dataset/mentors/{private_mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mentor"]["Chinese_name"], "后台可见私有导师")
        self.assertTrue(response.json()["mentor"]["is_private"])

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

    def test_owner_can_delete_private_mentor(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="系统安全",
            owner=self.normal_user,
        )

        response = self.client.delete(
            f"/dataset/mentors/{private_mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.normal_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Mentor.objects.filter(id=private_mentor.id).exists())

    def test_non_owner_cannot_delete_private_mentor(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="系统安全",
            owner=self.normal_user,
        )

        response = self.client.delete(
            f"/dataset/mentors/{private_mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.other_token}",
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Mentor.objects.filter(id=private_mentor.id).exists())

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

    def test_clean_arxiv_author_names_removes_prefix_before_colon(self):
        self.assertEqual(
            self.command._clean_arxiv_author_names("GLM Team : Alice, Bob"),
            "Alice, Bob",
        )
        self.assertEqual(
            self.command._clean_arxiv_author_names("Some Group, :, Alice, Bob"),
            "Alice, Bob",
        )
        self.assertEqual(
            self.command._clean_arxiv_author_names("Project X：Alice, Bob"),
            "Alice, Bob",
        )
        self.assertEqual(
            self.command._clean_arxiv_author_names("Consortium: Alice"),
            "Alice",
        )
        self.assertEqual(
            self.command._clean_arxiv_author_names("Alice, Bob"),
            "Alice, Bob",
        )

    @patch.object(FetchPapersCommand, "_fetch_s2_metadata")
    @patch("dataset.management.commands.fetch_papers.arxiv.Client")
    def test_fetch_from_arxiv_skips_partial_english_name_match(self, mock_arxiv_client_cls, mock_fetch_s2_metadata):
        mentor = Mentor.objects.create(
            Chinese_name="陈宇",
            English_name="Yu Chen",
            research_direction="人工智能",
        )
        result = MagicMock()
        result.title = "误召回论文"
        result.summary = "测试摘要"
        result.published = datetime(2026, 4, 25, 12, 0, 0)
        author_1 = MagicMock()
        author_1.name = "Wei Yu Chen"
        author_2 = MagicMock()
        author_2.name = "Other Author"
        result.authors = [author_1, author_2]
        result.entry_id = "http://arxiv.org/abs/2504.99999v1"
        result.categories = ["cs.AI"]
        mock_arxiv_client_cls.return_value.results.return_value = [result]
        mock_fetch_s2_metadata.return_value = ("cs.AI", "TLDR")

        self.command.fetch_from_arxiv(mentor)

        self.assertEqual(Paper.objects.count(), 0)
        self.assertEqual(len(self.command.created_paper_ids), 0)

    @patch("dataset.management.commands.fetch_papers.time.sleep")
    @patch.object(FetchPapersCommand, "_fetch_from_arxiv_once")
    def test_fetch_from_arxiv_retries_when_arxiv_returns_429(self, mock_fetch_once, mock_sleep):
        mentor = Mentor.objects.create(
            Chinese_name="测试导师",
            English_name="Test Mentor",
            research_direction="人工智能",
        )

        mock_fetch_once.side_effect = [
            Exception("Page request resulted in HTTP 429"),
            None,
        ]

        self.command.fetch_from_arxiv(mentor)

        self.assertEqual(mock_fetch_once.call_count, 2)
        mock_sleep.assert_called_once_with(self.command.ARXIV_RATE_LIMIT_BACKOFF_SECONDS[0])

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
        self.mentor_li = Mentor.objects.create(
            Chinese_name="李四",
            English_name="Li Si",
            research_direction="人工智能",
            email="lisi@example.com",
            profile="用于测试时间线作者链接。",
        )

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
        self.assertEqual(data["papers"][0]["subjects"], "cs.AI, cs.LG")
        self.assertEqual(data["papers"][0]["mentor_ids"], [self.mentor_li.id])

    def test_timeline_direction_response_supports_offset_limit_slicing(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "offset": 0,
                "limit": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["direction"], "人工智能 (Artificial Intelligence)")
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["limit"], 1)
        self.assertEqual(data["total_papers"], 2)
        self.assertFalse(data["has_previous"])
        self.assertTrue(data["has_next"])
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(data["papers"][0]["id"], self.paper_ai_new.id)

    def test_timeline_offset_limit_middle_slice_reports_both_directions(self):
        middle_paper = Paper.objects.create(
            title="AI 中间论文",
            abstract="摘要中间",
            publish_date=date(2024, 2, 1),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/5555.5555",
            tldr="tldr-middle",
        )

        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "offset": 1,
                "limit": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["offset"], 1)
        self.assertEqual(data["limit"], 1)
        self.assertEqual(data["total_papers"], 3)
        self.assertTrue(data["has_previous"])
        self.assertTrue(data["has_next"])
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(data["papers"][0]["id"], middle_paper.id)

    def test_timeline_offset_limit_tail_slice_reports_no_next(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "offset": 1,
                "limit": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["offset"], 1)
        self.assertEqual(data["limit"], 5)
        self.assertTrue(data["has_previous"])
        self.assertFalse(data["has_next"])
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(data["papers"][0]["id"], self.paper_ai_old.id)

    def test_timeline_papers_return_author_aligned_mentor_ids(self):
        mixed_paper = Paper.objects.create(
            title="混合作者论文",
            abstract="摘要5",
            publish_date=date(2024, 2, 20),
            author_names="李四,赵云",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/4444.4444",
            tldr="tldr4",
        )

        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "page": 1,
                "page_size": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        target_paper = next(paper for paper in data["papers"] if paper["id"] == mixed_paper.id)
        self.assertEqual(target_paper["mentor_ids"], [self.mentor_li.id, 0])

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

    def test_timeline_offset_and_limit_are_normalized(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "其他/未分类",
                "offset": -2,
                "limit": 999,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["offset"], 0)
        self.assertEqual(data["limit"], 100)
        self.assertFalse(data["has_previous"])
        self.assertFalse(data["has_next"])
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(data["papers"][0]["id"], self.paper_other.id)

    def test_timeline_rejects_bad_method(self):
        response = self.client.post(
            "/timeline/",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)

    def test_timeline_page_number_below_one_is_clamped(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "page": 0,
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["papers"][0]["id"], self.paper_ai_new.id)

    def test_timeline_non_numeric_page_uses_default(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "page": "not-number",
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 1)

    def test_timeline_non_numeric_page_size_uses_default(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "page": 1,
                "page_size": "not-number",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page_size"], 20)
        self.assertEqual(data["total_papers"], 2)

    def test_timeline_page_above_total_pages_returns_last_page(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "page": 999,
                "page_size": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["page"], 2)
        self.assertFalse(data["has_next"])
        self.assertTrue(data["has_previous"])
        self.assertEqual(data["papers"][0]["id"], self.paper_ai_old.id)

    def test_timeline_offset_above_total_clamps_to_last_available_item(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "offset": 999,
                "limit": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["offset"], 1)
        self.assertTrue(data["has_previous"])
        self.assertFalse(data["has_next"])
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(data["papers"][0]["id"], self.paper_ai_old.id)

    def test_timeline_calendar_metadata_returns_available_dates(self):
        same_day_followup = Paper.objects.create(
            title="AI 同日补充论文",
            abstract="摘要6",
            publish_date=date(2024, 2, 12),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/6666.6666",
            tldr="tldr6",
        )

        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "calendar": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["direction"], "人工智能 (Artificial Intelligence)")
        self.assertEqual(data["default_date"], "2024-02-12")
        self.assertEqual(data["latest_date"], "2024-02-12")
        self.assertEqual(data["earliest_date"], "2024-01-10")
        self.assertEqual(data["available_dates"], [
            {"date": "2024-02-12", "paper_count": 2},
            {"date": "2024-01-10", "paper_count": 1},
        ])
        self.assertGreater(same_day_followup.id, self.paper_ai_new.id)

    def test_timeline_date_mode_returns_only_selected_day_and_day_stats(self):
        same_day_followup = Paper.objects.create(
            title="AI 同日补充论文",
            abstract="摘要6",
            publish_date=date(2024, 2, 12),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/6666.6666",
            tldr="tldr6",
        )

        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "date": "2024-02-12",
                "limit": 6,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["direction"], "人工智能 (Artificial Intelligence)")
        self.assertEqual(data["limit"], 6)
        self.assertEqual(data["total_papers"], 3)
        self.assertFalse(data["has_newer"])
        self.assertTrue(data["has_older"])
        self.assertEqual([paper["id"] for paper in data["papers"]], [
            same_day_followup.id,
            self.paper_ai_new.id,
        ])
        self.assertEqual(
            [(paper["day_sequence"], paper["day_total"]) for paper in data["papers"]],
            [(1, 2), (2, 2)],
        )

    def test_timeline_before_cursor_supports_cross_day_loading(self):
        Paper.objects.create(
            title="AI 同日补充论文",
            abstract="摘要6",
            publish_date=date(2024, 2, 12),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/6666.6666",
            tldr="tldr6",
        )
        middle_paper = Paper.objects.create(
            title="AI 中间论文",
            abstract="摘要7",
            publish_date=date(2024, 2, 11),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/7777.7777",
            tldr="tldr7",
        )

        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "before_date": "2024-02-12",
                "before_id": self.paper_ai_new.id,
                "limit": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_newer"])
        self.assertFalse(data["has_older"])
        self.assertEqual([paper["id"] for paper in data["papers"]], [
            middle_paper.id,
            self.paper_ai_old.id,
        ])
        self.assertEqual(
            [(paper["publish_date"], paper["day_sequence"], paper["day_total"]) for paper in data["papers"]],
            [("2024-02-11", 1, 1), ("2024-01-10", 1, 1)],
        )

    def test_timeline_after_cursor_supports_cross_day_loading(self):
        older_day_paper = Paper.objects.create(
            title="AI 旧日论文",
            abstract="摘要6",
            publish_date=date(2024, 2, 11),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/6666.6666",
            tldr="tldr6",
        )
        same_day_followup = Paper.objects.create(
            title="AI 同日补充论文",
            abstract="摘要7",
            publish_date=date(2024, 2, 12),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/7777.7777",
            tldr="tldr7",
        )
        newest_paper = Paper.objects.create(
            title="AI 更新论文",
            abstract="摘要8",
            publish_date=date(2024, 2, 13),
            author_names="李四",
            subjects="cs.AI",
            arxiv_url="https://arxiv.org/abs/8888.8888",
            tldr="tldr8",
        )

        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "after_date": "2024-02-11",
                "after_id": older_day_paper.id,
                "limit": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["has_newer"])
        self.assertTrue(data["has_older"])
        self.assertEqual([paper["id"] for paper in data["papers"]], [
            newest_paper.id,
            same_day_followup.id,
            self.paper_ai_new.id,
        ])
        self.assertEqual(
            [(paper["publish_date"], paper["day_sequence"], paper["day_total"]) for paper in data["papers"]],
            [("2024-02-13", 1, 1), ("2024-02-12", 1, 2), ("2024-02-12", 2, 2)],
        )

    def test_timeline_date_mode_rejects_bad_date(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "人工智能 (Artificial Intelligence)",
                "date": "2024-02-31",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)

    def test_timeline_unknown_direction_returns_empty_page(self):
        response = self.client.get(
            "/timeline/",
            {
                "direction": "不存在方向",
                "page": 1,
                "page_size": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["direction"], "不存在方向")
        self.assertEqual(data["total_papers"], 0)
        self.assertEqual(data["total_pages"], 0)
        self.assertEqual(data["page"], 1)
        self.assertFalse(data["has_previous"])
        self.assertFalse(data["has_next"])
        self.assertEqual(data["papers"], [])

    def test_timeline_unknown_raw_subject_direction_uses_subject_fallback(self):
        raw_subject_paper = Paper.objects.create(
            title="新分类论文",
            abstract="摘要5",
            publish_date=date(2024, 4, 20),
            author_names="孙七",
            subjects="custom.NEW",
        )

        response = self.client.get(
            "/timeline/",
            {
                "direction": "custom.NEW",
                "page": 1,
                "page_size": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_papers"], 1)
        self.assertEqual(data["papers"][0]["id"], raw_subject_paper.id)
        self.assertEqual(data["papers"][0]["subjects"], "custom.NEW")


class ThuCrawlerUtilityTest(TestCase):
    """测试清华导师爬虫的纯解析与姓名匹配逻辑"""

    def test_get_english_name_formats_two_character_chinese_name(self):
        self.assertEqual(get_english_name("唐杰"), "Jie Tang")

    def test_get_english_name_formats_three_character_chinese_name(self):
        self.assertEqual(get_english_name("黄振春"), "Zhenchun Huang")

    def test_get_english_name_returns_empty_for_blank_input(self):
        self.assertEqual(get_english_name("   "), "")

    def test_build_given_name_surname_pinyin_formats_lookup_name(self):
        self.assertEqual(build_given_name_surname_pinyin("唐杰"), "jie-tang")

    def test_build_given_name_surname_pinyin_returns_empty_for_blank_input(self):
        self.assertEqual(build_given_name_surname_pinyin("   "), "")

    def test_normalize_name_handles_case_commas_and_hyphens(self):
        self.assertEqual(_normalize_name("  Tang,   Jie "), "tang jie")
        self.assertEqual(_normalize_name("Jie-Tang"), "jie tang")

    def test_english_name_variants_include_reversed_two_part_name(self):
        self.assertEqual(
            _english_name_variants("Jie Tang"),
            {"jie tang", "tang jie", "tang, jie"},
        )

    def test_english_name_variants_keep_multi_part_name_without_reversal(self):
        self.assertEqual(_english_name_variants("John Ronald Reuel"), {"john ronald reuel"})

    def test_english_name_variants_return_empty_set_for_blank_input(self):
        self.assertEqual(_english_name_variants("   "), set())

    def test_author_matching_normalizes_and_matches_exact_name_only(self):
        self.assertEqual(normalize_english_name("  Chen,   Yu "), "chen yu")
        self.assertEqual(english_name_variants("Yu Chen"), {"yu chen", "chen yu"})
        self.assertTrue(is_exact_english_author_match("Chen, Yu", "Yu Chen"))
        self.assertFalse(is_exact_english_author_match("Wei Yu Chen", "Yu Chen"))
        self.assertTrue(has_exact_english_author_match(["Wei Li", "Chen, Yu"], "Yu Chen"))
        self.assertFalse(has_exact_english_author_match(["Wei Yu Chen"], "Yu Chen"))

    @patch("dataset.services.thu_crawler.fetch_html")
    def test_parse_mentor_detail_extracts_research_email_and_profile(self, mock_fetch_html):
        mock_fetch_html.return_value = """
        <html>
          <head><title>唐杰-清华大学计算机系</title></head>
          <body>
            <p>邮箱：jie@example.com</p>
            <p>研究领域</p>
            <p>知识图谱</p>
            <p>数据挖掘</p>
            <p><strong>研究概况</strong></p>
            <p>教育背景</p>
            <p>博士毕业于测试大学</p>
            <p><strong>学术成果</strong></p>
          </body>
        </html>
        """

        mentor = parse_mentor_detail("https://example.com/tangjie.htm")

        self.assertEqual(mentor["Chinese_name"], "唐杰")
        self.assertEqual(mentor["English_name"], "Jie Tang")
        self.assertEqual(mentor["email"], "jie@example.com")
        self.assertEqual(mentor["research_direction"], "知识图谱\n数据挖掘")
        self.assertIn("教育背景", mentor["profile"])
        self.assertIn("博士毕业于测试大学", mentor["profile"])

    @patch("dataset.services.thu_crawler.fetch_html")
    def test_parse_mentor_detail_handles_missing_optional_sections(self, mock_fetch_html):
        mock_fetch_html.return_value = """
        <html>
          <head><title>李四-清华大学计算机系</title></head>
          <body><p>个人主页</p></body>
        </html>
        """

        mentor = parse_mentor_detail("https://example.com/lisi.htm")

        self.assertEqual(mentor["Chinese_name"], "李四")
        self.assertEqual(mentor["English_name"], "Si Li")
        self.assertEqual(mentor["email"], None)
        self.assertEqual(mentor["research_direction"], "")

    @patch("dataset.services.thu_crawler.fetch_html")
    def test_parse_mentor_detail_returns_unprovided_email_when_label_has_no_address(self, mock_fetch_html):
        mock_fetch_html.return_value = """
        <html>
          <head><title>王五-清华大学计算机系</title></head>
          <body><p>邮箱：暂无</p></body>
        </html>
        """

        mentor = parse_mentor_detail("https://example.com/wangwu.htm")

        self.assertEqual(mentor["email"], "未提供")

    @patch("dataset.services.thu_crawler.parse_mentor_detail")
    @patch("dataset.services.thu_crawler.fetch_html")
    def test_parse_mentor_list_uses_each_h2_anchor_detail_page(self, mock_fetch_html, mock_parse_detail):
        mock_fetch_html.return_value = """
        <html><body>
          <h2><a href="a.htm">A</a></h2>
          <h2><a href="/teacher/b.htm">B</a></h2>
        </body></html>
        """
        mock_parse_detail.side_effect = [
            {"Chinese_name": "导师A"},
            {"Chinese_name": "导师B"},
        ]

        mentors = parse_mentor_list("https://www.cs.tsinghua.edu.cn/szzk/jzgml.htm")

        self.assertEqual(mentors, [{"Chinese_name": "导师A"}, {"Chinese_name": "导师B"}])
        self.assertEqual(mock_parse_detail.call_count, 2)
        self.assertTrue(mock_parse_detail.call_args_list[0].args[0].endswith("/szzk/a.htm"))
        self.assertTrue(mock_parse_detail.call_args_list[1].args[0].endswith("/teacher/b.htm"))

    @patch("dataset.services.thu_crawler.parse_mentor_detail")
    @patch("dataset.services.thu_crawler.fetch_html")
    def test_crawl_mentor_by_name_matches_chinese_name(self, mock_fetch_html, mock_parse_detail):
        mock_fetch_html.return_value = """
        <html><body>
          <h2><a href="mentor-a.htm">导师A</a></h2>
          <h2><a href="mentor-b.htm">导师B</a></h2>
        </body></html>
        """
        mock_parse_detail.side_effect = [
            {"Chinese_name": "张三", "English_name": "San Zhang"},
            {"Chinese_name": "李四", "English_name": "Si Li"},
        ]

        mentor = crawl_mentor_by_name(chinese_name="李四")

        self.assertEqual(mentor["Chinese_name"], "李四")
        self.assertEqual(mock_parse_detail.call_count, 2)

    @patch("dataset.services.thu_crawler.parse_mentor_detail")
    @patch("dataset.services.thu_crawler.fetch_html")
    def test_crawl_mentor_by_name_matches_reversed_english_name(self, mock_fetch_html, mock_parse_detail):
        mock_fetch_html.return_value = """
        <html><body>
          <h2><a href="mentor-a.htm">导师A</a></h2>
        </body></html>
        """
        mock_parse_detail.return_value = {"Chinese_name": "唐杰", "English_name": "Jie Tang"}

        mentor = crawl_mentor_by_name(english_name="Tang Jie")

        self.assertEqual(mentor["Chinese_name"], "唐杰")

    @patch("dataset.services.thu_crawler.parse_mentor_detail")
    @patch("dataset.services.thu_crawler.fetch_html")
    def test_crawl_mentor_by_name_skips_items_without_anchor(self, mock_fetch_html, mock_parse_detail):
        mock_fetch_html.return_value = """
        <html><body>
          <h2>无链接导师</h2>
          <h2><a href="mentor-a.htm">导师A</a></h2>
        </body></html>
        """
        mock_parse_detail.return_value = {"Chinese_name": "王五", "English_name": "Wu Wang"}

        mentor = crawl_mentor_by_name(chinese_name="王五")

        self.assertEqual(mentor["Chinese_name"], "王五")
        mock_parse_detail.assert_called_once()

    @patch("dataset.services.thu_crawler.fetch_html")
    def test_crawl_mentor_by_name_returns_none_for_blank_lookup(self, mock_fetch_html):
        self.assertIsNone(crawl_mentor_by_name(chinese_name=" ", english_name=" "))
        mock_fetch_html.assert_not_called()

    @patch("dataset.services.thu_crawler.parse_mentor_detail")
    @patch("dataset.services.thu_crawler.fetch_html")
    def test_crawl_mentor_by_name_returns_none_when_no_match(self, mock_fetch_html, mock_parse_detail):
        mock_fetch_html.return_value = """
        <html><body>
          <h2><a href="mentor-a.htm">导师A</a></h2>
        </body></html>
        """
        mock_parse_detail.return_value = {"Chinese_name": "张三", "English_name": "San Zhang"}

        self.assertIsNone(crawl_mentor_by_name(chinese_name="不存在"))


class DatasetViewBoundaryTest(TestCase):
    """补充 dataset 接口仍未覆盖的参数与可见性边界"""

    def setUp(self):
        self.client = Client()
        self.admin_user = AccountUser.objects.create_user(
            username="boundary_admin",
            email="boundary-admin@example.com",
            password="admin12345",
            role="admin",
        )
        self.admin_token = generate_jwt_token("boundary_admin")
        self.student = AccountUser.objects.create_user(
            username="boundary_student",
            email="boundary-student@example.com",
            password="student12345",
            role="student",
        )
        self.student_token = generate_jwt_token("boundary_student")
        self.mentor = Mentor.objects.create(
            Chinese_name="边界导师",
            English_name="Boundary Mentor",
            research_direction="人工智能",
            email="boundary@example.com",
        )

    def test_create_mentor_rejects_english_name_that_is_too_long(self):
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "长英文导师",
                "English_name": "x" * 101,
                "research_direction": "机器学习",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid parameters. [English_name] is too long")

    def test_create_mentor_rejects_research_direction_that_is_too_long(self):
        response = self.client.post(
            "/dataset/mentors",
            data=json.dumps({
                "Chinese_name": "长方向导师",
                "English_name": "Long Direction",
                "research_direction": "x" * 256,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        self.assertEqual(response.json()["info"], "Invalid parameters. [research_direction] is too long")

    def test_get_mentor_detail_returns_404_for_missing_mentor(self):
        response = self.client.get("/dataset/mentors/999999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 2)
        self.assertEqual(response.json()["info"], "Mentor not found")

    def test_update_public_mentor_refreshes_bound_papers(self):
        old_paper = Paper.objects.create(title="旧导师论文", author_names="边界导师")
        new_paper = Paper.objects.create(title="新导师论文", author_names="新边界导师")
        self.mentor.add_paper(old_paper.id)

        response = self.client.put(
            f"/dataset/mentors/{self.mentor.id}",
            data=json.dumps({
                "Chinese_name": "新边界导师",
                "English_name": "New Boundary Mentor",
                "research_direction": "可信人工智能",
                "email": "new-boundary@example.com",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.mentor.refresh_from_db()
        self.assertEqual(self.mentor.research_direction, "可信人工智能")
        self.assertEqual(self.mentor.get_paper_id_list(), [new_paper.id])

    def test_create_custom_mentor_english_only_uses_english_as_chinese_name(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({"English_name": "John Smith"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.student_token}",
        )

        self.assertEqual(response.status_code, 200)
        mentor = Mentor.objects.get(owner=self.student, Chinese_name="John Smith")
        self.assertEqual(mentor.English_name, "John Smith")
        self.assertEqual(mentor.research_direction, "待补充")

    def test_create_custom_mentor_uses_submitted_english_name_directly(self):
        response = self.client.post(
            "/dataset/mentors/custom",
            data=json.dumps({"Chinese_name": "补全导师", "English_name": "Fallback Name"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.student_token}",
        )

        self.assertEqual(response.status_code, 200)
        mentor = Mentor.objects.get(owner=self.student, Chinese_name="补全导师")
        self.assertEqual(mentor.English_name, "Fallback Name")
        self.assertEqual(mentor.research_direction, "待补充")

    def test_owner_update_private_mentor_rejects_invalid_email(self):
        private_mentor = Mentor.objects.create(
            Chinese_name="私有边界导师",
            English_name="Private Boundary",
            research_direction="数据库",
            owner=self.student,
        )

        response = self.client.put(
            f"/dataset/mentors/{private_mentor.id}",
            data=json.dumps({
                "Chinese_name": "私有边界导师",
                "English_name": "Private Boundary",
                "research_direction": "数据库",
                "email": "not-an-email",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.student_token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], -2)
        private_mentor.refresh_from_db()
        self.assertIsNone(private_mentor.email)

    def test_delete_public_mentor_requires_admin_even_for_student(self):
        response = self.client.delete(
            f"/dataset/mentors/{self.mentor.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.student_token}",
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Mentor.objects.filter(id=self.mentor.id).exists())


class PersonalizedWeeklyPushViewTest(TestCase):
    """测试首页专属周报接口"""

    def setUp(self):
        self.client = Client()
        self.user = AccountUser.objects.create_user(
            username="personalized_user",
            email="personalized@example.com",
            password="student12345",
            role="student",
        )
        self.token = generate_jwt_token("personalized_user")
        self.other_user = AccountUser.objects.create_user(
            username="other_personalized_user",
            email="other-personalized@example.com",
            password="student12345",
            role="student",
        )

        self.followed_mentor = Mentor.objects.create(
            Chinese_name="关注导师",
            English_name="Followed Mentor",
            research_direction="机器学习",
        )
        self.private_mentor = Mentor.objects.create(
            Chinese_name="私有导师",
            English_name="Private Mentor",
            research_direction="自然语言处理",
            owner=self.user,
        )
        self.unrelated_mentor = Mentor.objects.create(
            Chinese_name="无关导师",
            English_name="Other Mentor",
            research_direction="数据库",
            owner=self.other_user,
        )
        MentorFollow.objects.create(student=self.user, mentor=self.followed_mentor)

        week_start, week_end = resolve_week_range(0, today=timezone.localdate())
        self.followed_paper = Paper.objects.create(
            title="关注导师本周论文",
            abstract="关注导师的论文摘要",
            publish_date=week_end,
            author_names="关注导师, Alice",
            subjects="cs.LG",
            arxiv_id="2605.00001",
        )
        self.private_paper = Paper.objects.create(
            title="私有导师本周论文",
            abstract="私有导师的论文摘要",
            publish_date=week_end - timedelta(days=1),
            author_names="私有导师, Bob",
            subjects="cs.CL",
        )
        self.unrelated_paper = Paper.objects.create(
            title="无关导师本周论文",
            abstract="无关摘要",
            publish_date=week_end - timedelta(days=2),
            author_names="无关导师",
            subjects="cs.DB",
        )
        self.old_followed_paper = Paper.objects.create(
            title="关注导师旧论文",
            abstract="旧论文摘要",
            publish_date=week_start - timedelta(days=1),
            author_names="关注导师, Alice",
            subjects="cs.AI",
        )

        self.followed_mentor.add_paper(self.followed_paper.id)
        self.followed_mentor.add_paper(self.old_followed_paper.id)
        self.private_mentor.add_paper(self.private_paper.id)
        self.unrelated_mentor.add_paper(self.unrelated_paper.id)

    def test_personalized_weekly_push_requires_login(self):
        response = self.client.post("/dataset/weekly-push/personalized")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], 2)

    @patch("dataset.services.weekly_push_summary.build_ai_summary_with_fallback")
    def test_personalized_weekly_push_only_uses_followed_and_private_mentor_weekly_papers(self, mock_ai_summary):
        mock_ai_summary.return_value = ("AI专属周报总结", "thucs-openai")

        response = self.client.post(
            "/dataset/weekly-push/personalized",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["weeklyPush"]
        self.assertEqual(payload["paperCount"], 2)
        self.assertEqual(payload["trackedMentorCount"], 2)
        self.assertEqual(payload["activeMentorCount"], 2)
        self.assertEqual(payload["trackedSubjectCount"], 0)
        self.assertEqual(payload["activeSubjectCount"], 0)
        self.assertEqual(payload["generatedBy"], "thucs-openai")
        self.assertEqual(payload["aiSummary"], "AI专属周报总结")

        returned_titles = [paper["title"] for paper in payload["papers"]]
        self.assertEqual(
            returned_titles,
            ["关注导师本周论文", "私有导师本周论文"],
        )
        self.assertEqual(payload["papers"][0]["mentorNames"], ["关注导师"])
        self.assertEqual(payload["papers"][1]["mentorNames"], ["私有导师"])

        mentor_group_names = [group["mentorName"] for group in payload["mentorGroups"]]
        self.assertEqual(mentor_group_names, ["关注导师", "私有导师"])
        self.assertEqual(
            payload["subjectDistribution"],
            [
                {"subject": "cs.CL", "count": 1},
                {"subject": "cs.LG", "count": 1},
            ],
        )
        self.assertIn("AI专属周报总结", payload["content"])

    @patch("dataset.services.weekly_push_summary.build_ai_summary_with_fallback")
    def test_personalized_weekly_push_includes_followed_subject_weekly_papers(self, mock_ai_summary):
        mock_ai_summary.return_value = ("AI专属周报总结", "thucs-openai")
        SubjectFollow.objects.create(user=self.user, subject="cs.DB")

        response = self.client.post(
            "/dataset/weekly-push/personalized",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["weeklyPush"]
        self.assertEqual(payload["paperCount"], 3)
        self.assertEqual(payload["trackedSubjectCount"], 1)
        self.assertEqual(payload["activeSubjectCount"], 1)

        returned_titles = [paper["title"] for paper in payload["papers"]]
        self.assertEqual(
            returned_titles,
            ["关注导师本周论文", "私有导师本周论文", "无关导师本周论文"],
        )
        self.assertEqual(payload["subjectGroups"][0]["subject"], "cs.DB")
        self.assertEqual(payload["subjectGroups"][0]["papers"][0]["title"], "无关导师本周论文")
        self.assertEqual(
            payload["subjectDistribution"],
            [
                {"subject": "cs.CL", "count": 1},
                {"subject": "cs.DB", "count": 1},
                {"subject": "cs.LG", "count": 1},
            ],
        )


class MentorRecentDirectionAnalysisViewTest(TestCase):
    """测试导师最近研究方向分析接口"""

    def setUp(self):
        self.client = Client()
        self.mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能",
            profile="测试导师",
        )
        self.recent_paper = Paper.objects.create(
            title="Recent Paper",
            abstract="This work studies agents and reasoning.",
            publish_date=timezone.localdate() - timedelta(days=30),
            author_names="张三",
        )
        self.old_paper = Paper.objects.create(
            title="Old Paper",
            abstract="This paper is old.",
            publish_date=timezone.localdate() - timedelta(days=500),
            author_names="张三",
        )
        self.mentor.set_paper_id_list([self.recent_paper.id, self.old_paper.id])
        self.mentor.save()

    @patch("dataset.views.build_ai_recent_direction_analysis")
    def test_recent_direction_analysis_uses_recent_papers_only(self, mock_ai_analysis):
        mock_ai_analysis.return_value = "导师近一年主要关注智能体与推理。"

        response = self.client.post(f"/dataset/mentors/{self.mentor.id}/recent-direction-analysis")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["paperCount"], 1)
        self.assertEqual(payload["generatedBy"], "thucs-openai")
        self.assertEqual(payload["analysis"], "导师近一年主要关注智能体与推理。")
        self.assertEqual(len(payload["papers"]), 1)
        self.assertEqual(payload["papers"][0]["title"], "Recent Paper")


class UtilsRequestAndTimeTest(TestCase):
    """覆盖 utils/utils_request.py 与 utils/utils_time.py 中尚未测试的函数"""

    def test_return_field_returns_only_listed_keys(self):
        source = {"a": 1, "b": 2, "c": 3}

        self.assertEqual(return_field(source, ["a", "c"]), {"a": 1, "c": 3})

    def test_return_field_returns_empty_dict_for_empty_field_list(self):
        self.assertEqual(return_field({"a": 1}, []), {})

    def test_return_field_raises_when_field_is_missing(self):
        with self.assertRaises(AssertionError):
            return_field({"a": 1}, ["a", "missing"])

    def test_get_timestamp_returns_positive_float(self):
        ts = get_timestamp()

        self.assertIsInstance(ts, float)
        self.assertGreater(ts, 0)


class WeeklyPushSummaryPureFunctionTest(TestCase):
    """覆盖 dataset/services/weekly_push_summary.py 中的纯函数"""

    def setUp(self):
        self.week_start = date(2026, 4, 13)
        self.week_end = date(2026, 4, 19)
        self.paper_a = Paper.objects.create(
            title="周报论文A",
            abstract="abstract A",
            publish_date=date(2026, 4, 18),
            author_names="Author A",
            subjects="cs.AI, cs.LG",
            arxiv_id="2604.00001",
            arxiv_url="https://arxiv.org/abs/2604.00001",
            tldr="TLDR A",
        )
        self.paper_b = Paper.objects.create(
            title="周报论文B",
            abstract="abstract B",
            publish_date=date(2026, 4, 14),
            author_names="Author B",
            subjects="",
            arxiv_id="2604.00002",
        )
        self.paper_no_date = Paper.objects.create(
            title="无日期论文",
            abstract="abstract C",
            publish_date=None,
            author_names="Author C",
            subjects="cs.CL",
        )

    def test_build_fixed_summary_returns_empty_message_without_papers(self):
        summary = build_fixed_summary(self.week_start, self.week_end, [])

        self.assertEqual(summary, "2026-04-13 到 2026-04-19 无新增论文。")

    def test_build_fixed_summary_aggregates_subjects_and_dates(self):
        summary = build_fixed_summary(
            self.week_start,
            self.week_end,
            [self.paper_a, self.paper_b],
        )

        self.assertIn("共收录 2 篇论文", summary)
        self.assertIn("2026-04-14 至 2026-04-18", summary)
        self.assertIn("cs.AI(1)", summary)
        self.assertIn("cs.LG(1)", summary)
        self.assertIn("其他/未分类(1)", summary)

    def test_build_fixed_summary_marks_unknown_dates_when_publish_date_missing(self):
        summary = build_fixed_summary(
            self.week_start,
            self.week_end,
            [self.paper_no_date],
        )

        self.assertIn("未知 至 未知", summary)
        self.assertIn("cs.CL(1)", summary)

    def test_compose_weekly_push_content_collapses_duplicate_summary(self):
        self.assertEqual(compose_weekly_push_content("fixed", "fixed"), "fixed")

    def test_compose_weekly_push_content_appends_ai_summary_section(self):
        composed = compose_weekly_push_content("fixed", "ai-summary")

        self.assertIn("【AI总结】", composed)
        self.assertTrue(composed.startswith("fixed"))
        self.assertTrue(composed.endswith("ai-summary"))

    def test_serialize_weekly_push_paper_resolves_arxiv_url_from_id(self):
        paper = Paper.objects.create(
            title="仅有 arXiv id",
            abstract="abstract",
            publish_date=date(2026, 4, 20),
            author_names="Author X",
            subjects="cs.AI",
            arxiv_id="2604.99999",
            arxiv_url="",
            tldr="tldr",
        )

        item = serialize_weekly_push_paper(paper)

        self.assertEqual(item["arxivUrl"], "https://arxiv.org/abs/2604.99999")
        self.assertEqual(item["arxivId"], "2604.99999")
        self.assertNotIn("mentorNames", item)
        self.assertEqual(item["publishDate"], "2026-04-20")

    def test_serialize_weekly_push_paper_keeps_existing_url_and_attaches_mentor_names(self):
        item = serialize_weekly_push_paper(self.paper_a, mentor_names=["张三", "李四"])

        self.assertEqual(item["arxivUrl"], "https://arxiv.org/abs/2604.00001")
        self.assertEqual(item["mentorNames"], ["张三", "李四"])
        self.assertEqual(item["tldr"], "TLDR A")

    def test_serialize_weekly_push_paper_handles_null_publish_date(self):
        item = serialize_weekly_push_paper(self.paper_no_date)

        self.assertIsNone(item["publishDate"])
        self.assertIsNone(item["arxivUrl"])

    def test_resolve_week_range_returns_previous_full_week_by_default(self):
        start, end = resolve_week_range(0, today=date(2026, 4, 22))

        self.assertEqual(start, date(2026, 4, 13))
        self.assertEqual(end, date(2026, 4, 19))

    def test_resolve_week_range_supports_positive_offsets(self):
        start, end = resolve_week_range(1, today=date(2026, 4, 22))

        self.assertEqual(start, date(2026, 4, 6))
        self.assertEqual(end, date(2026, 4, 12))


class WeeklyPushPublicViewTest(TestCase):
    """覆盖 /dataset/weekly-push/latest 与 /dataset/weekly-push/history 公共视图"""

    def setUp(self):
        from dataset.models import WeeklyPaperPush

        self.client = Client()
        self.older = WeeklyPaperPush.objects.create(
            week_start=date(2026, 4, 6),
            week_end=date(2026, 4, 12),
            paper_count=2,
            title="较早周报",
            fixed_summary="fixed-old",
            ai_summary="ai-old",
            content="content-old",
            papers=[{"id": 1, "title": "p1"}],
            generated_by="rule",
        )
        self.newer = WeeklyPaperPush.objects.create(
            week_start=date(2026, 4, 13),
            week_end=date(2026, 4, 19),
            paper_count=5,
            title="最新周报",
            fixed_summary="fixed-new",
            ai_summary="ai-new",
            content="content-new",
            papers=[{"id": 2, "title": "p2"}],
            generated_by="thucs-openai",
        )

    def test_weekly_push_latest_returns_most_recent_push(self):
        response = self.client.get("/dataset/weekly-push/latest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["weeklyPush"]
        self.assertEqual(payload["title"], "最新周报")
        self.assertEqual(payload["paperCount"], 5)
        self.assertEqual(payload["weekStart"], "2026-04-13")

    def test_weekly_push_latest_filters_by_week_start(self):
        response = self.client.get(
            "/dataset/weekly-push/latest",
            {"week_start": "2026-04-06"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["weeklyPush"]
        self.assertEqual(payload["title"], "较早周报")

    def test_weekly_push_latest_returns_404_for_unknown_week_start(self):
        response = self.client.get(
            "/dataset/weekly-push/latest",
            {"week_start": "1990-01-01"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 2)

    def test_weekly_push_latest_returns_null_when_no_push_exists(self):
        from dataset.models import WeeklyPaperPush

        WeeklyPaperPush.objects.all().delete()

        response = self.client.get("/dataset/weekly-push/latest")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["weeklyPush"])

    def test_weekly_push_latest_rejects_bad_method(self):
        response = self.client.post("/dataset/weekly-push/latest")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)

    def test_weekly_push_history_returns_pushes_in_reverse_order(self):
        response = self.client.get("/dataset/weekly-push/history")

        self.assertEqual(response.status_code, 200)
        history = response.json()["history"]
        self.assertEqual([item["title"] for item in history], ["最新周报", "较早周报"])
        self.assertEqual(history[0]["paperCount"], 5)
        self.assertEqual(history[0]["generatedBy"], "thucs-openai")
        self.assertIn("updatedAt", history[0])

    def test_weekly_push_history_rejects_bad_method(self):
        response = self.client.post("/dataset/weekly-push/history")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], -3)

    def test_weekly_paper_push_serialize_returns_full_payload(self):
        serialized = self.newer.serialize()

        self.assertEqual(
            set(serialized.keys()),
            {
                "id",
                "weekStart",
                "weekEnd",
                "paperCount",
                "title",
                "fixedSummary",
                "aiSummary",
                "content",
                "papers",
                "generatedBy",
                "updatedAt",
            },
        )
        self.assertEqual(serialized["weekStart"], "2026-04-13")
        self.assertEqual(serialized["papers"], [{"id": 2, "title": "p2"}])


class RuleBasedResearchAnalysisTest(TestCase):
    """覆盖 dataset/services/research_analysis.py"""

    def setUp(self):
        self.mentor = Mentor.objects.create(
            Chinese_name="张三",
            English_name="San Zhang",
            research_direction="人工智能",
        )
        self.cutoff = date(2026, 4, 1)
        self.today = date(2026, 4, 30)

    def test_rule_based_analysis_handles_empty_papers(self):
        from dataset.services.research_analysis import (
            build_rule_based_recent_direction_analysis,
        )

        analysis = build_rule_based_recent_direction_analysis(
            self.mentor, [], self.cutoff, self.today
        )

        self.assertIn("张三", analysis)
        self.assertIn("2026-04-01", analysis)
        self.assertIn("2026-04-30", analysis)
        self.assertIn("暂无", analysis)

    def test_rule_based_analysis_uses_top_subjects_and_keywords(self):
        from dataset.services.research_analysis import (
            build_rule_based_recent_direction_analysis,
        )

        papers = [
            Paper.objects.create(
                title="LLM Agents for Reasoning",
                abstract="We study large language model agents and reasoning.",
                publish_date=date(2026, 4, 20),
                author_names="张三",
                subjects="cs.AI, cs.LG",
            ),
            Paper.objects.create(
                title="Multimodal Retrieval Systems",
                abstract="A multimodal retrieval and recommendation system.",
                publish_date=date(2026, 4, 22),
                author_names="张三",
                subjects="cs.LG",
            ),
        ]

        analysis = build_rule_based_recent_direction_analysis(
            self.mentor, papers, self.cutoff, self.today
        )

        self.assertIn("近一年共发表 2 篇", analysis)
        self.assertIn("cs.LG", analysis)
        self.assertIn("retrieval", analysis)

    def test_rule_based_analysis_skips_subject_and_keyword_phrases_when_absent(self):
        from dataset.services.research_analysis import (
            build_rule_based_recent_direction_analysis,
        )

        paper = Paper.objects.create(
            title="一篇平淡的论文",
            abstract="本论文无关键词",
            publish_date=date(2026, 4, 10),
            author_names="张三",
            subjects="",
            tldr="无 TLDR",
        )

        analysis = build_rule_based_recent_direction_analysis(
            self.mentor, [paper], self.cutoff, self.today
        )

        self.assertIn("近一年共发表 1 篇", analysis)
        self.assertNotIn("从论文分类看", analysis)
        self.assertNotIn("从题目与摘要关键词看", analysis)

    @patch("dataset.services.research_analysis.call_thucs_chat_completion")
    def test_build_ai_recent_direction_analysis_passes_prompt_to_thucs(self, mock_call):
        from dataset.services.research_analysis import (
            build_ai_recent_direction_analysis,
        )

        mock_call.return_value = "AI生成的导师近期方向总结"
        paper = Paper.objects.create(
            title="A Paper About LLM",
            abstract="abstract about LLM",
            publish_date=date(2026, 4, 20),
            author_names="张三",
            subjects="cs.AI",
            tldr="LLM tldr",
        )

        result = build_ai_recent_direction_analysis(
            self.mentor, [paper], self.cutoff, self.today
        )

        self.assertEqual(result, "AI生成的导师近期方向总结")
        mock_call.assert_called_once()
        kwargs = mock_call.call_args.kwargs
        self.assertIn("A Paper About LLM", kwargs["user_prompt"])
        self.assertIn("2026-04-01", kwargs["user_prompt"])

    @patch("dataset.services.research_analysis.requests.post")
    def test_call_thucs_chat_completion_raises_when_api_key_missing(self, mock_post):
        from dataset.services.research_analysis import call_thucs_chat_completion

        with self.settings(THUCS_API_KEY=""):
            with self.assertRaises(RuntimeError):
                call_thucs_chat_completion(system_prompt="sys", user_prompt="user")
        mock_post.assert_not_called()

    @patch("dataset.services.research_analysis.requests.post")
    def test_call_thucs_chat_completion_returns_stripped_content(self, mock_post):
        from dataset.services.research_analysis import call_thucs_chat_completion

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "  AI 输出内容  "}}],
        }
        mock_post.return_value = mock_response

        with self.settings(
            THUCS_API_KEY="dummy",
            THUCS_API_BASE_URL="https://api.example.com/",
            THUCS_MODEL_NAME="custom-model",
        ):
            text = call_thucs_chat_completion(
                system_prompt="sys", user_prompt="user", temperature=0.1, timeout=5,
            )

        self.assertEqual(text, "AI 输出内容")
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["timeout"], 5)
        self.assertEqual(call_kwargs["json"]["model"], "custom-model")
        self.assertEqual(call_kwargs["json"]["temperature"], 0.1)

    @patch("dataset.services.research_analysis.requests.post")
    def test_call_thucs_chat_completion_raises_when_content_empty(self, mock_post):
        from dataset.services.research_analysis import call_thucs_chat_completion

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"choices": [{"message": {"content": "   "}}]}
        mock_post.return_value = mock_response

        with self.settings(THUCS_API_KEY="dummy"):
            with self.assertRaises(RuntimeError):
                call_thucs_chat_completion(system_prompt="sys", user_prompt="user")
