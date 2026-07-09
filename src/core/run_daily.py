"""Daily pipeline: collect trends → analyze (Gemini) → build dashboard → cross-trend extract.
For the scheduler (FF-Trend-Daily). 점수매기기(score)·옛 다이제스트 전송(deliver)은 제거됨.
트렌드 리포트 슬랙 발송은 별도 작업(FF-Trend-Report, send_report.py)이 담당."""
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

# 2) 대시보드 1차 빌드 — content_analyzer가 listing image URL 추출에 필요
try:
    run("build_dashboard.py (1차)", ROOT / "src" / "service" / "build_dashboard.py")
except Exception as e:
    log(f"build_dashboard 1차 skipped: {repr(e)[:100]}")

# 3) 본문·이미지 분석 — Gemini vision, 캐시 hit는 자동 스킵(새 글만)
try:
    run("content_analyzer.py", ROOT / "src" / "service" / "content_analyzer.py", "--all")
except Exception as e:
    log(f"content_analyzer skipped: {repr(e)[:100]}")

# 4) 교차검증 트렌드 추출 → cross_trends.json (트렌드 리포트 + 대시보드 교차검증 섹션의 원천)
#    Deep Think 적용본(=cross_trends.json, 실제 결과물) + 미적용 대조군 + 성능 비교 리포트를
#    한 번에 생성한다 (cross_trend_compare.py). 비교 불필요해지면 아래를 cross_trend_extractor.py
#    --model gemini-3.1-pro-preview --thinking high 단독 호출로 바꾸면 비용이 절반으로 준다.
#    ※ 대시보드 2차 빌드보다 먼저 실행 — 대시보드가 오늘자 cross_trends.json을 임베드하도록.
try:
    run("cross_trend_compare.py", ROOT / "src" / "service" / "cross_trend_compare.py")
except Exception as e:
    log(f"cross_trend_compare skipped: {repr(e)[:100]}")

# 5) 대시보드 2차 재빌드 — hero_image_index 대표 이미지 + 오늘자 cross_trends 교차검증 섹션 반영
try:
    run("build_dashboard.py (2차, hero+cross 적용)", ROOT / "src" / "service" / "build_dashboard.py")
except Exception as e:
    log(f"build_dashboard 2차 skipped: {repr(e)[:100]}")

# 6) trends.db 갱신 — 오늘 분석분을 로컬 DB에 누적(upsert). DB Browser가 파일을 열고 있으면
#    'database is locked'로 실패할 수 있으나 파이프라인은 계속 진행.
try:
    run("trenddb.py export", ROOT / "src" / "service" / "trenddb.py", "export")
except Exception as e:
    log(f"trenddb export skipped: {repr(e)[:100]}")

# 7) Google Sheets 공유 시트로 push — rachel/david가 같은 시트를 같이 보고 편집하는 단일 소스.
#    "시트가 주인" 정책: 새 글만 append, 기존 행(사람 편집 포함)은 절대 안 건드림.
try:
    run("sheets_push.py", ROOT / "src" / "service" / "sheets_push.py")
except Exception as e:
    log(f"sheets_push skipped: {repr(e)[:100]}")

log("=== run_daily done ===")
sys.exit(0)
