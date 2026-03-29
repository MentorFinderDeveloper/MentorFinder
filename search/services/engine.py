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


def _contains(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def search_mentors(keyword: str) -> list[dict]:
    """
    Temporary mock implementation.
    The real algorithm and ORM query can replace this later.
    """
    results = []
    for mentor in MOCK_MENTORS:
        searchable_text = " ".join([
            mentor["name"],
            mentor["researchDirection"],
            mentor["profile"],
            " ".join(mentor["paperTitles"]),
        ])
        if _contains(searchable_text, keyword):
            results.append(dict(mentor))
    return results


def search_papers(keyword: str) -> list[dict]:
    """
    Temporary mock implementation.
    The real algorithm and ORM query can replace this later.
    """
    results = []
    for paper in MOCK_PAPERS:
        searchable_text = " ".join([
            paper["title"],
            paper["abstract"],
            " ".join(paper["mentorNames"]),
        ])
        if _contains(searchable_text, keyword):
            results.append(dict(paper))
    return results
