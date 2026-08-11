"""뉴닉 (newneek.co) — 웹 '트렌드' 카테고리.
뉴스레터(고슴이의 비트)의 단편 요약을 보완하는 웹 섹션 (사용자 요청).
Next.js SPA + 카테고리 필터가 비공개 쿼리라 리스팅만 Playwright로 렌더링해서
/post/<id> 링크를 수집하고, 상세는 공개 REST(api.newneek.co/product/v1/articles/<id>)로
가져옴 — contentPlain(전문 텍스트)·dtPublished·썸네일 포함. 기사 단위 영구 캐시.
⚠️ 자체 sync_playwright()를 열므로 collect.py의 캐릿 with-block 밖에서 호출할 것.
각 항목: 제목·URL·날짜·요약·이미지.
"""
import json, re, sys, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

LIST_URL = "https://newneek.co/category/trend"
API_URL = "https://api.newneek.co/product/v1/articles/{id}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_CACHE = Path(__file__).resolve().parents[2] / "src" / "data" / "source_cache" / "newneek_body_cache.json"
_CACHE.parent.mkdir(parents=True, exist_ok=True)


def _load_cache():
    if _CACHE.exists():
        try:
            return json.loads(_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(c):
    try:
        _CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _list_post_ids():
    """카테고리 페이지를 headless 렌더링해 기사 링크를 등장 순서대로 수집.
    카드 href 형식: /@<핸들>/article/<id> (구형 /post/<id>도 대응)."""
    entries = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, locale="ko-KR",
                                viewport={"width": 1366, "height": 900})
        page.goto(LIST_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector('a[href*="/article/"], a[href^="/post/"]', timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2000)
        hrefs = page.eval_on_selector_all(
            'a[href]', "ns => ns.map(a => a.getAttribute('href'))")
        browser.close()
    seen = set()
    for h in hrefs or []:
        m = re.match(r"(/@[\w.\-]+/article|/post)/(\d+)", h or "")
        if m and m.group(2) not in seen:
            seen.add(m.group(2))
            entries.append((m.group(2), f"https://newneek.co{m.group(0)}"))
    return entries


def _fetch_detail(aid: str, cache: dict) -> dict:
    cached = cache.get(aid)
    if isinstance(cached, dict):
        return cached
    out = {"title": "", "date": "", "excerpt": "", "image": ""}
    try:
        req = urllib.request.Request(API_URL.format(id=aid),
                                     headers={"User-Agent": UA, "Accept": "application/json"})
        a = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace"))
        out["title"] = (a.get("title") or "").strip()
        out["date"] = (a.get("dtPublished") or "")[:10]
        desc = (a.get("description") or "").strip()
        plain = re.sub(r"\s+", " ", a.get("contentPlain") or "").strip()
        out["excerpt"] = (plain if len(plain) > len(desc) else desc)[:1800]
        thumb = (a.get("meta") or {}).get("thumbnail") or {}
        out["image"] = thumb.get("url") or ""
    except Exception:
        pass
    cache[aid] = out
    return out


def fetch_newneek(limit=15):
    entries = _list_post_ids()
    cache = _load_cache()
    out = []
    new_fetched = 0
    for aid, url in entries[:limit]:
        if aid not in cache:
            new_fetched += 1
        d = _fetch_detail(aid, cache)
        if not d.get("title"):
            continue
        out.append({
            "title": d["title"],
            "url": url,
            "date": d.get("date", ""),
            "excerpt": d.get("excerpt", ""),
            "image": d.get("image", ""),
        })
    if new_fetched:
        _save_cache(cache)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_newneek()
    print(f"뉴닉 트렌드: {len(items)}건")
    for it in items[:8]:
        print(f"- {it['date']} {it['title'][:60]}")
        print(f"    → {it['url']}")
        if it["excerpt"]:
            print(f"    └ {it['excerpt'][:80]}")
