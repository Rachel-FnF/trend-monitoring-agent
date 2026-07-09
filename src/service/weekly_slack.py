"""매주 월요일 13:00 슬랙 발송 — cross_trends.json을 카드 형태 메시지로 변환.

흐름: cross_trends.json 로드 → 슬랙 메시지 포맷 변환 → webhook POST.
별도 collect/analyze 안 함 (매일 아침 run_daily가 자동 갱신해둠).
"""
import json, os, sys, urllib.request
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
CROSS_FILE = ROOT / "src" / "data" / "cross_trends.json"


def build_message(data):
    title = data.get("report_title", "주간 트렌드 리포트")
    period = f"{data.get('period_from','')} ~ {data.get('period_to','')}"
    trends = data.get("trends", [])
    n_articles = data.get("input_articles", 0)

    lines = [
        f"*📊 {title}*",
        f"_기간: {period} · 분석 글 {n_articles}건 · 트렌드 {len(trends)}개_",
        "",
    ]
    for i, tr in enumerate(trends, 1):
        kw = tr.get("keyword", "")
        what = tr.get("what", "")
        why = tr.get("why", "")
        sources = tr.get("sources", [])
        articles = tr.get("articles", [])

        lines.append(f"*{i}. {kw}* `{len(articles)}건 · {', '.join(sources)}`")
        lines.append(f"• *무엇* {what}")
        lines.append(f"• *왜* {why}")
        if articles:
            lines.append("• *원문*")
            for a in articles[:4]:
                t = a.get("title", "")[:60]
                u = a.get("url", "")
                src = a.get("source", "")
                date = a.get("date", "")
                lines.append(f"   — <{u}|{t}> _({src}, {date})_")
            if len(articles) > 4:
                lines.append(f"   _…외 {len(articles)-4}건_")
        lines.append("")
    lines.append("_상세: 대시보드 docs/dashboard.html_")
    return "\n".join(lines)


def main():
    if not CROSS_FILE.exists():
        print(f"cross_trends.json 없음 — run_daily가 한 번 돌아야 생성됨")
        sys.exit(1)
    data = json.loads(CROSS_FILE.read_text(encoding="utf-8"))
    msg = build_message(data)
    print(f"메시지 길이: {len(msg)}자, 트렌드 {len(data.get('trends',[]))}개")

    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if not hook:
        print("SLACK_WEBHOOK_URL 환경변수 없음")
        sys.exit(1)

    if len(msg) > 38000:
        msg = msg[:38000] + "\n…(전문은 대시보드 참조)"
    payload = json.dumps({"text": msg}).encode("utf-8")
    try:
        req = urllib.request.Request(hook, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
        print("SLACK_SENT")
    except Exception as e:
        print(f"SLACK_FAIL: {repr(e)[:160]}")
        sys.exit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
