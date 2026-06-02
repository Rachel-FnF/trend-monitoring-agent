"""스티비 — 뉴닉 '고슴이의 비트' 뉴스레터 아카이브 수집.
SPA라 Playwright headless 렌더링 필요. 캐릿용 같은 영구 프로필 안 씀(로그인 불필요).
앵커 텍스트 패턴: "YYYY. M. D.[(광고)][이모지] 제목" — 자동으로 광고 분리.

페이지 안정성: SPA + 광고 스크립트 때문에 networkidle이 안 떨어지는 경우가 있어
domcontentloaded + wait_for_selector(stib.ee anchors)로 SPA 렌더링 완료를 명시적으로 대기.
빈 결과면 1회 재시도. 그래도 빈 결과면 src/data/stibee_debug.log에 진단 남김.

이미지: 각 글 페이지에 og:image가 없어서 본문 안 hero 이미지를 추출.
패턴 — 본문 안 img 태그들 중 처음 3개는 헤더 템플릿(공통 ntr ID 반복).
첫 등장하는 "새 ntr ID"의 첫 이미지가 본문 hero. URL 단위 캐시.
각 항목: 날짜·제목·URL·is_ad·이미지.
"""
import json, re, sys, datetime, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

PAGE_URL = "https://page.stibee.com/archives/325254"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

ROOT = Path(__file__).resolve().parents[2]
DBG = ROOT / "src" / "data" / "stibee_debug.log"
_IMG_CACHE = ROOT / "src" / "data" / "stibee_image_cache.json"

_LINE = re.compile(r"^(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\(광고\))?\s*(.*?)$")


def _parse(text: str):
    m = _LINE.match(text.strip())
    if not m:
        return None
    y, mo, d, ad, rest = m.groups()
    rest = re.sub(r"^[^\w가-힣\"'\[\(]+", "", rest).strip()
    return {"date": f"{y}-{int(mo):02d}-{int(d):02d}", "title": rest, "is_ad": bool(ad)}


def _diag(msg):
    """빈 결과일 때만 진단 로그 — 작업 스케줄러 stdout이 사라져도 추적 가능."""
    try:
        with open(DBG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except Exception:
        pass


def _load_img_cache():
    if _IMG_CACHE.exists():
        try:
            return json.loads(_IMG_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_img_cache(c):
    try:
        _IMG_CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _hero_image_for(url: str, cache: dict) -> str:
    """본문 첫 hero 이미지 — 처음 등장 ntr이 헤더(공통 템플릿).
    첫 새 ntr 이미지가 본문 hero. 못 찾으면 첫 img로 fallback."""
    if url in cache:
        return cache[url]
    img = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace")
        imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        first_ntr = None
        for src in imgs:
            m = re.search(r"\d+_(\d+)_", src)
            if not m:
                continue
            ntr = m.group(1)
            if first_ntr is None:
                first_ntr = ntr
                continue
            if ntr != first_ntr:
                img = src
                break
        if not img and imgs:
            img = imgs[0]
    except Exception:
        img = ""
    cache[url] = img
    return img


def _grab_anchors(page):
    """페이지 로드 + stib.ee 앵커 추출.
    networkidle이 SPA 광고 스크립트로 못 떨어지는 케이스 회피 → domcontentloaded 후
    실제 우리가 원하는 selector(a[href*='stib.ee'])가 그려질 때까지 명시적으로 대기."""
    page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(3000)  # SPA가 anchor를 그릴 시간
    try:
        page.wait_for_selector("a[href*='stib.ee']", timeout=10000)
    except Exception:
        pass  # selector 못 찾아도 일단 eval 시도
    return page.eval_on_selector_all(
        "a[href*='stib.ee']",
        "els => els.map(e => ({href: e.getAttribute('href') || '', text: (e.innerText || '').trim()}))"
    )


def fetch_stibee_gosumi(limit=15):
    diag_trail = []
    anchors = []

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            page = b.new_page(user_agent=UA, locale="ko-KR")

            # 1차 시도
            try:
                anchors = _grab_anchors(page)
                diag_trail.append(f"try1:anchors={len(anchors)}")
            except Exception as e:
                diag_trail.append(f"try1:fail={repr(e)[:80]}")
                anchors = []

            # 빈 결과면 1회 재시도
            if not anchors:
                page.wait_for_timeout(2000)
                try:
                    anchors = _grab_anchors(page)
                    diag_trail.append(f"try2:anchors={len(anchors)}")
                except Exception as e:
                    diag_trail.append(f"try2:fail={repr(e)[:80]}")
                    anchors = []
        finally:
            b.close()

    out = []
    seen = set()
    for a in anchors:
        href, text = a.get("href", ""), a.get("text", "")
        if not href or not text or href in seen:
            continue
        parsed = _parse(text)
        if not parsed:
            continue
        seen.add(href)
        out.append({**parsed, "url": href})
        if len(out) >= limit:
            break

    if not out:
        _diag(f"empty result | {' | '.join(diag_trail)}")
        return out

    # hero 이미지 보강 — 광고가 아닌 글만 fetch (광고는 어차피 다이제스트 제외).
    img_cache = _load_img_cache()
    fetched = 0
    for it in out:
        if it.get("is_ad"):
            it["image"] = ""
            continue
        if it["url"] not in img_cache:
            fetched += 1
        it["image"] = _hero_image_for(it["url"], img_cache)
    if fetched:
        _save_img_cache(img_cache)

    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_stibee_gosumi()
    print(f"고슴이의 비트: {len(items)}건 (광고 {sum(1 for x in items if x['is_ad'])}건 포함)")
    for it in items:
        mark = "(광고)" if it["is_ad"] else "      "
        print(f"- {it['date']} {mark} {it['title']}  ({it['url']})")
