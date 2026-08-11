"""패션비즈 (fashionbiz.co.kr) — 패션 업계 전문 미디어.
Next.js(App Router·RSC)라 리스팅 페이지는 클라이언트 렌더링 → 파싱 불가.
대신 server-sitemap.xml이 최신 기사 ~28건을 lastmod와 함께 제공 → 이걸 리스팅으로 사용.
기사 페이지는 RSC payload에 articleDetail(제목·mainImg·openResDate)과 본문 HTML이
서버렌더로 들어있어 정적 파싱 가능. 기사 단위 영구 캐시.

⚠️ 한계: 웹에서 기사별 카테고리(여성복/캐주얼/스포츠 등) 메타를 노출하지 않아
카테고리 필터링 불가 → 전체 최신 기사를 수집 (요청 카테고리 외 글도 포함될 수 있음).
일부 유료(readPermission) 기사는 본문 앞부분만 잡힐 수 있음.
각 항목: 제목·URL·날짜·요약·이미지.
"""
import json, re, sys, urllib.request, gzip, io
from html import unescape
from pathlib import Path

SITEMAP_URL = "https://fashionbiz.co.kr/server-sitemap.xml"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_CACHE = Path(__file__).resolve().parents[2] / "src" / "data" / "source_cache" / "fashionbiz_body_cache.json"
_CACHE.parent.mkdir(parents=True, exist_ok=True)


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9", "Accept-Encoding": "gzip"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


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


def _rsc_parts(page_html: str) -> list:
    """self.__next_f.push([1,"..."]) 조각들을 unicode escape 풀어서 리스트로."""
    parts = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page_html, re.DOTALL)
    return [
        p.encode("utf-8").decode("unicode_escape", "ignore")
         .encode("latin-1", "ignore").decode("utf-8", "ignore")
        for p in parts]


def _fetch_article(url: str, cache: dict) -> dict:
    aid = url.rstrip("/").rsplit("/", 1)[-1]
    cached = cache.get(aid)
    if isinstance(cached, dict):
        return cached
    out = {"title": "", "date": "", "image": "", "body": ""}
    try:
        html = _get(url)
        parts = _rsc_parts(html)
        rsc = "".join(parts)
        # articleDetail 블록 — 제목·대표이미지·공개일
        # 제목에 \" 이스케이프 따옴표가 있어도 끝까지 매칭 (예: 부고 기사 '…대표 "별세"')
        dm = re.search(r'"articleDetail","cts_id":\d+,"title":"((?:[^"\\]|\\.)+)"', rsc)
        if dm:
            out["title"] = unescape(re.sub(r"\\(.)", r"\1", dm.group(1)))
        im = re.search(r'"mainImg":"(https?://[^"]+)"', rsc)
        if im:
            out["image"] = im.group(1)
        rd = re.search(r'"openResDate":"(\d{4})-(\d{2})-(\d{2})', rsc)
        if rd:
            out["date"] = f"{rd.group(1)}-{rd.group(2)}-{rd.group(3)}"
        # og 메타 fallback
        if not out["title"]:
            om = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
            if om:
                out["title"] = unescape(om.group(1))
        if not out["image"]:
            om = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            if om:
                out["image"] = unescape(om.group(1))
        # 본문 — articleDetail의 "text":"$<ref>" 가 가리키는 T-청크(<ref>:T<hex길이>,본문HTML)
        # T헤더의 hex = 본문 UTF-8 바이트 길이 → 그만큼 잘라냄 (push 조각 경계 무관)
        body_html = ""
        ad_i = rsc.find('"articleDetail"')
        seg = rsc[ad_i:ad_i + 2000] if ad_i >= 0 else rsc
        rm = re.search(r'"text":"\$([0-9a-f]+)"', seg) or re.search(r'"text":"\$([0-9a-f]+)"', rsc)
        if rm:
            rid = rm.group(1)
            hm = re.search(rf'(?:^|[^0-9a-f]){rid}:T([0-9a-f]+),', rsc)
            if hm:
                blen = int(hm.group(1), 16)
                body_html = rsc[hm.end():].encode("utf-8")[:blen].decode("utf-8", "ignore")
        if not body_html:
            bm = re.search(r'"content":"((?:[^"\\]|\\.){200,}?)"', rsc)
            body_html = bm.group(1) if bm else ""
        if not body_html:
            body_html = " ".join(re.findall(r"<p>(.{40,}?)</p>", rsc)[:20])
        txt = re.sub(r"<[^>]+>", " ", body_html)
        txt = unescape(txt).replace("&nbsp;", " ")
        txt = re.sub(r"https?://\S+", " ", txt)  # 이미지 위주 기사의 bare URL 잔여물 제거
        out["body"] = re.sub(r"\s+", " ", txt).strip()[:1800]
    except Exception:
        pass
    # 파싱 실패분(제목 또는 본문 없음)은 캐시하지 않음 → 다음 실행 때 재시도
    if out["title"] and out["body"]:
        cache[aid] = out
    return out


def fetch_fashionbiz(limit=50):
    xml = _get(SITEMAP_URL)
    entries = re.findall(r"<url>\s*<loc>([^<]+)</loc>\s*(?:<lastmod>([^<]*)</lastmod>)?", xml)
    if not entries:
        locs = re.findall(r"<loc>([^<]+)</loc>", xml)
        mods = re.findall(r"<lastmod>([^<]*)</lastmod>", xml)
        entries = list(zip(locs, mods + [""] * (len(locs) - len(mods))))

    cache = _load_cache()
    out = []
    new_fetched = 0
    for url, lastmod in entries[:limit]:
        if "/article/" not in url:
            continue
        aid = url.rstrip("/").rsplit("/", 1)[-1]
        if aid not in cache:
            new_fetched += 1
        art = _fetch_article(url, cache)
        if not art.get("title"):
            continue
        out.append({
            "title": art["title"],
            "url": url,
            "date": art.get("date") or (lastmod or "")[:10],
            "excerpt": art.get("body", "")[:1800],
            "image": art.get("image", ""),
        })
    if new_fetched:
        _save_cache(cache)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_fashionbiz()
    print(f"패션비즈: {len(items)}건")
    for it in items[:8]:
        print(f"- {it['date']} {it['title']}")
        print(f"    → {it['url']}")
        if it["excerpt"]:
            print(f"    └ {it['excerpt'][:80]}")
