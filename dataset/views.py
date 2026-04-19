import json

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest

from account.models import User
from dataset.models import Mentor, Paper
from dataset.services.thu_crawler import build_given_name_surname_pinyin, crawl_mentor_by_name
from utils.utils_jwt import check_jwt_token
from utils.utils_request import BAD_METHOD, request_failed, request_success
from utils.utils_require import CheckRequire, MAX_CHAR_LENGTH, require
from django.shortcuts import render
from collections import defaultdict


def _extract_token(req: HttpRequest) -> str:
    auth_header = req.headers.get("Authorization", "").strip()
    if auth_header == "":
        return ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return auth_header


def _require_admin(req: HttpRequest):
    token = _extract_token(req)
    if token == "":
        return request_failed(2, "Unauthorized", 401)

    token_data = check_jwt_token(token)
    if token_data is None:
        return request_failed(2, "Unauthorized", 401)

    username = str(token_data.get("username", "")).strip()
    if username == "":
        return request_failed(2, "Unauthorized", 401)

    user = User.objects.filter(username=username).first()
    if user is None:
        return request_failed(2, "User not found", 401)

    if user.role != "admin":
        return request_failed(3, "Permission denied", 403)

    return None


def _resolve_user(req: HttpRequest):
    token = _extract_token(req)
    if token == "":
        return None

    token_data = check_jwt_token(token)
    if token_data is None:
        return None

    username = str(token_data.get("username", "")).strip()
    if username == "":
        return None

    return User.objects.filter(username=username).first()


def _require_user(req: HttpRequest):
    user = _resolve_user(req)
    if user is None:
        return None, request_failed(2, "Unauthorized", 401)
    return user, None


def _build_crawler_lookup_names(chinese_name: str, english_name: str) -> tuple[str, str]:
    normalized_english = english_name.strip()
    if normalized_english != "":
        # English name has priority when both Chinese and English are provided.
        return "", normalized_english

    normalized_chinese = chinese_name.strip()
    return "", build_given_name_surname_pinyin(normalized_chinese)


def _serialize_paper(paper: Paper):
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "publish_date": paper.publish_date,
        "author_names": paper.author_names,
    }


def _serialize_mentor(mentor: Mentor):
    return {
        "id": mentor.id,
        "Chinese_name": mentor.Chinese_name,
        "English_name": mentor.English_name,
        "research_direction": mentor.research_direction,
        "email": mentor.email,
        "profile": mentor.profile,
        "is_private": mentor.is_private,
        "paper_ids": [_serialize_paper(paper) for paper in mentor.get_papers()],
    }


def _validate_paper_payload(body: dict):
    title = require(body, "title", "string", err_msg="Missing or error type of [title]").strip()
    if title == "":
        raise KeyError("Invalid parameters. [title] cannot be empty", -2)
    if len(title) > MAX_CHAR_LENGTH:
        raise KeyError("Invalid parameters. [title] is too long", -2)

    abstract = str(body.get("abstract", "")).strip()
    author_names = str(body.get("author_names", "")).strip()
    publish_date = body.get("publish_date")

    if abstract and len(abstract) > 5000:
        raise KeyError("Invalid parameters. [abstract] is too long", -2)
    if author_names and len(author_names) > 5000:
        raise KeyError("Invalid parameters. [author_names] is too long", -2)

    return {
        "title": title,
        "abstract": abstract or None,
        "publish_date": publish_date if publish_date else None,
        "author_names": author_names,
    }


def _validate_mentor_payload(body: dict):
    chinese_name = require(
        body,
        "Chinese_name",
        "string",
        err_msg="Missing or error type of [Chinese_name]",
    ).strip()
    research_direction = require(
        body,
        "research_direction",
        "string",
        err_msg="Missing or error type of [research_direction]",
    ).strip()

    if chinese_name == "":
        raise KeyError("Invalid parameters. [Chinese_name] cannot be empty", -2)
    if research_direction == "":
        raise KeyError("Invalid parameters. [research_direction] cannot be empty", -2)

    if len(chinese_name) > 100:
        raise KeyError("Invalid parameters. [Chinese_name] is too long", -2)
    if len(research_direction) > MAX_CHAR_LENGTH:
        raise KeyError("Invalid parameters. [research_direction] is too long", -2)

    english_name = str(body.get("English_name", "")).strip()
    email = str(body.get("email", "")).strip()
    profile = str(body.get("profile", "")).strip()

    if english_name and len(english_name) > 100:
        raise KeyError("Invalid parameters. [English_name] is too long", -2)
    if email:
        try:
            validate_email(email)
        except ValidationError:
            raise KeyError("Invalid parameters. [email] format is invalid", -2)

    return {
        "Chinese_name": chinese_name,
        "English_name": english_name or None,
        "research_direction": research_direction,
        "email": email or None,
        "profile": profile or None,
    }


def _refresh_mentor_papers(mentor: Mentor):
    paper_ids = []
    for paper in Paper.objects.all():
        author_list = paper.get_author_list()
        if mentor.Chinese_name in author_list or (
            mentor.English_name and mentor.English_name in author_list
        ):
            paper_ids.append(paper.id)
    mentor.set_paper_id_list(paper_ids)
    mentor.save()


def _detach_paper_from_mentors(paper_id: int):
    for mentor in Mentor.objects.all():
        id_list = mentor.get_paper_id_list()
        if paper_id in id_list:
            mentor.set_paper_id_list([pid for pid in id_list if pid != paper_id])
            mentor.save()


@CheckRequire
def create_paper(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    body = json.loads(req.body.decode("utf-8"))
    paper_payload = _validate_paper_payload(body)

    paper = Paper.objects.create(**paper_payload)

    paper.bind_to_mentors_by_authors()

    return request_success({"paper": _serialize_paper(paper)})


@CheckRequire
def create_mentor(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    body = json.loads(req.body.decode("utf-8"))
    mentor_payload = _validate_mentor_payload(body)

    mentor = Mentor.objects.create(**mentor_payload, paper_ids="", owner=None)
    _refresh_mentor_papers(mentor)

    return request_success({"mentor": _serialize_mentor(mentor)})


@CheckRequire
def create_custom_mentor(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    body = json.loads(req.body.decode("utf-8"))

    chinese_name = str(body.get("Chinese_name", "")).strip()
    english_name = str(body.get("English_name", "")).strip()

    if chinese_name == "" and english_name == "":
        return request_failed(
            -2,
            "Invalid parameters. [Chinese_name] or [English_name] is required",
            400,
        )

    if len(chinese_name) > 100:
        return request_failed(-2, "Invalid parameters. [Chinese_name] is too long", 400)
    if len(english_name) > 100:
        return request_failed(-2, "Invalid parameters. [English_name] is too long", 400)

    lookup_chinese_name, lookup_english_name = _build_crawler_lookup_names(chinese_name, english_name)
    crawler_result = crawl_mentor_by_name(
        chinese_name=lookup_chinese_name,
        english_name=lookup_english_name,
    )
    if crawler_result is None:
        return request_failed(2, "Mentor not found by crawler", 404)

    final_chinese_name = str(crawler_result.get("Chinese_name") or chinese_name).strip()
    final_english_name = str(crawler_result.get("English_name") or english_name).strip()
    if final_chinese_name == "":
        return request_failed(2, "Mentor not found by crawler", 404)

    if Mentor.objects.filter(owner=user, Chinese_name=final_chinese_name).exists():
        return request_failed(3, "Mentor already exists in your private library", 409)

    mentor = Mentor.objects.create(
        Chinese_name=final_chinese_name,
        English_name=final_english_name or None,
        research_direction=str(crawler_result.get("research_direction") or "").strip() or "未提供",
        email=str(crawler_result.get("email") or "").strip() or None,
        profile=str(crawler_result.get("profile") or "").strip() or None,
        paper_ids="",
        owner=user,
    )
    _refresh_mentor_papers(mentor)

    return request_success({"mentor": _serialize_mentor(mentor)})


@CheckRequire
def my_custom_mentors(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD

    user, auth_error = _require_user(req)
    if auth_error is not None:
        return auth_error

    mentors = Mentor.objects.filter(owner=user).order_by("-id")
    return request_success({"mentors": [_serialize_mentor(mentor) for mentor in mentors]})


@CheckRequire
def paper_detail(req: HttpRequest, paper_id: int):
    if req.method not in ["PUT", "DELETE"]:
        return BAD_METHOD

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

    paper = Paper.objects.filter(id=paper_id).first()
    if paper is None:
        return request_failed(2, "Paper not found", 404)

    if req.method == "DELETE":
        _detach_paper_from_mentors(paper.id)
        paper.delete()
        return request_success()

    body = json.loads(req.body.decode("utf-8"))
    paper_payload = _validate_paper_payload(body)
    for key, value in paper_payload.items():
        setattr(paper, key, value)
    paper.save()

    _detach_paper_from_mentors(paper.id)
    paper.bind_to_mentors_by_authors()

    return request_success({"paper": _serialize_paper(paper)})


@CheckRequire
def mentor_detail(req: HttpRequest, mentor_id: int):
    if req.method not in ["GET", "PUT", "DELETE"]:
        return BAD_METHOD

    mentor = Mentor.objects.filter(id=mentor_id).first()
    if mentor is None:
        return request_failed(2, "Mentor not found", 404)

    current_user = _resolve_user(req)
    if not mentor.is_visible_to(current_user):
        return request_failed(2, "Mentor not found", 404)

    if req.method == "GET":
        return request_success({"mentor": _serialize_mentor(mentor)})

    if mentor.owner_id is None:
        auth_error = _require_admin(req)
        if auth_error is not None:
            return auth_error
    else:
        actor, auth_error = _require_user(req)
        if auth_error is not None:
            return auth_error
        if actor.role != "admin" and actor.id != mentor.owner_id:
            return request_failed(3, "Permission denied", 403)

    if req.method == "DELETE":
        mentor.delete()
        return request_success()

    body = json.loads(req.body.decode("utf-8"))
    mentor_payload = _validate_mentor_payload(body)
    for key, value in mentor_payload.items():
        setattr(mentor, key, value)
    mentor.save()

    _refresh_mentor_papers(mentor)

    return request_success({"mentor": _serialize_mentor(mentor)})


# 常见的 arXiv 分类代码与中文名称映射表
ARXIV_SUBJECT_MAPPING = {
    # --- 核心计算机科学 (Computer Science - 截图新增) ---
    'cs.AI': '人工智能 (Artificial Intelligence)',
    'cs.CV': '计算机视觉 (Computer Vision)',
    'cs.CL': '自然语言处理 (NLP)',
    'cs.LG': '机器学习 (Machine Learning)',
    'cs.RO': '机器人学 (Robotics)',
    'cs.SE': '软件工程 (Software Engineering)',
    'cs.CR': '加密与安全 (Security)',
    'cs.HC': '人机交互 (HCI)',
    'cs.CC': '计算复杂性 (Computational Complexity)',
    'cs.CE': '计算工程与科学 (Computational Engineering)',
    'cs.CG': '计算几何 (Computational Geometry)',
    'cs.CY': '计算机与社会 (Computers and Society)',
    'cs.DM': '离散数学 (Discrete Mathematics)',
    'cs.GT': '计算机科学与博弈论 (Game Theory)',
    'cs.MS': '数学软件 (Mathematical Software)',
    'cs.PF': '系统性能 (Performance)',
    'cs.SD': '声音与音频处理 (Sound/Audio)',
    'cs.ET': '新兴技术 (Emerging Technologies)',
    'cs.GR': '计算机图形学 (Computer Graphics)',
    'cs.IR': '信息检索 (Information Retrieval)',
    'cs.IT': '信息论 (Information Theory)',
    'cs.LO': '计算机科学逻辑 (Logic in Computer Science)',
    'cs.MA': '多智能体系统 (Multiagent Systems)',
    'cs.MM': '多媒体 (Multimedia)',
    'cs.NE': '神经与进化计算 (Neural and Evolutionary Computing)',
    'cs.NI': '网络与互联网体系结构 (Networking and Internet Architecture)',
    'cs.OS': '操作系统 (Operating Systems)',
    'cs.PL': '编程语言 (Programming Languages)',
    'cs.SI': '社会与信息网络 (Social and Information Networks)',

    'cs.AR': '硬件体系结构 (Hardware Architecture)',
    'cs.DB': '数据库 (Databases)',
    'cs.DC': '分布式、并行与集群计算 (Distributed and Parallel Computing)',
    'cs.DS': '数据结构与算法 (Data Structures and Algorithms)',
    # --- 天体物理学 (Astrophysics - 截图 5/6) ---
    'astro-ph.CO': '宇宙学与非星系天体物理 (Cosmology)',
    'astro-ph.EP': '地球与行星天体物理 (Planetary Astrophysics)',
    'astro-ph.GA': '星系天体物理 (Astrophysics of Galaxies)',
    'astro-ph.HE': '高能天体物理现象 (High Energy Astrophysics)',
    'astro-ph.IM': '天体物理仪器与方法 (Instrumentation)',
    'astro-ph.SR': '太阳与恒星天体物理 (Solar and Stellar)',

    # --- 凝聚态物理 (Condensed Matter - 截图 5/6) ---
    'cond-mat.mes-hall': '介观与纳米尺度物理 (Mesoscale Physics)',
    'cond-mat.mtrl-sci': '材料科学 (Materials Science)',
    'cond-mat.str-el': '强关联电子系统 (Strongly Correlated)',
    'cond-mat.supr-con': '超导性 (Superconductivity)',

    # --- 经济学 (Economics - 截图 2) ---
    'econ.EM': '计量经济学 (Econometrics)',
    'econ.GN': '一般经济学 (General Economics)',

    # --- 高能物理与相对论 (Physics High Energy - 截图 3) ---
    'gr-qc': '广义相对论与量子宇宙学 (General Relativity)',
    'hep-ex': '高能物理-实验 (High Energy Physics - Exp)',
    'hep-ph': '高能物理-现象学 (High Energy Physics - Phen)',
    'hep-th': '高能物理-理论 (High Energy Physics - Theory)',
    'quant-ph': '量子物理 (Quantum Physics)',

    # --- 数学 (Mathematics - 截图 3/4) ---
    'math-ph': '数学物理 (Mathematical Physics)',
    'math.AG': '代数几何 (Algebraic Geometry)',
    'math.AP': '偏微分方程分析 (Analysis of PDEs)',
    'math.CA': '经典分析与常微分方程 (Classical Analysis)',
    'math.CO': '组合数学 (Combinatorics)',
    'math.CV': '复变量 (Complex Variables)',
    'math.DG': '微分几何 (Differential Geometry)',
    'math.FA': '泛函分析 (Functional Analysis)',
    'math.GM': '一般数学 (General Mathematics)',
    'math.NA': '数值分析 (Numerical Analysis)',
    'math.NT': '数论 (Number Theory)',
    'math.RT': '表示论 (Representation Theory)',
    'math.OC': '优化与控制 (Optimization)',

    # --- 非线性科学 (Nonlinear Sciences - 截图 4) ---
    'nlin.AO': '适应与自组织系统 (Adaptation)',
    'nlin.CD': '混沌动力学 (Chaotic Dynamics)',
    'nlin.PS': '模式形成与孤子 (Pattern Formation)',

    # --- 应用物理学 (Applied Physics - 截图 4/1) ---
    'physics.atom-ph': '原子物理 (Atomic Physics)',
    'physics.data-an': '数据分析、统计与概率 (Data Analysis)',
    'physics.flu-dyn': '流体动力学 (Fluid Dynamics)',
    'physics.ins-det': '仪器与探测器 (Instrumentation)',
    'physics.med-ph': '医学物理 (Medical Physics)',
    'physics.optics': '光学 (Optics)',
    'physics.plasm-ph': '等离子体物理 (Plasma Physics)',
    'physics.soc-ph': '物理学与社会 (Physics and Society)',
    'physics.space-ph': '空间物理 (Space Physics)',

    # --- 定量生物学 (Quantitative Biology - 截图 1) ---
    'q-bio.BM': '生物分子 (Biomolecules)',
    'q-bio.GN': '基因组学 (Genomics)',
    'q-bio.MN': '分子网络 (Molecular Networks)',
    'q-bio.NC': '神经元与认知 (Neurons and Cognition)',

    # --- 统计学 (Statistics) ---
    'stat.ML': '统计机器学习 (Stat Machine Learning)',
    'stat.OT': '其他统计学 (Other Statistics)',
    # ---其他漏掉的领域---
    'eess.AS': '音频与语音处理 (Audio and Speech Processing)',
    'eess.IV': '图像与视频处理 (Image and Video Processing)',
    'eess.SP': '信号处理 (Signal Processing)',
    'eess.SY': '系统与控制 (Systems and Control)',
    'math.DS': '动力系统 (Dynamical Systems)',
    'math.PR': '概率论 (Probability)',
    'physics.comp-ph': '计算物理 (Computational Physics)',
    'q-bio.QM': '定量方法 (Quantitative Methods)',
    'stat.AP': '应用统计 (Applications)',
    'stat.ME': '统计方法论 (Methodology)',
}

#把论文按研究方向分类并按时间排序
def paper_timeline_view(request):
    if request.method != "GET":
        return BAD_METHOD

    papers = Paper.objects.exclude(publish_date__isnull=True).order_by("-publish_date")
    direction_groups = defaultdict(list)

    for paper in papers:
        if paper.subjects:
            raw_subjects = [s.strip() for s in paper.subjects.split(",")]
            for sub in raw_subjects:
                readable_name = ARXIV_SUBJECT_MAPPING.get(sub, sub)
                direction_groups[readable_name].append({
                    "id": paper.id,
                    "title": paper.title,
                    "publish_date": str(paper.publish_date) if paper.publish_date else None,
                    "author_names": paper.author_names,
                    "abstract": paper.abstract,
                })
        else:
            direction_groups["其他/未分类"].append({
                "id": paper.id,
                "title": paper.title,
                "publish_date": str(paper.publish_date) if paper.publish_date else None,
                "author_names": paper.author_names,
                "abstract": paper.abstract,
            })

    timeline = [
        {
            "direction": direction,
            "papers": papers_list,
        }
        for direction, papers_list in sorted(
            direction_groups.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]

    return request_success({"timeline": timeline})
