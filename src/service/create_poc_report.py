"""F&F 트렌드 모니터링 Agent — POC 보고자료를 노션에 작성.
부모: (F&F-ALL) 트랜드 모니터링 Agent 프로젝트 페이지의 자식 페이지로 생성.
다이어그램 자리는 callout 블록(🔲)으로 비워둠 — 나중에 캡처 첨부.
"""
import os, sys
from pathlib import Path
import httpx
from dotenv import load_dotenv

# /log 스킬과 동일한 NOTION_TOKEN 재사용
SKILLS_ENV = Path(os.path.expanduser("~")) / ".claude" / "skills" / "skills" / "log" / ".env"
load_dotenv(SKILLS_ENV)
TOKEN = os.environ.get("NOTION_TOKEN")
if not TOKEN:
    sys.exit(f"NOTION_TOKEN not found in {SKILLS_ENV}")

PARENT = "36cfd8bc-f558-8092-9242-df4e289a0b7a"  # (F&F-ALL) 트랜드 모니터링 Agent 프로젝트 페이지
TITLE = "F&F 트렌드 모니터링 Agent — POC 보고자료"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def rt(text, bold=False, italic=False, code=False, link=None, color="default"):
    o = {"type": "text", "text": {"content": text},
         "annotations": {"bold": bold, "italic": italic, "code": code,
                         "strikethrough": False, "underline": False, "color": color}}
    if link:
        o["text"]["link"] = {"url": link}
    return o


def h2(t): return {"object": "block", "type": "heading_2",
                   "heading_2": {"rich_text": [rt(t, bold=True)]}}
def h3(t): return {"object": "block", "type": "heading_3",
                   "heading_3": {"rich_text": [rt(t, bold=True)]}}
def p(*runs): return {"object": "block", "type": "paragraph",
                      "paragraph": {"rich_text": list(runs)}}
def bullet(*runs): return {"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": list(runs)}}
def numbered(*runs): return {"object": "block", "type": "numbered_list_item",
                             "numbered_list_item": {"rich_text": list(runs)}}
def callout(t, emoji="🔲", color="gray_background"):
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": [rt(t)], "icon": {"type": "emoji", "emoji": emoji}, "color": color}}
def divider(): return {"object": "block", "type": "divider", "divider": {}}
def quote(t): return {"object": "block", "type": "quote",
                      "quote": {"rich_text": [rt(t)]}}


blocks = [
    # Lede
    p(rt("매일 09:00 7개 소스에서 자동 수집 → Claude로 F&F 관점 분석 → 카드형 다이제스트(슬랙) + 인터랙티브 대시보드. "),
      rt("동작 원리·커스터마이징·예외 처리·방법론을 정리한 POC 보고자료입니다.")),
    divider(),

    # ━━ 1. 예시 ━━
    h2("1. 예시 — AI 요약 vs 원본 아티클"),
    p(rt("동일한 글을 자동 분석하면 다음과 같이 정제되어 카드형으로 출력됩니다.")),

    h3("📰 원본 (캐릿, 2026.05.21)"),
    p(rt("트렌드에도 매수·매도 타이밍이 있다? 분야별 '트렌드 지속 기간' 알려드립니다",
          link="https://www.careet.net/1896")),
    quote("(캐릿은 유료 멤버십 미디어 — 원문 직접 인용·재배포 금지. 내부 분석용 발췌만 보유)"),

    h3("🤖 AI 요약 (다이제스트 카드)"),
    p(rt("무엇 ", bold=True),
      rt("— 트렌드별 부상부터 정점까지의 평균 지속 기간을 분야별로 정리한 가이드. 단기 (1~2주) / 중기 (1~3개월) / 장기 (6개월+) 카테고리로 구분.")),
    p(rt("왜 뜨나 ", bold=True),
      rt("— Z세대 트렌드 사이클이 가속되며 마케터들의 시점 전략 수요가 증가. '언제 들어가서 언제 나올지'가 콘텐츠 효율을 좌우.")),
    p(rt("F&F 시사 ", bold=True),
      rt("[패션×라이프스타일] ", italic=True),
      rt("— MLB·Discovery의 시즌 캠페인 기획 시 트렌드 잔존 기간을 사전 매핑해야 ROI 확보. 단기 트렌드는 SNS·디지털, 장기 트렌드는 매장·콜라보·시그니처 라인으로 차등 배분 가능.")),
    p(rt("출처 표기 ", bold=True), rt("[캐릿 5/21] ")),
    divider(),

    # ━━ 2. POC 기술 ━━
    h2("2. POC 기술"),
    callout("기술 아키텍처 다이어그램 자리 — 캡처 후 첨부 예정 (수집→분석→발송→대시보드 전체 흐름)", emoji="🔲"),

    h3("스택"),
    bullet(rt("수집 ", bold=True),
           rt("Playwright headless(캐릿) + urllib + 표준 RSS 파싱(고구마팜·마케팅레시피) + 정규식(20대연구소) + Playwright(스티비 SPA)")),
    bullet(rt("분석 ", bold=True),
           rt("Anthropic Claude (claude-sonnet-4-6) + web_search 도구로 본문 없는 미세트렌드 보강")),
    bullet(rt("저장 ", bold=True),
           rt("JSON 스냅샷(collected_*.json) + 처음포착일 누적(seen.json) + enrich 캐시(dashboard_enrich.json)")),
    bullet(rt("발송 ", bold=True),
           rt("Slack incoming webhook ✅ / Gmail SMTP 코드 준비됨(보류 중)")),
    bullet(rt("자동화 ", bold=True),
           rt("Windows 작업 스케줄러 FF-Trend-Daily — 매일 09:00 무인 실행")),
    bullet(rt("대시보드 ", bold=True),
           rt("자체 포함 단일 HTML — Pretendard + Noto Serif KR + Fraunces 폰트, 어디서나 더블클릭으로 열림")),

    h3("파이프라인 (매일 09:00 자동 순차 실행)"),
    numbered(rt("collect.py — 5개 큐레이션 + Google Trends + 네이버 데이터랩 수집, 컷오프(2026-03-01) 자동 적용")),
    numbered(rt("score.py — Claude로 카드형 다이제스트(.md) 생성, 광고·무관 자동 패스")),
    numbered(rt("deliver.py — 슬랙 webhook 발송 (mrkdwn 변환)")),
    numbered(rt("build_dashboard.py — Claude로 항목별 enrich(URL 캐시) + 대시보드 HTML 재빌드")),

    h3("데이터 소스 7개"),
    bullet(rt("캐릿 ", bold=True), rt("careet.net (유료 멤버십, Playwright + 지속 프로필) — MZ 큐레이션 + 마이크로 트렌드 전광판")),
    bullet(rt("고구마팜 ", bold=True), rt("gogumafarm.kr (공개 RSS) — MZ 트렌드·밈")),
    bullet(rt("마케팅레시피 ", bold=True), rt("maily.so/marketingrecipe (공개 RSS) — Z세대 마케팅 인사이트·사례")),
    bullet(rt("20대연구소 ", bold=True), rt("20slab.org/Column (정적 HTML) — 검증된 세대 분석")),
    bullet(rt("고슴이의 비트 ", bold=True), rt("page.stibee.com (SPA · Playwright, 광고 자동 분리) — 뉴닉 라이프스타일")),
    bullet(rt("Google Trends KR ", bold=True), rt("공개 RSS — 오늘 급상승 검색어")),
    bullet(rt("네이버 데이터랩 ", bold=True), rt("쇼핑인사이트 내부 API — 지난 7일 카테고리별 인기검색어")),
    divider(),

    # ━━ 3. 사용자 커스터마이징 ━━
    h2("3. 사용자 커스터마이징 영역"),
    p(rt("F&F용으로 세팅된 템플릿이지만, 아래 8개 노브만 갈아끼우면 다른 회사·다른 산업에도 그대로 작동합니다.", italic=True)),

    h3("🏷️ 트렌드 카테고리 설정"),
    bullet(rt("캐릿 키워드 버티컬 10개 ", bold=True), rt("— 패션·유행템·뜨는브랜드·핫플레이스·KPOP·콜라보·굿즈·해외트렌드·비주얼레퍼런스·F&B")),
    bullet(rt("네이버 카테고리 3개 ", bold=True), rt("— 패션의류·패션잡화·화장품/미용")),
    bullet(rt("F&B 회사라면 ", italic=True), rt("— 식음료·외식·간편식·디저트 등으로 교체")),

    h3("⚖️ 가중치 & 점수화 기준"),
    bullet(rt("F&F 6기준 ", bold=True), rt("— 시점 · 실행가능성 · 카테고리 · 브랜드매칭 · 타깃 · 리스크")),
    bullet(rt("score.py 프롬프트 안에서 각 축의 비중 조정 가능 ", italic=True), rt("(스타트업이면 시점 우선, 대기업이면 실행가능성 우선 등)")),

    h3("🧭 방향성 (분석 톤)"),
    bullet(rt("F&F 시사 패션 중심 6각도 ", bold=True),
           rt("— 패션×음식, 패션×장소, 패션×인테리어, 패션×라이프스타일, 패션×밈, 패션×세대")),
    bullet(rt("다른 산업이면 각도 자체를 교체 ", italic=True),
           rt("(예: 식품×레시피, 식품×채널, 식품×건강, 식품×B2B)")),

    h3("🕘 수집 주기 · 시간"),
    bullet(rt("기본 매일 09:00 (Windows 작업 스케줄러)")),
    bullet(rt("매시간 / 주1회 / 이슈 푸시 등 자유 변경 가능")),

    h3("📨 자동화 발송 방법"),
    bullet(rt("Slack incoming webhook 작동 중 ", bold=True), rt("(.env SLACK_WEBHOOK_URL)")),
    bullet(rt("이메일 — Gmail SMTP 코드 준비됨, 사용자 보류 중")),
    bullet(rt("Teams · 카카오워크 · 노션 · 텔레그램 등으로 확장 가능")),

    h3("📅 데이터 기간 컷오프"),
    bullet(rt("환경변수 ", italic=False), rt("SINCE_DATE", code=True), rt(" (기본 2026-03-01)")),
    bullet(rt("옛 글이 자동으로 잘려 다이제스트가 항상 '최근'에 집중")),

    h3("➕ 소스 추가 · 제거"),
    bullet(rt("새 사이트도 같은 방식(공개 API/RSS/스크랩)으로 한 모듈만 만들면 collect.py에서 한 줄로 통합")),
    bullet(rt("예: Pinterest Trends · 인스타 해시태그 · 블룸버그 · 해외 이커머스 등")),
    divider(),

    # ━━ 4. 예외 처리 ━━
    h2("4. 예외 처리 방법"),

    h3("🚫 광고 제외 (3중 안전장치)"),
    numbered(rt("소스 단 — 캐릿은 ", bold=True),
             rt("'/숫자' 형태 기사 링크만"), rt(" 수집해 디스플레이 광고·자체 홍보 블록은 애초에 안 봄. 뉴스레터 페이지(협찬 섹션 포함)도 수집 대상 제외.")),
    numbered(rt("AI 판별 — Claude가 ", bold=True),
             rt("광고·협찬·홍보성 콘텐츠를 자동 식별해 '이번엔 패스'로 분류"),
             rt(". 단 ", italic=False), rt("광고를 분석한 ", italic=True),
             rt("에디토리얼(예: '장원영 ETF 광고 기획 비하인드')은 트렌드 콘텐츠로 유지.")),
    numbered(rt("스티비 메타 — 뉴닉의 ", bold=True),
             rt("(광고)", code=True), rt(" 표기를 모듈에서 자동 마킹(", italic=False),
             rt("is_ad=True", code=True), rt(")해 다이제스트 단계에서 무조건 제외.")),

    h3("🎯 F&F와 맞지 않는 트렌드 거르기"),
    bullet(rt("Google Trends 무관 신호 ", bold=True),
           rt("— 주식 종목코드(예: 005930) · 정치인물명 · 일반 사건사고는 자동으로 '이번엔 패스'. 뉴스 제목이 맥락 단서.")),
    bullet(rt("네이버 상시 일반 키워드 ", bold=True),
           rt("— '티셔츠'·'샴푸'처럼 항상 상위에 떠 있는 키워드는 해석 안 함. 급상승·신규·브랜드명·특이 아이템만 다룸.")),
    bullet(rt("20대연구소 일반 데이터 ", bold=True),
           rt("— 트렌드 본카드가 아닌 '참고 레퍼런스'·'모니터링 포인트' 섹션으로 자동 분리.")),
    bullet(rt("score.py 프롬프트 명시 규칙 ", bold=True),
           rt("— 'F&F 무관(주식·정치·사건사고)은 이번엔 패스로 묶어라' / '광고·협찬·홍보성은 트렌드가 아니다'.")),

    callout("예외 처리(광고 + 무관 신호) 파이프라인 다이어그램 자리 — 캡처 후 첨부 예정", emoji="🔲"),
    divider(),

    # ━━ 5. 방법론 ━━
    h2("5. 트렌드 확보 방법론 (test 1)"),
    p(rt("'트렌드를 일찍 + 선별 + 자동'으로 잡기 위한 5가지 설계 원칙.")),

    h3("5.1 다층 소스 구조 (시간 × 폭)"),
    bullet(rt("이른 신호 (1~7일) ", bold=True),
           rt("— 캐릿 전광판 · Google Trends KR · 네이버 데이터랩")),
    bullet(rt("중기 큐레이션 (2~3개월) ", bold=True),
           rt("— 고구마팜 · 마케팅레시피 · 20대연구소 · 고슴이의 비트")),
    bullet(rt("장기 인기 (3년+) ", bold=True),
           rt("— 캐릿 기사 (인기순+최신순 혼합)")),

    h3("5.2 교차검증 (cross-validation)"),
    bullet(rt("같은 트렌드가 2개+ 소스에 동시 등장 → 신뢰도 가점 + "),
           rt("[캐릿+고구마팜]", code=True), rt(" 같은 태그 자동 부여")),
    bullet(rt("실측 사례 ", bold=True),
           rt("— 럭키맥싱(3곳: 캐릿 5/11 → 마케팅레시피 5/21 → 고슴이 4/10), AI 활용·직장인 커리어(4곳), 젤리슈즈(캐릿 전광판 + 네이버 실구매)")),

    h3("5.3 시점 축"),
    bullet(rt("seen.json", code=True), rt("에 글별 처음 포착일을 누적 기록 → 캐릿의 ", italic=False),
           rt("'유행예감 / 유행중 / 유행지남'", italic=True), rt(" 라벨과 동기화")),
    bullet(rt("소스 간 시차로 트렌드 생애주기 시각화 ", italic=True),
           rt("(예: 캐릿이 마케팅레시피보다 2주~4개월 앞서 잡음 → 마케팅레시피 등장 시점 = 대중화 단계)")),

    h3("5.4 본문 보강"),
    bullet(rt("캐릿: 처음 잡힌 새 글 상위 30개에 본문 발췌(2000자) 자동 추가")),
    bullet(rt("미세 트렌드(전광판): 트렌드 이름만 있을 때 Claude의 ", italic=False),
           rt("web_search", code=True),
           rt(" 도구로 외부 자료에서 무엇/왜를 파악, 못 찾으면 '확인 필요'로 정직 처리, 추측 금지")),

    h3("5.5 패션 중심 F&F 시사 6각도"),
    bullet(rt("패션 × 음식 ", bold=True), rt("— F&B 트렌드를 콜라보·굿즈·캠페인으로 환산")),
    bullet(rt("패션 × 장소 ", bold=True), rt("— 핫플·팝업·여행을 매장·VMD·체험으로")),
    bullet(rt("패션 × 인테리어 ", bold=True), rt("— 공간·미감을 매장·디스플레이·아이덴티티로")),
    bullet(rt("패션 × 라이프스타일 ", bold=True), rt("— 취향·여가·웰니스를 톤·페르소나·세컨라인으로")),
    bullet(rt("패션 × 밈 ", bold=True), rt("— 콘텐츠·SNS 흐름을 마케팅·캠페인·디지털로")),
    bullet(rt("패션 × 세대 ", bold=True), rt("— Z·30대·40대+ 매핑을 브랜드 포지셔닝·세컨라인으로")),

    callout("소스 다층 구조 + 시점 축 + 교차검증 다이어그램 자리 — 캡처 후 첨부 예정", emoji="🔲"),
    divider(),

    p(rt("Generated 2026-06-01 — 트렌드 모니터링 Agent POC", italic=True, color="gray")),
]

# Notion API has 100-block limit per request
body = {
    "parent": {"page_id": PARENT},
    "properties": {"title": [{"text": {"content": TITLE}}]},
    "children": blocks[:100],
}
r = httpx.post("https://api.notion.com/v1/pages", headers=HEADERS, json=body, timeout=30)
if r.status_code != 200:
    sys.exit(f"create page FAIL: {r.status_code} {r.text[:500]}")
page = r.json()
print(f"CREATED page: {page['url']}")

if len(blocks) > 100:
    rest = blocks[100:]
    r2 = httpx.patch(f"https://api.notion.com/v1/blocks/{page['id']}/children",
                     headers=HEADERS, json={"children": rest}, timeout=30)
    if r2.status_code != 200:
        print(f"WARN append failed: {r2.status_code} {r2.text[:200]}")
    else:
        print(f"appended {len(rest)} more blocks")

print(f"DONE — {len(blocks)} blocks total")
