"""Insight (인사이트, insight.co.kr) — /trend 카테고리.
패션·뷰티·셀럽·콘텐츠·이슈 중심 뉴스 큐레이션.
정적 HTML(schema.org NewsArticle 마크업)이라 깔끔하게 파싱.
RSS 없음 → /trend listing 페이지 직접 파싱.
각 항목: 제목·URL·날짜·이미지·요약.
"""
import re, sys, urllib.request
from html import unescape

LIST_URL = "https://www.insight.co.kr/trend/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _parse_date(s: str) -> str:
    # "2026년 06월 02일" 또는 "2026-06-02" 또는 "2026.06.02"
    m = re.search(r"(\d{4})[년.\-]\s*(\d{1,2})[월.\-]\s*(\d{1,2})", s or "")
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def fetch_insight(limit=15):
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    body = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")

    # 카드 패턴: <article class="main-section-list-item" ...> ... </article>
    article_re = re.compile(
        r'<article\s+class="main-section-list-item[^"]*"[^>]*>(?P<inner>.*?)</article>',
        re.DOTALL,
    )

    out = []
    seen = set()
    for m in article_re.finditer(body):
        inner = m.group("inner")
        url_m = re.search(r'<a\s+href="(https?://www\.insight\.co\.kr/news/\d+)"', inner)
        if not url_m:
            continue
        url = url_m.group(1)
        if url in seen:
            continue
        seen.add(url)

        # 제목 — itemprop="headline" 안 <a> 내부
        title_m = re.search(
            r'<h2[^>]+itemprop="headline"[^>]*>\s*<a[^>]*>\s*(.*?)\s*</a>\s*</h2>',
            inner, re.DOTALL,
        )
        title = _clean(title_m.group(1)) if title_m else ""
        if not title:
            # fallback — alt text of figure img
            alt_m = re.search(r'<img[^>]+alt="([^"]+)"', inner)
            title = unescape(alt_m.group(1)).strip() if alt_m else ""

        # 이미지 — img.insight.co.kr 도메인
        img_m = re.search(r'<img\s+src="(https?://img\.insight\.co\.kr/[^"]+)"', inner)
        image = img_m.group(1) if img_m else ""

        # 날짜 — datePublished 또는 별도 시간 표기. listing엔 명시적 날짜 없을 수 있음
        date_m = re.search(r'datePublished"[^>]*content="([^"]+)"', inner)
        date_iso = _parse_date(date_m.group(1)) if date_m else ""

        # 요약 — description meta 또는 figcaption
        cap_m = re.search(r'<figcaption[^>]*>\s*(.*?)\s*</figcaption>', inner, re.DOTALL)
        excerpt = _clean(cap_m.group(1)) if cap_m else ""
        if excerpt == title:
            excerpt = ""

        out.append({
            "title": title or "(제목 없음)",
            "url": url,
            "date": date_iso,
            "image": image,
            "excerpt": excerpt[:300],
        })
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_insight()
    print(f"Insight: {len(items)}건")
    for it in items[:8]:
        print(f"- {it['date']} {it['title']}")
        print(f"    → {it['url']}")
        if it["image"]:
            print(f"    img: {it['image'][:90]}")
