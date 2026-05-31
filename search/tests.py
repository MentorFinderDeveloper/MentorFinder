from django.test import TestCase

from account.models import User
from dataset.models import Mentor, Paper
from search.services.engine import _split_keyword_logic, search_papers_fuzzy
from utils.utils_jwt import generate_jwt_token


class SearchTests(TestCase):
    # 初始化搜索测试所需的用户、导师、论文和鉴权令牌数据。
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner1",
            email="owner1@example.com",
            password="abc12345",
            role="student",
        )
        self.owner_token = generate_jwt_token("owner1")

        self.other_user = User.objects.create_user(
            username="other1",
            email="other1@example.com",
            password="abc12345",
            role="student",
        )
        self.other_token = generate_jwt_token("other1")

        self.banned_user = User.objects.create_user(
            username="banned1",
            email="banned1@example.com",
            password="abc12345",
            role=User.ROLE_BANNED,
        )
        self.banned_token = generate_jwt_token("banned1")

        self.admin = User.objects.create_user(
            username="admin1",
            email="admin1@example.com",
            password="abc12345",
            role="admin",
        )
        self.admin_token = generate_jwt_token("admin1")

        self.zs = Mentor.objects.create(
            Chinese_name="张三",
            English_name="Zhang San",
            research_direction="机器学习",
            email="zhangsan@example.com",
            profile="主要研究机器学习与数据挖掘。",
        )
        self.ls = Mentor.objects.create(
            Chinese_name="李四",
            English_name="Li Si",
            research_direction="自然语言处理",
            email="lisi@example.com",
            profile="主要研究自然语言处理与大模型应用。",
        )

        self.paper1 = Paper.objects.create(
            title="机器学习方法研究",
            abstract="本文讨论常见机器学习方法及其应用场景。",
            publish_date="2024-05-01",
            author_names="张三",
            subjects="cs.LG, cs.AI",
        )
        self.paper2 = Paper.objects.create(
            title="大语言模型在问答系统中的应用",
            abstract="本文介绍大语言模型在智能问答中的实践。",
            publish_date="2024-06-15",
            author_names="李四,张三",
            subjects="cs.CL",
        )

        self.private_paper = Paper.objects.create(
            title="隐私导师论文",
            abstract="仅用于测试私有导师检索可见性。",
            publish_date="2024-07-01",
            author_names="王五",
            subjects="cs.CR",
        )

        self.private_mentor = Mentor.objects.create(
            Chinese_name="王五",
            English_name="Wang Wu",
            research_direction="强化学习",
            email="wangwu@example.com",
            profile="私有导师",
            owner=self.owner,
        )

        self.zs.add_paper(self.paper1.id)
        self.zs.add_paper(self.paper2.id)
        self.ls.add_paper(self.paper2.id)
        self.private_mentor.add_paper(self.private_paper.id)

    # 生成带 Bearer 前缀的认证请求头。
    def auth_headers(self, token: str):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    # 验证健康检查接口返回搜索模块状态。
    def test_search_health(self):
        res = self.client.get("/search/health")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["module"], "search")

    # 验证健康检查接口会拒绝错误的请求方法。
    def test_search_health_bad_method(self):
        res = self.client.post("/search/health")

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    # 验证导师搜索可按中文姓名精确匹配。
    def test_search_mentors_by_name(self):
        res = self.client.get("/search/mentors", {"keyword": "张三"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "张三")
        self.assertEqual(len(res.json()["mentors"]), 1)

        mentor = res.json()["mentors"][0]
        self.assertEqual(
            set(mentor.keys()),
            {"id", "Chinese_name", "English_name", "research_direction", "email", "profile", "paperTitles", "is_private"},
        )
        self.assertEqual(mentor["Chinese_name"], "张三")
        self.assertEqual(mentor["English_name"], "Zhang San")
        self.assertEqual(mentor["research_direction"], "机器学习")
        self.assertEqual(mentor["paperTitles"], ["机器学习方法研究", "大语言模型在问答系统中的应用"])
        self.assertEqual(mentor["is_private"], False)

    # 验证导师搜索可按研究方向精确匹配。
    def test_search_mentors_by_research_direction(self):
        res = self.client.get("/search/mentors", {"keyword": "机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    # 验证导师搜索支持英文名精确匹配。
    def test_search_mentors_by_english_name(self):
        res = self.client.get("/search/mentors", {"keyword": "Zhang San"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    # 验证导师搜索对英文名匹配不区分大小写。
    def test_search_mentors_by_english_name_case_insensitive(self):
        res = self.client.get("/search/mentors", {"keyword": "zhang san"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    # 验证导师搜索支持英文名顺序和逗号变体的精确匹配。
    def test_search_mentors_by_english_name_variants_exact(self):
        for keyword in ["San Zhang", "San, Zhang"]:
            with self.subTest(keyword=keyword):
                res = self.client.get("/search/mentors", {"keyword": keyword})

                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["code"], 0)
                self.assertEqual(len(res.json()["mentors"]), 1)
                self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    # 验证导师搜索支持且逻辑组合查询。
    def test_search_mentors_supports_and_logic(self):
        res = self.client.get("/search/mentors", {"keyword": "张三 且 机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([mentor["Chinese_name"] for mentor in res.json()["mentors"]], ["张三"])

    # 验证导师搜索支持或逻辑组合查询。
    def test_search_mentors_supports_or_logic(self):
        res = self.client.get("/search/mentors", {"keyword": "张三 或 李四"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(
            {mentor["Chinese_name"] for mentor in res.json()["mentors"]},
            {"张三", "李四"},
        )

    # 验证导师搜索支持括号优先级逻辑。
    def test_search_mentors_supports_parentheses_precedence(self):
        res = self.client.get("/search/mentors", {"keyword": "(张三 或 李四) 且 自然语言处理"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([mentor["Chinese_name"] for mentor in res.json()["mentors"]], ["李四"])

    # 验证逻辑关键词拆分支持符号形式的或运算符。
    def test_split_keyword_logic_supports_pipe_operators(self):
        self.assertEqual(_split_keyword_logic("张三 | 李四"), [["张三"], ["李四"]])
        self.assertEqual(_split_keyword_logic("张三 || 李四"), [["张三"], ["李四"]])

    # 验证逻辑关键词拆分支持符号形式的且运算符。
    def test_split_keyword_logic_supports_ampersand_operators(self):
        self.assertEqual(_split_keyword_logic("张三 & 机器学习"), [["张三", "机器学习"]])
        self.assertEqual(_split_keyword_logic("张三 && 机器学习"), [["张三", "机器学习"]])

    # 验证逻辑关键词拆分会忽略多余连续运算符和空白。
    def test_split_keyword_logic_ignores_redundant_symbol_operators(self):
        self.assertEqual(_split_keyword_logic("张三 ||| 李四"), [["张三"], ["李四"]])
        self.assertEqual(_split_keyword_logic("张三 &&&& 机器学习"), [["张三", "机器学习"]])

    # 验证论文搜索可按标题精确匹配。
    def test_search_papers_by_exact_title(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习方法研究"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "机器学习方法研究")
        self.assertEqual(len(res.json()["papers"]), 1)

        paper = res.json()["papers"][0]
        self.assertEqual(
            set(paper.keys()),
            {"id", "title", "abstract", "publish_date", "author_names", "subjects", "arxiv_id", "arxiv_url", "mentorNames", "mentor_ids"},
        )
        self.assertEqual(paper["title"], "机器学习方法研究")
        self.assertEqual(paper["subjects"], "cs.LG, cs.AI")
        self.assertEqual(paper["mentorNames"], ["张三"])
        self.assertEqual(paper["mentor_ids"], [self.zs.id])
        self.assertEqual(paper["author_names"], "张三")

    # 验证论文搜索可匹配逗号分隔的 subjects 词项。
    def test_search_papers_by_subject_token_in_comma_separated_subjects(self):
        res = self.client.get("/search/papers", {"keyword": "cs.AI"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["机器学习方法研究"])

    # 验证论文搜索可通过导师研究方向命中关联论文。
    def test_search_papers_by_mentor_research_direction(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(
            {paper["title"] for paper in res.json()["papers"]},
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

    # 验证论文搜索可通过导师中文名命中关联论文。
    def test_search_papers_by_mentor_name(self):
        res = self.client.get("/search/papers", {"keyword": "李四"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    # 验证论文搜索可通过导师英文名命中关联论文。
    def test_search_papers_by_mentor_english_name(self):
        res = self.client.get("/search/papers", {"keyword": "Li Si"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    # 验证论文搜索支持导师英文名变体的精确匹配。
    def test_search_papers_by_mentor_english_name_variants_exact(self):
        for keyword in ["Si Li", "Si, Li"]:
            with self.subTest(keyword=keyword):
                res = self.client.get("/search/papers", {"keyword": keyword})

                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["code"], 0)
                self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    # 验证论文搜索支持且逻辑组合查询。
    def test_search_papers_supports_and_logic(self):
        res = self.client.get("/search/papers", {"keyword": "张三 且 cs.AI"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["机器学习方法研究"])

    # 验证论文搜索支持或逻辑组合查询。
    def test_search_papers_supports_or_logic(self):
        res = self.client.get("/search/papers", {"keyword": "cs.AI 或 cs.CL"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(
            {paper["title"] for paper in res.json()["papers"]},
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

    # 验证论文搜索支持括号优先级逻辑。
    def test_search_papers_supports_parentheses_precedence(self):
        res = self.client.get("/search/papers", {"keyword": "(张三 或 李四) 且 cs.AI"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["机器学习方法研究"])

    # 验证异常括号输入会回退到平铺逻辑拆分而不是报错。
    def test_search_logic_falls_back_for_unbalanced_parentheses(self):
        res = self.client.get("/search/mentors", {"keyword": "(张三 或 李四 且 自然语言处理"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([mentor["Chinese_name"] for mentor in res.json()["mentors"]], ["李四"])

    # 验证论文搜索可按作者名命中论文。
    def test_search_papers_by_author_names(self):
        res = self.client.get("/search/papers", {"keyword": "张三"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(
            {paper["title"] for paper in res.json()["papers"]},
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

    # 验证超大作者列表的论文仍能稳定完成搜索序列化。
    def test_search_papers_with_large_author_list(self):
        authors = [f"Author {index}" for index in range(1001)]
        target_mentor = Mentor.objects.create(
            Chinese_name="Author 500",
            English_name="Author 500",
            research_direction="规模化匹配测试",
            email="author500@example.com",
            profile="用于验证搜索序列化不会生成过深的表达式树。",
        )
        large_author_paper = Paper.objects.create(
            title="超大作者列表论文",
            abstract="用于验证搜索结果序列化的稳定性。",
            publish_date="2024-09-01",
            author_names=",".join(authors),
            subjects="cs.DS",
        )

        res = self.client.get("/search/papers", {"keyword": "超大作者列表论文"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["papers"][0]["title"], large_author_paper.title)
        self.assertIn(target_mentor.id, res.json()["papers"][0]["mentor_ids"])

    # 验证论文搜索会去重多来源命中的同一论文。
    def test_search_papers_deduplicate_multi_source_matches(self):
        res = self.client.get("/search/papers", {"keyword": "张三"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)

        paper_titles = [paper["title"] for paper in res.json()["papers"]]
        self.assertEqual(
            set(paper_titles),
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )
        self.assertEqual(len(paper_titles), len(set(paper_titles)))

    # 验证标题精确命中优先于导师匹配结果。
    def test_search_papers_title_match_has_priority_over_mentor_match(self):
        mentor_same_as_title = Mentor.objects.create(
            Chinese_name="机器学习方法研究",
            English_name="Title Name",
            research_direction="知识图谱",
            email="titlementor@example.com",
            profile="用于验证标题优先级。",
        )
        mentor_same_as_title.add_paper(self.paper2.id)

        res = self.client.get("/search/papers", {"keyword": "机器学习方法研究"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["机器学习方法研究"])

    # 验证精确模式下标题不支持模糊子串匹配。
    def test_search_papers_title_does_not_support_fuzzy_match(self):
        res = self.client.get("/search/papers", {"keyword": "语言模型"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["papers"], [])

    # 验证论文模糊搜索支持标题子串匹配。
    def test_search_papers_fuzzy_by_title_substring(self):
        papers = search_papers_fuzzy("语言模型")

        self.assertEqual([paper["title"] for paper in papers], ["大语言模型在问答系统中的应用"])

    # 验证论文模糊搜索支持导师中文名子串匹配。
    def test_search_papers_fuzzy_by_mentor_chinese_name_substring(self):
        papers = search_papers_fuzzy("张")

        self.assertEqual(
            {paper["title"] for paper in papers},
            {"机器学习方法研究", "大语言模型在问答系统中的应用"},
        )

    # 验证论文模糊搜索支持导师英文名子串匹配。
    def test_search_papers_fuzzy_by_mentor_english_name_substring(self):
        papers = search_papers_fuzzy("Li")

        self.assertEqual([paper["title"] for paper in papers], ["大语言模型在问答系统中的应用"])

    # 验证论文模糊搜索支持导师英文名变体匹配。
    def test_search_papers_fuzzy_by_mentor_english_name_variants(self):
        mentor_variant = Mentor.objects.create(
            Chinese_name="薛伟",
            English_name="Wei Xue",
            research_direction="图表示学习",
            email="xuewei@example.com",
            profile="用于验证英文名不同写法的模糊搜索。",
        )
        paper_variant = Paper.objects.create(
            title="英文名变体论文",
            abstract="用于验证英文名不同写法的模糊搜索。",
            publish_date="2024-08-01",
            author_names="Xue Wei",
            subjects="cs.LG",
        )
        paper_variant.bind_to_mentors_by_authors()

        res = self.client.get("/search/mentors", {"keyword": "wei, xue", "search_mode": "fuzzy"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([mentor["Chinese_name"] for mentor in res.json()["mentors"]], ["薛伟"])

        papers = search_papers_fuzzy("wei, xue")

        self.assertEqual([paper["title"] for paper in papers], ["英文名变体论文"])

        paper_res = self.client.get("/search/papers", {"keyword": "英文名变体论文"})

        self.assertEqual(paper_res.status_code, 200)
        self.assertEqual(paper_res.json()["code"], 0)
        self.assertEqual(paper_res.json()["papers"][0]["mentor_ids"], [mentor_variant.id])

    # 验证论文模糊搜索支持导师研究方向子串匹配。
    def test_search_papers_fuzzy_by_research_direction_substring(self):
        papers = search_papers_fuzzy("自然语言")

        self.assertEqual([paper["title"] for paper in papers], ["大语言模型在问答系统中的应用"])

    # 验证论文模糊搜索支持摘要子串匹配。
    def test_search_papers_fuzzy_by_abstract_substring(self):
        papers = search_papers_fuzzy("智能问答")

        self.assertEqual([paper["title"] for paper in papers], ["大语言模型在问答系统中的应用"])

    # 验证论文模糊搜索支持 subjects 子串匹配。
    def test_search_papers_fuzzy_by_subject_substring(self):
        papers = search_papers_fuzzy("cs.AI")

        self.assertEqual([paper["title"] for paper in papers], ["机器学习方法研究"])

    # 验证分词后的模糊短语可跨字段无序匹配。
    def test_search_papers_fuzzy_tokenized_phrase_matches_unordered_fields(self):
        paper = Paper.objects.create(
            title="Retrieval augmented generation survey",
            abstract="This work studies neural retrieval and generation pipelines.",
            publish_date="2024-08-10",
            author_names="Alice Chen",
            subjects="cs.IR, cs.CL",
        )

        papers = search_papers_fuzzy("retrieval generation")

        self.assertIn(paper.title, [item["title"] for item in papers])

    # 验证论文模糊搜索会优先返回更直接的匹配结果。
    def test_search_papers_fuzzy_orders_more_direct_matches_first(self):
        abstract_only = Paper.objects.create(
            title="辅助测试论文",
            abstract="这里在摘要中提到图神经网络。",
            publish_date="2024-08-11",
            author_names="Alice",
            subjects="cs.LG",
        )
        title_match = Paper.objects.create(
            title="图神经网络综述",
            abstract="摘要",
            publish_date="2024-08-10",
            author_names="Bob",
            subjects="cs.LG",
        )

        papers = search_papers_fuzzy("图神经网络")

        titles = [paper["title"] for paper in papers]
        self.assertLess(titles.index(title_match.title), titles.index(abstract_only.title))

    # 验证论文模糊搜索结果会做去重处理。
    def test_search_papers_fuzzy_deduplicates_results(self):
        papers = search_papers_fuzzy("张")

        paper_titles = [paper["title"] for paper in papers]
        self.assertEqual(len(paper_titles), len(set(paper_titles)))

    # 验证论文模糊搜索在无匹配时返回空列表。
    def test_search_papers_fuzzy_no_match_returns_empty_list(self):
        papers = search_papers_fuzzy("量子拓扑星舰")

        self.assertEqual(papers, [])

    # 验证导师接口支持模糊搜索模式。
    def test_search_mentors_api_fuzzy_mode(self):
        res = self.client.get("/search/mentors", {"keyword": "张", "search_mode": "fuzzy"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["search_mode"], "fuzzy")
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "张三")

    # 验证论文接口支持模糊搜索模式。
    def test_search_papers_api_fuzzy_mode(self):
        res = self.client.get("/search/papers", {"keyword": "语言模型", "search_mode": "fuzzy"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["search_mode"], "fuzzy")
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    # 验证论文接口默认返回 default 排序模式。
    def test_search_papers_default_sort_mode(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["sort_mode"], "default")

    # 验证论文接口支持按最早时间排序。
    def test_search_papers_sort_mode_early(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "sort_mode": "early"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["sort_mode"], "early")
        self.assertEqual(
            [paper["title"] for paper in res.json()["papers"]],
            ["机器学习方法研究", "大语言模型在问答系统中的应用"],
        )

    # 验证论文接口支持按最晚时间排序。
    def test_search_papers_sort_mode_late(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "sort_mode": "late"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["sort_mode"], "late")
        self.assertEqual(
            [paper["title"] for paper in res.json()["papers"]],
            ["大语言模型在问答系统中的应用", "机器学习方法研究"],
        )

    # 验证导师搜索接口支持分页能力。
    def test_search_mentors_supports_pagination(self):
        Mentor.objects.create(
            Chinese_name="张六",
            English_name="Zhang Liu",
            research_direction="机器学习工程",
            email="zhangliu@example.com",
            profile="用于分页测试",
        )

        page1 = self.client.get(
            "/search/mentors",
            {
                "keyword": "学习",
                "search_mode": "fuzzy",
                "page": 1,
                "page_size": 1,
            },
        )
        page2 = self.client.get(
            "/search/mentors",
            {
                "keyword": "学习",
                "search_mode": "fuzzy",
                "page": 2,
                "page_size": 1,
            },
        )

        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)

        page1_data = page1.json()
        page2_data = page2.json()

        self.assertEqual(page1_data["total"], 2)
        self.assertEqual(page1_data["total_pages"], 2)
        self.assertEqual(page1_data["page"], 1)
        self.assertTrue(page1_data["has_next"])
        self.assertFalse(page1_data["has_previous"])
        self.assertEqual(len(page1_data["mentors"]), 1)

        self.assertEqual(page2_data["total"], 2)
        self.assertEqual(page2_data["total_pages"], 2)
        self.assertEqual(page2_data["page"], 2)
        self.assertFalse(page2_data["has_next"])
        self.assertTrue(page2_data["has_previous"])
        self.assertEqual(len(page2_data["mentors"]), 1)

    # 验证论文搜索接口支持分页能力。
    def test_search_papers_supports_pagination(self):
        page1 = self.client.get(
            "/search/papers",
            {
                "keyword": "张",
                "search_mode": "fuzzy",
                "sort_mode": "early",
                "page": 1,
                "page_size": 1,
            },
        )
        page2 = self.client.get(
            "/search/papers",
            {
                "keyword": "张",
                "search_mode": "fuzzy",
                "sort_mode": "early",
                "page": 2,
                "page_size": 1,
            },
        )

        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)

        page1_data = page1.json()
        page2_data = page2.json()

        self.assertEqual(page1_data["total"], 2)
        self.assertEqual(page1_data["total_pages"], 2)
        self.assertEqual(page1_data["page"], 1)
        self.assertEqual(page1_data["papers"][0]["title"], "机器学习方法研究")
        self.assertTrue(page1_data["has_next"])
        self.assertFalse(page1_data["has_previous"])

        self.assertEqual(page2_data["total"], 2)
        self.assertEqual(page2_data["total_pages"], 2)
        self.assertEqual(page2_data["page"], 2)
        self.assertEqual(page2_data["papers"][0]["title"], "大语言模型在问答系统中的应用")
        self.assertFalse(page2_data["has_next"])
        self.assertTrue(page2_data["has_previous"])

    # 验证接口会拒绝非法的搜索模式参数。
    def test_search_api_invalid_search_mode(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "search_mode": "partial"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    # 验证接口会拒绝非法的排序模式参数。
    def test_search_api_invalid_sort_mode(self):
        res = self.client.get("/search/papers", {"keyword": "机器学习", "sort_mode": "random"})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    # 验证搜索无匹配时导师和论文接口均返回空列表。
    def test_search_no_match_returns_empty_list(self):
        mentor_res = self.client.get("/search/mentors", {"keyword": "量子拓扑星舰"})
        paper_res = self.client.get("/search/papers", {"keyword": "量子拓扑星舰"})

        self.assertEqual(mentor_res.status_code, 200)
        self.assertEqual(mentor_res.json()["mentors"], [])
        self.assertEqual(paper_res.status_code, 200)
        self.assertEqual(paper_res.json()["papers"], [])

    # 验证匿名用户搜索导师时不会看到私有导师。
    def test_search_mentors_excludes_private_mentor_without_auth(self):
        res = self.client.get("/search/mentors", {"keyword": "王五"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["mentors"], [])

    # 验证私有导师所有者可搜索到自己的私有导师。
    def test_search_mentors_includes_private_mentor_for_owner(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "王五"},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "王五")

    # 验证其他普通用户搜索不到他人的私有导师。
    def test_search_mentors_excludes_private_mentor_for_other_user(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "王五"},
            **self.auth_headers(self.other_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["mentors"], [])

    # 验证私有导师所有者可通过导师名搜索到关联私有论文。
    def test_search_papers_by_private_mentor_name_includes_owner_results(self):
        res = self.client.get(
            "/search/papers",
            {"keyword": "王五"},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["隐私导师论文"])

    # 验证其他普通用户无法通过私有导师名搜索到私有论文。
    def test_search_papers_by_private_mentor_name_excludes_other_user_results(self):
        res = self.client.get(
            "/search/papers",
            {"keyword": "王五"},
            **self.auth_headers(self.other_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["papers"], [])

    # 验证私有导师相关的论文模糊搜索遵守所有者可见性。
    def test_search_papers_fuzzy_private_mentor_respects_owner_visibility(self):
        owner_res = self.client.get(
            "/search/papers",
            {"keyword": "王", "search_mode": "fuzzy"},
            **self.auth_headers(self.owner_token),
        )
        other_res = self.client.get(
            "/search/papers",
            {"keyword": "王", "search_mode": "fuzzy"},
            **self.auth_headers(self.other_token),
        )

        self.assertEqual(owner_res.status_code, 200)
        self.assertEqual([paper["title"] for paper in owner_res.json()["papers"]], ["隐私导师论文"])
        self.assertEqual(other_res.status_code, 200)
        self.assertEqual(other_res.json()["papers"], [])

    # 验证管理员可以搜索到私有导师。
    def test_search_mentors_includes_private_mentor_for_admin(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "王五"},
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(len(res.json()["mentors"]), 1)
        self.assertEqual(res.json()["mentors"][0]["Chinese_name"], "王五")

    # 验证管理员可以通过私有导师名搜索到私有论文。
    def test_search_papers_by_private_mentor_name_includes_admin_results(self):
        res = self.client.get(
            "/search/papers",
            {"keyword": "王五"},
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual([paper["title"] for paper in res.json()["papers"]], ["隐私导师论文"])

    # 验证缺少关键词参数时接口返回参数错误。
    def test_search_keyword_missing(self):
        res = self.client.get("/search/mentors")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    # 验证空关键词会返回当前用户可见的全部论文。
    def test_search_keyword_empty(self):
        res = self.client.get("/search/papers", {"keyword": "   "})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["keyword"], "")
        # 匿名用户：空关键词只返回公共论文，私有导师论文不得泄漏
        self.assertEqual(res.json()["total"], 2)
        titles = {paper["title"] for paper in res.json()["papers"]}
        self.assertEqual(titles, {"机器学习方法研究", "大语言模型在问答系统中的应用"})
        self.assertNotIn("隐私导师论文", titles)

    # 验证空关键词下所有者可看到私有论文。
    def test_search_papers_empty_keyword_includes_private_for_owner(self):
        res = self.client.get(
            "/search/papers",
            {"keyword": ""},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["total"], 3)
        self.assertIn("隐私导师论文", {paper["title"] for paper in res.json()["papers"]})

    # 验证空关键词下其他普通用户看不到私有论文。
    def test_search_papers_empty_keyword_excludes_private_for_other_user(self):
        res = self.client.get(
            "/search/papers",
            {"keyword": ""},
            **self.auth_headers(self.other_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["total"], 2)
        self.assertNotIn("隐私导师论文", {paper["title"] for paper in res.json()["papers"]})

    # 验证空关键词下管理员可看到私有论文。
    def test_search_papers_empty_keyword_includes_private_for_admin(self):
        res = self.client.get(
            "/search/papers",
            {"keyword": ""},
            **self.auth_headers(self.admin_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["total"], 3)
        self.assertIn("隐私导师论文", {paper["title"] for paper in res.json()["papers"]})

    # 验证匿名模糊搜索空关键词时不会泄漏私有论文。
    def test_search_papers_empty_keyword_fuzzy_excludes_private_for_anonymous(self):
        res = self.client.get(
            "/search/papers",
            {"keyword": "  ", "search_mode": "fuzzy"},
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["total"], 2)
        self.assertNotIn("隐私导师论文", {paper["title"] for paper in res.json()["papers"]})

    # 验证公共论文即使被私有导师收藏也仍然保持公开可见。
    def test_search_papers_public_paper_added_by_private_mentor_stays_visible(self):
        # 已在公共库的论文（被公共导师张三关联），同时被他人私有导师收藏，
        # 应对所有用户保持可见——公共优先。
        self.private_mentor.add_paper(self.paper1.id)

        res = self.client.get(
            "/search/papers",
            {"keyword": ""},
            **self.auth_headers(self.other_token),
        )

        self.assertEqual(res.status_code, 200)
        titles = {paper["title"] for paper in res.json()["papers"]}
        self.assertIn("机器学习方法研究", titles)
        self.assertNotIn("隐私导师论文", titles)

    # 验证空关键词导师搜索会返回当前用户可见的全部导师。
    def test_search_empty_keyword_returns_all_visible_mentors(self):
        anonymous_res = self.client.get("/search/mentors", {"keyword": ""})
        owner_res = self.client.get(
            "/search/mentors",
            {"keyword": ""},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(anonymous_res.status_code, 200)
        self.assertEqual(anonymous_res.json()["code"], 0)
        self.assertEqual(anonymous_res.json()["total"], 2)
        self.assertEqual({mentor["Chinese_name"] for mentor in anonymous_res.json()["mentors"]}, {"张三", "李四"})

        self.assertEqual(owner_res.status_code, 200)
        self.assertEqual(owner_res.json()["code"], 0)
        self.assertEqual(owner_res.json()["total"], 3)
        self.assertEqual(
            {mentor["Chinese_name"] for mentor in owner_res.json()["mentors"]},
            {"张三", "李四", "王五"},
        )

    # 验证导师搜索会拒绝过长关键词。
    def test_search_keyword_too_long_for_mentors(self):
        res = self.client.get("/search/mentors", {"keyword": "x" * 256})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    # 验证论文搜索会拒绝过长关键词。
    def test_search_keyword_too_long_for_papers(self):
        res = self.client.get("/search/papers", {"keyword": "x" * 256})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], -2)

    # 验证搜索前会先裁剪关键词两端空白。
    def test_search_keyword_trimmed_before_search(self):
        mentor_res = self.client.get("/search/mentors", {"keyword": "  张三  "})
        paper_res = self.client.get("/search/papers", {"keyword": "  李四  "})

        self.assertEqual(mentor_res.status_code, 200)
        self.assertEqual(mentor_res.json()["keyword"], "张三")
        self.assertEqual(len(mentor_res.json()["mentors"]), 1)

        self.assertEqual(paper_res.status_code, 200)
        self.assertEqual(paper_res.json()["keyword"], "李四")
        self.assertEqual([paper["title"] for paper in paper_res.json()["papers"]], ["大语言模型在问答系统中的应用"])

    # 验证导师搜索接口会拒绝错误的请求方法。
    def test_search_bad_method(self):
        res = self.client.post("/search/mentors", {"keyword": "张三"})

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    # 验证论文搜索接口会拒绝错误的请求方法。
    def test_search_papers_bad_method(self):
        res = self.client.post("/search/papers", {"keyword": "张三"})

        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.json()["code"], -3)

    # 验证 visibility=mine 时只返回当前用户拥有的私有导师。
    def test_search_mentors_visibility_mine_returns_only_owned_private_mentors(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "", "visibility": "mine"},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        names = [mentor["Chinese_name"] for mentor in res.json()["mentors"]]
        self.assertEqual(names, ["王五"])

    # 验证 visibility=public 时只返回公共导师。
    def test_search_mentors_visibility_public_excludes_private_owned_mentors(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "", "visibility": "public"},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        names = {mentor["Chinese_name"] for mentor in res.json()["mentors"]}
        self.assertEqual(names, {"张三", "李四"})

    # 验证非法 visibility 参数会回退到 all。
    def test_search_mentors_invalid_visibility_falls_back_to_all(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "", "visibility": "unknown"},
            **self.auth_headers(self.owner_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        names = {mentor["Chinese_name"] for mentor in res.json()["mentors"]}
        self.assertEqual(names, {"张三", "李四", "王五"})

    # 验证非法令牌会被静默当作匿名用户处理。
    def test_search_mentors_rejects_invalid_token_silently_and_returns_public(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": ""},
            HTTP_AUTHORIZATION="Bearer not-a-real-token",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        names = {mentor["Chinese_name"] for mentor in res.json()["mentors"]}
        self.assertEqual(names, {"张三", "李四"})

    # 验证空的 Bearer 令牌会被当作匿名用户处理。
    def test_search_mentors_treats_blank_bearer_token_as_anonymous(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": ""},
            HTTP_AUTHORIZATION="Bearer    ",
        )

        self.assertEqual(res.status_code, 200)
        names = {mentor["Chinese_name"] for mentor in res.json()["mentors"]}
        self.assertEqual(names, {"张三", "李四"})

    # 验证被封禁用户令牌不会获得私有导师可见性。
    def test_search_mentors_treats_banned_token_as_anonymous(self):
        res = self.client.get(
            "/search/mentors",
            {"keyword": "王五"},
            **self.auth_headers(self.banned_token),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["code"], 0)
        self.assertEqual(res.json()["mentors"], [])

    # 验证非法分页参数会回退到默认页码和页大小。
    def test_search_mentors_invalid_page_inputs_fall_back_to_defaults(self):
        res = self.client.get(
            "/search/mentors",
            {
                "keyword": "",
                "page": "not-number",
                "page_size": "not-number",
            },
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 10)
