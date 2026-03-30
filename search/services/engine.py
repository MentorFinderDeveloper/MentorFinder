MOCK_MENTORS = [
    {
        "id": 1,
        "name": "张三",
        "researchDirection": "机器学习",
        "email": "zhangsan@example.com",
        "profile": "主要研究机器学习与数据挖掘。",
        "paperTitles": [
            "机器学习方法研究",
            "面向推荐系统的特征建模",
        ],
    },
    {
        "id": 2,
        "name": "李四",
        "researchDirection": "自然语言处理",
        "email": "lisi@example.com",
        "profile": "主要研究自然语言处理与大模型应用。",
        "paperTitles": [
            "大语言模型在问答系统中的应用",
        ],
    },
]

MOCK_PAPERS = [
    {
        "id": 101,
        "title": "机器学习方法研究",
        "abstract": "本文讨论常见机器学习方法及其应用场景。",
        "publishDate": "2024-05-01",
        "mentorNames": ["张三"],
    },
    {
        "id": 102,
        "title": "大语言模型在问答系统中的应用",
        "abstract": "本文介绍大语言模型在智能问答中的实践。",
        "publishDate": "2024-06-15",
        "mentorNames": ["李四", "张三"],
    },
]


def _is_exact_match(text: str, keyword: str) -> bool:
    return text.casefold() == keyword.casefold()


def _copy_paper(paper: dict) -> dict:
    return dict(paper)


def _copy_mentor(mentor: dict) -> dict:
    return dict(mentor)


def _find_papers_by_titles(titles: list[str]) -> list[dict]:
    title_set = set(titles)
    return [
        _copy_paper(paper)
        for paper in MOCK_PAPERS
        if paper["title"] in title_set
    ]


def search_mentors(keyword: str) -> list[dict]:
    """
    Temporary mock implementation.
    The real algorithm and ORM query can replace this later.
    """
    return [
        _copy_mentor(mentor)
        for mentor in MOCK_MENTORS
        if _is_exact_match(mentor["name"], keyword)
    ]


def search_papers(keyword: str) -> list[dict]:
    """
    Temporary mock implementation.
    The real algorithm and ORM query can replace this later.
    """
    results_by_id = {}

    # 1. Exact paper title match.
    for paper in MOCK_PAPERS:
        if _is_exact_match(paper["title"], keyword):
            results_by_id[paper["id"]] = _copy_paper(paper)

    # 2. Exact research direction match -> all papers of matched mentors.
    for mentor in MOCK_MENTORS:
        if _is_exact_match(mentor["researchDirection"], keyword):
            for paper in _find_papers_by_titles(mentor["paperTitles"]):
                results_by_id.setdefault(paper["id"], paper)

    # 3. Exact mentor name match -> all papers of matched mentors.
    for mentor in MOCK_MENTORS:
        if _is_exact_match(mentor["name"], keyword):
            for paper in _find_papers_by_titles(mentor["paperTitles"]):
                results_by_id.setdefault(paper["id"], paper)

    return list(results_by_id.values())
