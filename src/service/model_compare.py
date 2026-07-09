"""모델 비교 테스트 — Gemini 3.5 Pro vs Claude Sonnet 4.6.

동일 글 20건을 동일 PROMPT로 두 모델에 보내 평가지표 5개 비교:
- 일관성: 같은 글 2회 호출 결과 일치도 (5건 샘플)
- 정확성: brands·people 추출 갯수 (참고)
- 추출 깊이: marketing_insight 글자수·키워드 다양도
- 비용: 토큰 × per-token 단가
- 응답 속도: 호출 시작 ~ 종료

출력:
- src/data/model_compare.json (raw 결과 + 요약)
- docs/model_compare.html (시각화)
"""
import base64, datetime, json, os, sys, time, traceback
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
import anthropic

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "src" / "data"
DOCS = ROOT / "docs"
ANALYSIS_FILE = DATA / "article_content_analysis.json"
ARTICLES_DIR = DATA / "articles"
IMAGES_DIR = DATA / "article_images"
OUT_JSON = DATA / "model_compare.json"
OUT_HTML = DOCS / "model_compare.html"

GEMINI_MODEL = "gemini-pro-latest"  # 현재 stable Pro 최신 (3.x preview 있으나 안정성 우선)
CLAUDE_MODEL = "claude-sonnet-4-6"

# per 1M tokens (USD, 2026 추정)
PRICING = {
    GEMINI_MODEL: {"input": 1.25, "output": 5.0},
    CLAUDE_MODEL: {"input": 3.0, "output": 15.0},
}

# content_analyzer.py PROMPT 동일 (hero_image_index 포함 19개)
PROMPT = """너는 트렌드 아티클 분석가다. 첨부된 본문 텍스트와 본문 안 이미지들을 종합 분석해.

[출력 — JSON 객체 1개만]
{
  "one_line_summary": "한 줄 요약 (1문장)",
  "full_description": "전체 내용 2~4문장 종합 설명 (구체적 사례·브랜드·수치 포함)",
  "image_by_image": ["이미지 1 설명", "이미지 2 설명", ...],
  "hero_image_index": 0,
  "content_category": "패션/뷰티 | 라이프스타일 | F&B | 테크 | 마케팅 | 뉴스 | 라이프 | 기타 중 하나",
  "content_format": "기사 | 인터뷰 | 화보 | 리뷰 | 정보전달 | 이벤트 | 제품홍보 | 데이터분석 | 기타",
  "topics": ["키워드 5~10개"],
  "brands_products": ["등장 브랜드·제품"],
  "people": ["등장 인물·셀럽"],
  "scene_setting": "배경·공간",
  "text_in_media": ["이미지 안 표시된 텍스트들"],
  "mood_tone": "톤·분위기 한 줄",
  "is_sponsored": true | false,
  "sponsorship_note": "광고·협찬 판단 근거 1문장",
  "marketing_insight": "마케팅 시사점 1~2문장",
  "target_audience": "타깃 독자 1문장"
}

규칙:
- image_by_image는 첨부된 이미지 순서대로 N개 (이미지 N장 = 배열 길이 N).
- hero_image_index는 image_by_image 배열의 0-based 인덱스. 가장 핵심 시각 표현 1장 선택. 배너·CTA·로고·아이콘 제외.
- 광고·협찬은 #광고 #제작지원 #협찬 표기 또는 PR/보도자료 톤일 때 true.
- JSON 객체만 출력. 다른 텍스트 일체 금지."""


def _source_from_url(url):
    for k, v in [("careet.net", "캐릿"), ("gogumafarm", "고구마팜"),
                 ("maily.so", "마케팅레시피"), ("20slab", "20대연구소"),
                 ("stib.ee", "고슴이의 비트"), ("the-edit", "The Edit"),
                 ("heypop", "HeyPop"), ("insight.co.kr", "Insight")]:
        if k in url:
            return v
    return "기타"


def load_sample(n=20):
    """다양한 source 분포로 N글 선정. body.txt + images 있는 글만."""
    d = json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
    by_src = {}
    for url, rec in d.items():
        # article_id 추출
        import re
        m = re.search(r"/(\d+)(?:[?#/]|$)", url) or re.search(r"/([\w-]+)/?$", url)
        aid = m.group(1) if m else re.sub(r"[^\w-]", "_", url[-30:])
        body_p = ARTICLES_DIR / f"{aid}.txt"
        img_dir = IMAGES_DIR / aid
        if not body_p.exists():
            continue
        imgs = sorted(img_dir.glob("img_*"))
        if not imgs:
            continue
        src = _source_from_url(url)
        by_src.setdefault(src, []).append((aid, url, body_p, imgs))

    sample = []
    sources = list(by_src.keys())
    per = max(1, n // max(1, len(sources)))
    for s in sources:
        sample.extend(by_src[s][:per])
    # 부족하면 더 채움
    if len(sample) < n:
        for s in sources:
            extras = by_src[s][per:per + 3]
            for e in extras:
                if len(sample) >= n:
                    break
                sample.append(e)
            if len(sample) >= n:
                break
    return sample[:n]


def _mime(p):
    ext = p.suffix.lower().lstrip(".")
    return f"image/{'jpeg' if ext == 'jpg' else ext}"


def call_gemini(body_text, image_paths):
    """Gemini 3.5 Pro vision 호출."""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    contents = [PROMPT + "\n\n[본문]\n" + body_text]
    total = 0
    for p in image_paths[:12]:
        try:
            data = p.read_bytes()
            sz = len(data)
            if sz > 7_500_000 or total + sz > 25_000_000:
                continue
            contents.append(types.Part.from_bytes(data=data, mime_type=_mime(p)))
            total += sz
        except Exception:
            pass
    t0 = time.time()
    resp = client.models.generate_content(model=GEMINI_MODEL, contents=contents)
    elapsed = time.time() - t0
    text = resp.text or ""
    usage = getattr(resp, "usage_metadata", None)
    in_tok = getattr(usage, "prompt_token_count", 0) if usage else 0
    out_tok = getattr(usage, "candidates_token_count", 0) if usage else 0
    return text, elapsed, in_tok, out_tok


def call_claude(body_text, image_paths):
    """Claude Sonnet 4.6 vision 호출."""
    client = anthropic.Anthropic()
    content = [{"type": "text", "text": PROMPT + "\n\n[본문]\n" + body_text}]
    total = 0
    for p in image_paths[:8]:  # Claude는 10MB 제한 더 빡빡
        try:
            data = p.read_bytes()
            sz = len(data)
            if sz > 4_500_000 or total + sz > 18_000_000:
                continue
            b64 = base64.standard_b64encode(data).decode("ascii")
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": _mime(p), "data": b64}})
            total += sz
        except Exception:
            pass
    t0 = time.time()
    msg = client.messages.create(model=CLAUDE_MODEL, max_tokens=4000,
                                 messages=[{"role": "user", "content": content}])
    elapsed = time.time() - t0
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    in_tok = msg.usage.input_tokens
    out_tok = msg.usage.output_tokens
    return text, elapsed, in_tok, out_tok


def parse_json(text):
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


def cost_for(model, in_tok, out_tok):
    p = PRICING.get(model, {"input": 0, "output": 0})
    return (in_tok * p["input"] + out_tok * p["output"]) / 1_000_000


def metrics(j):
    if not j:
        return {"brands_n": 0, "people_n": 0, "topics_n": 0,
                "insight_len": 0, "category": "", "format": ""}
    return {
        "brands_n": len(j.get("brands_products", []) or []),
        "people_n": len(j.get("people", []) or []),
        "topics_n": len(j.get("topics", []) or []),
        "insight_len": len(j.get("marketing_insight", "") or ""),
        "category": j.get("content_category", ""),
        "format": j.get("content_format", ""),
    }


def jaccard(a, b):
    s1, s2 = set(a or []), set(b or [])
    if not s1 and not s2:
        return 1.0
    return len(s1 & s2) / max(1, len(s1 | s2))


def save(results):
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    sample = load_sample(20)
    print(f"샘플 {len(sample)}글 (source 분포):")
    from collections import Counter
    cnt = Counter(_source_from_url(s[1]) for s in sample)
    for src, n in cnt.most_common():
        print(f"  {src}: {n}")

    results = {"per_article": [], "consistency": [], "summary": None,
               "started_at": datetime.datetime.now().isoformat(timespec="seconds")}
    save(results)

    for i, (aid, url, body_p, imgs) in enumerate(sample, 1):
        src = _source_from_url(url)
        print(f"\n[{i}/{len(sample)}] {src} · {aid}")
        body = body_p.read_text(encoding="utf-8")[:6000]

        # Gemini
        g_json, g_t, g_in, g_out, g_err = None, 0, 0, 0, ""
        try:
            g_text, g_t, g_in, g_out = call_gemini(body, imgs)
            g_json = parse_json(g_text)
            print(f"  Gemini Pro: {g_t:.1f}s · {g_in}+{g_out} tok · ${cost_for(GEMINI_MODEL, g_in, g_out):.4f}")
        except Exception as e:
            g_err = repr(e)[:200]
            print(f"  Gemini fail: {g_err[:80]}")

        # Claude
        c_json, c_t, c_in, c_out, c_err = None, 0, 0, 0, ""
        try:
            c_text, c_t, c_in, c_out = call_claude(body, imgs)
            c_json = parse_json(c_text)
            print(f"  Claude 4.6: {c_t:.1f}s · {c_in}+{c_out} tok · ${cost_for(CLAUDE_MODEL, c_in, c_out):.4f}")
        except Exception as e:
            c_err = repr(e)[:200]
            print(f"  Claude fail: {c_err[:80]}")

        results["per_article"].append({
            "article_id": aid, "url": url, "source": src,
            "gemini": {"json": g_json, "time": g_t, "in_tok": g_in, "out_tok": g_out,
                       "cost": cost_for(GEMINI_MODEL, g_in, g_out),
                       "error": g_err, **metrics(g_json)},
            "claude": {"json": c_json, "time": c_t, "in_tok": c_in, "out_tok": c_out,
                       "cost": cost_for(CLAUDE_MODEL, c_in, c_out),
                       "error": c_err, **metrics(c_json)},
        })
        save(results)

    # 일관성 — 첫 5글 재호출
    print(f"\n=== 일관성 (5글 재호출) ===")
    for i, item in enumerate(results["per_article"][:5], 1):
        aid = item["article_id"]
        body_p = ARTICLES_DIR / f"{aid}.txt"
        img_dir = IMAGES_DIR / aid
        imgs = sorted(img_dir.glob("img_*"))
        body = body_p.read_text(encoding="utf-8")[:6000]
        print(f"\n[{i}/5] {aid}")
        g2, c2 = None, None
        try:
            t, *_ = call_gemini(body, imgs); g2 = parse_json(t[0] if isinstance(t, tuple) else t)
        except Exception:
            try:
                tx, _, _, _ = call_gemini(body, imgs); g2 = parse_json(tx)
            except Exception as e:
                print(f"  Gemini consistency fail: {repr(e)[:80]}")
        try:
            tx, _, _, _ = call_claude(body, imgs); c2 = parse_json(tx)
        except Exception as e:
            print(f"  Claude consistency fail: {repr(e)[:80]}")

        g1 = item["gemini"].get("json") or {}
        c1 = item["claude"].get("json") or {}
        results["consistency"].append({
            "article_id": aid,
            "gemini_category_match": (g1.get("content_category") == (g2 or {}).get("content_category")) if g2 else None,
            "gemini_brands_jaccard": jaccard(g1.get("brands_products"), (g2 or {}).get("brands_products")) if g2 else None,
            "gemini_topics_jaccard": jaccard(g1.get("topics"), (g2 or {}).get("topics")) if g2 else None,
            "claude_category_match": (c1.get("content_category") == (c2 or {}).get("content_category")) if c2 else None,
            "claude_brands_jaccard": jaccard(c1.get("brands_products"), (c2 or {}).get("brands_products")) if c2 else None,
            "claude_topics_jaccard": jaccard(c1.get("topics"), (c2 or {}).get("topics")) if c2 else None,
        })
        save(results)

    # 요약
    g_ok = [p["gemini"] for p in results["per_article"] if p["gemini"]["time"] > 0]
    c_ok = [p["claude"] for p in results["per_article"] if p["claude"]["time"] > 0]

    def avg(lst, key):
        v = [x[key] for x in lst if isinstance(x.get(key), (int, float))]
        return sum(v) / max(1, len(v))

    def total(lst, key):
        return sum(x.get(key, 0) or 0 for x in lst)

    cons = results["consistency"]
    def avg_cons(field, default=None):
        v = [c[field] for c in cons if isinstance(c.get(field), (int, float))]
        return sum(v) / max(1, len(v)) if v else default
    def rate_cons(field):
        v = [1 if c.get(field) is True else 0 for c in cons if c.get(field) is not None]
        return sum(v) / max(1, len(v)) if v else None

    summary = {
        "sample_n": len(results["per_article"]),
        "consistency_n": len(cons),
        "gemini": {
            "model": GEMINI_MODEL,
            "ok_count": len(g_ok),
            "avg_time_sec": avg(g_ok, "time"),
            "total_cost_usd": total(g_ok, "cost"),
            "avg_brands_n": avg(g_ok, "brands_n"),
            "avg_people_n": avg(g_ok, "people_n"),
            "avg_topics_n": avg(g_ok, "topics_n"),
            "avg_insight_len": avg(g_ok, "insight_len"),
            "category_consistency_rate": rate_cons("gemini_category_match"),
            "brands_jaccard_avg": avg_cons("gemini_brands_jaccard"),
            "topics_jaccard_avg": avg_cons("gemini_topics_jaccard"),
        },
        "claude": {
            "model": CLAUDE_MODEL,
            "ok_count": len(c_ok),
            "avg_time_sec": avg(c_ok, "time"),
            "total_cost_usd": total(c_ok, "cost"),
            "avg_brands_n": avg(c_ok, "brands_n"),
            "avg_people_n": avg(c_ok, "people_n"),
            "avg_topics_n": avg(c_ok, "topics_n"),
            "avg_insight_len": avg(c_ok, "insight_len"),
            "category_consistency_rate": rate_cons("claude_category_match"),
            "brands_jaccard_avg": avg_cons("claude_brands_jaccard"),
            "topics_jaccard_avg": avg_cons("claude_topics_jaccard"),
        },
        "finished_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    results["summary"] = summary
    save(results)
    build_html(results)
    print(f"\n=== 완료 ===")
    print(f"  Gemini Pro: avg {summary['gemini']['avg_time_sec']:.1f}s · ${summary['gemini']['total_cost_usd']:.4f} · 일관성 {summary['gemini']['category_consistency_rate']}")
    print(f"  Claude 4.6: avg {summary['claude']['avg_time_sec']:.1f}s · ${summary['claude']['total_cost_usd']:.4f} · 일관성 {summary['claude']['category_consistency_rate']}")
    print(f"WROTE {OUT_HTML}")


def build_html(results):
    s = results.get("summary", {})
    g, c = s.get("gemini", {}), s.get("claude", {})
    per = results.get("per_article", [])

    def fmt(v, kind="num"):
        if v is None: return "—"
        if kind == "pct": return f"{v*100:.0f}%"
        if kind == "$": return f"${v:.4f}"
        if kind == "sec": return f"{v:.1f}s"
        if isinstance(v, float): return f"{v:.1f}"
        return str(v)

    def winner(g_val, c_val, lower_better=False):
        if g_val is None or c_val is None: return ""
        if lower_better:
            return "g" if g_val < c_val else "c"
        return "g" if g_val > c_val else "c"

    rows = []
    for p in per:
        gg, cc = p["gemini"], p["claude"]
        rows.append(f"""
      <tr>
        <td><a href="{p['url']}" target="_blank">{p['source']} · {p['article_id']}</a></td>
        <td>{gg['category']}</td><td>{cc['category']}</td>
        <td>{gg['brands_n']}</td><td>{cc['brands_n']}</td>
        <td>{gg['people_n']}</td><td>{cc['people_n']}</td>
        <td>{gg['insight_len']}자</td><td>{cc['insight_len']}자</td>
        <td>{fmt(gg['time'],'sec')}</td><td>{fmt(cc['time'],'sec')}</td>
        <td>{fmt(gg['cost'],'$')}</td><td>{fmt(cc['cost'],'$')}</td>
      </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<title>모델 비교 테스트 · Gemini Pro vs Claude Sonnet 4.6</title>
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css" />
<style>
  :root{{--ink:#15110e;--bg:#fafaf6;--surface:#fff;--line:#e7e3dc;--muted:#7a756e;--g:#3d6b6e;--c:#c8482a;--pill:#f4f0e8}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--ink);font-size:17px;line-height:1.65;
        font-family:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,sans-serif}}
  .wrap{{max-width:1180px;margin:0 auto;padding:64px 40px 96px}}
  .tag{{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
        color:var(--c);background:#fef2ec;padding:5px 12px;border-radius:99px;margin-bottom:20px}}
  h1{{font-size:42px;font-weight:800;letter-spacing:-.025em;line-height:1.2;margin-bottom:14px}}
  .lede{{font-size:18px;color:#3a342f;max-width:760px;margin-bottom:36px}}
  .meta{{display:flex;gap:24px;flex-wrap:wrap;padding:16px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-bottom:48px}}
  .meta-item{{font-size:14px;color:var(--muted)}}
  .meta-item b{{color:var(--ink);font-weight:600}}

  h2{{font-size:26px;font-weight:800;letter-spacing:-.01em;margin:48px 0 18px;padding-bottom:8px;border-bottom:1px solid var(--line)}}

  .vs{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:24px 0}}
  .card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:24px 28px}}
  .card-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;padding-bottom:12px;border-bottom:1px solid var(--line)}}
  .card-name{{font-size:18px;font-weight:700}}
  .card.g .card-name{{color:var(--g)}}
  .card.c .card-name{{color:var(--c)}}
  .card-tag{{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:3px 10px;border-radius:99px}}
  .card.g .card-tag{{background:#eaf2f2;color:var(--g)}}
  .card.c .card-tag{{background:#fef2ec;color:var(--c)}}

  .stats{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin-top:12px}}
  .stat{{display:flex;flex-direction:column;gap:4px}}
  .stat-label{{font-size:12px;color:var(--muted);font-weight:600;letter-spacing:.04em;text-transform:uppercase}}
  .stat-value{{font-size:24px;font-weight:700;letter-spacing:-.015em}}
  .stat.win .stat-value::after{{content:" ★";color:#a87a17;font-size:18px}}

  table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:14.5px}}
  th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line)}}
  th{{background:var(--pill);font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase}}
  td a{{color:var(--ink);text-decoration:none;font-weight:600}}
  td a:hover{{color:var(--c)}}

  .note{{background:#fef2ec;border-left:4px solid var(--c);padding:14px 20px;border-radius:6px;margin:18px 0;font-size:15px}}
  footer{{margin-top:64px;padding-top:24px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}
</style></head><body><div class="wrap">

<span class="tag">Model Comparison · Decision Brief</span>
<h1>분석 모델 비교 테스트</h1>
<p class="lede">동일 트렌드 글 <b>{s.get('sample_n','-')}건</b>을 동일 PROMPT로 두 모델에 보내, 5가지 평가지표로 비교한 결과.</p>

<div class="meta">
  <div class="meta-item"><b>샘플 수</b> · {s.get('sample_n','-')}건</div>
  <div class="meta-item"><b>일관성 테스트</b> · {s.get('consistency_n','-')}건 (각 모델 2회 호출)</div>
  <div class="meta-item"><b>실행 시각</b> · {s.get('finished_at','-')}</div>
</div>

<h2>요약 비교</h2>
<div class="vs">
  <div class="card g">
    <div class="card-head"><span class="card-name">Gemini 3.5 Pro</span><span class="card-tag">Google</span></div>
    <div class="stats">
      <div class="stat {'win' if winner(g.get('avg_time_sec'),c.get('avg_time_sec'),True)=='g' else ''}">
        <div class="stat-label">평균 응답 시간</div>
        <div class="stat-value">{fmt(g.get('avg_time_sec'),'sec')}</div>
      </div>
      <div class="stat {'win' if winner(g.get('total_cost_usd'),c.get('total_cost_usd'),True)=='g' else ''}">
        <div class="stat-label">총 비용</div>
        <div class="stat-value">{fmt(g.get('total_cost_usd'),'$')}</div>
      </div>
      <div class="stat {'win' if winner(g.get('avg_brands_n'),c.get('avg_brands_n'))=='g' else ''}">
        <div class="stat-label">평균 brands_products</div>
        <div class="stat-value">{fmt(g.get('avg_brands_n'))}</div>
      </div>
      <div class="stat {'win' if winner(g.get('avg_insight_len'),c.get('avg_insight_len'))=='g' else ''}">
        <div class="stat-label">평균 insight 길이</div>
        <div class="stat-value">{fmt(g.get('avg_insight_len'))}자</div>
      </div>
      <div class="stat {'win' if winner(g.get('category_consistency_rate'),c.get('category_consistency_rate'))=='g' else ''}">
        <div class="stat-label">카테고리 일관성</div>
        <div class="stat-value">{fmt(g.get('category_consistency_rate'),'pct')}</div>
      </div>
      <div class="stat {'win' if winner(g.get('brands_jaccard_avg'),c.get('brands_jaccard_avg'))=='g' else ''}">
        <div class="stat-label">brands Jaccard</div>
        <div class="stat-value">{fmt(g.get('brands_jaccard_avg'),'pct')}</div>
      </div>
      <div class="stat"><div class="stat-label">성공 호출</div><div class="stat-value">{g.get('ok_count','-')}/{s.get('sample_n','-')}</div></div>
      <div class="stat"><div class="stat-label">평균 topics</div><div class="stat-value">{fmt(g.get('avg_topics_n'))}</div></div>
    </div>
  </div>

  <div class="card c">
    <div class="card-head"><span class="card-name">Claude Sonnet 4.6</span><span class="card-tag">Anthropic</span></div>
    <div class="stats">
      <div class="stat {'win' if winner(g.get('avg_time_sec'),c.get('avg_time_sec'),True)=='c' else ''}">
        <div class="stat-label">평균 응답 시간</div>
        <div class="stat-value">{fmt(c.get('avg_time_sec'),'sec')}</div>
      </div>
      <div class="stat {'win' if winner(g.get('total_cost_usd'),c.get('total_cost_usd'),True)=='c' else ''}">
        <div class="stat-label">총 비용</div>
        <div class="stat-value">{fmt(c.get('total_cost_usd'),'$')}</div>
      </div>
      <div class="stat {'win' if winner(g.get('avg_brands_n'),c.get('avg_brands_n'))=='c' else ''}">
        <div class="stat-label">평균 brands_products</div>
        <div class="stat-value">{fmt(c.get('avg_brands_n'))}</div>
      </div>
      <div class="stat {'win' if winner(g.get('avg_insight_len'),c.get('avg_insight_len'))=='c' else ''}">
        <div class="stat-label">평균 insight 길이</div>
        <div class="stat-value">{fmt(c.get('avg_insight_len'))}자</div>
      </div>
      <div class="stat {'win' if winner(g.get('category_consistency_rate'),c.get('category_consistency_rate'))=='c' else ''}">
        <div class="stat-label">카테고리 일관성</div>
        <div class="stat-value">{fmt(c.get('category_consistency_rate'),'pct')}</div>
      </div>
      <div class="stat {'win' if winner(g.get('brands_jaccard_avg'),c.get('brands_jaccard_avg'))=='c' else ''}">
        <div class="stat-label">brands Jaccard</div>
        <div class="stat-value">{fmt(c.get('brands_jaccard_avg'),'pct')}</div>
      </div>
      <div class="stat"><div class="stat-label">성공 호출</div><div class="stat-value">{c.get('ok_count','-')}/{s.get('sample_n','-')}</div></div>
      <div class="stat"><div class="stat-label">평균 topics</div><div class="stat-value">{fmt(c.get('avg_topics_n'))}</div></div>
    </div>
  </div>
</div>

<div class="note">★ 표시는 그 항목에서 우위 모델. 응답 시간·비용은 낮을수록, 추출 갯수·insight 길이·일관성은 높을수록 좋다고 가정.</div>

<h2>글별 상세 비교</h2>
<table>
  <thead><tr>
    <th rowspan="2">글</th>
    <th colspan="2">카테고리</th>
    <th colspan="2">brands</th>
    <th colspan="2">people</th>
    <th colspan="2">insight 길이</th>
    <th colspan="2">응답 시간</th>
    <th colspan="2">비용</th>
  </tr><tr>
    <th>G</th><th>C</th><th>G</th><th>C</th><th>G</th><th>C</th><th>G</th><th>C</th><th>G</th><th>C</th><th>G</th><th>C</th>
  </tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>

<footer>모델 비교 테스트 · 사내 분석 자료 · {s.get('finished_at','-')}</footer>

</div></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
