"""고구마팜 — 트렌드 카테고리 RSS 수집 (공개·로그인불필요).
MZ 트렌드·밈 콘텐츠. 캐릿과 결이 같은 큐레이션 미디어라 직접 교차검증 신호로 쓰기 좋다.
각 항목: 제목·URL·발행일·작성자·카테고리·요약(본문 첫 단락).
"""
import re, sys, urllib.request, xml.etree.ElementTree as ET
from html import unescape

RSS_URL = "https://gogumafarm.kr/category/trends/feed/"
NS = {"dc": "http://purl.org/dc/elements/1.1/", "content": "http://purl.org/rss/1.0/modules/content/"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# 이모지/시스템 아이콘 도메인 — 본문 이미지로 잡으면 안 됨
_IMG_BLACKLIST = ("s.w.org/images/core/emoji", "wp-includes/images/smilies")

_MONTHS = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
           "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}


def _rfc822_to_iso(s: str) -> str:
    # "Fri, 29 May 2026 04:00:00 +0000" → "2026-05-29"
    m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", s or "")
    if not m:
        return ""
    d, mo, y = m.group(1), _MONTHS.get(m.group(2), ""), m.group(3)
    return f"{y}-{mo}-{int(d):02d}" if mo else ""


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _first_image(html: str) -> str:
    """본문 HTML(content:encoded)에서 첫 본문 이미지 URL. 이모지/시스템 아이콘은 스킵."""
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html or ""):
        url = m.group(1)
        if any(b in url for b in _IMG_BLACKLIST):
            continue
        return url
    return ""


def fetch_gogumafarm(limit=20):
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": UA})
    xml_bytes = urllib.request.urlopen(req, timeout=25).read()
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        date_iso = _rfc822_to_iso(item.findtext("pubDate") or "")
        author = (item.findtext("dc:creator", default="", namespaces=NS) or "").strip()
        cats = [c.text.strip() for c in item.findall("category") if c is not None and c.text]
        desc = _strip_html(item.findtext("description") or "")
        content_html = item.findtext("content:encoded", default="", namespaces=NS) or ""
        image = _first_image(content_html)
        out.append({
            "title": title, "url": link, "date": date_iso,
            "author": author, "categories": cats, "excerpt": desc[:600],
            "image": image,
        })
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_gogumafarm()
    print(f"고구마팜 트렌드: {len(items)}건")
    for it in items[:10]:
        print(f"- {it['date']} | {it['title']} (by {it['author']}, cat:{','.join(it['categories'][:3])})")
        print(f"    └ {it['excerpt'][:120]}")
