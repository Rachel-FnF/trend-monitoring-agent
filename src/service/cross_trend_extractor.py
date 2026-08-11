"""교차검증 트렌드 추출 — article_content_analysis.json을 메타 분석.

여러 글에 공통으로 나타나는 트렌드를 Gemini에게 추출시켜, 카드 형태 JSON으로 저장.
출력: src/data/cross_trends.json (기간·제목·트렌드 카드 N개)

각 트렌드 카드 = 키워드 + 무엇 + 왜 + 잡힌 소스들 + 원문 글 리스트(title·url·source·date)

모델/추론 모드 선택 (성능 테스트용):
- 기본: gemini-3.5-flash, thinking 없음 (기존 동작 그대로).
- Deep Think: --model gemini-3.1-pro-preview --thinking high
- env로도 지정 가능: CROSS_TREND_MODEL, CROSS_TREND_THINKING(none|low|high)
- 다른 코드(compare 등)에서 재사용하도록 extract() 함수로 분리.
"""
import argparse, datetime, json, os, sys, time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "src" / "data"
ANALYSIS_FILE = DATA / "article_content_analysis.json"
OUT_FILE = DATA / "cross_trends.json"

# 기본 모델 = 기존과 동일(flash). env로 덮어쓸 수 있음.
DEFAULT_MODEL = os.environ.get("CROSS_TREND_MODEL", "gemini-3.5-flash")
DEFAULT_THINKING = os.environ.get("CROSS_TREND_THINKING", "none")  # none|low|high

# Gemini 호출 재시도 — 일시 오류(429/503)·깨진 JSON 응답 1번에 파이프라인 전체가 죽지 않도록
RETRIES = 3
RETRY_WAIT_SEC = 20  # 대기 = RETRY_WAIT_SEC × 시도번호 (20s, 40s)


PROMPT = """너는 트렌드 분석가다. 아래 글들의 분석 결과를 메타 분석해, 여러 글에 공통으로 등장하는 핵심 교차검증 트렌드를 추출해줘.

[추출 규칙]
- 최소 2개 이상의 글에서 공통 등장하는 트렌드만 포함
- "마케팅" 같은 너무 일반적인 키워드 금지 — 구체적이고 식별 가능한 것만
- 트렌드 5~12개 (양보다 질)
- 한국어로 작성, 깔끔하고 간결하고 부드러운 톤
- JSON 객체 1개만 출력. 다른 텍스트 일체 금지.

[출력 형식]
{
  "report_title": "기간을 잘 반영한 보고서 제목 (예: '2026년 5월 5주차 ~ 6월 1주차 교차검증 트렌드')",
  "trends": [
    {
      "keyword": "짧고 명확한 트렌드 키워드 (예: '시니어 인플루언서')",
      "what": "이 트렌드가 무엇인지 1~2문장 설명",
      "why": "왜 지금 뜨고 있는지 1~2문장 설명",
      "article_ids": ["1914", "1876", ...]
    },
    ...
  ]
}

[입력 — 분석된 글 목록]
"""


_SOURCE_MAP = [
    ("careet.net", "캐릿"), ("gogumafarm.kr", "고구마팜"),
    ("maily.so/marketingrecipe", "마케팅레시피"), ("20slab.org", "20대연구소"),
    ("stib.ee", "고슴이의 비트"), ("the-edit.co.kr", "The Edit"),
    ("heypop.kr", "HeyPop"), ("insight.co.kr", "Insight"),
    ("newneek.co", "뉴닉"), ("eyesmag.com", "Eyesmag"),
    ("fashionbiz.co.kr", "패션비즈"), ("vogue.co.kr", "Vogue"),
]
def _source_from_url(url):
    for k, v in _SOURCE_MAP:
        if k in url: return v
    return ""


def load_items():
    """분석 JSON을 읽어 Gemini 입력용 메타 리스트 + 기간 산출."""
    if not ANALYSIS_FILE.exists():
        raise FileNotFoundError("article_content_analysis.json 없음")
    data = json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
    if not data:
        raise ValueError("분석된 글 없음")

    items, dates = [], []
    for url, rec in data.items():
        aid = url.rstrip("/").split("/")[-1] if "/" in url else url
        aid = rec.get("article_id") or aid
        title = rec.get("title", "")[:80]
        source = rec.get("source") or _source_from_url(url)
        date = rec.get("date", "")
        summary = rec.get("one_line_summary", "")[:120]
        topics = rec.get("topics", [])[:8]
        brands = rec.get("brands_products", [])[:6]
        if date:
            dates.append(date)
        items.append({
            "article_id": aid, "title": title, "source": source, "date": date,
            "summary": summary, "topics": topics, "brands": brands, "url": url,
        })

    dates_sorted = sorted([d for d in dates if d])
    period_from = dates_sorted[0] if dates_sorted else ""
    period_to = dates_sorted[-1] if dates_sorted else ""
    return items, period_from, period_to


def build_input_text(items):
    lines = []
    for it in items:
        topics_str = ", ".join(it["topics"]) if it["topics"] else "-"
        brands_str = ", ".join(it["brands"]) if it["brands"] else "-"
        lines.append(
            f"[{it['article_id']}] {it['source']} · {it['date']} · {it['title']}\n"
            f"  요약: {it['summary']}\n  토픽: {topics_str}\n  브랜드: {brands_str}"
        )
    return "\n\n".join(lines)


def _client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수 없음")
    return genai.Client(api_key=api_key)


def call_model(input_text, model=DEFAULT_MODEL, thinking="none"):
    """Gemini 호출. thinking in {none, low, high}. 반환: (text, elapsed, in_tok, out_tok, think_tok)."""
    client = _client()
    full_prompt = PROMPT + input_text
    cfg = None
    if thinking and thinking != "none":
        cfg = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=thinking)
        )
    t0 = time.time()
    resp = client.models.generate_content(model=model, contents=[full_prompt], config=cfg)
    elapsed = time.time() - t0
    text = (resp.text or "").strip()
    u = getattr(resp, "usage_metadata", None)
    in_tok = getattr(u, "prompt_token_count", 0) or 0 if u else 0
    out_tok = getattr(u, "candidates_token_count", 0) or 0 if u else 0
    think_tok = getattr(u, "thoughts_token_count", 0) or 0 if u else 0
    return text, elapsed, in_tok, out_tok, think_tok


def _parse_json(text):
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        raise ValueError(f"JSON 추출 실패. 원본 앞부분:\n{text[:400]}")
    return json.loads(text[s:e + 1])


def postprocess(result, items, period_from, period_to, model, thinking,
                elapsed=0.0, in_tok=0, out_tok=0, think_tok=0):
    """article_ids → 실제 글 메타로 변환 + 잡힌 소스 리스트 + 메타 필드."""
    id_to_meta = {it["article_id"]: it for it in items}
    for tr in result.get("trends", []):
        ids = tr.get("article_ids", [])
        articles, sources = [], []
        for aid in ids:
            meta = id_to_meta.get(str(aid))
            if not meta:
                continue
            articles.append({
                "article_id": meta["article_id"], "title": meta["title"],
                "url": meta["url"], "source": meta["source"], "date": meta["date"],
            })
            if meta["source"] and meta["source"] not in sources:
                sources.append(meta["source"])
        tr["sources"] = sources
        tr["articles"] = articles
        tr.pop("article_ids", None)

    return {
        "report_title": result.get("report_title", ""),
        "period_from": period_from,
        "period_to": period_to,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "thinking": thinking,
        "timing_sec": round(elapsed, 2),
        "tokens": {"input": in_tok, "output": out_tok, "thinking": think_tok},
        "input_articles": len(items),
        "trends": result.get("trends", []),
    }


def extract(model=DEFAULT_MODEL, thinking="none", verbose=True):
    """전체 추출 파이프라인을 한 번에 실행하고 out dict 반환 (파일 저장은 호출측이)."""
    items, period_from, period_to = load_items()
    input_text = build_input_text(items)
    if verbose:
        print(f"입력 글: {len(items)}건, 기간: {period_from} ~ {period_to}")
        print(f"모델: {model} · thinking={thinking} · 입력 {len(PROMPT)+len(input_text):,}자")
    for attempt in range(1, RETRIES + 1):
        try:
            text, elapsed, in_tok, out_tok, think_tok = call_model(input_text, model, thinking)
            result = _parse_json(text)
            break
        except Exception as e:
            if attempt == RETRIES:
                raise
            wait = RETRY_WAIT_SEC * attempt
            print(f"  시도 {attempt}/{RETRIES} 실패: {repr(e)[:120]} → {wait}s 후 재시도")
            time.sleep(wait)
    out = postprocess(result, items, period_from, period_to, model, thinking,
                      elapsed, in_tok, out_tok, think_tok)
    if verbose:
        print(f"  완료: {elapsed:.1f}s · in={in_tok} out={out_tok} think={think_tok} · 트렌드 {len(out['trends'])}개")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--thinking", default=DEFAULT_THINKING, choices=["none", "low", "high"])
    ap.add_argument("--out", default=str(OUT_FILE))
    args = ap.parse_args()

    out = extract(model=args.model, thinking=args.thinking)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"WROTE {args.out}")
    print(f"  보고서 제목: {out['report_title']}")
    print(f"  트렌드 카드: {len(out['trends'])}개")
    for tr in out["trends"][:5]:
        print(f"  - {tr['keyword']} ({len(tr['articles'])}건, 소스: {', '.join(tr['sources'])})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
