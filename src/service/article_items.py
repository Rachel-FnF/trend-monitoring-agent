"""article_items.py — 수집 스냅샷 + 외부 소스 실시간 fetch를 정규화된 글 목록으로.

content_analyzer가 "오늘 분석할 글 목록"을 얻는 유일한 진입점.
(옛 build_dashboard.py의 정규화 파트만 분리 — 대시보드 렌더링은 제거됨, 2026-08-19)

읽기: src/data/collected_<today>.json (없으면 가장 최근 파일)
보강: 외부 소스 11종 실시간 fetch (캐시 hit는 각 모듈이 알아서 스킵)
필터: SINCE_DATE(기본 = 오늘-21일) 이후 항목만.
반환: [{source, date, title, url, category, tags, excerpt, image}, ...]
"""
import os
import re
import json
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "data"

SINCE_DATE = os.environ.get("SINCE_DATE") or (datetime.date.today() - datetime.timedelta(days=21)).isoformat()
TODAY = datetime.date.today().isoformat()


def since(d: str) -> bool:
    if not d:
        return True
    s = d.replace(".", "-").strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    return s >= SINCE_DATE


def _safe(fn, name):
    try:
        out = fn()
        print(f"  {name}: {len(out)}")
        return out
    except Exception as e:
        print(f"  {name}_fail: {repr(e)[:100]}")
        return []


def collect_items():
    """정규화된 글 목록 반환 (날짜 내림차순)."""
    # 1. 캐릿 스냅샷 (collect.py 산출물)
    snap = DATA / "collected" / f"collected_{TODAY}.json"
    if not snap.exists():
        files = sorted((DATA / "collected").glob("collected_*.json"), reverse=True)
        if not files:
            raise SystemExit("NO_COLLECTED — 먼저 collect.py 실행 필요")
        snap = files[0]
    careet_data = json.loads(snap.read_text(encoding="utf-8"))
    print(f"careet snapshot: {snap.name}")

    # 2. 외부 소스 실시간 fetch
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

    gogu = _safe(fetch_gogumafarm, "gogumafarm")
    maily = _safe(fetch_maily_marketingrecipe, "marketingrecipe")
    slab = _safe(fetch_slab20, "slab20")
    gosum = _safe(fetch_stibee_gosumi, "gosumi")
    edit_ = _safe(fetch_the_edit, "the_edit")
    heypop_ = _safe(fetch_heypop, "heypop")
    insight_ = _safe(fetch_insight, "insight")
    newneek_ = _safe(fetch_newneek, "newneek")
    eyesmag_ = _safe(fetch_eyesmag, "eyesmag")
    fashionbiz_ = _safe(fetch_fashionbiz, "fashionbiz")
    vogue_ = _safe(fetch_vogue, "vogue")

    # 3. Normalize
    items = []

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
            dm = re.search(r"(20\d\d)\.(\d\d)\.(\d\d)", body)
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

    # 캐릿 전광판(MicroTrend)은 소스에서 제외 (사용자 요청, 대시보드 시절부터 동일)

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
        # is_ad 필터 없음 (광고 글도 포함, 마킹만)
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
    print(f"items total: {len(items)} (since={SINCE_DATE})")
    return items


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    sys.stdout.reconfigure(encoding="utf-8")
    for it in collect_items()[:15]:
        print(f"- [{it['source']}] {it['date']} {it['title'][:50]}")
