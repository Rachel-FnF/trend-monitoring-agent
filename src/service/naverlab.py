"""Naver DataLab 쇼핑인사이트 — F&F 카테고리(패션의류·패션잡화·화장품/미용) 인기검색어.

공개 내부 API(getCategoryKeywordRank.naver), 인증키 불필요(Referer 헤더만 필요).
네이버는 한국 최대 검색·쇼핑 엔진이라 전 연령대·대중 검색수요 신호 → 40~50대 약점 보완.
"""
import sys, json, datetime, urllib.request, urllib.parse

ENDPOINT = "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver"
CATS = [("패션의류", "50000000"), ("패션잡화", "50000001"), ("화장품/미용", "50000002")]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _fetch(cid, start, end, count):
    body = urllib.parse.urlencode({
        "cid": cid, "timeUnit": "date", "startDate": start, "endDate": end,
        "age": "", "gender": "", "device": "", "page": "1", "count": str(count)}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        "User-Agent": UA,
        "Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    data = json.loads(urllib.request.urlopen(req, timeout=25).read().decode("utf-8"))
    return [r.get("keyword", "").strip() for r in data.get("ranks", []) if r.get("keyword")]


def fetch_naver_shopping_kr(count=10):
    end = datetime.date.today() - datetime.timedelta(days=1)   # 데이터 1일 지연
    start = end - datetime.timedelta(days=6)
    s, e = start.isoformat(), end.isoformat()
    out = []
    for name, cid in CATS:
        try:
            kws = _fetch(cid, s, e, count)
        except Exception:
            kws = []
        out.append({"category": name, "period": f"{s}~{e}", "keywords": kws})
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for c in fetch_naver_shopping_kr():
        print(f"[{c['category']}] ({c['period']})")
        print("  " + ", ".join(c["keywords"]))
