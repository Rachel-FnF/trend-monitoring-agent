"""마케팅레시피 (maily.so/marketingrecipe) — 공식 RSS 수집 (공개·로그인불필요).
Z세대 마케팅 인사이트·F&B·트렌드 사례. '한-입 트렌드' '마슐랭 가이드' 'Zㅜ방장의 마케팅 Talk' 등.
캐릿/고구마팜이 '무엇이 뜨나'라면 이건 '마케터가 어떻게 활용했나' — F&F 실행 인사이트용.

이미지: RSS에 없어서 각 글 페이지의 og:image 메타 태그를 별도 fetch. URL 단위 캐시로
한 번 받은 글은 재fetch 안 함(매일 빌드 시 새 글만 fetch).
각 항목: 제목·URL·발행일·카테고리·부제·이미지.
"""
import json, re, sys, urllib.request, xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path

RSS_URL = "https://maily.so/marketingrecipe/feed"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# og:image 캐시 (URL → image URL). 한 번 fetch한 글은 재사용.
_CACHE_PATH = Path(__file__).resolve().parents[2] / "src" / "data" / "maily_image_cache.json"

_MONTHS = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
           "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}


def _rfc822_to_iso(s: str) -> str:
    m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", s or "")
    if not m:
        return ""
    d, mo, y = m.group(1), _MONTHS.get(m.group(2), ""), m.group(3)
    return f"{y}-{mo}-{int(d):02d}" if mo else ""


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", unescape(s)).strip()


def _load_cache():
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(c):
    try:
        _CACHE_PATH.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


_IMG_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', re.IGNORECASE),
    re.compile(r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
]


def _fetch_og_image(url: str, cache: dict) -> str:
    if url in cache:
        return cache[url]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace")
        for pat in _IMG_PATTERNS:
            m = pat.search(html)
            if m:
                cache[url] = m.group(1)
                return m.group(1)
    except Exception:
        pass
    cache[url] = ""  # 못 찾아도 캐시(다음에 재시도 안 함)
    return ""


def fetch_maily_marketingrecipe(limit=15):
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": UA})
    xml_bytes = urllib.request.urlopen(req, timeout=25).read()
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append({
            "title": title, "url": link,
            "date": _rfc822_to_iso(item.findtext("pubDate") or ""),
            "category": (item.findtext("category") or "").strip(),
            "subtitle": _strip_html(item.findtext("description") or "")[:400],
        })
        if len(out) >= limit:
            break

    # og:image 보강 (캐시 hit는 즉시 반환, 새 URL만 fetch)
    cache = _load_cache()
    new_fetched = 0
    for it in out:
        if it["url"] not in cache:
            new_fetched += 1
        it["image"] = _fetch_og_image(it["url"], cache)
    if new_fetched:
        _save_cache(cache)

    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_maily_marketingrecipe()
    print(f"마케팅레시피: {len(items)}건")
    for it in items[:10]:
        print(f"- {it['date']} [{it['category']}] {it['title']}")
        print(f"    └ {it['subtitle']}")
