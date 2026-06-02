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

PROMPT = """너는 F&F(한국 패션·뷰티 기업) 트렌드 분석가다. 아래 트렌드들을 각각 3필드로 짧고 정확하게 분석하라.

[F&F 브랜드]
패션: MLB · MLB Kids · Discovery Expedition · Duvetica · Sergio Tacchini (MLB는 중국 사업이 핵심)
뷰티: F&CO(바닐라코 — 클렌징·베이스 메이크업), 헤트라스(향수)

[F&F 시사 각도 — 반드시 하나 선택, 패션을 항상 중심에]
- 패션×음식 : F&B/맛/식문화 → 패션 콜라보·굿즈·캠페인
- 패션×장소 : 핫플·팝업·지역·여행 → 매장·VMD·체험 전략
- 패션×인테리어 : 공간·연출·미감 → 매장·디스플레이·브랜드 아이덴티티
- 패션×라이프스타일 : 취향·여가·웰니스·웰빙 → 톤·페르소나·세컨라인
- 패션×밈 : 콘텐츠·SNS·바이럴·말투 → 마케팅·캠페인·디지털
- 패션×세대 : Z세대·30대·40대+ 매핑 → 브랜드 포지셔닝·세컨라인

[트렌드 목록 — JSON, 순서대로 분석]
{ITEMS_JSON}

[출력 — JSON 배열만, 입력 순서 그대로]
[
  {{"what":"트렌드 정체를 본문 근거로 2~3문장. 구체적 사례·브랜드·수치 있으면 인용.",
    "why":"왜 지금 부상하는지 1~2문장. 본문에 근거 없으면 빈 문자열.",
    "ff_angle":"패션×음식|패션×장소|패션×인테리어|패션×라이프스타일|패션×밈|패션×세대 중 하나",
    "ff_point":"패션을 중심에 두고 ff_angle 렌즈로 F&F가 활용할 인사이트 1~2문장. 가능하면 구체 브랜드(MLB/Discovery/Duvetica/Sergio/F&CO/헤트라스)와 행동(콜라보·매장·캠페인·굿즈·세컨라인)을 명시. 일반론·추측 금지."}},
  ...
]

[규칙]
- 광고·홍보성: what="홍보성 콘텐츠로 트렌드 분석 대상 아님", 나머지 빈 문자열.
- F&F 무관(주식·정치·사건사고): ff_angle="패션×라이프스타일", ff_point="직접 활용도 낮음 — 참고만".
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
