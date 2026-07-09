"""교차검증 트렌드 — Deep Think 적용본 vs 미적용본 성능 비교 (A/B 테스트).

같은 입력(article_content_analysis.json)으로 두 설정을 돌려 비교한다:
- 실험군(적용)  = Deep Think : gemini-3.1-pro-preview + thinking_level=high
- 대조군(미적용) = 기존       : gemini-3.5-flash, thinking 없음

출력:
- src/data/cross_trends.json          ← Deep Think 결과 (= 실제 결과물, 다운스트림이 사용)
- src/data/cross_trends_control.json  ← 미적용(기존) 결과 (대조군)
- src/data/cross_trends_compare.json  ← 두 결과 + 비교 지표 raw
- docs/cross_trends_compare.html       ← 성능 비교 리포트 (사람용)

run_daily.py 5단계에서 이 스크립트를 호출하면, 매일 적용본을 만들면서 동시에 비교본도 남긴다.
"""
import datetime, json, sys, traceback
from pathlib import Path

import cross_trend_extractor as cte

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "data"
DOCS = ROOT / "docs"
LOG = DATA / "run.log"  # run_daily.py와 같은 로그 파일에 적용 내역을 남긴다


def log(msg):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
OUT_LIVE = DATA / "cross_trends.json"            # Deep Think = 실제 결과물
OUT_CONTROL = DATA / "cross_trends_control.json"  # 미적용 대조군
OUT_COMPARE = DATA / "cross_trends_compare.json"
OUT_HTML = DOCS / "cross_trends_compare.html"

# 설정
DEEP = {"label": "Deep Think (적용)", "model": "gemini-3.1-pro-preview", "thinking": "high"}
CTRL = {"label": "기존 Flash (미적용)", "model": "gemini-3.5-flash", "thinking": "none"}

# per 1M tokens (USD, 2026 추정 단가 — 상대 비교용)
PRICING = {
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.0},
    "gemini-3.5-flash": {"input": 0.30, "output": 2.50},
}


def cost_of(out):
    p = PRICING.get(out["model"], {"input": 0, "output": 0})
    tk = out["tokens"]
    # thinking 토큰은 output 과금으로 가정
    return (tk["input"] * p["input"] + (tk["output"] + tk["thinking"]) * p["output"]) / 1_000_000


def _norm(kw):
    return "".join((kw or "").split()).lower()


import re as _re

def _eng_tokens(kw):
    return {t.lower() for t in _re.findall(r"[A-Za-z]{4,}", kw or "")}

def _hangul(kw):
    return "".join(_re.findall(r"[가-힣]", kw or ""))

def _has_common_substr(a, b, n=3):
    """a, b 두 문자열이 길이 n 이상 공통 부분문자열을 갖는지 (개념 매칭용)."""
    if len(a) < n or len(b) < n:
        return False
    grams = {a[i:i + n] for i in range(len(a) - n + 1)}
    return any(b[i:i + n] in grams for i in range(len(b) - n + 1))

def _related(a, b):
    """키워드 a, b 가 같은 개념을 가리키는지 (영문 토큰 공유 또는 한글 부분문자열 공유)."""
    if _eng_tokens(a) & _eng_tokens(b):
        return True
    return _has_common_substr(_hangul(a), _hangul(b), 3)


def _avg(nums):
    nums = [n for n in nums if isinstance(n, (int, float))]
    return sum(nums) / len(nums) if nums else 0


def metrics(out):
    trends = out.get("trends", [])
    return {
        "trend_count": len(trends),
        "avg_what_len": round(_avg([len(t.get("what", "")) for t in trends]), 1),
        "avg_why_len": round(_avg([len(t.get("why", "")) for t in trends]), 1),
        "avg_articles": round(_avg([len(t.get("articles", [])) for t in trends]), 2),
        "avg_sources": round(_avg([len(t.get("sources", [])) for t in trends]), 2),
        "total_cited": sum(len(t.get("articles", [])) for t in trends),
        "time_sec": out.get("timing_sec", 0),
        "tokens": out.get("tokens", {}),
        "cost_usd": round(cost_of(out), 4),
        "keywords": [t.get("keyword", "") for t in trends],
    }


def jaccard(a, b):
    s1, s2 = {_norm(x) for x in a}, {_norm(x) for x in b}
    s1.discard(""); s2.discard("")
    if not s1 and not s2:
        return 1.0
    return round(len(s1 & s2) / len(s1 | s2), 3)


def run():
    log(f"cross_trend_compare 시작 — Deep Think 적용본({DEEP['model']}, thinking={DEEP['thinking']}) + 대조군({CTRL['model']})")
    print("=== cross_trend A/B 비교 시작 ===")
    # 입력은 한 번만 로드해 두 모델에 동일 적용 (extract 내부에서 각자 로드하지만 동일 파일이라 동일)
    print(f"\n[1/2] 대조군: {CTRL['label']}")
    ctrl = cte.extract(model=CTRL["model"], thinking=CTRL["thinking"])
    OUT_CONTROL.write_text(json.dumps(ctrl, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n[2/2] 실험군: {DEEP['label']}")
    deep = cte.extract(model=DEEP["model"], thinking=DEEP["thinking"])
    # Deep Think 결과를 '실제 결과물'로 저장 → send_report / trenddb 가 이걸 사용
    OUT_LIVE.write_text(json.dumps(deep, ensure_ascii=False, indent=1), encoding="utf-8")

    cmp = compare_and_render(deep, ctrl)
    md, mc = cmp["deep"]["metrics"], cmp["control"]["metrics"]
    log(f"cross_trend_compare 완료 — 적용(Deep)={md['trend_count']}개·{md['time_sec']}s·"
        f"think{md['tokens'].get('thinking',0)}tok·${md['cost_usd']} | "
        f"미적용={mc['trend_count']}개·{mc['time_sec']}s·${mc['cost_usd']} | "
        f"개념겹침 {int(cmp['concept_overlap']*100)}% → cross_trends.json은 Deep Think 결과")
    return cmp


def compare_and_render(deep, ctrl):
    """두 결과 dict로 비교 지표 계산 + compare.json + html 생성 (API 호출 없음)."""
    m_ctrl, m_deep = metrics(ctrl), metrics(deep)
    kw_ctrl, kw_deep = m_ctrl["keywords"], m_deep["keywords"]

    # 개념 단위 매칭 (표현이 달라도 같은 개념이면 공통으로 인정)
    common, only_deep = [], []
    for d in kw_deep:
        (common if any(_related(d, c) for c in kw_ctrl) else only_deep).append(d)
    only_ctrl = [c for c in kw_ctrl if not any(_related(c, d) for d in kw_deep)]
    denom = max(len(kw_deep), len(kw_ctrl), 1)
    concept_overlap = round(len(common) / denom, 3)

    compare = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "input_articles": deep.get("input_articles", 0),
        "period": f"{deep.get('period_from','')} ~ {deep.get('period_to','')}",
        "deep": {"config": DEEP, "metrics": m_deep},
        "control": {"config": CTRL, "metrics": m_ctrl},
        "concept_overlap": concept_overlap,
        "keyword_overlap_jaccard": jaccard(kw_deep, kw_ctrl),  # 참고: 글자-그대로 겹침
        "only_in_deep": only_deep,
        "only_in_control": only_ctrl,
        "common_keywords": common,
    }
    OUT_COMPARE.write_text(json.dumps(compare, ensure_ascii=False, indent=1), encoding="utf-8")
    build_html(compare, deep, ctrl)

    print("\n=== 완료 ===")
    print(f"  적용(Deep): 트렌드 {m_deep['trend_count']}개 · {m_deep['time_sec']}s · ${m_deep['cost_usd']} · think={m_deep['tokens'].get('thinking',0)}tok")
    print(f"  미적용:     트렌드 {m_ctrl['trend_count']}개 · {m_ctrl['time_sec']}s · ${m_ctrl['cost_usd']}")
    print(f"  개념 겹침: {int(concept_overlap*100)}% · Deep 단독 {len(only_deep)}개 · 미적용 단독 {len(only_ctrl)}개")
    print(f"  WROTE {OUT_HTML}")
    return compare


def rebuild():
    """저장된 cross_trends.json(Deep) + cross_trends_control.json(기존)으로 리포트만 재생성."""
    deep = json.loads(OUT_LIVE.read_text(encoding="utf-8"))
    ctrl = json.loads(OUT_CONTROL.read_text(encoding="utf-8"))
    return compare_and_render(deep, ctrl)


def _trend_cards(out):
    cards = []
    for t in out.get("trends", []):
        srcs = ", ".join(t.get("sources", []))
        arts = "".join(
            f'<li><a href="{a.get("url","")}" target="_blank">{a.get("source","")} · {a.get("title","")}</a></li>'
            for a in t.get("articles", [])[:6]
        )
        cards.append(f"""
        <div class="trend">
          <div class="kw">{t.get('keyword','')}</div>
          <div class="wh"><b>무엇</b> {t.get('what','')}</div>
          <div class="wh"><b>왜</b> {t.get('why','')}</div>
          <div class="src">소스 {len(t.get('sources',[]))} · {srcs} · 글 {len(t.get('articles',[]))}건</div>
          <ul class="arts">{arts}</ul>
        </div>""")
    return "".join(cards)


def build_html(cmp, deep, ctrl):
    d, c = cmp["deep"]["metrics"], cmp["control"]["metrics"]

    def cell(dv, cv, lower_better=False, suffix=""):
        try:
            dwin = (dv < cv) if lower_better else (dv > cv)
            cwin = (cv < dv) if lower_better else (cv > dv)
        except TypeError:
            dwin = cwin = False
        ds = " win" if dwin else ""
        cs = " win" if cwin else ""
        return (f'<td class="d{ds}">{dv}{suffix}</td>'
                f'<td class="c{cs}">{cv}{suffix}</td>')

    pill = lambda items, cls: "".join(f'<span class="pill {cls}">{x}</span>' for x in items) or '<span class="muted">—</span>'

    rows = f"""
    <tr><th>추출 트렌드 수</th>{cell(d['trend_count'], c['trend_count'])}</tr>
    <tr><th>평균 '무엇' 설명 길이</th>{cell(d['avg_what_len'], c['avg_what_len'], suffix='자')}</tr>
    <tr><th>평균 '왜' 설명 길이</th>{cell(d['avg_why_len'], c['avg_why_len'], suffix='자')}</tr>
    <tr><th>트렌드당 평균 근거 글</th>{cell(d['avg_articles'], c['avg_articles'], suffix='건')}</tr>
    <tr><th>트렌드당 평균 교차 소스</th>{cell(d['avg_sources'], c['avg_sources'], suffix='개')}</tr>
    <tr><th>총 인용 글</th>{cell(d['total_cited'], c['total_cited'], suffix='건')}</tr>
    <tr><th>응답 시간</th>{cell(d['time_sec'], c['time_sec'], lower_better=True, suffix='s')}</tr>
    <tr><th>추론(thinking) 토큰</th>{cell(d['tokens'].get('thinking',0), c['tokens'].get('thinking',0), suffix='tok')}</tr>
    <tr><th>출력 토큰</th>{cell(d['tokens'].get('output',0), c['tokens'].get('output',0), suffix='tok')}</tr>
    <tr><th>예상 비용</th>{cell(d['cost_usd'], c['cost_usd'], lower_better=True, suffix=' USD')}</tr>
    """

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>교차검증 트렌드 · Deep Think A/B 성능 테스트</title>
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css" />
<style>
  :root{{--ink:#15110e;--bg:#fafaf6;--surface:#fff;--line:#e7e3dc;--muted:#8a847c;--d:#3d6b6e;--c:#b9742a;--pill:#f4f0e8;--win:#fbf4df}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--ink);font-size:16px;line-height:1.6;font-family:"Pretendard Variable",Pretendard,-apple-system,sans-serif}}
  .wrap{{max-width:1140px;margin:0 auto;padding:56px 36px 96px}}
  .tag{{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--c);background:#fdf1e6;padding:5px 12px;border-radius:99px;margin-bottom:18px}}
  h1{{font-size:38px;font-weight:800;letter-spacing:-.025em;line-height:1.2;margin-bottom:12px}}
  .lede{{font-size:17px;color:#3a342f;max-width:780px;margin-bottom:30px}}
  .meta{{display:flex;gap:22px;flex-wrap:wrap;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-bottom:40px;font-size:14px;color:var(--muted)}}
  .meta b{{color:var(--ink);font-weight:600}}
  h2{{font-size:24px;font-weight:800;margin:46px 0 16px;padding-bottom:8px;border-bottom:1px solid var(--line)}}
  table{{width:100%;border-collapse:collapse;font-size:15px;background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
  th,td{{padding:12px 16px;text-align:left;border-bottom:1px solid var(--line)}}
  thead th{{background:var(--pill);font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}}
  tbody th{{font-weight:600;color:#4a443d;width:34%}}
  td.d,td.c{{font-variant-numeric:tabular-nums;font-weight:600}}
  td.d{{color:var(--d)}} td.c{{color:var(--c)}}
  td.win{{background:var(--win)}}
  td.win::after{{content:" ★";color:#a87a17}}
  .colhead{{display:flex;gap:0}}
  .legend{{display:flex;gap:20px;margin:14px 0 0;font-size:13px;color:var(--muted)}}
  .dot{{display:inline-block;width:10px;height:10px;border-radius:99px;margin-right:6px;vertical-align:middle}}
  .dot.d{{background:var(--d)}} .dot.c{{background:var(--c)}}
  .note{{background:#fdf1e6;border-left:4px solid var(--c);padding:13px 18px;border-radius:6px;margin:18px 0;font-size:14.5px}}
  .kwbox{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:14px 0}}
  .kwbox h3{{font-size:15px;margin-bottom:10px}}
  .pill{{display:inline-block;font-size:13px;padding:5px 11px;border-radius:99px;margin:0 6px 8px 0}}
  .pill.d{{background:#eaf2f2;color:var(--d)}} .pill.c{{background:#fdeee0;color:var(--c)}} .pill.x{{background:var(--pill);color:#4a443d}}
  .muted{{color:var(--muted)}}
  .cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}}
  .panel{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 20px}}
  .panel.dh{{border-top:3px solid var(--d)}} .panel.ch{{border-top:3px solid var(--c)}}
  .panel h3{{font-size:16px;margin-bottom:4px}} .panel .sub{{font-size:12.5px;color:var(--muted);margin-bottom:14px}}
  .trend{{border-bottom:1px solid var(--line);padding:12px 0}}
  .trend:last-child{{border-bottom:none}}
  .kw{{font-weight:700;font-size:15.5px;margin-bottom:5px}}
  .wh{{font-size:13.5px;color:#3a342f;margin:2px 0}} .wh b{{color:var(--muted);font-weight:600;margin-right:5px}}
  .src{{font-size:12px;color:var(--muted);margin-top:5px}}
  .arts{{list-style:none;margin-top:6px}} .arts li{{font-size:12px;margin:2px 0}} .arts a{{color:var(--muted);text-decoration:none}} .arts a:hover{{color:var(--c)}}
  footer{{margin-top:60px;padding-top:22px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}
</style></head><body><div class="wrap">

<span class="tag">A/B Performance Test · Cross-Trend Extraction</span>
<h1>교차검증 트렌드 — Deep Think 성능 테스트</h1>
<p class="lede">동일한 입력 글 <b>{cmp['input_articles']}건</b>({cmp['period']})을 같은 프롬프트로 두 설정에 돌려, 트렌드 추출 품질·속도·비용을 비교한 결과입니다.</p>

<div class="meta">
  <div><b>실험군(적용)</b> · {DEEP['model']} · thinking=high</div>
  <div><b>대조군(미적용)</b> · {CTRL['model']} · thinking 없음</div>
  <div><b>실행</b> · {cmp['generated_at']}</div>
</div>

<h2>성능 지표 비교</h2>
<table>
  <thead><tr><th>지표</th><th><span class="dot d"></span>Deep Think (적용)</th><th><span class="dot c"></span>기존 (미적용)</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="legend">
  <span><span class="dot d"></span>Deep Think = {DEEP['model']}</span>
  <span><span class="dot c"></span>기존 = {CTRL['model']}</span>
  <span>★ = 해당 지표 우위</span>
</div>
<div class="note">★는 그 항목에서 더 나은 쪽. <b>시간·비용은 낮을수록</b>, 설명 길이·근거 글·교차 소스는 <b>높을수록</b> 좋다고 가정합니다. 추론 토큰은 Deep Think가 '생각'에 쓴 양으로, 비용↑의 원인이자 품질↑의 근거입니다.</div>

<h2>키워드 비교 — 개념 겹침 {int(cmp['concept_overlap']*100)}%</h2>
<div class="note">표현이 달라도 같은 개념(예: '럭키맥싱'과 '럭키맥싱(Luckymaxxing)')이면 공통으로 셉니다. 겹치는 개념은 두 모델이 모두 잡은 '확실한' 트렌드, Deep Think 단독은 더 깊은 추론으로 추가로 잡아낸 것입니다.</div>
<div class="kwbox">
  <h3>공통 발견 ({len(cmp['common_keywords'])}) — 양쪽 모두 잡은 확실한 트렌드</h3>
  {pill(cmp['common_keywords'], 'x')}
</div>
<div class="kwbox">
  <h3><span class="dot d"></span>Deep Think 만 발견 ({len(cmp['only_in_deep'])}) — 더 깊은 추론으로 잡아낸 것</h3>
  {pill(cmp['only_in_deep'], 'd')}
</div>
<div class="kwbox">
  <h3><span class="dot c"></span>기존 만 발견 ({len(cmp['only_in_control'])})</h3>
  {pill(cmp['only_in_control'], 'c')}
</div>

<h2>실제 추출 결과 (나란히 보기)</h2>
<div class="cols">
  <div class="panel dh">
    <h3>Deep Think (적용) — 실제 결과물</h3>
    <div class="sub">{deep.get('report_title','')}</div>
    {_trend_cards(deep)}
  </div>
  <div class="panel ch">
    <h3>기존 Flash (미적용) — 대조군</h3>
    <div class="sub">{ctrl.get('report_title','')}</div>
    {_trend_cards(ctrl)}
  </div>
</div>

<footer>교차검증 트렌드 A/B 성능 테스트 · 사내 분석 자료 · {cmp['generated_at']}<br>
비용은 2026년 추정 단가 기준의 상대 비교값입니다 (정확한 청구액 아님).</footer>

</div></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if "--rebuild" in sys.argv:
            rebuild()  # 저장된 결과로 리포트만 재생성 (API 호출 없음)
        else:
            run()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
