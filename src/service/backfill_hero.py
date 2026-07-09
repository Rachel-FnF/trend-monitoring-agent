"""기존 analysis/<글ID>.json에 hero_image_index 백필.

이미지 다시 다운로드/전송하지 않고, 기존 image_by_image[] 묘사 텍스트만 보고
Gemini에 hero index만 요청. 빠르고 저렴.

조건:
- hero_image_index가 이미 채워진(0 아닌) 글은 스킵 (idempotent)
- image_by_image가 비어있으면 스킵
"""
import json, os, re, sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "src" / "data"
ANALYSIS_DIR = DATA / "analysis"
COMBINED = DATA / "article_content_analysis.json"
MODEL = "gemini-3.5-flash"

PROMPT_TMPL = """아래 N개 이미지 묘사 중 이 글의 가장 핵심 시각 표현 1장의 인덱스(0-based)를 골라.

[규칙]
- 배너·CTA·로고·아이콘·구독 유도·홍보 배너는 절대 제외
- 사람·제품·공간·이벤트 현장이 명확히 보이는 이미지를 우선
- 글의 트렌드 본질을 가장 잘 드러내는 1장
- JSON 1개만 출력. 다른 텍스트 일체 금지. {"hero_image_index": N}

[글 제목]
{title}

[이미지 묘사 목록]
{images}
"""


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY 환경변수 없음"); sys.exit(1)
    client = genai.Client(api_key=api_key)

    combined = json.loads(COMBINED.read_text(encoding="utf-8"))
    files = sorted(ANALYSIS_DIR.glob("*.json"))
    print(f"백필 대상 후보: {len(files)}건")

    n_filled, n_skip_done, n_skip_no_img, n_fail = 0, 0, 0, 0
    for p in files:
        aid = p.stem
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            n_fail += 1; continue

        ibi = rec.get("image_by_image") or []
        if not ibi:
            n_skip_no_img += 1; continue

        # 이미 채워진 글(0 아닌 값)은 스킵. 0은 모호하니 image_urls 길이 검증으로
        existing = rec.get("hero_image_index")
        # 0이 의도적인지 확인 안 되므로, hero가 0이고 image_urls가 비어있지 않으면 그대로 둠
        # 백필 우선순위: hero 필드 없거나 (0이지만 백필 한 적 없으면 채움 — 사실상 모든 옛 글 채움)
        # 옛 글들은 기본값 0으로 들어있으니 다 채움
        title = rec.get("title", "")[:120]
        img_lines = []
        for i, desc in enumerate(ibi):
            d = (desc or "")[:200]
            img_lines.append(f"[{i}] {d}")
        prompt = (PROMPT_TMPL
                  .replace("{title}", title)
                  .replace("{images}", "\n".join(img_lines)))

        try:
            resp = client.models.generate_content(model=MODEL, contents=[prompt])
            text = (resp.text or "").strip()
            s, e = text.find("{"), text.rfind("}")
            if s < 0: raise ValueError("no JSON")
            obj = json.loads(text[s:e + 1])
            idx = obj.get("hero_image_index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(ibi):
                raise ValueError(f"invalid index {idx}")
            rec["hero_image_index"] = idx
            p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            # 통합 인덱스도 갱신
            url = rec.get("url")
            if url and url in combined:
                combined[url]["hero_image_index"] = idx
            n_filled += 1
            if n_filled % 10 == 0:
                COMBINED.write_text(json.dumps(combined, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  진행: {n_filled}건 채움")
        except Exception as e:
            n_fail += 1
            print(f"  fail {aid}: {repr(e)[:80]}")

    COMBINED.write_text(json.dumps(combined, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== 완료 ===")
    print(f"  채움: {n_filled}건 / 이미 채워짐 스킵: {n_skip_done}건 / 이미지 없어 스킵: {n_skip_no_img}건 / 실패: {n_fail}건")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
