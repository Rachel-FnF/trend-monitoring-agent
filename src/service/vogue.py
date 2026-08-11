"""Vogue Korea (vogue.co.kr) — 패션·뷰티·리빙 카테고리.
IG 대체용 트렌드 정보 소스 (사용자 요청). WordPress 정적 HTML.
리스팅: 각 카테고리 페이지의 schema.org ItemList(ld+json)에서 제목+URL을 그대로 얻음.
본문·날짜·이미지: 각 글 페이지의 article:published_time·og:image·<p>들로 보강 + URL 영구 캐시.
각 항목: 제목·URL·날짜·카테고리(패션/뷰티/리빙)·요약·이미지.
"""
import json, re, sys, urllib.request
from html import unescape
from pathlib import Path

CATEGORIES = {
    "패션": "https://www.vogue.co.kr/fashion",
    "뷰티": "https://www.vogue.co.kr/beauty",
    "리빙": "https://www.vogue.co.kr/living",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_META_CACHE = Path(__file__).resolve().parents[2] / "src" / "data" / "source_cache" / "vogue_meta_cache.json"
_META_CACHE.parent.mkdir(parents=True, exist_ok=True)


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


def _load_cache():
    if _META_CACHE.exists():
        try:
            return json.loads(_META_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(c):
    try:
        _META_CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _fetch_meta(url: str, cache: dict) -> dict:
    """글 페이지에서 날짜·이미지·본문 추출. URL 단위 영구 캐시."""
    cached = cache.get(url)
    if isinstance(cached, dict):
        return cached
    out = {"date": "", "image": "", "body": ""}
    try:
        html = _get(url, timeout=15)
        m = re.search(r'<meta\s+property="article:published_time"\s+content="(\d{4})-(\d{2})-(\d{2})', html)
        if not m:
            m = re.search(r'"datePublished"\s*:\s*"(\d{4})-(\d{2})-(\d{2})', html)
        if m:
            out["date"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        im = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
        if im:
            out["image"] = unescape(im.group(1))
        body_parts = []
        for p_html in re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
            txt = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", p_html))).strip()
            if len(txt) > 40:
                body_parts.append(txt)
            if sum(len(x) + 1 for x in body_parts) > 1800:
                break
        out["body"] = " ".join(body_parts)[:1800]
    except Exception:
        pass
    cache[url] = out
    return out


def fetch_vogue(limit_per_cat=8):
    cache = _load_cache()
    out = []
    seen = set()
    new_fetched = 0
    for cat, list_url in CATEGORIES.items():
        try:
            html = _get(list_url, timeout=25)
        except Exception:
            continue
        entries = []
        for lm in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(lm)
            except Exception:
                continue
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                entries = data.get("itemListElement", [])
                break
        for e in entries[:limit_per_cat]:
            title = unescape((e.get("name") or "").strip())
            url = (e.get("url") or "").strip()
            if not title or not url or url in seen:
                continue
            seen.add(url)
            if url not in cache:
                new_fetched += 1
            meta = _fetch_meta(url, cache)
            out.append({
                "title": title,
                "url": url,
                "date": meta.get("date", ""),
                "category": cat,
                "excerpt": meta.get("body", "")[:1800],
                "image": meta.get("image", ""),
            })
    if new_fetched:
        _save_cache(cache)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_vogue()
    print(f"Vogue: {len(items)}건")
    for it in items[:12]:
        print(f"- {it['date']} [{it['category']}] {it['title']}")
        if it["excerpt"]:
            print(f"    └ {it['excerpt'][:80]}")
