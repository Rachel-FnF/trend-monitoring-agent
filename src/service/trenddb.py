# -*- coding: utf-8 -*-
"""
trenddb.py — 트렌드 분석 결과(JSON)를 SQLite DB로 만들고, 동료 DB와 합치는 도구.

왜 SQLite인가?
  - DB 전체가 'trends.db' 파일 하나라서, 슬랙/메신저 DM으로 그냥 보내면 됨.
  - 서버·인터넷 불필요. 더블클릭 안 해도 이 스크립트로 다 처리.

핵심 아이디어:
  - 각 글은 article_id(파일명, 예: 1876)를 기준키로 씀.
  - 둘 다 같은 글을 모아도 article_id 하나로 자동 중복제거(dedup)됨.
  - 'owners' 칸에 누가 그 글을 모았는지 이름을 누적 → 합쳐도 출처가 남음.
  - 본문(body_text)은 저장 안 함 (캐릿 = 유료 미디어, 외부 공유 금지).

사용법:
  # 0) (각 PC에서 딱 한 번) 이 PC의 이름표 설정
  venv\\Scripts\\python.exe src\\service\\trenddb.py set-owner rachel   # 레이첼 PC
  venv\\Scripts\\python.exe src\\service\\trenddb.py set-owner david    # 데이빗 PC

  # 1) 내 JSON들을 DB로 만들기 (위에서 설정한 이름이 자동으로 붙음)
  venv\\Scripts\\python.exe src\\service\\trenddb.py export

  # 2) 동료가 보낸 DB를 내 DB에 합치기 (받은 파일의 이름표 그대로 보존)
  venv\\Scripts\\python.exe src\\service\\trenddb.py merge 동료.db

  # 3) 현황 보기 (누가 몇 건, 합치면 총 몇 건)
  venv\\Scripts\\python.exe src\\service\\trenddb.py stats

  # (선택) 합쳐진 DB를 다시 JSON 한 덩어리로 빼기
  venv\\Scripts\\python.exe src\\service\\trenddb.py to-json merged.json
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

# 윈도우 콘솔에서 한글이 깨지지 않게 출력 인코딩을 UTF-8로 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 경로 설정 ───────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ANALYSIS_DIR = os.path.join(PROJECT_ROOT, "src", "data", "analysis")
DEFAULT_DB = os.path.join(PROJECT_ROOT, "trends.db")  # DM으로 주고받을 파일
OWNER_FILE = os.path.join(PROJECT_ROOT, "trenddb_owner.txt")  # 이 PC의 주인 이름 (1회 설정)


def read_owner():
    """이 PC에 설정된 주인 이름을 읽는다. set-owner로 저장됨. 없으면 None."""
    try:
        with open(OWNER_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None

# JSON에서 그대로 가져올 단순 텍스트/불리언 칸들
SCALAR_FIELDS = [
    "title", "url", "date",
    "one_line_summary", "full_description",
    "content_category", "content_format",
    "mood_tone", "scene_setting", "sponsorship_note",
    "marketing_insight", "target_audience",
]
# 리스트/딕셔너리라서 JSON 문자열로 저장할 칸들
JSON_FIELDS = ["topics", "brands_products", "people", "image_urls", "image_by_image", "text_in_media"]


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn):
    """trends 테이블이 없으면 만들고, 옛 DB에 빠진 칸이 있으면 추가(마이그레이션)한다."""
    cols = ",\n        ".join([f"{c} TEXT" for c in SCALAR_FIELDS] +
                              [f"{c} TEXT" for c in JSON_FIELDS])
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS trends (
            article_id     TEXT PRIMARY KEY,
            {cols},
            is_sponsored   INTEGER,
            hero_image_index INTEGER,
            owners         TEXT,          -- 이 글을 모은 사람 이름들 (콤마 구분)
            updated_at     TEXT,          -- 데이터 분석/갱신 시각 (충돌 시 최신 우선)
            first_seen     TEXT,          -- 최초 포착일 (seen.json 기반, 주로 캐릿)
            db_added       TEXT           -- DB 최초 등록일 (모든 소스 공통, 일자별 누적의 기준)
        )
    """)
    # 기존 DB(칸 없는 버전)에 새 날짜 칸 추가
    have = {r["name"] for r in conn.execute("PRAGMA table_info(trends)")}
    for col in ("first_seen", "db_added"):
        if col not in have:
            conn.execute(f"ALTER TABLE trends ADD COLUMN {col} TEXT")
    conn.commit()


def row_from_json(article_id, data, owner, updated_at, first_seen=None, db_added=None):
    """JSON 한 건 + 메타정보 → DB에 넣을 dict."""
    row = {"article_id": article_id, "owners": owner, "updated_at": updated_at,
           "first_seen": first_seen, "db_added": db_added}
    for c in SCALAR_FIELDS:
        row[c] = data.get(c)
    for c in JSON_FIELDS:
        val = data.get(c)
        row[c] = json.dumps(val, ensure_ascii=False) if val is not None else None
    row["is_sponsored"] = 1 if data.get("is_sponsored") else 0
    hi = data.get("hero_image_index")
    row["hero_image_index"] = hi if isinstance(hi, int) else None
    return row


def _earliest(*vals):
    """비어있지 않은 날짜 중 가장 이른 것. 다 비면 None."""
    v = [x for x in vals if x]
    return min(v) if v else None


def upsert(conn, row):
    """
    article_id 기준으로 넣거나(insert) 합친다(merge).
    충돌 규칙:
      - updated_at(분석 갱신일)이 더 최신인 쪽의 '내용'을 채택.
      - owners(수집자)는 두 쪽 합집합.
      - first_seen·db_added(최초 날짜)는 더 '이른' 값 보존 — 내용 갱신 여부와 무관한 사실이므로.
    반환: 'added' | 'updated' | 'owner_added' | 'skipped'
    """
    cur = conn.execute("SELECT * FROM trends WHERE article_id = ?", (row["article_id"],))
    existing = cur.fetchone()

    if existing is None:
        cols = list(row.keys())
        conn.execute(
            f"INSERT INTO trends ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
            [row[c] for c in cols],
        )
        return "added"

    # 합집합(owners) · 최소(날짜) 계산 — 사실값이라 내용 갱신과 별개로 항상 보존
    old_owners = set(filter(None, (existing["owners"] or "").split(",")))
    new_owners = set(filter(None, (row.get("owners") or "").split(",")))
    merged_owners = ",".join(sorted(old_owners | new_owners))
    merged_first_seen = _earliest(existing["first_seen"], row.get("first_seen"))
    merged_db_added = _earliest(existing["db_added"], row.get("db_added"))

    facts_changed = (merged_owners != (existing["owners"] or "")
                     or merged_first_seen != existing["first_seen"]
                     or merged_db_added != existing["db_added"])

    incoming_newer = (row.get("updated_at") or "") > (existing["updated_at"] or "")

    if incoming_newer:
        # 내용 전체 갱신 + 사실값(owners·날짜) 병합 반영
        row2 = dict(row)
        row2["owners"] = merged_owners
        row2["first_seen"] = merged_first_seen
        row2["db_added"] = merged_db_added
        cols = [c for c in row2.keys() if c != "article_id"]
        conn.execute(
            f"UPDATE trends SET {','.join(c + '=?' for c in cols)} WHERE article_id=?",
            [row2[c] for c in cols] + [row2["article_id"]],
        )
        return "updated"
    elif facts_changed:
        # 내용은 기존 게 더 최신 → 사실값(owners·날짜)만 보강
        conn.execute(
            "UPDATE trends SET owners=?, first_seen=?, db_added=? WHERE article_id=?",
            (merged_owners, merged_first_seen, merged_db_added, row["article_id"]),
        )
        return "owner_added"
    else:
        return "skipped"


# ── 명령어: export ──────────────────────────────────────────────────────────
def cmd_export(args):
    owner = (args.owner or read_owner() or "").strip()
    if not owner:
        sys.exit("[오류] 이 PC의 이름표가 없습니다.\n"
                 "  먼저 한 번만:  trenddb.py set-owner <이름>   (예: set-owner david)\n"
                 "  또는 매번:     trenddb.py export --owner <이름>")
    db_path = args.db
    src_dir = args.from_dir or ANALYSIS_DIR
    if not os.path.isdir(src_dir):
        sys.exit(f"[오류] 분석 JSON 폴더가 없습니다: {src_dir}\n"
                 f"  (--from <폴더> 로 분석 결과 JSON이 있는 폴더를 지정할 수 있습니다)")

    conn = connect(db_path)
    ensure_schema(conn)

    # 최초 포착일 출처 (캐릿 위주). 없으면 빈 dict → first_seen은 None 처리.
    seen = {}
    try:
        with open(os.path.join(PROJECT_ROOT, "src", "data", "seen.json"), encoding="utf-8") as fp:
            seen = json.load(fp)
    except FileNotFoundError:
        pass

    files = [f for f in os.listdir(src_dir) if f.endswith(".json")]
    counts = {"added": 0, "updated": 0, "owner_added": 0, "skipped": 0, "error": 0}
    for fn in files:
        path = os.path.join(src_dir, fn)
        article_id = os.path.splitext(fn)[0]
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
            # 파일 수정시각을 updated_at(분석 갱신일)으로 사용
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
            first_seen = seen.get(article_id)          # 최초 포착일 (없으면 None)
            db_added = first_seen or mtime[:10]        # DB 최초 등록일 (모든 소스 공통, 신규는 upsert가 보존)
            row = row_from_json(article_id, data, owner, mtime, first_seen, db_added)
            result = upsert(conn, row)
            counts[result] += 1
        except Exception as e:
            counts["error"] += 1
            print(f"  ! {fn}: {e}")

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0]
    conn.close()
    print(f"\n[완료] '{owner}' 이름으로 {len(files)}개 파일 처리 → {db_path}")
    print(f"  신규 {counts['added']} / 갱신 {counts['updated']} / "
          f"이름추가 {counts['owner_added']} / 변화없음 {counts['skipped']} / 오류 {counts['error']}")
    print(f"  현재 DB 총 글 수: {total}건")


# ── 명령어: merge ───────────────────────────────────────────────────────────
def cmd_merge(args):
    other = args.other_db
    db_path = args.db
    label = (args.as_owner or "").strip()  # 보통은 비워둠 → 받은 파일의 이름표 그대로 보존
    if not os.path.isfile(other):
        sys.exit(f"[오류] 합칠 DB 파일을 찾을 수 없습니다: {other}")

    conn = connect(db_path)
    ensure_schema(conn)
    other_conn = connect(other)

    try:
        rows = other_conn.execute("SELECT * FROM trends").fetchall()
    except sqlite3.OperationalError:
        sys.exit(f"[오류] {other} 안에 trends 테이블이 없습니다. trenddb.py로 만든 DB가 맞나요?")

    counts = {"added": 0, "updated": 0, "owner_added": 0, "skipped": 0}
    for r in rows:
        row = dict(r)
        if label:
            row["owners"] = label  # 동료가 무슨 이름을 썼든 일괄로 이 이름표로 통일
        result = upsert(conn, row)
        counts[result] += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0]
    conn.close()
    other_conn.close()
    print(f"[완료] {other} 의 {len(rows)}건을 {db_path} 에 합쳤습니다.")
    print(f"  새로 추가 {counts['added']} / 내용갱신 {counts['updated']} / "
          f"출처만추가 {counts['owner_added']} / 이미보유 {counts['skipped']}")
    print(f"  합친 후 총 글 수: {total}건 (중복은 article_id로 자동 제거됨)")


# ── 명령어: stats ───────────────────────────────────────────────────────────
def cmd_stats(args):
    db_path = args.db
    if not os.path.isfile(db_path):
        sys.exit(f"[오류] DB가 없습니다: {db_path}  (먼저 export 하세요)")
    conn = connect(db_path)
    ensure_schema(conn)

    total = conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0]
    print(f"총 글 수: {total}건\n")

    print("[사람별 보유 건수]")
    owner_count = {}
    for r in conn.execute("SELECT owners FROM trends"):
        for o in filter(None, (r["owners"] or "").split(",")):
            owner_count[o] = owner_count.get(o, 0) + 1
    for o, c in sorted(owner_count.items(), key=lambda x: -x[1]):
        print(f"  {o}: {c}건")

    both = conn.execute(
        "SELECT COUNT(*) FROM trends WHERE owners LIKE '%,%'").fetchone()[0]
    print(f"  (둘 이상이 함께 모은 글: {both}건)\n")

    print("[카테고리별]")
    for r in conn.execute(
        "SELECT content_category AS c, COUNT(*) AS n FROM trends "
        "GROUP BY content_category ORDER BY n DESC LIMIT 10"):
        print(f"  {r['c'] or '(미분류)'}: {r['n']}건")
    conn.close()


# ── 명령어: to-json (선택) ──────────────────────────────────────────────────
def cmd_to_json(args):
    db_path = args.db
    if not os.path.isfile(db_path):
        sys.exit(f"[오류] DB가 없습니다: {db_path}")
    conn = connect(db_path)
    out = []
    for r in conn.execute("SELECT * FROM trends ORDER BY date DESC"):
        d = dict(r)
        for c in JSON_FIELDS:
            if d.get(c):
                try:
                    d[c] = json.loads(d[c])
                except Exception:
                    pass
        d["is_sponsored"] = bool(d.get("is_sponsored"))
        out.append(d)
    conn.close()
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    print(f"[완료] {len(out)}건 → {args.out}")


def cmd_set_owner(args):
    name = args.name.strip()
    if not name:
        sys.exit("[오류] 이름이 비었습니다.")
    with open(OWNER_FILE, "w", encoding="utf-8") as f:
        f.write(name)
    print(f"[완료] 이 PC의 이름표를 '{name}' 로 설정했습니다.")
    print(f"  이제부터 그냥 'export' 만 해도 '{name}' 이름으로 저장됩니다.")
    print(f"  (설정 파일: {OWNER_FILE})")


def main():
    p = argparse.ArgumentParser(description="트렌드 분석 JSON ↔ SQLite DB 도구")
    p.add_argument("--db", default=DEFAULT_DB, help=f"내 DB 파일 경로 (기본: {DEFAULT_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)

    pso = sub.add_parser("set-owner", help="이 PC의 이름표를 1회 설정")
    pso.add_argument("name", help="이 PC 주인 이름 (예: rachel 또는 david)")
    pso.set_defaults(func=cmd_set_owner)

    pe = sub.add_parser("export", help="내 JSON들을 DB로 만들기")
    pe.add_argument("--owner", default=None,
                    help="이름표 직접 지정 (생략 시 set-owner로 저장한 이름 사용)")
    pe.add_argument("--from", dest="from_dir", default=None,
                    help="분석 JSON 폴더 경로 (생략 시 src/data/analysis)")
    pe.set_defaults(func=cmd_export)

    pm = sub.add_parser("merge", help="동료 DB를 내 DB에 합치기")
    pm.add_argument("other_db", help="합칠 상대방 .db 파일 경로")
    pm.add_argument("--as", dest="as_owner", default=None,
                    help="받은 데이터의 이름표를 강제로 바꿀 때만 사용 "
                         "(보통 생략 → 보내준 사람 이름 그대로 보존)")
    pm.set_defaults(func=cmd_merge)

    ps = sub.add_parser("stats", help="현황 보기")
    ps.set_defaults(func=cmd_stats)

    pj = sub.add_parser("to-json", help="DB를 JSON 한 덩어리로 빼기")
    pj.add_argument("out", help="출력 JSON 경로")
    pj.set_defaults(func=cmd_to_json)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
