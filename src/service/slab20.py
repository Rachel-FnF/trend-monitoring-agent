"""대학내일 20대연구소 — /Column 페이지 정적 스크랩 (RSS 없음, 공개·로그인불필요).
16년 축적 세대 연구 콘텐츠. '트렌드'보다는 '검증된 세대 분석' — 다이제스트의 '참고 레퍼런스'·
'모니터링 포인트' 보강용. 첫 화면 12건만 가져온다(SPA 페이지네이션은 클라이언트 JS).

본문: listing에는 본문이 없어서 각 글 페이지(/Archives/{id})의 <p> 본문 추출 +
URL 단위 영구 캐시. 새 글만 fetch.
각 항목: 유형(뉴스레터/인사이트 칼럼 등)·제목·발행일·URL·이미지·본문.
"""
import json, re, sys, urllib.request
from html import unescape
from pathlib import Path

LIST_URL = "https://www.20slab.org/NewsLetter"  # 사용자 요청: 뉴스레터 전용 페이지
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_BODY_CACHE = Path(__file__).resolve().parents[2] / "src" / "data" / "source_cache" / "slab20_body_cache.json"
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


def _fetch_body(url: str, cache: dict) -> str:
    """글 페이지의 <p> 본문 합쳐 1800자 이내. 캐시 hit면 즉시."""
    if url in cache:
        return cache[url]
    body = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace")
        parts = []
        for p_html in re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
            txt = re.sub(r"<[^>]+>", "", p_html)
            txt = unescape(re.sub(r"\s+", " ", txt)).strip()
            if len(txt) > 50:
                parts.append(txt)
            if sum(len(x) + 1 for x in parts) > 1800:
                break
        body = " ".join(parts)[:1800]
    except Exception:
        pass
    cache[url] = body
    return body


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

    # 본문 보강 — 각 글 페이지에서 <p> 본문 1800자 이내 추출 + 캐시
    cache = _load_cache()
    new_fetched = 0
    for it in out:
        if it["url"] not in cache:
            new_fetched += 1
        it["excerpt"] = _fetch_body(it["url"], cache)
    if new_fetched:
        _save_cache(cache)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_slab20()
    print(f"20대연구소 칼럼: {len(items)}건")
    for it in items:
        print(f"- {it['date']} [{it['type']}] {it['title']}  ({it['url']})")
