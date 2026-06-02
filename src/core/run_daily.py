"""Daily pipeline: collect careet trends, then score into the F&F digest. For the scheduler."""
import subprocess, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / "venv" / "Scripts" / "python.exe"
LOG = ROOT / "src" / "data" / "run.log"


def log(msg):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


log("=== run_daily start ===")
c = subprocess.run([str(PY), str(ROOT / "src" / "core" / "collect.py")])
log(f"collect.py exit={c.returncode}")
if c.returncode != 0:
    log("collect failed — skipping score (세션 만료 시 setup_profile.py 재실행 필요)")
    sys.exit(c.returncode)
s = subprocess.run([str(PY), str(ROOT / "src" / "core" / "score.py")])
log(f"score.py exit={s.returncode}")
if s.returncode == 0:
    d = subprocess.run([str(PY), str(ROOT / "src" / "service" / "deliver.py")])
    log(f"deliver.py exit={d.returncode}")

# Rebuild dashboard from latest snapshot (best-effort, never blocks the pipeline)
try:
    b = subprocess.run([str(PY), str(ROOT / "src" / "service" / "build_dashboard.py")])
    log(f"build_dashboard.py exit={b.returncode}")
except Exception as e:
    log(f"build_dashboard skipped: {repr(e)[:100]}")

log("=== run_daily done ===")
sys.exit(s.returncode)
