"""The Edit (디에디트, the-edit.co.kr) — 라이프스타일·소비 큐레이션.
"사는 재미가 없으면 사는 재미라도" 컨셉의 에디토리얼 미디어.
카테고리: STYLE·TECH·EAT·LIFE·CULTURE (제품 추천·트렌드 분석).
RSS 없음 → 홈페이지 정적 HTML. URL id 추출 후 각 id 주변 context에서 정보 잡음.
각 항목: 제목·URL·날짜·카테고리·요약·이미지.
"""
import re, sys, urllib.request
from html import unescape

LIST_URL = "https://the-edit.co.kr/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _parse_date(s: str) -> str:
    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", s or "")
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def fetch_the_edit(limit=15):
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    body = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")

    # 1) 모든 article URL id 추출 (등장 순서 유지)
    ids = []
    seen = set()
    for m in re.finditer(r'https://the-edit\.co\.kr/(\d+)(?=["/])', body):
        aid = m.group(1)
        if aid not in seen:
            seen.add(aid)
            ids.append(aid)

    out = []
    for aid in ids:
        # 카드 단위 정확 추출 — title 위쪽 약 2500자 / 아래쪽 약 600자가 한 카드 영역
        # url의 anchor 위치 찾기
        anchor_re = re.compile(rf'<a\s+href="https://the-edit\.co\.kr/{aid}"[^>]*>\s*([^<]+?)\s*</a>')
        am = anchor_re.search(body)
        if not am:
            continue
        title = unescape(am.group(1)).strip()
        if not title or len(title) < 3:
            continue
        pos = am.start()

        # 카드 위쪽 컨텍스트
        before = body[max(0, pos - 3000):pos]
        # 카테고리 = 위쪽 마지막 h4.meta
        cat_matches = re.findall(r'<h4\s+class="meta">\s*([^<]+?)\s*</h4>', before)
        category = unescape(cat_matches[-1]).strip() if cat_matches else ""
        # 이미지 = 위쪽 마지막 data-lazy-src (그 카드의 이미지)
        img_matches = re.findall(r'data-lazy-src="(https?://the-edit\.co\.kr/wp-content/uploads/[^"]+?)"', before)
        # ?lt; 카드 사이 거리가 너무 멀면 무관할 수 있어 — 마지막 매칭의 위치가 anchor 위치에서 4000자 이내면 채택
        image = ""
        if img_matches:
            last_img = img_matches[-1]
            last_pos = before.rfind(last_img)
            if last_pos >= 0 and (len(before) - last_pos) < 4000:
                image = last_img

        # 카드 아래쪽 컨텍스트
        after = body[pos:pos + 1200]
        excerpt_m = re.search(r'<p\s+class="excerpt">\s*([^<]*?)\s*</p>', after)
        excerpt = unescape(excerpt_m.group(1)).strip() if excerpt_m else ""
        date_m = re.search(r'<p\s+class="date">\s*([^<]+?)\s*</p>', after)
        date_iso = _parse_date(date_m.group(1)) if date_m else ""

        out.append({
            "title": title,
            "url": f"https://the-edit.co.kr/{aid}",
            "date": date_iso,
            "category": category,
            "excerpt": excerpt[:300],
            "image": image,
        })
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_the_edit()
    print(f"The Edit: {len(items)}건")
    for it in items[:10]:
        print(f"- {it['date']} [{it['category']}] {it['title']}")
        if it["excerpt"]:
            print(f"    └ {it['excerpt'][:80]}")
        if it["image"]:
            print(f"    img: {it['image'][:90]}")
