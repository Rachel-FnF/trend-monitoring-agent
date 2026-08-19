"""Daily pipeline: collect trends → analyze (Gemini) → trends.db → Google Sheets push.
For the scheduler (FF-Trend-Daily). 최종 산출물 = 구글 공유 시트 (매일 새 글 append).
대시보드·교차검증·슬랙 발송은 2026-08-19 정리에서 제거됨 (git 히스토리에 보존)."""
import subprocess
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / "venv" / "Scripts" / "python.exe"
LOG = ROOT / "src" / "data" / "run.log"


def log(msg):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(label, *args):
    r = subprocess.run([str(PY)] + [str(a) for a in args])
    log(f"{label} exit={r.returncode}")
    return r.returncode


log("=== run_daily start ===")

# 1) 수집 — 실패하면(세션 만료 등) 이후 단계가 의미 없으므로 중단
if run("collect.py", ROOT / "src" / "core" / "collect.py") != 0:
    log("collect failed — 중단 (세션 만료 시 setup_profile.py 재실행 필요)")
    sys.exit(1)

# 2) 본문·이미지 분석 — Gemini vision. 글 목록은 article_items.collect_items()로 직접 취득,
#    URL 단위 영구 캐시라 새 글만 분석 비용 발생.
try:
    run("content_analyzer.py", ROOT / "src" / "service" / "content_analyzer.py", "--all")
except Exception as e:
    log(f"content_analyzer skipped: {repr(e)[:100]}")

# 3) trends.db 갱신 — 오늘 분석분을 로컬 DB에 누적(upsert). DB Browser가 파일을 열고 있으면
#    'database is locked'로 실패할 수 있으나 파이프라인은 계속 진행.
try:
    run("trenddb.py export", ROOT / "src" / "service" / "trenddb.py", "export")
except Exception as e:
    log(f"trenddb export skipped: {repr(e)[:100]}")

# 4) Google Sheets 공유 시트로 push — 최종 산출물. "시트가 주인" 정책:
#    새 글만 append, 기존 행(사람 편집 포함)은 절대 안 건드림.
try:
    run("sheets_push.py", ROOT / "src" / "service" / "sheets_push.py")
except Exception as e:
    log(f"sheets_push skipped: {repr(e)[:100]}")

log("=== run_daily done ===")
sys.exit(0)
