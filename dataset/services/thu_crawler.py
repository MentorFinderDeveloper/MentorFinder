import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
# BASE_HEADERS = {
#     "User-Agent": "Mozilla/5.0"
# }
url = "https://www.cs.tsinghua.edu.cn/szzk/jzgml.htm"
en_url = "https://www.cs.tsinghua.edu.cn/csen/Faculty/Full_time_Faculty.htm"
BASE_HEADERS = {
    # 1. 最重要：告诉服务器你是个真实的 Chrome 浏览器
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    
    # 2. 告诉服务器你接受的语言（防止中文乱码）
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    
    # 3. 告诉服务器是从哪里来的（有时需要，建议带上）
    "Host": "www.cs.tsinghua.edu.cn",
    
    # 4. Cookie（如果网页需要登录或者有访问限制，就带上这行）
    "Cookie": "JSESSIONID=9BADD2F3B34224773C1E64E4F391F457.yunxing21"
}
def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=BASE_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text

def parse_mentor_list(ch_url: str,en_url: str) -> list[dict]:
    html = fetch_html(ch_url)
    enhtml = fetch_html(en_url)
    soup = BeautifulSoup(html, "lxml")
    ensoup = BeautifulSoup(enhtml, "lxml")

    mentors = []
    for item ,enitem in zip(soup.select("h2"),ensoup.select("h2")):
        relative_url = item.select_one("a")["href"]
        detail_url = urljoin(url,relative_url)
        en_relative_url = enitem.select_one("a")["href"]
        
        en_detail_url = urljoin(en_url,en_relative_url)
        mentors.append(parse_mentor_detail(detail_url,en_detail_url))
    return mentors
def parse_mentor_detail(detail_url: str,en_detail_url: str) -> dict:
    html = fetch_html(detail_url)
    soup = BeautifulSoup(html, "lxml")
    enhtml = fetch_html(en_detail_url)
    ensoup = BeautifulSoup(enhtml, "lxml")
    start_node = soup.find(lambda tag: tag.name == "p" and "研究领域" in tag.get_text())
    direction_list = []

    if start_node:
        # 2. 遍历它后面的所有“兄弟”标签
        for sibling in start_node.find_next_siblings():
                    
            # 3. 停止条件：如果遇到了下一个标题（即包含 strong 的 p），就停止
            if sibling.find('strong') or sibling.name=='h4' or "研究概况" in sibling.get_text(strip = True)  \
                or "讲授课程" in sibling.get_text(strip = True) or "工作履历" in sibling.get_text(strip = True):
                break
                    
            # 4. 提取内容：把中间的 p 标签文本存起来
            text = sibling.get_text(strip=True)
            if text:
                direction_list.append(text)
    research_direction = "\n".join(direction_list)

    # 查找内容中邮箱
    email = None
    email_tag = soup.find('p', string=re.compile("邮箱")) if soup.find('p', string=re.compile("邮箱")) else soup.find('p', string=re.compile("邮件"))
    if email_tag:
        email_text = email_tag.get_text()
    # 正则匹配邮箱模式
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', email_text)
        email = email_match.group(0) if email_match else "未提供"
    #导师概况
    profile = ""
    for description in ["教育背景","研究概况","奖励与荣誉"]:
        start_node = soup.find(lambda tag: tag.name == "p" and description in tag.get_text())

        info_list = []

        if start_node:
            # 2. 遍历它后面的所有“兄弟”标签
            for sibling in start_node.find_next_siblings():
                
                # 3. 停止条件：如果遇到了下一个标题（即包含 strong 的 p），就停止
                if sibling.find('strong') or "学术成果" in sibling.get_text(strip = True)   \
                    or "代表性论文" in sibling.get_text(strip = True):
                    break
                
                # 4. 提取内容：把中间的 p 标签文本存起来
                text = sibling.get_text(strip=True)
                if text:
                    info_list.append(text)
        if len(info_list):
            info_list.insert(0,description)
        profile += "\n".join(info_list)+'\n'
    #
    return {
        "Chinese_name": soup.select_one("title").get_text().split('-')[0] if soup.select_one("title").get_text().split('-')[0] else "",
        "English_name": ensoup.select_one("title").get_text().split('-')[0] if ensoup.select_one("title").get_text().split('-')[0] else "",
        "research_direction": research_direction,
        "email":email,
        "profile": profile,
    }
