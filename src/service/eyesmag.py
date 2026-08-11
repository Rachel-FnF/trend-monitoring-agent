"""Eyesmag (아이즈매거진, eyesmag.com) — 패션 카테고리.
스트리트 패션·스니커즈·브랜드 발매 소식 중심 매거진.
Next.js SPA지만 공개 REST API(/api/v1/posts)가 있어 리스팅·본문 모두 API로 해결.
서버가 카테고리 파라미터를 무시하므로 최신 글을 넉넉히 받아 클라이언트에서
패션 카테고리 id(444=패션, 445=뉴스, 509=슈즈)로 필터링.
content는 TIPTAP JSON → text 노드만 추출해 본문으로.
각 항목: 제목·URL·날짜·카테고리·요약·이미지·태그. (추가 페이지 fetch·캐시 불필요)
"""
import json, re, sys, urllib.request
from html import unescape

API_URL = "https://www.eyesmag.com/api/v1/posts?page=1&limit={limit}"
FASHION_CAT_IDS = {444, 445, 509}  # 패션 + 하위그룹(뉴스·슈즈) — /category/fashion/all 기준
CDN = "https://cdn.eyesmag.com/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _tiptap_text(content_json: str, cap=1800) -> str:
    """TIPTAP doc JSON에서 text 노드만 순서대로 이어붙임."""
    try:
        doc = json.loads(content_json)
    except Exception:
        return ""
    parts = []
    total = 0

    def walk(node):
        nonlocal total
        if total > cap:
            return
        if isinstance(node, dict):
            t = node.get("text")
            if isinstance(t, str) and t.strip():
                parts.append(t.strip())
                total += len(t) + 1
            for child in node.get("content", []) or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(doc)
    return re.sub(r"\s+", " ", " ".join(parts))[:cap]


def fetch_eyesmag(limit=15, scan=60):
    req = urllib.request.Request(API_URL.format(limit=scan),
                                 headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    data = json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace"))

    out = []
    for it in data.get("items", []):
        pid, name = it.get("id"), (it.get("name") or "").strip()
        if not pid:
            continue
        cat_ids = {c.get("id") for c in (it.get("categories") or [])}
        if not (cat_ids & FASHION_CAT_IDS):
            continue
        thumb = it.get("thumbnail") or ""
        if thumb and not thumb.startswith("http"):
            thumb = CDN + thumb.lstrip("/")
        cats = [c.get("name", "") for c in (it.get("categories") or []) if c.get("name")]
        body = _tiptap_text(it.get("content") or "")
        excerpt = (it.get("excerpt") or "").strip()
        if len(body) > len(excerpt):
            excerpt = body
        out.append({
            "title": unescape((it.get("title") or "").strip()),
            "url": f"https://www.eyesmag.com/posts/{pid}/{name}" if name else f"https://www.eyesmag.com/posts/{pid}",
            "date": (it.get("publishedAt") or "")[:10],
            "category": ", ".join(cats[:2]),
            "excerpt": excerpt[:1800],
            "image": thumb,
            "tags": it.get("tags") or [],
        })
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_eyesmag()
    print(f"Eyesmag: {len(items)}건")
    for it in items[:8]:
        print(f"- {it['date']} [{it['category']}] {it['title']}")
        print(f"    → {it['url']}")
        if it["excerpt"]:
            print(f"    └ {it['excerpt'][:80]}")
