# -*- coding: utf-8 -*-
"""
send_report.py — cross_trends.json(교차검증 트렌드)을 '트렌드 리포트'로 정리해 슬랙으로 보낸다.

- 데이터 원천: src/data/cross_trends.json (run_daily.py가 매일 생성)
- 전송: .env 의 SLACK_WEBHOOK_URL (incoming webhook)
- 매일 아침 스케줄러가 호출 (FF-Trend-Report, 08:30)

사용:
  venv\\Scripts\\python.exe src\\service\\send_report.py          # 슬랙 전송
  venv\\Scripts\\python.exe src\\service\\send_report.py --dry    # 전송 안 하고 미리보기만
"""
import os
import sys
import json
import datetime
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
CROSS = ROOT / "src" / "data" / "cross_trends.json"

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
MAX_TRENDS = 8          # 리포트에 담을 트렌드 최대 개수
LINKS_PER_TREND = 2     # 트렌드별 예시 글 링크 개수


def build_message():
    if not CROSS.exists():
        return None, f"cross_trends.json 없음: {CROSS}"
    d = json.load(open(CROSS, encoding="utf-8"))
    trends = d.get("trends", [])[:MAX_TRENDS]
    if not trends:
        return None, "트렌드가 비어 있음 (수집/분석이 안 됐을 수 있음)"

    today = datetime.date.today()
    header = f"*🔥 트렌드 리포트 | {today.isoformat()} ({WEEKDAY_KR[today.weekday()]})*"

    # 데이터 신선도 표시 (오늘 생성분이 아니면 주의 표시)
    gen = (d.get("generated_at") or "")[:10]
    fresh = "🟢 오늘 수집분" if gen == today.isoformat() else f"🟡 {gen} 수집분(오늘 갱신 안 됨)"
    sub = (f"_{d.get('period_from','?')} ~ {d.get('period_to','?')} · "
           f"입력 {d.get('input_articles','?')}건 · 트렌드 {len(trends)}개 · {fresh}_")

    lines = [header, sub, "───────────"]
    for i, t in enumerate(trends, 1):
        lines.append(f"*{i}. {t.get('keyword','')}*")
        if t.get("what"):
            lines.append(f"📌 {t['what']}")
        if t.get("why"):
            lines.append(f"💡 _왜:_ {t['why']}")
        srcs = t.get("sources") or []
        arts = t.get("articles") or []
        if srcs:
            lines.append(f"🔗 출처: {', '.join(srcs)} (관련글 {len(arts)}개)")
        for a in arts[:LINKS_PER_TREND]:
            url, title = a.get("url"), (a.get("title") or "").strip()
            if url and title:
                lines.append(f"   • <{url}|{title}>")
        lines.append("")  # 트렌드 간 빈 줄

    lines.append("───────────")
    lines.append("_매일 아침 자동 발송 · 대시보드: docs/dashboard.html_")
    return "\n".join(lines), None


def main():
    dry = "--dry" in sys.argv
    text, err = build_message()
    if err:
        print("REPORT_SKIP:", err)
        sys.exit(2)

    if dry:
        print("----- 미리보기 (슬랙 전송 안 함) -----\n")
        print(text)
        print(f"\n----- 길이: {len(text)}자 -----")
        return

    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if not hook:
        print("SLACK_SKIP: SLACK_WEBHOOK_URL 미설정")
        sys.exit(2)

    if len(text) > 38000:
        text = text[:38000] + "\n…(생략)"
    payload = json.dumps({"text": text}).encode("utf-8")
    try:
        req = urllib.request.Request(hook, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
        print("SLACK_SENT (트렌드 리포트 전송 완료)")
    except Exception as e:
        print("SLACK_FAIL:", repr(e)[:160])
        sys.exit(1)


if __name__ == "__main__":
    main()
