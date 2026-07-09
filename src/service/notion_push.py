# -*- coding: utf-8 -*-
"""
notion_push.py — 로컬 trends.db의 글을 Notion 공유 DB에 upsert(중복없이 추가/갱신).

양쪽(rachel/david)이 같은 Notion DB에 push → merge 단계 없이 한 곳에서 같이 본다.
중복 기준 = article_id. 충돌 시: 수집자(owners) 합집합, 날짜는 더 이른 값 보존.

.env 키:
  TEAM_NOTION_TOKEN (또는 NOTION_TOKEN)   - Notion 통합 토큰
  NOTION_TREND_DB_ID                       - 대상 DB id

사용:
  venv\\Scripts\\python.exe src\\service\\notion_push.py          # 전체 push
  venv\\Scripts\\python.exe src\\service\\notion_push.py --limit 3  # 3건만 (테스트)
"""
import os
import sys
import json
import time
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]


def _load_env(p):
    """python-dotenv 있으면 쓰고, 없으면 .env 수동 파싱 (데이빗 PC는 pip 설치 불필요)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(p)
        return
    except ImportError:
        pass
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(ROOT / ".env")
DB = ROOT / "trends.db"
TOKEN = (os.environ.get("NOTION_TREND_TOKEN") or os.environ.get("TEAM_NOTION_TOKEN")
         or os.environ.get("NOTION_TOKEN"))
DBID = os.environ.get("NOTION_TREND_DB_ID")
NVER = "2022-06-28"


def api(path, body=None, method="POST"):
    """Notion API 호출 — 429(rate limit)는 잠깐 쉬고 재시도."""
    for attempt in range(5):
        req = urllib.request.Request(
            "https://api.notion.com/v1/" + path,
            data=json.dumps(body).encode() if body is not None else None, method=method,
            headers={"Authorization": f"Bearer {TOKEN}", "Notion-Version": NVER,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                time.sleep(float(e.headers.get("Retry-After", 1)) + 0.5)
                continue
            raise RuntimeError(f"{e.code}: {e.read().decode()[:200]}")


def rt(s):
    return [{"type": "text", "text": {"content": (s or "")[:1900]}}] if s else []


def ms(s):
    """JSON 배열 문자열 → multi_select 옵션들. 콤마 금지 규칙 회피 + 25개 제한."""
    try:
        arr = json.loads(s) if s else []
    except Exception:
        arr = []
    out = []
    for x in arr[:25]:
        name = str(x).replace(",", " ").strip()[:90]
        if name:
            out.append({"name": name})
    return out


def datev(s):
    s = (s or "").strip()
    return {"start": s} if s else None


def earliest(*v):
    v = [x for x in v if x]
    return min(v) if v else None


def fetch_existing():
    """이미 Notion DB에 있는 글: article_id -> {page_id, owners, first_seen, db_added}"""
    m = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = api(f"databases/{DBID}/query", body)
        for pg in r["results"]:
            p = pg["properties"]
            aid = "".join(t["plain_text"] for t in p.get("article_id", {}).get("rich_text", []))
            if not aid:
                continue

            def d(name):
                v = p.get(name, {}).get("date")
                return v["start"] if v else None
            m[aid] = {"page_id": pg["id"],
                      "owners": {o["name"] for o in p.get("수집자", {}).get("multi_select", [])},
                      "first_seen": d("최초포착일"), "db_added": d("DB등록일")}
        if not r.get("has_more"):
            break
        cursor = r["next_cursor"]
    return m


def build_props(row, owners, first_seen, db_added):
    props = {
        "제목": {"title": rt(row["title"]) or [{"type": "text", "text": {"content": row["article_id"]}}]},
        "article_id": {"rich_text": rt(row["article_id"])},
        "한줄요약": {"rich_text": rt(row["one_line_summary"])},
        "마케팅인사이트": {"rich_text": rt(row["marketing_insight"])},
        "토픽": {"multi_select": ms(row["topics"])},
        "브랜드": {"multi_select": ms(row["brands_products"])},
        "수집자": {"multi_select": [{"name": o} for o in sorted(owners) if o]},
        "광고": {"checkbox": bool(row["is_sponsored"])},
    }
    if row["url"]:
        props["URL"] = {"url": row["url"]}
    if row["content_category"]:
        props["카테고리"] = {"select": {"name": str(row["content_category"]).replace(",", " ")[:90]}}
    for pname, val in (("발행일", row["date"]), ("최초포착일", first_seen),
                       ("DB등록일", db_added), ("갱신일", row["updated_at"])):
        dv = datev(val)
        if dv:
            props[pname] = {"date": dv}
    return props


def main():
    if not TOKEN or not DBID:
        print("SKIP: .env에 NOTION 토큰 / NOTION_TREND_DB_ID 가 필요합니다.")
        sys.exit(2)
    if not DB.exists():
        print("SKIP: trends.db 없음 (먼저 trenddb.py export)")
        sys.exit(2)

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM trends"
    if limit:
        q += f" LIMIT {limit}"
    rows = conn.execute(q).fetchall()

    existing = fetch_existing()
    added = updated = err = 0
    for row in rows:
        aid = row["article_id"]
        local_owners = set(filter(None, (row["owners"] or "").split(",")))
        ex = existing.get(aid)
        try:
            if ex:
                owners = ex["owners"] | local_owners
                fs = earliest(ex["first_seen"], row["first_seen"])
                da = earliest(ex["db_added"], row["db_added"])
                api(f"pages/{ex['page_id']}", {"properties": build_props(row, owners, fs, da)}, "PATCH")
                updated += 1
            else:
                api("pages", {"parent": {"database_id": DBID},
                              "properties": build_props(row, local_owners, row["first_seen"], row["db_added"])})
                added += 1
            time.sleep(0.34)  # rate limit 여유 (~3 req/s)
        except Exception as e:
            err += 1
            print(f"  ! {aid}: {repr(e)[:120]}")

    print(f"NOTION_PUSH 완료: 추가 {added} / 갱신 {updated} / 오류 {err} (총 {len(rows)}건)")


if __name__ == "__main__":
    main()
