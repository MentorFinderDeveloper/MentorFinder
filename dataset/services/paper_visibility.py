"""共享的论文可见性逻辑。

私有导师（`owner` 非空）的论文只应对其拥有者本人以及管理员可见，
不能进入公共的论文时间线或不带关键词的搜索结果。搜索与时间线都复用
这里的实现，保证两处的可见性规则始终一致。
"""

from dataset.models import Mentor, Paper


def _iter_mentor_paper_ids(mentors_qs):
    """从导师查询集的 ``paper_ids`` 字段惰性产出论文 ID。

    只取 ``paper_ids`` 字符串列，不实例化 ``Mentor`` 对象，避免在公共导师
    数量很大时产生大量 ORM 开销。
    """
    rows = mentors_qs.values_list("paper_ids", flat=True).iterator(chunk_size=500)
    for paper_ids_str in rows:
        if not paper_ids_str:
            continue
        for raw_id in paper_ids_str.split(","):
            raw_id = raw_id.strip()
            if raw_id:
                yield int(raw_id)


def collect_mentor_paper_ids(mentors) -> list[int]:
    """收集一批导师所关联的全部论文 ID（去重）。"""
    return list(set(_iter_mentor_paper_ids(mentors)))


def hidden_private_paper_ids(user) -> list[int]:
    """返回对该用户不可见的私有导师论文 ID 列表。

    采用「公共优先」语义：只有「被他人的私有导师关联、且没有被任何公共
    导师关联」的论文才会被隐藏。一篇论文只要进入了公共库（被任一公共导师
    关联），即使某用户的私有导师也添加了它，仍应对所有人可见。

    管理员可见全部，返回空列表；匿名用户隐藏所有他人私有导师的私有独占
    论文；普通用户在此基础上保留自己拥有的私有导师论文。

    性能：私有导师是小众 opt-in 功能，绝大多数请求下候选集为空，会在收集
    完私有导师论文后立即返回，不触碰公共导师；仅当确有他人私有导师论文时
    才遍历公共导师，且候选集被覆盖干净后提前结束。
    """
    if user is not None and getattr(user, "role", "") == "admin":
        return []

    hidden_private_mentors = Mentor.objects.exclude(owner__isnull=True)
    if user is not None:
        hidden_private_mentors = hidden_private_mentors.exclude(owner_id=user.id)

    # 候选 = 他人私有导师关联的论文（私有导师很少，开销小）
    remaining = set(_iter_mentor_paper_ids(hidden_private_mentors))
    if not remaining:
        return []

    # 公共优先：逐个移除被公共导师关联的论文；移除干净即可提前结束
    public_mentors = Mentor.objects.filter(owner__isnull=True)
    for paper_id in _iter_mentor_paper_ids(public_mentors):
        remaining.discard(paper_id)
        if not remaining:
            return []

    return list(remaining)


def visible_papers(user):
    """返回排除了他人私有导师论文的 Paper 查询集。"""
    hidden_paper_ids = hidden_private_paper_ids(user)
    if not hidden_paper_ids:
        return Paper.objects.all()
    return Paper.objects.exclude(id__in=hidden_paper_ids)
