# -*- coding: utf-8 -*-
"""
데이빗_sheets_push.py — 데이빗 PC 전용 독립 실행 스크립트.
내 trends.db 의 새 글을 '트렌드 통합 DB' 구글시트에 append(새 글만 추가)한다.

[시트가 주인 정책]
  - 시트에 없는 글(article_id)만 맨 아래에 추가한다.
  - 이미 있는 행은 절대 수정/삭제하지 않는다. (레이첼/데이빗이 손으로 고친 내용 보존)
  - 사람이 채우는 칸(메모/활용아이디어/상태)은 건드리지 않는다.

[준비물 — 이 스크립트와 같은 폴더에 두기]
  1) gcp_sa.json   (레이첼이 DM으로 보내준 서비스계정 키 파일)
  2) trends.db     (내 분석결과로 만든 DB. trenddb.py export 로 생성)
  설치(1회):  pip install google-auth requests

[실행]
  python 데이빗_sheets_push.py                     # 새 글 push
  python 데이빗_sheets_push.py --dry                # 올라갈 건수만 미리보기
  python 데이빗_sheets_push.py C:\경로\trends.db    # 다른 위치의 db 지정
"""
import sys
import json
import sqlite3
from pathlib import Path

# ===== 설정 (바꿀 일 거의 없음) =====
SHEET_ID = "1w7qX0tpfOI8FbNUDs740tQ7uobGIhuol46WflZc8ENk"  # 트렌드 통합 DB (rachel + david)
TAB = "trends"
# ===================================

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
KEY = HERE / "gcp_sa.json"

SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
BASE = "https://sheets.googleapis.com/v4/spreadsheets"
HEADER = ["제목", "article_id", "URL", "카테고리", "한줄요약", "토픽", "브랜드",
          "마케팅인사이트", "발행일", "최초포착일", "DB등록일", "갱신일", "수집자", "광고"]
HUMAN = ["메모", "활용아이디어", "상태"]
AID_COL = 1  # article_id = B열


def find_db():
    for a in sys.argv[1:]:
        if a.lower().endswith(".db"):
            p = Path(a)
            if p.exists():
                return p
            print(f"오류: 지정한 DB 없음: {p}")
            sys.exit(2)
    p = HERE / "trends.db"
    if p.exists():
        return p
    print(f"오류: trends.db 를 찾을 수 없습니다. 이 스크립트와 같은 폴더({HERE})에 두거나,")
    print("      python 데이빗_sheets_push.py C:\\경로\\trends.db 처럼 경로를 지정하세요.")
    sys.exit(2)


def _joinarr(s):
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
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        print("오류: 라이브러리가 없습니다. 명령창에서 먼저 실행하세요:")
        print("      pip install google-auth requests")
        sys.exit(2)
    if not KEY.exists():
        print(f"오류: 서비스계정 키 없음: {KEY}")
        print("      레이첼이 보내준 gcp_sa.json 을 이 스크립트와 같은 폴더에 두세요.")
        sys.exit(2)
    creds = service_account.Credentials.from_service_account_file(str(KEY), scopes=SCOPE)
    return AuthorizedSession(creds)


def ensure_tab(sess):
    meta = sess.get(f"{BASE}/{SHEET_ID}", params={"fields": "sheets.properties.title"})
    meta.raise_for_status()
    titles = [s["properties"]["title"] for s in meta.json().get("sheets", [])]
    if TAB not in titles:
        sess.post(f"{BASE}/{SHEET_ID}:batchUpdate",
                  json={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}).raise_for_status()
    r = sess.get(f"{BASE}/{SHEET_ID}/values/{TAB}!A1:1")
    r.raise_for_status()
    first = r.json().get("values", [[]])
    if not first or not first[0]:
        sess.put(f"{BASE}/{SHEET_ID}/values/{TAB}!A1",
                 params={"valueInputOption": "RAW"},
                 json={"values": [HEADER + HUMAN]}).raise_for_status()


def existing_ids(sess):
    col = chr(ord("A") + AID_COL)
    r = sess.get(f"{BASE}/{SHEET_ID}/values/{TAB}!{col}2:{col}")
    r.raise_for_status()
    return {row[0].strip() for row in r.json().get("values", []) if row and row[0].strip()}


def main():
    db = find_db()
    dry = "--dry" in sys.argv
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM trends ORDER BY db_added, article_id").fetchall()

    sess = get_session()
    ensure_tab(sess)
    have = existing_ids(sess)
    new_rows = [row_to_values(r) for r in rows if (r["article_id"] or "").strip() not in have]
    skipped = len(rows) - len(new_rows)

    if dry:
        print(f"미리보기: 추가예정 {len(new_rows)} / 이미있음 {skipped} (총 {len(rows)}건)")
        for v in new_rows[:10]:
            print("  +", v[1], v[0][:40])
        return

    if new_rows:
        sess.post(f"{BASE}/{SHEET_ID}/values/{TAB}!A1:append",
                  params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
                  json={"values": new_rows}).raise_for_status()
    print(f"완료: 시트에 추가 {len(new_rows)} / 이미있음(건너뜀) {skipped} (총 {len(rows)}건)")


if __name__ == "__main__":
    main()
