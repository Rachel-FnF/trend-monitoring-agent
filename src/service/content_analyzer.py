"""아티클 본문 + 이미지 종합 분석 (Gemini vision).

참조 포맷: content_analysis.json (인스타·X 게시물 분석, gemini-3.5-flash 사용)
— 아티클 기준으로 변형.

흐름:
1. 글 페이지 fetch (캐릿은 Playwright 영구 프로필, 그 외 urllib)
2. 본문 텍스트 → src/data/articles/<id>.txt 저장
3. 본문 안 <img> URL 추출 → src/data/article_images/<id>/img_N.<ext> 다운로드
4. Gemini vision으로 본문 + 이미지들 종합 분석
5. JSON 저장 (src/data/article_content_analysis.json) — URL 단위 영구 캐시
"""
import datetime, json, os, re, sys, urllib.request
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "src" / "data"
ARTICLES_DIR = DATA / "articles"
IMAGES_DIR = DATA / "article_images"
RAW_DIR = DATA / "raw"
ANALYSIS_DIR = DATA / "analysis"
ANALYSIS_FILE = DATA / "article_content_analysis.json"
for d in (ARTICLES_DIR, IMAGES_DIR, RAW_DIR, ANALYSIS_DIR):
    d.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PROFILE = ROOT / "profile"
MODEL = "gemini-3.5-flash"  # 공식 API ID (사용자 지정, GA)


def _load_analysis():
    if ANALYSIS_FILE.exists():
        try:
            return json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_analysis(d):
    ANALYSIS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _is_careet(url):
    return "careet.net" in url


def fetch_article_page(url):
    """글 페이지 fetch → (html, full_text). 캐릿은 영구 프로필 Playwright."""
    if _is_careet(url):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE), headless=True, user_agent=UA, locale="ko-KR")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2200)
            html = page.content()
            text = page.inner_text("article") if page.locator("article").count() else page.inner_text("body")
            ctx.close()
            return html, text
    else:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return html, text


_IMG_BLACKLIST = ("emoji", "sprite", "icon-", "/icon/", "logo-", "/avatar", "profile_img",
                  "blank", "transparent", "pixel.gif", "s.w.org", "wp-includes/images/smilies")


def extract_images(html, url, max_n=12):
    """본문 안 <img> URL 추출. 광고·아이콘·로고 등 노이즈 필터."""
    imgs = re.findall(r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']', html)
    seen, out = set(), []
    base_match = re.match(r'https?://[^/]+', url)
    base = base_match.group(0) if base_match else ""
    for src in imgs:
        if not src or src in seen:
            continue
        # 절대 URL 만들기
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/") and base:
            src = base + src
        elif not src.startswith("http"):
            continue
        # data URI · SVG 스킵
        if src.startswith("data:") or src.lower().endswith(".svg"):
            continue
        if any(b in src.lower() for b in _IMG_BLACKLIST):
            continue
        seen.add(src)
        out.append(src)
        if len(out) >= max_n:
            break
    return out


def download_image(img_url, save_dir, idx):
    """이미지 다운로드 → 저장. 확장자 URL에서 자동 추출."""
    ext = ".jpg"
    m = re.search(r"\.(jpg|jpeg|png|webp|gif)(?:\?|$)", img_url, re.IGNORECASE)
    if m:
        ext = "." + m.group(1).lower()
        if ext == ".jpeg":
            ext = ".jpg"
    save_path = save_dir / f"img_{idx:02d}{ext}"
    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=15).read()
        if len(data) < 1024:  # 1KB 미만은 픽셀/스페이서일 가능성
            return None
        save_path.write_bytes(data)
        return save_path
    except Exception as e:
        print(f"  img {idx} fail: {repr(e)[:60]}")
        return None


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
- hero_image_index는 image_by_image 배열의 0-based 인덱스. 이 글의 가장 핵심 시각 표현(트렌드 본질을 가장 잘 드러내는 메인 이미지) 1장을 선택. 배너·CTA·로고·아이콘은 제외. 사람·제품·공간이 명확히 보이고 본문 맥락과 가장 잘 맞는 이미지를 우선.
- 광고·협찬은 #광고 #제작지원 #협찬 같은 명시 표기 또는 PR/보도자료 톤일 때 true.
- JSON 객체만 출력. 다른 텍스트 일체 금지."""


_VISION_MAX = 7_500_000      # 단일 이미지 raw 7.5MB (Gemini는 좀 더 여유)
_BATCH_MAX = 25_000_000      # 누적 raw 25MB
_MAX_IMAGES = 12             # 첨부 이미지 최대 12장


def _mime_for(p):
    ext = p.suffix.lower().lstrip(".")
    return f"image/{'jpeg' if ext == 'jpg' else ext}"


def analyze(url, body_text, image_paths):
    """본문 + 이미지 vision 분석 (Gemini). 단일/누적 사이즈 제한.
    큰 이미지는 vision 첨부에서 제외(다운로드 사본은 유지)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY 환경변수 없음"}
    client = genai.Client(api_key=api_key)
    sendable, total = [], 0
    for p in image_paths:
        if len(sendable) >= _MAX_IMAGES:
            break
        size = p.stat().st_size
        if size > _VISION_MAX:
            print(f"  oversized skip: {p.name} ({size/1024/1024:.1f}MB)")
            continue
        if total + size > _BATCH_MAX:
            print(f"  batch full at {len(sendable)} images (total {total/1024/1024:.1f}MB)")
            break
        sendable.append(p)
        total += size

    prompt_text = (
        f"[글 URL] {url}\n\n"
        f"[본문 텍스트]\n{body_text[:6000]}\n\n"
        f"[이미지 {len(sendable)}장 첨부 — 순서대로 image_by_image 작성]\n\n"
        f"{PROMPT}"
    )
    contents = [prompt_text]
    for p in sendable:
        try:
            with open(p, "rb") as f:
                img_bytes = f.read()
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=_mime_for(p)))
        except Exception as e:
            print(f"  image embed fail: {p.name} ({repr(e)[:50]})")

    try:
        response = client.models.generate_content(model=MODEL, contents=contents)
        text = response.text or ""
    except Exception as e:
        return {"error": f"Gemini API error: {repr(e)[:200]}"}

    s, e_idx = text.find("{"), text.rfind("}")
    if s >= 0 and e_idx > s:
        # 일부 마크다운 코드펜스(```json) 제거
        raw_json = text[s:e_idx + 1]
        try:
            return json.loads(raw_json)
        except Exception as ex:
            return {"error": f"json parse: {ex}", "raw": text[:800]}
    return {"error": "no JSON found", "raw": text[:800]}


def analyze_article(url, source_name="", title="", date=""):
    """한 글 전체 처리. 성공 캐시는 즉시 반환, error 캐시는 재시도."""
    analysis = _load_analysis()
    if url in analysis and "error" not in analysis[url]:
        print(f"  cached: {url}")
        return analysis[url]
    if url in analysis and "error" in analysis[url]:
        print(f"  retry (prev error): {url}")

    # article_id 추출
    m = re.search(r"/(\d+)(?:[?#/]|$)", url) or re.search(r"/([\w-]+)/?$", url)
    aid = m.group(1) if m else re.sub(r"[^\w-]", "_", url[-30:])

    print(f"\n[분석] {url} (id={aid}, source={source_name})")
    html, full_text = fetch_article_page(url)
    print(f"  본문 텍스트: {len(full_text)}자")

    # 본문 저장
    body_save = ARTICLES_DIR / f"{aid}.txt"
    body_save.write_text(full_text[:10000], encoding="utf-8")
    print(f"  본문 저장: {body_save.name}")

    # 이미지 추출 + 다운로드
    img_urls = extract_images(html, url)
    print(f"  이미지 URL: {len(img_urls)}개")
    img_dir = IMAGES_DIR / aid
    img_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    image_urls_ok = []
    for i, iu in enumerate(img_urls):
        p = download_image(iu, img_dir, i + 1)
        if p:
            image_paths.append(p)
            image_urls_ok.append(iu)
    print(f"  다운로드: {len(image_paths)}개 → {img_dir.name}/")

    # Claude vision 분석
    print(f"  Claude vision 분석 중...")
    result = analyze(url, full_text[:6000], image_paths)

    # 사용자 지정 필드 + 지정 순서로 정리 (url 아래 date 추가)
    result["title"] = title  # 원본 글 제목
    result["url"] = url
    result["date"] = date    # 원문 기사 발행일 (raw·dashboard에서 전달)
    result["image_urls"] = image_urls_ok
    ORDERED_KEYS = [
        "title", "url", "date",
        "one_line_summary", "full_description",
        "image_by_image", "image_urls", "hero_image_index",
        "content_category", "content_format",
        "is_sponsored", "mood_tone", "scene_setting",
        "sponsorship_note", "marketing_insight", "target_audience",
        "topics", "brands_products", "people", "text_in_media",
    ]
    _LIST_FIELDS = {"image_by_image", "image_urls", "topics", "brands_products", "people", "text_in_media"}
    clean = {}
    for k in ORDERED_KEYS:
        if k in result:
            clean[k] = result[k]
        elif k == "is_sponsored":
            clean[k] = False
        elif k == "hero_image_index":
            clean[k] = 0
        elif k in _LIST_FIELDS:
            clean[k] = []
        else:
            clean[k] = ""
    result = clean

    # 저장 — 통합 JSON + 글당 파일 둘 다
    analysis[url] = result
    _save_analysis(analysis)
    try:
        (ANALYSIS_DIR / f"{aid}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"  per-article 저장 실패: {repr(e)[:60]}")
    print(f"  분석 저장: 통합 + analysis/{aid}.json")
    return result


def _save_raw_record(item):
    """카드 raw record를 src/data/raw/<글ID>.json에 저장 (글당 1 파일)."""
    url = item.get("url", "")
    if not url:
        return
    m = re.search(r"/(\d+)(?:[?#/]|$)", url) or re.search(r"/([\w-]+)/?$", url)
    aid = m.group(1) if m else re.sub(r"[^\w-]", "_", url[-30:])
    p = RAW_DIR / f"{aid}.json"
    try:
        p.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"  raw save fail: {aid} ({repr(e)[:50]})")


def analyze_all_from_dashboard():
    """docs/dashboard.html (또는 DASHBOARD_IN 환경변수 파일) 안 모든 카드 URL 일괄 분석.
    동시에 각 카드의 raw record를 src/data/raw/<글ID>.json으로 분리 저장."""
    html_path = ROOT / "docs" / os.environ.get("DASHBOARD_IN", "dashboard.html")
    if not html_path.exists():
        print("dashboard.html 없음 — 먼저 build_dashboard.py 실행 필요")
        return
    html = html_path.read_text(encoding="utf-8")
    m = re.search(r"const DATA = ({.*?});\s*const SRC_COLOR", html, re.DOTALL)
    data = json.loads(m.group(1))
    # URL+source, 중복 제거
    seen_urls = set()
    pairs = []
    raw_saved = 0
    for it in data.get("items", []):
        u = it.get("url", "")
        if not u or u in seen_urls or u.startswith("#"):
            continue
        if "/MicroTrend" in u and any(u == p[0] for p in pairs):
            continue
        seen_urls.add(u)
        pairs.append((u, it.get("source", ""), it.get("title", ""), it.get("date", "")))
        _save_raw_record(it)
        raw_saved += 1
    print(f"  raw record 저장: {raw_saved}건 → {RAW_DIR}")
    print(f"\n총 {len(pairs)} 글 일괄 분석 시작 (캐시 hit는 스킵)\n")
    ok, fail, skip = 0, 0, 0
    cache_pre = _load_analysis()
    for i, (url, src, title, date) in enumerate(pairs, 1):
        print(f"\n[{i}/{len(pairs)}] {src}")
        if url in cache_pre:
            print(f"  cached: {url}")
            skip += 1
            continue
        try:
            analyze_article(url, src, title, date)
            ok += 1
        except Exception as e:
            print(f"  실패: {repr(e)[:140]}")
            fail += 1
    print(f"\n=== 일괄 분석 완료 ===")
    print(f"  새 분석: {ok}건, 캐시 hit: {skip}건, 실패: {fail}건")
    print(f"  분석 파일: {ANALYSIS_FILE}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        analyze_all_from_dashboard()
    else:
        # 단일 URL 모드
        url = sys.argv[1] if len(sys.argv) > 1 else "https://www.careet.net/1914"
        source = sys.argv[2] if len(sys.argv) > 2 else "캐릿"
        result = analyze_article(url, source)
        print()
        print("=== 결과 (요약) ===")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])
