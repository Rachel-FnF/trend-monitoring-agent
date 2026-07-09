"""Google Trends — 한국(KR) 일일 급상승 검색어 수집 (공개 RSS, 로그인/키 불필요).
RSS는 '오늘 1일치 스냅샷'만 줘 → 매일 데이터를 google_trends_history.json에 누적.
누적 데이터에서 SINCE_DATE 이후 항목을 합쳐 14일치 뷰 제공.
각 항목: 검색어(term) · 트래픽(traffic) · 관련 뉴스(news) · 첫 등장일(seen).
"""
import datetime, json, os, sys, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

RSS_URL = "https://trends.google.com/trending/rss?geo=KR"
NS = {"ht": "https://trends.google.com/trending/rss"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_HISTORY = Path(__file__).resolve().parents[2] / "src" / "data" / "source_cache" / "google_trends_history.json"
_HISTORY.parent.mkdir(parents=True, exist_ok=True)


def _fetch_today(limit=20):
    """오늘자 RSS 스냅샷 그대로."""
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": UA})
    xml_bytes = urllib.request.urlopen(req, timeout=25).read()
    root = ET.fromstring(xml_bytes)
    out = []
    for item in root.iter("item"):
        term = (item.findtext("title") or "").strip()
        if not term:
            continue
        traffic = (item.findtext("ht:approx_traffic", default="", namespaces=NS) or "").strip()
        news = []
        for n in item.findall("ht:news_item/ht:news_item_title", NS):
            if n is not None and n.text:
                news.append(n.text.strip())
        out.append({"term": term, "traffic": traffic, "news": news[:2]})
        if len(out) >= limit:
            break
    return out


def _load_history():
    if _HISTORY.exists():
        try:
            return json.loads(_HISTORY.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_history(h):
    try:
        _HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def fetch_google_trends_kr(limit=20):
    """오늘자 fetch + history 누적 + SINCE_DATE(기본 21일 전) 이후 통합 반환.
    각 term의 가장 이른 seen 날짜 + 최신 traffic 유지. 같은 term은 중복 제거."""
    today = datetime.date.today().isoformat()
    since = os.environ.get("SINCE_DATE") or (datetime.date.today() - datetime.timedelta(days=21)).isoformat()

    history = _load_history()
    today_items = []
    try:
        today_items = _fetch_today(limit=30)
    except Exception:
        pass
    if today_items:
        history[today] = today_items
        # 오래된 날짜 정리(SINCE 이전)
        history = {d: v for d, v in history.items() if d >= since}
        _save_history(history)

    # SINCE 이후 누적 데이터 통합 — term 중복 시 가장 이른 등장일 + 가장 최신 traffic/news 사용
    merged = {}
    for d in sorted(history.keys()):
        if d < since:
            continue
        for it in history[d]:
            t = it["term"]
            if t not in merged:
                merged[t] = {**it, "seen": d}
            else:
                # traffic·news는 최신값으로 갱신
                merged[t].update({k: v for k, v in it.items() if k != "term" and v})
    out = sorted(merged.values(), key=lambda x: x.get("seen", ""), reverse=True)
    return out[:limit * 3]  # 누적이므로 더 많이 반환 가능


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_google_trends_kr()
    print(f"google_trends KR: {len(items)}건")
    for it in items[:12]:
        print(f"- {it['term']} ({it['traffic']}) | 뉴스: {' / '.join(it['news'])[:80]}")
