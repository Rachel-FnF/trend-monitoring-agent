"""TikTok Creative Center — 한국 인기 해시태그 수집.

직접 API는 서명 토큰을 요구(40101)해서, Creative Center 페이지를 headless 브라우저로 띄우고
페이지가 내부적으로 호출하는 trend API 응답(브라우저가 서명함)을 가로채 파싱한다.
"""
import sys, json
from playwright.sync_api import sync_playwright

PAGE = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en?period=7&region=KR"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def fetch_tiktok_hashtags_kr(limit=15):
    captured = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        def on_resp(r):
            if "popular_trend/hashtag/list" in r.url:
                try:
                    captured.append(r.json())
                except Exception:
                    pass
        page.on("response", on_resp)
        try:
            page.goto(PAGE, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(7000)
        except Exception:
            pass
        ctx.close(); b.close()

    out = []
    for data in captured:
        lst = (data.get("data") or {}).get("list") or []
        for it in lst:
            name = it.get("hashtag_name") or it.get("hashtag")
            if not name:
                continue
            ind = (it.get("industry_info") or {}).get("value") or ""
            out.append({"hashtag": "#" + name, "rank": it.get("rank"),
                        "views": it.get("video_views") or it.get("publish_cnt"), "industry": ind})
        if out:
            break
    # dedupe by hashtag, keep order
    seen, res = set(), []
    for h in out:
        if h["hashtag"] not in seen:
            seen.add(h["hashtag"]); res.append(h)
    return res[:limit]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    items = fetch_tiktok_hashtags_kr()
    print(f"tiktok hashtags KR: {len(items)}건")
    for it in items:
        print(f"- {it['hashtag']} (rank {it.get('rank')}, {it.get('industry')})")
