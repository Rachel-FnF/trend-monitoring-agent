"""Build docs/dashboard.html from latest collected snapshot + live new-source fetch.

읽기: src/data/collected_<today>.json (없으면 가장 최근 파일)
보강: 4개 신규 소스(고구마팜·마케팅레시피·20대연구소·고슴이) 실시간 fetch.
필터: SINCE_DATE(기본 2026-03-01) 이후 항목만.
교차검증: 큐레이션된 9개 컨셉 키워드로 2개+ 소스 동시 등장 항목 묶음.
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

SINCE_DATE = os.environ.get("SINCE_DATE") or (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
TODAY = datetime.date.today().isoformat()


def since(d: str) -> bool:
    if not d:
        return True
    s = d.replace(".", "-").strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    return s >= SINCE_DATE


# 1. Load careet snapshot
careet_file = DATA / f"collected_{TODAY}.json"
if not careet_file.exists():
    files = sorted(DATA.glob("collected_*.json"), reverse=True)
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

# 3. Normalize all items
items = []

for a in careet_data.get("articles", []):
    if not since(a.get("date", "")):
        continue
    title = (a.get("title", "") or "").strip()
    if not title:
        continue
    items.append({
        "source": "캐릿", "date": a.get("date", "").replace(".", "-")[:10],
        "title": title, "url": a.get("url", ""),
        "category": a.get("label", "") or "기사",
        "tags": a.get("keywords", []),
        "excerpt": (a.get("body_excerpt", "") or "")[:300],
        "image": a.get("image", ""),
    })

for m in careet_data.get("micro_trends", []):
    if not since(m.get("datetime", "")):
        continue
    items.append({
        "source": "캐릿 전광판", "date": m.get("datetime", "")[:10],
        "title": m.get("name", ""), "url": "https://www.careet.net/MicroTrend",
        "category": "이른 신호", "tags": m.get("sources", []), "excerpt": "",
    })

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
        "category": t, "tags": [t] if t else [], "excerpt": "",
        "image": s.get("image", ""),
    })

for k in gosum:
    if not since(k.get("date", "")) or k.get("is_ad"):
        continue
    items.append({
        "source": "고슴이의 비트", "date": k.get("date", ""),
        "title": k.get("title", ""), "url": k.get("url", ""),
        "category": "라이프스타일", "tags": [], "excerpt": "",
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

items.sort(key=lambda x: x.get("date", ""), reverse=True)
print(f"items total: {len(items)}")

# 3.5. Enrich each item with 무엇/왜/F&F 시사 (Claude, cached by URL)
from service.enrich import enrich_items
items = enrich_items(items)

# 4. Cross-validated concept matching
CROSS = [
    {"concept": "AI 활용 · 직장인 커리어", "icon": "🤖",
     "kw": ["ai ", " ai", "ai·", "ai를", "ai가", "ai에", "ai부터", "ai의", "ai로", "ai와"],
     "what": "AI(특히 생성형)가 직장인 일상 도구로 정착. '학벌·스펙'보다 'AI 활용 능력'이 새 커리어 경쟁력으로 부상하고, 비개발자도 AI로 사이트·앱을 만드는 시대.",
     "why": "Claude·GPT·Gemini 보급으로 진입장벽 급감. Z세대 1억 건+ AI 서비스 누적 사용한 통계가 정량 근거. AI·SNS 피로 반작용으로 '아날로그 취미'도 동시 부상.",
     "ff": "전사 디지털 캠페인 · 직원 활용 트렌드 · 헤트라스/F&CO 디지털 도구"},
    {"concept": "럭키맥싱 · 관악산 등산", "icon": "⛰️",
     "kw": ["럭키맥싱", "관악산"],
     "what": "운기·기복 신앙을 일상 행동으로 옮기는 Z세대 트렌드. 관악산 등 영험한 장소 방문이 '운 모으기 의식'으로 의미 부여됨. 신메뉴 홍보를 관악산 정상에서 한 영상이 600만 조회수.",
     "why": "취업·집값·연애 등 통제 불가능한 변수 앞에서 작은 의식으로 통제감을 얻으려는 심리. SNS 인증 욕구와 결합해 콘텐츠 확산.",
     "ff": "Discovery Expedition 직결 — Z세대 운기 신앙 + 등산 + 도시 근접 아웃도어"},
    {"concept": "템플스테이 · 콰이어트케이션", "icon": "🌿",
     "kw": ["템플스테이", "콰이어트", "사찰"],
     "what": "자극을 적극적으로 차단하는 휴식 트렌드. 사찰 머무름(템플스테이), 디지털 디톡스, 무자극 콘텐츠가 '번아웃 시대 휴식법'으로 떠오름.",
     "why": "디지털 피로·번아웃 누적으로 '자극보다 비움'을 선호하는 정서 전환. 일본 사찰·국내 템플스테이 등 무자극 콘텐츠 확산.",
     "ff": "Discovery · 헤트라스 — 무자극 휴식·웰니스 톤"},
    {"concept": "엉뚱한 복수 · Whimsical Anger", "icon": "🎭",
     "kw": ["엉뚱한 복수", "whimsical"],
     "what": "분노를 직접 표출하지 않고 엉뚱하거나 위트 있는 방식으로 풀어내는 Z세대 정서. '학교를 때린다'·'직장을 부순다' 같은 표현으로 SNS에서 공유.",
     "why": "직접적 분노 표현은 사회적 비용이 큼 → 유머·과장으로 가공해 공감 형성. 글로벌 Z세대 사이 공통 패턴.",
     "ff": "글로벌 Z세대 정서 시그널 — 콘텐츠 톤 단서"},
    {"concept": "바이브 코딩", "icon": "💻",
     "kw": ["바이브 코딩", "바이브코딩", "vibe"],
     "what": "비개발자가 AI 도구로 사이트·앱·게임을 즉흥적으로 만드는 흐름. 코드 한 줄 안 써도 자연어로 결과물을 만들어내는 시대.",
     "why": "Claude Artifacts·Cursor·V0 등 도구의 폭발적 보급. 'AI와 함께라면 아이디어 하나로 뚝딱' 인식 정착.",
     "ff": "디지털 마케팅 · 비개발자 도구 활용 흐름"},
    {"concept": "젤리슈즈 꾸미기", "icon": "👡",
     "kw": ["젤리슈즈"],
     "what": "투명·반투명 젤리슈즈에 비즈·참·스티커를 직접 꾸미는 액세서리 트렌드. SNS 인증샷 유행 + 네이버 패션잡화 인기검색어 TOP3 진입.",
     "why": "본인만의 커스터마이징 욕구 + 저가 진입가 + 여름 시즌 적합. 캐릿 전광판이 잡은 미세 신호를 네이버 실구매 데이터가 검증.",
     "ff": "네이버 패션잡화 TOP3 (실구매 검증) · 액세서리 꾸미기"},
    {"concept": "햄버거 마케팅 · 롯데리아 vs 맥도날드", "icon": "🍔",
     "kw": ["맥도날드", "롯데리아"],
     "what": "한국 햄버거 시장의 세대별 브랜드 이미지 분석. '맥도날드 = 20대' vs '롯데리아 = 10대'라는 Z세대 인식, 침착맨 콜라보·감튀 캠페인 등 마케팅 사례.",
     "why": "신규 진입(쉑쉑·파이브가이즈) + 기존 브랜드 콜라보 공세로 시장 활성화. Z세대가 본 브랜드 정체성이 마케팅 가치로 환산됨.",
     "ff": "세대별 브랜드 나이 이미지 — 브랜드 포지셔닝 참고"},
    {"concept": "코르티스 · K-pop Z세대 마케팅", "icon": "🎤",
     "kw": ["코르티스"],
     "what": "신예 K-pop 그룹 코르티스의 차별화된 Z세대 마케팅. 영크크 협업·구글맵 활용·과한 광고 없이 자연스러운 노출 전략.",
     "why": "'광고 같지 않은 광고'를 선호하는 Z세대 정서에 부합. 기존 K-pop 마케팅과 다른 결로 화제성 확보.",
     "ff": "K-pop IP 콜라보 · MZ 마케팅 톤"},
    {"concept": "콜라보 시장 분석", "icon": "🤝",
     "kw": ["콜라보 시장", "콜라보로 살아남", "콜라보 시장에서"],
     "what": "콜라보 시장이 포화 상태로 진입. 단순 합치기는 신선함을 잃고, '왜 이 두 브랜드?'에 명확한 답이 있어야 화제성 확보 가능.",
     "why": "모든 브랜드가 콜라보를 남발 → 차별화 어려움. 29CM 같은 큐레이션 플랫폼이 '잘하는 콜라보' 평가 기준 제공.",
     "ff": "MLB·Discovery·F&CO 콜라보 전략 — 시장 포화 대응"},
]

# Match items (큐레이션 5개 소스)
for cv in CROSS:
    matched = []
    for it in items:
        blob = (it["title"] + " " + (it.get("excerpt", "") or "")).lower()
        if any(k.lower() in blob for k in cv["kw"]):
            matched.append({"source": it["source"], "date": it["date"],
                            "title": it["title"], "url": it["url"]})
    # Match naver shopping keywords (실구매 검증 신호)
    naver_seen = set()
    for c in careet_data.get("naver_shopping", []):
        cat = c.get("category", "")
        for kw in c.get("keywords", []):
            kw_lower = kw.lower()
            if cat in naver_seen:
                continue
            if any(k.lower() in kw_lower for k in cv["kw"]):
                matched.append({"source": "네이버 데이터랩", "date": "최근 7일",
                                "title": f"[{cat}] {kw} (인기검색어)",
                                "url": "https://datalab.naver.com/shoppingInsight/sCategory.naver"})
                naver_seen.add(cat)
    cv["items"] = matched
    cv["source_count"] = len(set(m["source"] for m in matched))

cross_validated = [c for c in CROSS if c["source_count"] >= 2]
cross_validated.sort(key=lambda c: (-c["source_count"], -len(c["items"])))
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

out = DOCS / "dashboard.html"
out.write_text(html_out, encoding="utf-8")
print(f"WROTE {out} ({len(html_out):,} chars)")
