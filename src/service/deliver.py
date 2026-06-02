"""Deliver today's F&F digest via email (HTML) and/or Slack — each gated by .env config.

.env keys (all optional; a channel is used only if its keys are present):
  EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_TO   (Gmail SMTP; TO can be comma-separated)
  SLACK_WEBHOOK_URL                            (Slack incoming webhook)
"""
import os, re, sys, json, smtplib, datetime, urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
TODAY = datetime.date.today().isoformat()
DIGEST = ROOT / "docs" / "review" / f"digest_{TODAY}.md"

if not DIGEST.exists():
    print("NO_DIGEST:", DIGEST); sys.exit(2)
md = DIGEST.read_text(encoding="utf-8")


def to_slack(text):
    """Convert GitHub-style markdown → Slack mrkdwn (no ###; *bold* uses single asterisk)."""
    out = []
    for ln in text.splitlines():
        s = ln.rstrip()
        if s.strip() == "---":
            out.append("───────────"); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            s = "*" + m.group(2).strip() + "*"          # headers → bold line
        else:
            s = re.sub(r"^>\s?", "", s)                  # drop blockquote marker
        s = re.sub(r"\*\*(.+?)\*\*", r"*\1*", s)         # **bold** → *bold*
        s = re.sub(r"^(\s*)[-*]\s+", r"\1• ", s)         # bullets → •
        out.append(s)
    return "\n".join(out)


# ---- Email (Gmail SMTP, HTML so tables render) ----
sender = os.environ.get("EMAIL_SENDER")
app_pw = os.environ.get("EMAIL_APP_PASSWORD")
to = os.environ.get("EMAIL_TO")
if sender and app_pw and to:
    try:
        import markdown as md_lib
        body = md_lib.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    except Exception:
        body = "<pre>" + md.replace("<", "&lt;") + "</pre>"
    html = (f"<meta charset='utf-8'><div style='font-family:Apple SD Gothic Neo,sans-serif;"
            f"max-width:780px;line-height:1.5'>{body}</div>")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[F&F 트렌드] 오늘의 다이제스트 {TODAY}"
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(md, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("EMAIL_SMTP_PORT", "465"))
    rcpts = [a.strip() for a in to.split(",")]
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as s:
                s.login(sender, app_pw); s.sendmail(sender, rcpts, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as s:
                s.starttls(); s.login(sender, app_pw); s.sendmail(sender, rcpts, msg.as_string())
        print(f"EMAIL_SENT ({host}:{port}) ->", to)
    except Exception as e:
        print("EMAIL_FAIL:", repr(e)[:140])
else:
    print("EMAIL_SKIP (env 미설정)")

# ---- Slack (incoming webhook; plain text — tables show as raw) ----
hook = os.environ.get("SLACK_WEBHOOK_URL")
if hook:
    body = to_slack(md)
    if len(body) > 38000:
        body = body[:38000] + "\n…(전문은 파일 참조)"
    payload = json.dumps({"text": body}).encode("utf-8")
    try:
        req = urllib.request.Request(hook, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
        print("SLACK_SENT")
    except Exception as e:
        print("SLACK_FAIL:", repr(e)[:140])
else:
    print("SLACK_SKIP (env 미설정)")
