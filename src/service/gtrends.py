"""Google Trends — 한국(KR) 일일 급상승 검색어 수집 (공개 RSS, 로그인/키 불필요).
각 항목: 검색어(term) · 대략 트래픽(traffic) · 관련 뉴스 제목(news) — 뉴스 제목이 '왜 뜨나' 단서가 된다.
"""
import sys, urllib.request, xml.etree.ElementTree as ET

RSS_URL = "https://trends.google.com/trending/rss?geo=KR"
NS = {"ht": "https://trends.google.com/trending/rss"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def fetch_google_trends_kr(limit=20):
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": UA})
    xml_bytes = urllib.request.urlopen(req, timeout=25).read()
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        term = (item.findtext("title") or "").strip()
        if not term:
            continue
        traffic = (item.findtext("ht:approx_traffic", default="", namespaces=NS) or "").strip()
        news = []
        for n in item.findall("ht:news_item/ht:news_item_title", NS):
            if n is not None and n.text:
                news.append(n.text.strip())
        out.append({"term": term, "traffic": traffic, "news": news[:2]})
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_google_trends_kr()
    print(f"google_trends KR: {len(items)}건")
    for it in items[:12]:
        print(f"- {it['term']} ({it['traffic']}) | 뉴스: {' / '.join(it['news'])[:80]}")
