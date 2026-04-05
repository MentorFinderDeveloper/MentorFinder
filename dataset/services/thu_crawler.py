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
    