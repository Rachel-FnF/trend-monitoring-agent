# -*- coding: utf-8 -*-
"""
send_db.py — trends.db 파일을 슬랙 채널에 자동 업로드한다 (봇 토큰 필요).

⚠️ incoming webhook(SLACK_WEBHOOK_URL)으로는 파일 업로드가 안 됨 → 봇 토큰 필요.
필요한 .env 키:
  SLACK_BOT_TOKEN   = xoxb-...   (Slack 앱의 Bot User OAuth Token, 스코프 files:write)
  SLACK_DB_CHANNEL  = C0XXXXXXX  (업로드할 채널 ID. 봇을 그 채널에 /invite 해둬야 함)

사용:
  venv\\Scripts\\python.exe src\\service\\send_db.py
스케줄: FF-Trend-DB-Send (매일 08:35, export 이후)
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DB = ROOT / "trends.db"

TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CHANNEL = os.environ.get("SLACK_DB_CHANNEL")


def api(method, data=None, json_body=None):
    """슬랙 Web API 호출 (Bearer 토큰)."""
    url = f"https://slack.com/api/{method}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    else:
        body = urllib.parse.urlencode(data or {}).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if not TOKEN or not CHANNEL:
        print("SKIP: .env에 SLACK_BOT_TOKEN / SLACK_DB_CHANNEL 가 필요합니다.")
        sys.exit(2)
    if not DB.exists():
        print(f"SKIP: {DB} 없음 (먼저 trenddb.py export)")
        sys.exit(2)

    size = DB.stat().st_size
    today = datetime.datetime.now().date().isoformat()
    fname = f"trends_{today}.db"

    # 1) 업로드 URL 발급
    r1 = api("files.getUploadURLExternal", data={"filename": fname, "length": size})
    if not r1.get("ok"):
        print("FAIL getUploadURLExternal:", r1.get("error"))
        sys.exit(1)
    upload_url, file_id = r1["upload_url"], r1["file_id"]

    # 2) 파일 바이트를 업로드 URL로 전송 (multipart)
    content = DB.read_bytes()
    boundary = "----trenddbboundary7f3a"
    pre = (f"--{boundary}\r\n"
           f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
           f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    post = f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        upload_url, data=pre + content + post,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=120)
    except Exception as e:
        print("FAIL upload:", repr(e)[:160])
        sys.exit(1)

    # 3) 업로드 완료 처리 + 채널 공유
    r3 = api("files.completeUploadExternal", json_body={
        "files": [{"id": file_id, "title": fname}],
        "channel_id": CHANNEL,
        "initial_comment": f"📦 트렌드 DB 자동 전송 ({today}) — `trenddb.py merge`로 합치세요.",
    })
    if not r3.get("ok"):
        print("FAIL completeUploadExternal:", r3.get("error"))
        sys.exit(1)
    print(f"SLACK_DB_SENT ({fname}, {size // 1024}KB → 채널 {CHANNEL})")


if __name__ == "__main__":
    main()
