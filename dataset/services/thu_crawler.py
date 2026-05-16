import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from pypinyin import lazy_pinyin  # 新增导入拼音库

url = "https://www.cs.tsinghua.edu.cn/szzk/jzgml.htm"

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Host": "www.cs.tsinghua.edu.cn",
    # "Cookie": "JSESSIONID=9BADD2F3B34224773C1E64E4F391F457.yunxing21"
}

BRACKETED_TEXT_RE = re.compile(r"\s*[\(（][^()（）]*[\)）]\s*")

def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=BASE_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def strip_bracketed_name_content(name: str) -> str:
    normalized = str(name or "").replace("\u3000", " ").strip()
    if normalized == "":
        return ""

    previous = None
    while previous != normalized:
        previous = normalized
        normalized = BRACKETED_TEXT_RE.sub(" ", normalized)

    return " ".join(normalized.split()).strip()

def get_english_name(chinese_name: str) -> str:
    """将中文姓名转换为英文拼音，格式为 '名 姓' (例如 'Guangwen Yang')"""
    chinese_name = strip_bracketed_name_content(chinese_name)
    if not chinese_name:
        return ""

    # lazy_pinyin('黄振春') 会返回 ['huang', 'zhen', 'chun']
    pinyin_list = lazy_pinyin(chinese_name)
    
    if len(pinyin_list) == 0:
        return ""
    elif len(pinyin_list) == 1:
        return pinyin_list[0].capitalize()
    else:
        # 中国人姓名通常第一个字是姓
        last_name = pinyin_list[0].capitalize()
        # 后面的字合并在一起作为名，并首字母大写
        first_name = "".join(pinyin_list[1:]).capitalize()
        return f"{first_name} {last_name}"

def parse_mentor_list(ch_url: str) -> list[dict]:
    # 移除了所有对英文 url 的请求，大幅提升爬虫速度
    html = fetch_html(ch_url)
    soup = BeautifulSoup(html, "lxml")

    mentors = []
    for item in soup.select("h2"):
        relative_url = item.select_one("a")["href"]
        detail_url = urljoin(url, relative_url)
        mentors.append(parse_mentor_detail(detail_url))
        
    return mentors


def build_given_name_surname_pinyin(chinese_name: str) -> str:
    """将中文姓名转换为名-姓全拼，例如“唐杰” -> "jie-tang"。"""
    normalized = strip_bracketed_name_content(chinese_name)
    if normalized == "":
        return ""

    pinyin_list = lazy_pinyin(normalized)
    if len(pinyin_list) == 0:
        return ""
    if len(pinyin_list) == 1:
        return pinyin_list[0].lower()

    surname = pinyin_list[0].lower()
    given_name = "".join(pinyin_list[1:]).lower()
    return f"{given_name}-{surname}"


def _normalize_name(name: str) -> str:
    lowered = strip_bracketed_name_content(name).lower()
    # Support inputs like "jie-tang" and "tang, jie" by normalizing separators.
    lowered = lowered.replace("-", " ").replace(",", " ")
    return " ".join(lowered.split())


def _english_name_variants(english_name: str) -> set[str]:
    normalized = _normalize_name(english_name)
    if normalized == "":
        return set()

    variants = {normalized}
    parts = normalized.split(" ")
    if len(parts) == 2:
        variants.add(f"{parts[1]} {parts[0]}")
        variants.add(f"{parts[1]}, {parts[0]}")
    return variants


def crawl_mentor_by_name(chinese_name: str = "", english_name: str = "") -> dict | None:
    target_cn = strip_bracketed_name_content(chinese_name)
    target_en_variants = _english_name_variants(english_name)

    if target_cn == "" and not target_en_variants:
        return None

    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    for item in soup.select("h2"):
        anchor = item.select_one("a")
        if anchor is None or "href" not in anchor.attrs:
            continue

        detail_url = urljoin(url, anchor["href"])
        mentor = parse_mentor_detail(detail_url)

        if target_cn and mentor.get("Chinese_name", "").strip() == target_cn:
            return mentor

        mentor_en_variants = _english_name_variants(str(mentor.get("English_name", "")))
        if target_en_variants and mentor_en_variants & target_en_variants:
            return mentor

    return None

def parse_mentor_detail(detail_url: str) -> dict:
    html = fetch_html(detail_url)
    soup = BeautifulSoup(html, "lxml")
    #查找研究领域
    start_node = soup.find(lambda tag: tag.name == "p" and "研究领域" in tag.get_text())
    direction_list = []

    if start_node:
        for sibling in start_node.find_next_siblings():
            if sibling.find('strong') or sibling.name=='h4' or "研究概况" in sibling.get_text(strip = True)  \
                or "讲授课程" in sibling.get_text(strip = True) or "工作履历" in sibling.get_text(strip = True)  \
                or "研究概况" in sibling.get_text(strip = True) or "奖励与荣誉" in sibling.get_text(strip = True):
                break
            text = sibling.get_text(strip=True)
            if text:
                direction_list.append(text)
    research_direction = "\n".join(direction_list)

    # 查找内容中邮箱
    email = None
    email_tag = soup.find('p', string=re.compile("邮箱")) if soup.find('p', string=re.compile("邮箱")) else soup.find('p', string=re.compile("邮件"))
    if email_tag:
        email_text = email_tag.get_text()
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', email_text)
        email = email_match.group(0) if email_match else "未提供"
        
    #导师概况
    profile = ""
    for description in ["教育背景","研究概况","奖励与荣誉"]:
        start_node = soup.find(lambda tag: tag.name == "p" and description in tag.get_text())
        info_list = []

        if start_node:
            for sibling in start_node.find_next_siblings():
                if sibling.find('strong') or "学术成果" in sibling.get_text(strip = True)   \
                    or "代表性论文" in sibling.get_text(strip = True) or "研究概况" in sibling.get_text(strip = True) or "奖励与荣誉" in sibling.get_text(strip = True):
                    break
                text = sibling.get_text(strip=True)
                if text:
                    info_list.append(text)
        if len(info_list):
            info_list.insert(0, description)
        profile += "\n".join(info_list) + '\n'

    # 提取中文名
    chinese_name_raw = soup.select_one("title").get_text().split('-')[0]
    chinese_name = strip_bracketed_name_content(chinese_name_raw)

    return {
        "Chinese_name": chinese_name,
        "English_name": get_english_name(chinese_name),  # 直接使用函数转换拼音
        "research_direction": research_direction,
        "email": email,
        "profile": profile,
    }

# 测试代码（方便你在本地直接测试运行）
if __name__ == "__main__":
    mentors = parse_mentor_list(url)
    print(f"成功抓取 {len(mentors)} 位导师信息！")
    # 打印前2个检查效果
    for m in mentors[:2]:
        print(f"中文名: {m['Chinese_name']} -> 英文名: {m['English_name']}")
