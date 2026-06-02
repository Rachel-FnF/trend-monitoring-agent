"""ONE-TIME: register a PERSISTENT careet profile, fully automated except the email OTP.

The script (in its own persistent Chromium window): logs in -> at the device gate it DELETES
one device (frees a slot) -> clicks '인증번호 발송' -> waits for Claude to drop the OTP code in
.otp -> fills #AuthCode + #Name -> clicks '등록 완료' -> verifies. The user only relays the OTP
from the account email; they never touch this window. Never force-kill (persistent profile keeps
the session). Selectors: 삭제=button.btn.acc, code=#AuthCode, name=#Name.
"""
import os, sys, time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
EMAIL = os.environ["CAREET_EMAIL"]
PASSWORD = os.environ["CAREET_PASSWORD"]
PROFILE = ROOT / "profile"
PROFILE.mkdir(exist_ok=True)
OTP_FILE = ROOT / ".otp"
DATA = ROOT / "src" / "data"
DATA.mkdir(exist_ok=True)
DEVNAME = "trend-agent"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def p(*a):
    print(*a, flush=True)


def login_state(page):
    page.goto("https://www.careet.net/MyPage/Membership", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    u = page.url
    if "User/Login" in u:
        return "out"
    if "CheckAccess" in u:
        return "gate"
    if "MyPage/Membership" in u:
        return "in"
    return "unknown:" + u


def safe_close(ctx):
    try:
        ctx.close()
    except Exception:
        pass


if OTP_FILE.exists():
    OTP_FILE.unlink()

with sync_playwright() as pw:
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE), headless=False, user_agent=UA,
        viewport={"width": 1366, "height": 900}, locale="ko-KR", args=["--start-maximized"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.on("dialog", lambda d: d.accept())  # auto-accept any confirm popups

    st = login_state(page)
    p("STATE:", st)
    if st == "out":
        p("LOGIN: 로그인 중...")
        page.goto("https://www.careet.net/User/Login", wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#Email", timeout=20000)
        except Exception:
            p("LOGIN_FORM_NOT_FOUND url =", page.url); safe_close(ctx); sys.exit(1)
        page.fill("#Email", EMAIL)
        page.fill("#PCode", PASSWORD)
        try:
            page.check("#AutoLogin")
        except Exception:
            pass
        page.click("#btnNext")
        page.wait_for_timeout(5000)
        st = login_state(page)
        p("STATE after login:", st)

    if st == "in":
        p("REGISTERED_OK: 이미 로그인됨, 지속 프로필 저장됨."); safe_close(ctx); sys.exit(0)
    if st != "gate":
        p("UNEXPECTED_STATE:", st); safe_close(ctx); sys.exit(1)

    if "CheckAccess" not in page.url:
        page.goto("https://www.careet.net/User/CheckAccess", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

    # 1) delete one device to free a slot
    dels = page.locator("button.btn.acc")
    cnt = dels.count()
    p("device delete buttons:", cnt)
    if cnt > 0:
        try:
            dels.first.click()
            page.wait_for_timeout(3000)
            p("DELETED one device (slot freed)")
        except Exception as e:
            p("delete error:", repr(e)[:80])

    # 2) send OTP
    try:
        page.locator("button:has-text('인증번호 발송'), a:has-text('인증번호 발송')").first.click()
        page.wait_for_timeout(2000)
        p("OTP_SENT: 이메일(hyoeun28@fnfcorp.com)에서 인증번호 확인 후 클로드에게 알려주세요.")
    except Exception as e:
        p("send-otp error:", repr(e)[:80])

    # 3) wait for the OTP code from Claude (.otp file)
    code = None
    for _ in range(300):  # 15 min
        time.sleep(3)
        if OTP_FILE.exists():
            code = OTP_FILE.read_text(encoding="utf-8").strip()
            try:
                OTP_FILE.unlink()
            except Exception:
                pass
            break
    if not code:
        p("OTP_TIMEOUT: 인증번호 미수신. 다시 실행하세요."); safe_close(ctx); sys.exit(1)
    p("GOT_OTP:", code)

    # 4) fill + submit
    try:
        page.fill("#AuthCode", code)
        page.fill("#Name", DEVNAME)
        page.locator("button:has-text('등록 완료'), a:has-text('등록 완료')").first.click()
        page.wait_for_timeout(4000)
    except Exception as e:
        p("submit error:", repr(e)[:120])

    # 5) verify
    st2 = "?"
    try:
        for _ in range(4):
            st2 = login_state(page)
            if st2 == "in":
                break
            time.sleep(4)
    except Exception as e:
        st2 = "window_closed"

    if st2 == "in":
        p("REGISTERED_OK: 등록 성공! 지속 프로필 저장됨.")
    else:
        try:
            page.screenshot(path=str(DATA / "reg_fail.png"), full_page=True)
        except Exception:
            pass
        p(f"STILL_NOT_IN: state={st2}. data/reg_fail.png 확인.")
    safe_close(ctx)
