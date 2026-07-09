"""Unattended careet collector — runs headless on the device-registered persistent profile.

Scrapes homepage, the micro-trend board, and the F&F keyword verticals; dedupes; tracks
first-seen date per article (data/seen.json) for the timing axis; fetches body excerpts for
NEW articles; writes data/collected_YYYY-MM-DD.json.

Run after setup_profile.py has registered the profile once. Exit code 2 = profile not logged
in (re-run setup_profile.py).
"""
import os, re, sys, json, datetime
from pathlib import Path
from urllib.parse import quote
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
PROFILE = ROOT / "profile"
DATA = ROOT / "src" / "data"
DATA.mkdir(exist_ok=True)
TODAY = datetime.date.today().isoformat()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Date cutoff — only keep items dated on/after this.
# 환경변수 SINCE_DATE override 가능. 미설정 시 기본 = 오늘로부터 21일 전 (최근 3주).
# Affects 캐릿/고구마팜/마케팅레시피/20대연구소/고슴이/The Edit/Insight.
# Google Trends·네이버 데이터랩은 이미 최근 1~7일 스냅샷이라 영향 없음.
# HeyPop은 listing에 date가 없어 자동으로 통과(보수적).
SINCE_DATE = os.environ.get("SINCE_DATE") or (datetime.date.today() - datetime.timedelta(days=21)).isoformat()


def since(d: str) -> bool:
    """True if date string (YYYY-MM-DD / YYYY.MM.DD / 'YYYY-MM-DD HH:MM') >= SINCE_DATE.
    날짜를 모르면(공백) 유지(보수적). 형식 깨지면 컷."""
    if not d:
        return True
    s = d.replace(".", "-").strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return False
    return s >= SINCE_DATE

# 사용자 요청: 캐릿 시리즈 3개만 (요즘뜨는밈 + Z세대 최신근황 + 이주의 유행템)
SERIES = {
    "요즘뜨는밈": "/Content/Series/1",
    "Z세대 최신근황": "/Content/Series/2",
    "이주의 유행템": "/Content/Series/5",
}
CARD_JS = r"""ns => ns.filter(a=>/^\/\d+$/.test(a.getAttribute('href')||'')).map(a=>{
  let t=(a.innerText||'').replace(/\s+/g,' ').trim();
  const lm=t.match(/유행\s*(예감|중|지남)/); const dm=t.match(/20\d\d\.\d\d\.\d\d/);
  let cut=t.length; if(lm)cut=Math.min(cut,t.indexOf(lm[0])); if(dm)cut=Math.min(cut,t.indexOf(dm[0]));
  t=t.slice(0,cut).replace(/북마크$/,'').trim();
  const imgEl = a.querySelector('img') || a.closest('article, li, div')?.querySelector('img');
  let img = imgEl?.getAttribute('src') || imgEl?.getAttribute('data-src') || '';
  if (img.startsWith('//')) img = 'https:' + img;
  else if (img.startsWith('/')) img = 'https://www.careet.net' + img;
  return {id:a.getAttribute('href').slice(1), title:t.slice(0,120), date:dm?dm[0]:'', label:lm?lm[0].replace(/\s+/g,''):'', image:img};
})"""


def p(*a):
    print(*a, flush=True)


def logged_in(page):
    try:
        return page.locator("a:has-text('로그아웃'), a[href*=Logout]").count() > 0
    except Exception:
        return False


def cards(page):
    try:
        return page.eval_on_selector_all("a[href]", CARD_JS)
    except Exception:
        return []


def parse_micro(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out, i = [], 0
    while i < len(lines) - 2:
        if re.fullmatch(r"20\d\d\.\d\d\.\d\d \d\d:\d\d", lines[i]):
            out.append({"datetime": lines[i].replace(".", "-", 2), "name": lines[i + 1],
                        "sources": [s.strip() for s in re.split(r"[,/]", lines[i + 2])]})
            i += 3
        else:
            i += 1
    seen, uniq = set(), []
    for m in out:
        k = (m["datetime"], m["name"])
        if k not in seen:
            seen.add(k); uniq.append(m)
    return uniq


with sync_playwright() as pw:
    if not PROFILE.exists():
        p("NO_PROFILE: profile 없음. setup_profile.py 먼저 실행하세요."); sys.exit(2)
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE), headless=True, user_agent=UA,
        viewport={"width": 1366, "height": 900}, locale="ko-KR")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # verify session via members-only page redirect
    page.goto("https://www.careet.net/MyPage/Membership", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    if "User/Login" in page.url or "CheckAccess" in page.url:
        p("SESSION_INVALID: 세션 만료/미등록. setup_profile.py 재실행 필요. url=" + page.url)
        ctx.close(); sys.exit(2)
    page.goto("https://www.careet.net/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    articles = {}        # id -> record
    def add(rec, kw=None):
        r = articles.setdefault(rec["id"], {**rec, "keywords": []})
        if kw and kw not in r["keywords"]:
            r["keywords"].append(kw)
        for f in ("date", "label", "title", "image"):
            if not r.get(f) and rec.get(f):
                r[f] = rec[f]

    # 사용자 요청: 시리즈 3개 (요즘뜨는밈·Z세대 최신근황·이주의 유행템)
    # 홈·MicroTrend·키워드 vertical은 제외.
    micro = []  # MicroTrend 미사용
    for label, path in SERIES.items():
        page.goto(f"https://www.careet.net{path}", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        cs = cards(page)
        for c in cs:
            add(c, label)
        p(f"series '{label}': {len(cs)}")

    # first-seen tracking
    seen_path = DATA / "seen.json"
    seen = json.loads(seen_path.read_text(encoding="utf-8")) if seen_path.exists() else {}
    new_ids = []
    for aid, r in articles.items():
        if aid not in seen:
            seen[aid] = TODAY
            new_ids.append(aid)
        r["first_seen"] = seen[aid]
        r["url"] = f"https://www.careet.net/{aid}"
    seen_path.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")

    # SINCE_DATE filter — keep first-seen for ALL articles (seen.json untouched) but
    # drop pre-cutoff items from this run's payload. 본문 fetch도 잘려 비용 절감.
    _before = len(articles)
    articles = {aid: r for aid, r in articles.items() if since(r.get("date", ""))}
    new_ids = [aid for aid in new_ids if aid in articles]
    micro = [m for m in micro if since(m.get("datetime", ""))]
    p(f"articles total: {len(articles)} (new today: {len(new_ids)}, since={SINCE_DATE}, cut {_before - len(articles)})")

    # Body cache — 한 번 fetch한 글의 본문은 영구 저장해 매일 재사용.
    # collected_<today>.json은 매일 새로 만들어지지만 body는 글이 살아있는 동안 안 바뀜 →
    # SINCE 윈도우 안에서는 옛 글도 본문 유지(분석 일관성·캐릿 hit 절감).
    body_cache_path = DATA / "source_cache" / "careet_body_cache.json"
    body_cache_path.parent.mkdir(parents=True, exist_ok=True)
    body_cache = json.loads(body_cache_path.read_text(encoding="utf-8")) if body_cache_path.exists() else {}
    # 1단계: 캐시 hit 적용
    cache_hits = 0
    for aid, r in articles.items():
        if not r.get("body_excerpt") and aid in body_cache:
            r["body_excerpt"] = body_cache[aid]
            cache_hits += 1
    # 2단계: 본문이 비어있는 글을 fetch (new_ids 우선 + 캐시 miss인 옛 글, cap 30)
    to_fetch = [aid for aid in new_ids if not articles[aid].get("body_excerpt")]
    extras = [aid for aid in articles if aid not in to_fetch and not articles[aid].get("body_excerpt")]
    # 최근 글 우선(date desc)
    extras.sort(key=lambda a: articles[a].get("date", ""), reverse=True)
    fetch_queue = (to_fetch + extras)[:30]
    p(f"body cache: {cache_hits} hit, {len(fetch_queue)} to fetch (new={len(to_fetch)}, extras={min(len(extras), 30-len(to_fetch))})")
    for aid in fetch_queue:
        try:
            page.goto(f"https://www.careet.net/{aid}", wait_until="domcontentloaded")
            page.wait_for_timeout(1800)
            # 발행일 fallback — listing에서 못 잡은 글들 보강. body 태그 상단 800자에서 첫 20YY.MM.DD
            if not articles[aid].get("date"):
                try:
                    top = page.inner_text("body")[:800]
                    dm = re.search(r"(20\d\d)\.(\d\d)\.(\d\d)", top)
                    if dm:
                        articles[aid]["date"] = f"{dm.group(1)}.{dm.group(2)}.{dm.group(3)}"
                except Exception:
                    pass
            body = page.inner_text("article") if page.locator("article").count() else page.inner_text("main")
            excerpt = re.sub(r"\s+", " ", body)[:2000]
            articles[aid]["body_excerpt"] = excerpt
            body_cache[aid] = excerpt
        except Exception:
            articles[aid].setdefault("body_excerpt", "")
    body_cache_path.write_text(json.dumps(body_cache, ensure_ascii=False, indent=1), encoding="utf-8")

    ctx.close()

# ↓ caret 끝났으니 sync_playwright() with-block 밖에서 다른 소스 fetch.
#   (안에서 호출하면 fetch_stibee_gosumi()가 또 sync_playwright()를 열려고 해서 충돌)

# Google Trends (한국 급상승) — careet 밖 원시 신호 (공개 RSS)
try:
    sys.path.insert(0, str(ROOT / "src"))
    from service.gtrends import fetch_google_trends_kr
    gtrends = fetch_google_trends_kr()
    p(f"google_trends: {len(gtrends)}")
except Exception as e:
    gtrends = []
    p("gtrends_fail:", repr(e)[:100])

# Naver DataLab 쇼핑인사이트 — 사용자 요청으로 소스 제외
naver = []

# 고구마팜 — MZ 트렌드·밈 (RSS, 캐릿과 결 같은 큐레이션, 직접 교차검증)
try:
    from service.gogumafarm import fetch_gogumafarm
    gogumafarm = fetch_gogumafarm()
    p(f"gogumafarm: {len(gogumafarm)}")
except Exception as e:
    gogumafarm = []
    p("gogumafarm_fail:", repr(e)[:100])

# 마케팅레시피 — Z세대 마케팅 인사이트·사례 (RSS, 실행 인사이트형)
try:
    from service.maily_marketingrecipe import fetch_maily_marketingrecipe
    marketingrecipe = fetch_maily_marketingrecipe()
    p(f"marketingrecipe: {len(marketingrecipe)}")
except Exception as e:
    marketingrecipe = []
    p("marketingrecipe_fail:", repr(e)[:100])

# 20대연구소 — 세대 연구 칼럼·인사이트 (정적 스크랩, 검증·레퍼런스용)
try:
    from service.slab20 import fetch_slab20
    slab20 = fetch_slab20()
    p(f"slab20: {len(slab20)}")
except Exception as e:
    slab20 = []
    p("slab20_fail:", repr(e)[:100])

# 스티비 — 뉴닉 '고슴이의 비트' (SPA·Playwright, 광고 자동 분리)
# ※ 이게 자체 sync_playwright()를 열기 때문에 반드시 위 with 블록 밖에서 호출!
try:
    from service.stibee_gosumi import fetch_stibee_gosumi
    gosumi = fetch_stibee_gosumi()
    p(f"gosumi: {len(gosumi)} (ads {sum(1 for x in gosumi if x.get('is_ad'))})")
except Exception as e:
    gosumi = []
    p("gosumi_fail:", repr(e)[:100])

# The Edit (디에디트) — 라이프스타일 큐레이션 (STYLE·EAT·TECH·LIFE·CULTURE)
try:
    from service.the_edit import fetch_the_edit
    the_edit = fetch_the_edit()
    p(f"the_edit: {len(the_edit)}")
except Exception as e:
    the_edit = []
    p("the_edit_fail:", repr(e)[:100])

# HeyPop (헤이팝) — 팝업·공간·디자인 트렌드
try:
    from service.heypop import fetch_heypop
    heypop = fetch_heypop()
    p(f"heypop: {len(heypop)}")
except Exception as e:
    heypop = []
    p("heypop_fail:", repr(e)[:100])

# Insight (인사이트) — 트렌드 뉴스 (패션·뷰티·셀럽·이슈)
try:
    from service.insight import fetch_insight
    insight = fetch_insight()
    p(f"insight: {len(insight)}")
except Exception as e:
    insight = []
    p("insight_fail:", repr(e)[:100])

# SINCE_DATE filter — RSS·정적 소스도 컷오프 적용 (구글·네이버는 이미 최근 스냅샷이라 패스).
gogumafarm = [g for g in gogumafarm if since(g.get("date", ""))]
marketingrecipe = [m for m in marketingrecipe if since(m.get("date", ""))]
slab20 = [s for s in slab20 if since(s.get("date", ""))]
gosumi = [k for k in gosumi if since(k.get("date", ""))]
the_edit = [t for t in the_edit if since(t.get("date", ""))]
heypop = [h for h in heypop if since(h.get("date", ""))]  # date 비어있으면 통과
insight = [i for i in insight if since(i.get("date", ""))]
p(f"after SINCE_DATE({SINCE_DATE}): gogumafarm={len(gogumafarm)} marketingrecipe={len(marketingrecipe)} slab20={len(slab20)} gosumi={len(gosumi)} the_edit={len(the_edit)} heypop={len(heypop)} insight={len(insight)}")

out = {
    "collected_at": TODAY,
    "since_date": SINCE_DATE,
    "source": "캐릿(요즘뜨는밈+Z세대 최신근황+이주의 유행템) + Google Trends KR + 고구마팜(트렌드) + 마케팅레시피(한-입 트렌드) + 20대연구소(뉴스레터) + 고슴이의 비트 + The Edit(STYLE) + HeyPop(POP-UP) + Insight(트렌드)",
    "copyright_note": "캐릿 유료 미디어. 무단 전재·재배포 금지, 내부 분석용.",
    "counts": {
        "articles": len(articles), "micro_trends": len(micro), "new_today": len(new_ids),
        "google_trends": len(gtrends), "naver_categories": len(naver),
        "gogumafarm": len(gogumafarm), "marketingrecipe": len(marketingrecipe),
        "slab20": len(slab20), "gosumi": len(gosumi),
        "the_edit": len(the_edit), "heypop": len(heypop), "insight": len(insight),
    },
    "micro_trends": micro,
    "google_trends": gtrends,
    "naver_shopping": naver,
    "gogumafarm": gogumafarm,
    "marketingrecipe": marketingrecipe,
    "slab20": slab20,
    "gosumi": gosumi,
    "the_edit": the_edit,
    "heypop": heypop,
    "insight": insight,
    "articles": sorted(articles.values(), key=lambda r: r.get("date", ""), reverse=True),
}
collected_dir = DATA / "collected"
collected_dir.mkdir(parents=True, exist_ok=True)
outpath = collected_dir / f"collected_{TODAY}.json"
outpath.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
p(f"WROTE {outpath}")
