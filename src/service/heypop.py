"""HeyPop (헤이팝, heypop.kr) — 팝업·공간·디자인 트렌드 미디어.
"매일 새로운 팝업 및 공간 트렌드와 디자인 스폿, 브랜드 이슈" 컨셉.
카테고리: Style·Gourmet·Culture·Tech·News·Exhibition 등.
/trend 페이지 정적 HTML. <a class="title"> anchor 기준으로 잡고, 위쪽에서 이미지,
아래쪽에서 요약·태그 추출. 본문은 각 글 페이지에서 <p> 합쳐 보강(영구 캐시).
각 항목: 제목·URL·날짜(이미지 파일명에서 추출)·이미지·요약·본문·카테고리 태그.
"""
import json, re, sys, urllib.request
from html import unescape
from pathlib import Path

LIST_URL = "https://heypop.kr/n/?c=POP-UP"  # 사용자 요청: POP-UP 카테고리만
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_BODY_CACHE = Path(__file__).resolve().parents[2] / "src" / "data" / "source_cache" / "heypop_body_cache.json"
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
    """글 페이지 <p> 본문 합쳐 1800자 이내. 캐시 hit면 즉시."""
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


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fetch_heypop(limit=15):
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    body = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")

    # content-list 영역만 (메뉴·헤더의 노이즈 제거)
    content_m = re.search(r'<div[^>]+class="[^"]*content-list[^"]*"[^>]*>(.*?)<footer', body, re.DOTALL)
    scope = content_m.group(1) if content_m else body

    # title anchor 기준
    title_re = re.compile(
        r'<a\s+href="(?:https://heypop\.kr)?/n/(\d+)/?"\s+class="title">\s*(.+?)\s*</a>',
        re.DOTALL,
    )

    out = []
    seen = set()
    for m in title_re.finditer(scope):
        aid = m.group(1)
        if aid in seen:
            continue
        seen.add(aid)
        title = _clean(m.group(2))
        if not title:
            continue
        pos = m.start()

        # 위쪽 800자에서 이미지 (해당 카드의 이미지)
        before = scope[max(0, pos - 800):pos]
        # 마지막 img가 그 카드의 이미지
        img_matches = re.findall(r'<img[^>]+src="([^"]+)"', before)
        image = img_matches[-1] if img_matches else ""

        # 아래 1000자에서 요약·태그
        after = scope[pos:pos + 1000]
        desc_m = re.search(r'<p\s+class="simple-desc">\s*([^<]+?)\s*</p>', after)
        excerpt = unescape(desc_m.group(1)).strip() if desc_m else ""
        tag_matches = re.findall(r'<a\s+href="[^"]*\?c=[^"]+"\s+class="tag">\s*([^<]+?)\s*</a>', after)
        categories = [unescape(t).strip() for t in tag_matches]

        # 날짜 — 이미지 파일명에 'YYYYMMDD_' 패턴이 있어 거기서 추출.
        date_iso = ""
        if image:
            dm = re.search(r"(\d{4})(\d{2})(\d{2})_\d", image)
            if dm:
                date_iso = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
        out.append({
            "title": title,
            "url": f"https://heypop.kr/n/{aid}",
            "date": date_iso,
            "image": image,
            "excerpt": excerpt[:300],
            "categories": categories,
        })
        if len(out) >= limit:
            break

    # 본문 보강 — 각 글 페이지 <p> 합쳐 1800자
    cache = _load_cache()
    new_fetched = 0
    for it in out:
        if it["url"] not in cache:
            new_fetched += 1
        body = _fetch_body(it["url"], cache)
        if body and len(body) > len(it.get("excerpt", "")):
            it["excerpt"] = body
    if new_fetched:
        _save_cache(cache)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_heypop()
    print(f"HeyPop: {len(items)}건")
    for it in items[:10]:
        cats = ",".join(it.get("categories", [])[:3])
        print(f"- [{cats}] {it['title']}")
        if it["excerpt"]:
            print(f"    └ {it['excerpt'][:80]}")
        if it["image"]:
            print(f"    img: {it['image'][:90]}")
