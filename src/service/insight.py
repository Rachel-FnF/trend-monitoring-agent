"""Insight (인사이트, insight.co.kr) — /trend 카테고리.
패션·뷰티·셀럽·콘텐츠·이슈 중심 뉴스 큐레이션.
정적 HTML(schema.org NewsArticle 마크업)이라 깔끔하게 파싱.
RSS 없음 → /trend listing 페이지 직접 파싱.
본문은 각 글 페이지의 og:description(뉴스 본문 요약)으로 보강 + 영구 캐시.
각 항목: 제목·URL·날짜·이미지·요약·본문.
"""
import json, re, sys, urllib.request
from html import unescape
from pathlib import Path

LIST_URL = "https://www.insight.co.kr/trend/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_BODY_CACHE = Path(__file__).resolve().parents[2] / "src" / "data" / "source_cache" / "insight_body_cache.json"
_BODY_CACHE.parent.mkdir(parents=True, exist_ok=True)


def _load_cache():
    if _BODY_CACHE.exists():
        try:
            return json.loads(_BODY_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(c):
    try:
        _BODY_CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


_OG_DESC_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
]


def _fetch_body(url: str, cache: dict) -> str:
    """뉴스 본문 — og:description 우선(보통 1~2문장 요약), 부족하면 첫 <p> 보강."""
    if url in cache:
        return cache[url]
    body = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace")
        for pat in _OG_DESC_PATTERNS:
            m = pat.search(html)
            if m:
                body = unescape(m.group(1)).strip()
                break
    except Exception:
        pass
    cache[url] = body
    return body


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

    # 카드 패턴: 모든 <article> 태그 — class 무관 (헤드라인+리스트 둘 다 포함).
    # 내부에 /news/숫자 anchor가 있는 article만 카드로 처리.
    article_re = re.compile(
        r'<article[^>]*>(?P<inner>.*?)</article>',
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

        # 날짜 — listing엔 datePublished 메타 없음. 이미지 URL path에서 추출:
        # img.insight.co.kr/static/YYYY/MM/DD/...
        date_iso = ""
        if image:
            dm = re.search(r"/static/(\d{4})/(\d{2})/(\d{2})/", image)
            if dm:
                date_iso = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
        # fallback: 혹시 datePublished 메타가 있으면 우선
        date_meta_m = re.search(r'datePublished"[^>]*content="([^"]+)"', inner)
        if date_meta_m:
            date_iso = _parse_date(date_meta_m.group(1)) or date_iso

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

    # 본문 보강 — 각 글 페이지 og:description 가져옴(영구 캐시)
    cache = _load_cache()
    new_fetched = 0
    for it in out:
        if it["url"] not in cache:
            new_fetched += 1
        body = _fetch_body(it["url"], cache)
        if body and len(body) > len(it.get("excerpt", "")):
            it["excerpt"] = body[:600]
    if new_fetched:
        _save_cache(cache)
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
