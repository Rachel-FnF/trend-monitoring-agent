"""대학내일 20대연구소 — /Column 페이지 정적 스크랩 (RSS 없음, 공개·로그인불필요).
16년 축적 세대 연구 콘텐츠. '트렌드'보다는 '검증된 세대 분석' — 다이제스트의 '참고 레퍼런스'·
'모니터링 포인트' 보강용. 첫 화면 12건만 가져온다(SPA 페이지네이션은 클라이언트 JS).
각 항목: 유형(뉴스레터/인사이트 칼럼 등)·제목·발행일·URL.
"""
import re, sys, urllib.request
from html import unescape

LIST_URL = "https://www.20slab.org/Column"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def fetch_slab20(limit=12):
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    body = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", errors="replace")

    out = []
    for m in re.finditer(r'<a href="/Archives/(\d+)">(.*?)</a>', body, re.DOTALL):
        aid, block = m.group(1), m.group(2)
        type_m = re.search(r'<div class="type[^"]*">([^<]+)</div>', block)
        title_m = re.search(r'<div class="title[^"]*">([^<]+)</div>', block)
        date_m = re.search(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", block)
        img_m = re.search(r'<img[^>]+src="([^"]+)"', block)
        if not title_m:
            continue
        out.append({
            "id": aid,
            "type": unescape(type_m.group(1).strip()) if type_m else "",
            "title": unescape(title_m.group(1).strip()),
            "date": f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}" if date_m else "",
            "url": f"https://www.20slab.org/Archives/{aid}",
            "image": img_m.group(1) if img_m else "",
        })
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_slab20()
    print(f"20대연구소 칼럼: {len(items)}건")
    for it in items:
        print(f"- {it['date']} [{it['type']}] {it['title']}  ({it['url']})")
