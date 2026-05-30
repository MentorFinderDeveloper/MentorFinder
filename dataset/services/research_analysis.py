from __future__ import annotations

from collections import Counter
from datetime import date

import requests
from django.conf import settings

from dataset.models import Mentor, Paper


def call_thucs_chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.4,
    timeout: int = 25,
) -> str:
    api_key = str(getattr(settings, "THUCS_API_KEY", "") or "").strip()
    api_base_url = str(
        getattr(settings, "THUCS_API_BASE_URL", "https://api-ai.thucs.cn") or "https://api-ai.thucs.cn"
    ).rstrip("/")
    model_name = str(getattr(settings, "THUCS_MODEL_NAME", "qwen-plus") or "qwen-plus").strip()

    if api_key == "":
        raise RuntimeError("THUCS_API_KEY is not configured")

    response = requests.post(
        f"{api_base_url}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    text = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if text == "":
        raise RuntimeError("Empty response from THUCS AI")
    return text


def build_rule_based_recent_direction_analysis(
    mentor: Mentor,
    papers: list[Paper],
    cutoff_date: date,
    today: date,
) -> str:
    if not papers:
        return f"{mentor.Chinese_name} 在 {cutoff_date.isoformat()} 到 {today.isoformat()} 之间暂无带发表日期的关联论文，暂时无法分析最近研究方向。"

    subject_counter = Counter()
    keyword_counter = Counter()

    for paper in papers:
        for subject in [item.strip() for item in (paper.subjects or "").split(",") if item.strip()]:
            subject_counter.update([subject])

        combined_text = f"{paper.title} {(paper.tldr or paper.abstract or '')}".lower()
        for keyword in [
            "llm", "language model", "大模型", "多模态", "multimodal",
            "agent", "智能体", "alignment", "对齐", "reasoning", "推理",
            "retrieval", "检索", "graph", "图", "recommendation", "推荐",
            "security", "安全", "vision", "视觉", "robot", "机器人",
            "database", "数据库", "system", "系统", "optimization", "优化",
        ]:
            if keyword in combined_text:
                keyword_counter.update([keyword])

    subject_part = "、".join(subject for subject, _ in subject_counter.most_common(3))
    keyword_part = "、".join(keyword for keyword, _ in keyword_counter.most_common(5))

    sentences = [
        f"{mentor.Chinese_name} 近一年共发表 {len(papers)} 篇可统计论文。",
        f"从导师原始研究方向看，当前公开方向为“{mentor.research_direction or '未提供'}”。",
    ]
    if subject_part != "":
        sentences.append(f"从论文分类看，近期更集中在 {subject_part}。")
    if keyword_part != "":
        sentences.append(f"从题目与摘要关键词看，近期反复出现的话题包括 {keyword_part}。")
    sentences.append("整体上可以认为其最近研究工作围绕上述主题持续展开。")
    return "".join(sentences)


def build_ai_recent_direction_analysis(
    mentor: Mentor,
    papers: list[Paper],
    cutoff_date: date,
    today: date,
) -> str:
    paper_lines = []
    for paper in papers[:20]:
        paper_lines.append(
            "\n".join(
                [
                    f"标题: {paper.title}",
                    f"日期: {paper.publish_date.isoformat() if paper.publish_date else '未知'}",
                    f"作者: {paper.author_names or '未知'}",
                    f"摘要: {(paper.tldr or paper.abstract or '暂无摘要').strip()[:600]}",
                ]
            )
        )


    user_prompt = (
        f"请根据以下导师近一年论文信息，总结该导师最近的研究方向。只总结计算机领域相关方向\n"
        f"导师姓名: {mentor.Chinese_name}\n"
        f"导师英文名: {mentor.English_name or '未提供'}\n"
        f"系统记录研究方向: {mentor.research_direction or '未提供'}\n"
        f"统计时间范围: {cutoff_date.isoformat()} 到 {today.isoformat()}\n"
        f"论文数量: {len(papers)}\n\n"
        "要求：\n"
        "1. 输出 180-320 字中文。\n"
        "2. 聚焦“最近在做什么”，不要泛泛介绍。\n"
        "3. 优先从题目和摘要中提炼具体主题、方法和应用场景。\n"
        "4. 如果主题有明显聚类，直接指出 2-4 个重点方向。\n"
        "5. 不要编造论文中没有的信息。\n\n"
        " 格式要求：只返回纯文本内容,不要使用任何 Markdown 格式"
        "不要使用 *、#、** 等标记符号,使用数字+点（如'1. '）或直接换行,使用自然语言和普通标点符号"
        "论文列表：\n"
        + ("\n\n".join(paper_lines) if paper_lines else "无")
    )

    return call_thucs_chat_completion(
        system_prompt="你是一个严谨的科研分析助手，擅长根据论文题目和摘要总结导师近期研究方向。",
        user_prompt=user_prompt,
        temperature=0.3,
    )
