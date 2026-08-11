"""Build docs/dashboard.html from latest collected snapshot + live new-source fetch.

읽기: src/data/collected_<today>.json (없으면 가장 최근 파일)
보강: 4개 신규 소스(고구마팜·마케팅레시피·20대연구소·고슴이) 실시간 fetch.
필터: SINCE_DATE(기본 = 오늘-21일, 최근 3주) 이후 항목만.
교차검증: cross_trends.json(Gemini 교차분석)에서 2개+ 소스 트렌드를 카드로 노출.
출력: docs/dashboard.html (자체 포함 HTML+CSS+JS, JSON 임베드).
"""
import os, sys, json, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "data"
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

SINCE_DATE = os.environ.get("SINCE_DATE") or (datetime.date.today() - datetime.timedelta(days=21)).isoformat()
TODAY = datetime.date.today().isoformat()


def since(d: str) -> bool:
    if not d:
        return True
    s = d.replace(".", "-").strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    return s >= SINCE_DATE


# 1. Load careet snapshot
careet_file = DATA / "collected" / f"collected_{TODAY}.json"
if not careet_file.exists():
    files = sorted((DATA / "collected").glob("collected_*.json"), reverse=True)
    if not files:
        sys.exit("NO_COLLECTED")
    careet_file = files[0]
careet_data = json.loads(careet_file.read_text(encoding="utf-8"))
print(f"careet snapshot: {careet_file.name}")

# 2. Live-fetch 4 new sources (today's collect.py may have run before they were wired)
from service.gogumafarm import fetch_gogumafarm
from service.maily_marketingrecipe import fetch_maily_marketingrecipe
from service.slab20 import fetch_slab20
from service.stibee_gosumi import fetch_stibee_gosumi
from service.the_edit import fetch_the_edit
from service.heypop import fetch_heypop
from service.insight import fetch_insight
from service.newneek import fetch_newneek
from service.eyesmag import fetch_eyesmag
from service.fashionbiz import fetch_fashionbiz
from service.vogue import fetch_vogue


def safe(fn, name):
    try:
        out = fn()
        print(f"  {name}: {len(out)}")
        return out
    except Exception as e:
        print(f"  {name}_fail: {repr(e)[:100]}")
        return []


gogu = safe(fetch_gogumafarm, "gogumafarm")
maily = safe(fetch_maily_marketingrecipe, "marketingrecipe")
slab = safe(fetch_slab20, "slab20")
gosum = safe(fetch_stibee_gosumi, "gosumi")
edit_ = safe(fetch_the_edit, "the_edit")
heypop_ = safe(fetch_heypop, "heypop")
insight_ = safe(fetch_insight, "insight")
newneek_ = safe(fetch_newneek, "newneek")
eyesmag_ = safe(fetch_eyesmag, "eyesmag")
fashionbiz_ = safe(fetch_fashionbiz, "fashionbiz")
vogue_ = safe(fetch_vogue, "vogue")

# 3. Normalize all items
items = []

import re as _re_date
for a in careet_data.get("articles", []):
    if not since(a.get("date", "")):
        continue
    title = (a.get("title", "") or "").strip()
    if not title:
        continue
    # date fallback — listing에서 못 잡은 경우 본문 첫 날짜(작성일) 추출
    date_str = a.get("date", "").replace(".", "-")[:10]
    if not date_str:
        body = a.get("body_excerpt", "") or ""
        dm = _re_date.search(r"(20\d\d)\.(\d\d)\.(\d\d)", body)
        if dm:
            date_str = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
    items.append({
        "source": "캐릿", "date": date_str,
        "title": title, "url": a.get("url", ""),
        "category": a.get("label", "") or "기사",
        "tags": a.get("keywords", []),
        "excerpt": (a.get("body_excerpt", "") or "")[:300],
        "image": a.get("image", ""),
    })

# 사용자 요청: 캐릿 전광판(MicroTrend) 소스 제거 — 카드 생성 안 함.

for g in gogu:
    if not since(g.get("date", "")):
        continue
    items.append({
        "source": "고구마팜", "date": g.get("date", ""),
        "title": g.get("title", ""), "url": g.get("url", ""),
        "category": ",".join(g.get("categories", [])[:2]),
        "tags": g.get("categories", []),
        "excerpt": g.get("excerpt", "")[:300],
        "image": g.get("image", ""),
    })

for m in maily:
    if not since(m.get("date", "")):
        continue
    cat = (m.get("category", "") or "").strip()
    items.append({
        "source": "마케팅레시피", "date": m.get("date", ""),
        "title": m.get("title", ""), "url": m.get("url", ""),
        "category": cat, "tags": [cat] if cat else [],
        "excerpt": (m.get("subtitle", "") or "")[:300],
        "image": m.get("image", ""),
    })

for s in slab:
    if not since(s.get("date", "")):
        continue
    t = s.get("type", "") or ""
    items.append({
        "source": "20대연구소", "date": s.get("date", ""),
        "title": s.get("title", ""), "url": s.get("url", ""),
        "category": t, "tags": [t] if t else [],
        "excerpt": (s.get("excerpt", "") or "")[:300],
        "image": s.get("image", ""),
    })

for k in gosum:
    # 사용자 요청: is_ad 필터 제거 (광고 카드도 다 포함)
    if not since(k.get("date", "")):
        continue
    items.append({
        "source": "고슴이의 비트", "date": k.get("date", ""),
        "title": k.get("title", ""), "url": k.get("url", ""),
        "category": "라이프스타일", "tags": [],
        "excerpt": (k.get("body", "") or "")[:300],
        "image": k.get("image", ""),
    })

for t in edit_:
    if not since(t.get("date", "")):
        continue
    cat = (t.get("category", "") or "").strip()
    items.append({
        "source": "The Edit", "date": t.get("date", ""),
        "title": t.get("title", ""), "url": t.get("url", ""),
        "category": cat, "tags": [cat] if cat else [],
        "excerpt": (t.get("excerpt", "") or "")[:300],
        "image": t.get("image", ""),
    })

for h in heypop_:
    if not since(h.get("date", "")):
        continue
    cats = h.get("categories", []) or []
    items.append({
        "source": "HeyPop", "date": h.get("date", ""),
        "title": h.get("title", ""), "url": h.get("url", ""),
        "category": ",".join(cats[:2]),
        "tags": cats,
        "excerpt": (h.get("excerpt", "") or "")[:300],
        "image": h.get("image", ""),
    })

for s in insight_:
    if not since(s.get("date", "")):
        continue
    items.append({
        "source": "Insight", "date": s.get("date", ""),
        "title": s.get("title", ""), "url": s.get("url", ""),
        "category": "트렌드 뉴스", "tags": [],
        "excerpt": (s.get("excerpt", "") or "")[:300],
        "image": s.get("image", ""),
    })

for n in newneek_:
    if not since(n.get("date", "")):
        continue
    items.append({
        "source": "뉴닉", "date": n.get("date", ""),
        "title": n.get("title", ""), "url": n.get("url", ""),
        "category": "트렌드", "tags": [],
        "excerpt": (n.get("excerpt", "") or "")[:300],
        "image": n.get("image", ""),
    })

for e in eyesmag_:
    if not since(e.get("date", "")):
        continue
    cat = (e.get("category", "") or "").strip()
    items.append({
        "source": "Eyesmag", "date": e.get("date", ""),
        "title": e.get("title", ""), "url": e.get("url", ""),
        "category": cat or "패션", "tags": e.get("tags", [])[:5],
        "excerpt": (e.get("excerpt", "") or "")[:300],
        "image": e.get("image", ""),
    })

for f in fashionbiz_:
    if not since(f.get("date", "")):
        continue
    items.append({
        "source": "패션비즈", "date": f.get("date", ""),
        "title": f.get("title", ""), "url": f.get("url", ""),
        "category": "패션 비즈니스", "tags": [],
        "excerpt": (f.get("excerpt", "") or "")[:300],
        "image": f.get("image", ""),
    })

for v in vogue_:
    if not since(v.get("date", "")):
        continue
    cat = (v.get("category", "") or "").strip()
    items.append({
        "source": "Vogue", "date": v.get("date", ""),
        "title": v.get("title", ""), "url": v.get("url", ""),
        "category": cat, "tags": [cat] if cat else [],
        "excerpt": (v.get("excerpt", "") or "")[:300],
        "image": v.get("image", ""),
    })

items.sort(key=lambda x: x.get("date", ""), reverse=True)
print(f"items total: {len(items)}")

# 카드 ↔ 검색·쇼핑 신호 매칭 — 카드 title/excerpt에 키워드 있으면 related_signals에 추가
# 네이버 데이터랩은 매칭 풀에서 제외 (사용자 요청)
def _match_signals(items, gt_terms, nv_keywords):
    for it in items:
        hay = (it.get("title", "") + " " + it.get("excerpt", "")).lower()
        sigs = []
        for term in gt_terms:
            if not term or len(term) < 2:
                continue
            if term.lower() in hay:
                sigs.append(f"Google: {term}")
        # 중복 제거 + 6개까지
        seen = set(); uniq = []
        for s in sigs:
            if s not in seen:
                seen.add(s); uniq.append(s)
        if uniq:
            it["related_signals"] = uniq[:6]

# Google Trends 14일 누적 (네이버 데이터랩은 소스에서 제거됨)
try:
    from service.gtrends import fetch_google_trends_kr
    _gt_data = fetch_google_trends_kr()
except Exception:
    _gt_data = careet_data.get("google_trends", [])
print(f"signals: gt={len(_gt_data)}")
_gt_terms = [g.get("term", "") for g in _gt_data]
_match_signals(items, _gt_terms, [])

# hero_image 적용 — analysis/<글ID>.json의 hero_image_index가 있으면 그 이미지를 카드 대표로 교체
# article_id 규칙은 content_analyzer와 동일해야 매칭됨
_ANALYSIS_DIR = ROOT / "src" / "data" / "analysis"
from service.content_analyzer import article_id_from_url as _aid_from_url
_hero_n = 0
for _it in items:
    _url = _it.get("url", "") or ""
    _aid = _aid_from_url(_url)
    _p = _ANALYSIS_DIR / f"{_aid}.json"
    if not _p.exists():
        continue
    try:
        _rec = json.loads(_p.read_text(encoding="utf-8"))
        _idx = _rec.get("hero_image_index")
        _urls = _rec.get("image_urls") or []
        if isinstance(_idx, int) and 0 <= _idx < len(_urls) and _urls[_idx]:
            _it["image"] = _urls[_idx]
            _hero_n += 1
    except Exception:
        pass
print(f"hero_image 적용: {_hero_n}건")
matched = sum(1 for it in items if it.get("related_signals"))
print(f"  → matched cards: {matched}")

# 3.5. Enrich each item with 무엇/왜/F&F 시사 (Claude, cached by URL)
from service.enrich import enrich_items
items = enrich_items(items)

# 4. Cross-validated trends — cross_trends.json (Gemini 교차분석, cross_trend_compare.py가 매일 생성)
#    keyword/무엇/왜/sources/근거글 구조를 그대로 카드로 사용. 2개+ 소스 트렌드만 노출.
#    (옛 하드코딩 컨셉 리스트는 21일 윈도우가 흐르면 매칭이 0으로 붕괴해 제거 — 2026-07-08)
CROSS_ICONS = ["⭐", "🔥", "🌊", "🎯", "🧲", "💡", "🌀", "🎨", "🚀", "🧩", "📈", "🎪"]
cross_validated = []
_ct_file = DATA / "cross_trends.json"
if _ct_file.exists():
    try:
        _ct = json.loads(_ct_file.read_text(encoding="utf-8"))
        for _i, _tr in enumerate(_ct.get("trends", [])):
            _srcs = _tr.get("sources", [])
            if len(_srcs) < 2:
                continue
            cross_validated.append({
                "concept": _tr.get("keyword", ""),
                "icon": CROSS_ICONS[_i % len(CROSS_ICONS)],
                "what": _tr.get("what", ""),
                "why": _tr.get("why", ""),
                "items": [{"source": _a.get("source", ""), "date": _a.get("date", ""),
                           "title": _a.get("title", ""), "url": _a.get("url", "")}
                          for _a in _tr.get("articles", [])],
                "source_count": len(_srcs),
            })
        cross_validated.sort(key=lambda c: (-c["source_count"], -len(c["items"])))
        print(f"cross_trends.json: generated_at={_ct.get('generated_at','')} · "
              f"trends={len(_ct.get('trends', []))} → 2+소스 {len(cross_validated)}개")
    except Exception as _e:
        print(f"cross_trends load fail: {repr(_e)[:100]}")
else:
    print("cross_trends.json 없음 — 교차검증 섹션 비움")
print(f"cross_validated concepts: {len(cross_validated)}")

# 5. Stats
stats = {
    "total": len(items),
    "sources": len(set(it["source"] for it in items)),
    "cross": len(cross_validated),
    "period_from": SINCE_DATE, "period_to": TODAY,
    "generated_at": datetime.datetime.now().isoformat(timespec="minutes"),
    "careet_snapshot": careet_file.stem.replace("collected_", ""),
}

dashboard_data = {
    "stats": stats, "items": items, "cross_validated": cross_validated,
    "google_trends": careet_data.get("google_trends", []),
    "naver_shopping": careet_data.get("naver_shopping", []),
}

# 6. Render HTML (template at TEMPLATE_PATH)
TEMPLATE = (ROOT / "src" / "service" / "dashboard_template.html").read_text(encoding="utf-8")
payload = json.dumps(dashboard_data, ensure_ascii=False).replace("</", "<\\/")
html_out = TEMPLATE.replace("__DATA_JSON__", payload)

out = DOCS / os.environ.get("DASHBOARD_OUT", "dashboard.html")
out.write_text(html_out, encoding="utf-8")
print(f"WROTE {out} ({len(html_out):,} chars)")
