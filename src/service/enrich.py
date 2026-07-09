"""Claude로 각 트렌드를 (무엇/왜 뜨나/F&F 시사) 3필드로 분석.
캐시는 src/data/dashboard_enrich.json (URL 단위 영속화) — 새 항목만 새로 분석.
배치 5개씩 한 번의 API 호출 → 토큰·비용 절감.
"""
import json, sys
from pathlib import Path
from dotenv import load_dotenv
import anthropic

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
CACHE = ROOT / "src" / "data" / "dashboard_enrich.json"
MODEL = "claude-sonnet-4-6"
BATCH = 5

PROMPT = """너는 한국 트렌드 분석가다. 아래 트렌드들을 각각 2필드로 짧고 정확하게 분석하라.

[트렌드 목록 — JSON, 순서대로 분석]
{ITEMS_JSON}

[출력 — JSON 배열만, 입력 순서 그대로]
[
  {{"what":"트렌드 정체를 본문 근거로 2~3문장. 구체적 사례·브랜드·수치 있으면 인용.",
    "why":"왜 지금 부상하는지 1~2문장. 본문에 근거 없으면 빈 문자열."}},
  ...
]

[규칙]
- 명시적 광고·협찬·PR/보도자료(예: "(광고)" 표기, 브랜드 보도자료 톤, "본 콘텐츠는 ㅇㅇ의 지원을 받아 작성"): what="홍보성 콘텐츠로 트렌드 분석 대상 아님", why="".
- **단, 에디터의 1인칭 제품 추천·후기·리뷰(예: "안녕, 에디터 ㅇㅇ다", "내가 써보니…")는 광고가 아니라 라이프스타일 큐레이션의 정상적인 트렌드 신호이므로 정상 분석.** The Edit·HeyPop·고구마팜·마케팅레시피 등 큐레이션 매체의 기본 톤이다.
- 무관 신호(주식 종목코드·정치인물·일반 사건사고): what="일반 뉴스/사건사고 — 트렌드 분석 대상 아님", why="".
- 정보 부족: "확인 필요" 표기, 추측 금지.
- 캐릿 본문은 유료 미디어 → 인용하지 말고 본인 표현으로 요약.

JSON 배열만 출력. 다른 텍스트 일체 금지."""


def _load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(c):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def _strip_json_array(text):
    s, e = text.find("["), text.rfind("]")
    return text[s:e+1] if s >= 0 and e > s else ""


def enrich_items(items, force=False, max_new=None):
    """items 리스트의 각 항목에 what/why/ff_angle/ff_point 키 추가.
    캐시 hit는 건드리지 않고, 새 URL만 Claude 호출. max_new로 한 번 빌드의 신규 처리 상한 설정 가능."""
    cache = {} if force else _load_cache()
    client = anthropic.Anthropic()

    new = [it for it in items if it.get("url") and it["url"] not in cache]
    if max_new and len(new) > max_new:
        print(f"enrich: capping new items {len(new)} → {max_new}")
        new = new[:max_new]
    print(f"enrich: total={len(items)} cached={len(items) - len(new)} new={len(new)}")

    for i in range(0, len(new), BATCH):
        batch = new[i:i + BATCH]
        payload = [{"i": j + 1, "source": it["source"], "date": it["date"],
                    "title": it["title"], "excerpt": (it.get("excerpt") or "")[:500]}
                   for j, it in enumerate(batch)]
        prompt = PROMPT.format(ITEMS_JSON=json.dumps(payload, ensure_ascii=False, indent=1))
        try:
            msg = client.messages.create(model=MODEL, max_tokens=4000,
                                         messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            arr_text = _strip_json_array(text)
            if not arr_text:
                print(f"  batch {i // BATCH + 1}: no JSON array, skipping")
                continue
            data = json.loads(arr_text)
            for it, enr in zip(batch, data):
                cache[it["url"]] = {
                    "what": (enr.get("what") or "").strip(),
                    "why": (enr.get("why") or "").strip(),
                    "ff_angle": (enr.get("ff_angle") or "").strip(),
                    "ff_point": (enr.get("ff_point") or "").strip(),
                }
            _save_cache(cache)
            print(f"  batch {i // BATCH + 1}/{(len(new) + BATCH - 1) // BATCH} done ({len(batch)} items)")
        except Exception as e:
            print(f"  batch {i // BATCH + 1} fail: {repr(e)[:140]}")
            continue

    # Apply to all items (cached + newly enriched)
    for it in items:
        enr = cache.get(it.get("url", ""), {})
        it["what"] = enr.get("what", "")
        it["why"] = enr.get("why", "")
        it["ff_angle"] = enr.get("ff_angle", "")
        it["ff_point"] = enr.get("ff_point", "")
    return items


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("enrich.py — module entry. Use via build_dashboard.py.")
    c = _load_cache()
    print(f"cache size: {len(c)} URLs")
