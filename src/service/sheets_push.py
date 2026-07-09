# -*- coding: utf-8 -*-
"""
sheets_push.py — 로컬 trends.db의 글을 Google Sheets 공유 시트에 append(새 글만 추가).

"시트가 주인" 정책:
  - 수집기는 시트에 *없는* article_id 행만 맨 아래에 추가한다.
  - 이미 있는 행은 절대 수정/삭제하지 않는다. (사람이 분류·요약을 고쳐써도 그대로 보존)
  - 자동 칸은 A~N(아래 HEADER 순서). 사람 칸(메모/활용아이디어/상태 등)은 그 오른쪽(O~)에 자유롭게.
    ⚠️ A~N 칸은 순서를 바꾸거나 지우지 말 것(append가 왼쪽부터 채움). 새 칸은 항상 오른쪽에 추가.

rachel·david 둘 다 같은 시트(SHEETS_TREND_ID)에 push → merge 단계 없이 한 곳에서 같이 본다.

.env 키:
  GOOGLE_SA_KEY     - 구글 서비스계정 JSON 키 경로 (기본: 프로젝트루트/gcp_sa.json)
  SHEETS_TREND_ID   - 대상 스프레드시트 ID (URL의 /d/<여기>/edit)
  SHEETS_TAB        - 탭(워크시트) 이름 (기본: trends)

사용:
  venv\\Scripts\\python.exe src\\service\\sheets_push.py            # 새 글 push
  venv\\Scripts\\python.exe src\\service\\sheets_push.py --limit 3  # 3건만 (테스트)
  venv\\Scripts\\python.exe src\\service\\sheets_push.py --dry      # 추가될 건수만 미리보기
"""
import os
import sys
import json
import sqlite3
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
KEY = Path(os.environ.get("GOOGLE_SA_KEY") or (ROOT / "gcp_sa.json"))
if not KEY.is_absolute():
    KEY = ROOT / KEY  # 스케줄러는 CWD가 프로젝트 루트가 아님 — 상대경로는 ROOT 기준으로 해석
SHEET_ID = os.environ.get("SHEETS_TREND_ID")
TAB = os.environ.get("SHEETS_TAB", "trends")
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
BASE = "https://sheets.googleapis.com/v4/spreadsheets"

# 자동 칸 순서 (A~N). 사람 칸은 시트에서 오른쪽(O~)에 직접 추가한다.
HEADER = ["제목", "article_id", "URL", "카테고리", "한줄요약", "토픽", "브랜드",
          "마케팅인사이트", "발행일", "최초포착일", "DB등록일", "갱신일", "수집자", "광고"]
HUMAN = ["메모", "활용아이디어", "상태"]  # 헤더 최초 생성 시에만 같이 적어둠 (이후 건드리지 않음)
AID_COL = 1  # article_id 는 두 번째 칸(B) — 0-based index 1


def _joinarr(s):
    """JSON 배열 문자열 → 'a, b, c'. 파싱 실패 시 원문."""
    try:
        arr = json.loads(s) if s else []
        if isinstance(arr, list):
            return ", ".join(str(x).strip() for x in arr if str(x).strip())
    except Exception:
        pass
    return (s or "").strip()


def row_to_values(row):
    return [
        (row["title"] or "")[:1000],
        row["article_id"] or "",
        row["url"] or "",
        (row["content_category"] or "")[:100],
        (row["one_line_summary"] or "")[:1500],
        _joinarr(row["topics"])[:1000],
        _joinarr(row["brands_products"])[:1000],
        (row["marketing_insight"] or "")[:1500],
        row["date"] or "",
        row["first_seen"] or "",
        row["db_added"] or "",
        row["updated_at"] or "",
        row["owners"] or "",
        "Y" if row["is_sponsored"] else "",
    ]


def get_session():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    if not KEY.exists():
        print(f"SKIP: 서비스계정 키 없음: {KEY}  (.env의 GOOGLE_SA_KEY 확인)")
        sys.exit(2)
    creds = service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPE)
    return AuthorizedSession(creds)


def ensure_tab(sess):
    """탭이 없으면 만들고, 헤더가 비었으면 헤더(자동+사람 칸)를 1회 적는다."""
    meta = sess.get(f"{BASE}/{SHEET_ID}", params={"fields": "sheets.properties.title"})
    meta.raise_for_status()
    titles = [s["properties"]["title"] for s in meta.json().get("sheets", [])]
    if TAB not in titles:
        sess.post(f"{BASE}/{SHEET_ID}:batchUpdate",
                  json={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}).raise_for_status()
        print(f"  탭 생성: {TAB}")
    # 헤더 확인
    r = sess.get(f"{BASE}/{SHEET_ID}/values/{TAB}!A1:1")
    r.raise_for_status()
    first = r.json().get("values", [[]])
    if not first or not first[0]:
        sess.put(f"{BASE}/{SHEET_ID}/values/{TAB}!A1",
                 params={"valueInputOption": "RAW"},
                 json={"values": [HEADER + HUMAN]}).raise_for_status()
        print("  헤더 작성 완료")


def existing_ids(sess):
    """시트에 이미 있는 article_id 집합. (article_id 칸 = B)"""
    col = chr(ord("A") + AID_COL)  # 'B'
    r = sess.get(f"{BASE}/{SHEET_ID}/values/{TAB}!{col}2:{col}")
    r.raise_for_status()
    vals = r.json().get("values", [])
    return {row[0].strip() for row in vals if row and row[0].strip()}


def main():
    if not SHEET_ID:
        print("SKIP: .env에 SHEETS_TREND_ID(스프레드시트 ID)가 필요합니다.")
        sys.exit(2)
    if not DB.exists():
        print("SKIP: trends.db 없음 (먼저 trenddb.py export)")
        sys.exit(2)

    dry = "--dry" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM trends ORDER BY db_added, article_id"
    if limit:
        q += f" LIMIT {limit}"
    rows = conn.execute(q).fetchall()

    sess = get_session()
    ensure_tab(sess)
    have = existing_ids(sess)

    new_rows = [row_to_values(r) for r in rows if (r["article_id"] or "").strip() not in have]
    skipped = len(rows) - len(new_rows)

    if dry:
        print(f"SHEETS_PUSH(dry): 추가예정 {len(new_rows)} / 이미있음 {skipped} (총 {len(rows)}건)")
        for v in new_rows[:10]:
            print("  +", v[1], v[0][:40])
        return

    if new_rows:
        # append: A1:append → 헤더 아래 첫 빈 행부터 INSERT_ROWS. 자동 칸(A~N)만 채우고
        #         사람 칸(O~)은 비워 둠 → 사람 입력 영역 보존.
        resp = sess.post(f"{BASE}/{SHEET_ID}/values/{TAB}!A1:append",
                         params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                         json={"values": new_rows})
        resp.raise_for_status()

    print(f"SHEETS_PUSH 완료: 추가 {len(new_rows)} / 이미있음(건너뜀) {skipped} (총 {len(rows)}건)")


if __name__ == "__main__":
    main()
