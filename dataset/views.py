import json

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest

from account.models import User
from dataset.models import Mentor, Paper
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

    mentor = Mentor.objects.create(**mentor_payload, paper_ids="")
    _refresh_mentor_papers(mentor)

    return request_success({"mentor": _serialize_mentor(mentor)})


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

    if req.method == "GET":
        return request_success({"mentor": _serialize_mentor(mentor)})

    auth_error = _require_admin(req)
    if auth_error is not None:
        return auth_error

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
    # --- 核心计算机科学 (Computer Science) ---
    'cs.AI': '人工智能 (Artificial Intelligence)',
    'cs.CV': '计算机视觉 (Computer Vision)',
    'cs.CL': '自然语言处理 (NLP)',
    'cs.LG': '机器学习 (Machine Learning)',
    'cs.RO': '机器人学 (Robotics)',
    'cs.SE': '软件工程 (Software Engineering)',
    'cs.CR': '加密与安全 (Cryptography and Security)',
    'cs.HC': '人机交互 (Human-Computer Interaction)',
    'cs.DB': '数据库 (Databases)',
    'cs.DC': '分布式与并行计算 (Distributed and Parallel Computing)',
    'cs.DS': '数据结构与算法 (Data Structures and Algorithms)',
    'cs.IR': '信息检索 (Information Retrieval)',
    'cs.IT': '信息论 (Information Theory)',
    'cs.LG': '机器学习 (Machine Learning)',
    'cs.MA': '多智能体系统 (Multiagent Systems)',
    'cs.MM': '多媒体 (Multimedia)',
    'cs.NE': '神经与进化计算 (Neural and Evolutionary Computing)',
    'cs.NI': '网络与互联网体系结构 (Networking and Internet Architecture)',
    'cs.OS': '操作系统 (Operating Systems)',
    'cs.PL': '编程语言 (Programming Languages)',
    'cs.SI': '社会与信息网络 (Social and Information Networks)',
    'cs.GR': '计算机图形学 (Computer Graphics)',
    'cs.AR': '硬件体系结构 (Hardware Architecture)',
    'cs.ET': '新兴技术 (Emerging Technologies)',
    'cs.SY': '系统与控制 (Systems and Control)',
    'cs.LO': '计算机科学逻辑 (Logic in Computer Science)',

    # --- 统计学 (Statistics) ---
    'stat.ML': '统计机器学习 (Machine Learning)',
    'stat.AP': '应用统计 (Applications)',
    'stat.ME': '统计方法论 (Methodology)',
    'stat.TH': '统计理论 (Statistics Theory)',
    'stat.CO': '统计计算 (Computation)',

    # --- 数学相关 (Mathematics) ---
    'math.OC': '优化与控制 (Optimization and Control)',
    'math.ST': '统计理论 (Statistics Theory)',
    'math.PR': '概率论 (Probability)',
    'math.DS': '动力系统 (Dynamical Systems)',

    # --- 电气工程与系统科学 (EESS) ---
    'eess.IV': '图像与视频处理 (Image and Video Processing)',
    'eess.AS': '音频与语音处理 (Audio and Speech Processing)',
    'eess.SP': '信号处理 (Signal Processing)',
    'eess.SY': '系统与控制 (Systems and Control)',

    # --- 其他常见 ---
    'physics.comp-ph': '计算物理 (Computational Physics)',
    'q-bio.QM': '定量方法 (Quantitative Methods)',
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
        for direction, papers_list in sorted(direction_groups.items())
    ]

    return request_success({"timeline": timeline})
