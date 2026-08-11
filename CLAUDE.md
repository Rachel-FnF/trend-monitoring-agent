# CLAUDE.md — 트렌드 모니터링 Agent (AI 작업 컨텍스트)

이 파일은 Claude/AI 에이전트가 이 프로젝트를 다룰 때 참고하는 컨텍스트다.

## 목적
8개 큐레이션·검색 소스를 매일 수집 → 21일 윈도우로 필터 → 본문+이미지 종합 분석 → 대시보드 카드로 표시. 트렌드를 *일찍* 잡고 *맥락 함께* 보는 게 핵심. F&F 적합성 점수화는 사용자 요청으로 제외, 일반 트렌드 다이제스트로 전환.

## 수집 소스 (사용자가 좁힌 카테고리만)
| 소스 | URL · 범위 | 모듈 |
|---|---|---|
| 캐릿 | `/Content/Series/1` (요즘뜨는밈) + `/2` (Z세대 최신근황) + `/5` (이주의 유행템) + `/TrendKeyword/TrendList?...라이프스타일` (소비 트렌드>라이프스타일) | `src/core/collect.py` (Playwright, 로그인) |
| 고구마팜 | `/category/trends/feed/` (트렌드 RSS) | `src/service/gogumafarm.py` |
| 마케팅레시피 | maily RSS → 카테고리 == `한-입 트렌드`만 필터 | `src/service/maily_marketingrecipe.py` |
| 20대연구소 | `https://www.20slab.org/NewsLetter` (뉴스레터 페이지만) | `src/service/slab20.py` |
| 뉴닉 고슴이의 비트 | `page.stibee.com/archives/325254` (광고 글도 포함, Playwright SPA) | `src/service/stibee_gosumi.py` |
| The Edit | `/category/style` (STYLE 카테고리 — 패션+뷰티) | `src/service/the_edit.py` |
| HeyPop | `/n/?c=POP-UP` (POP-UP 카테고리만, 정적 4건 한계) | `src/service/heypop.py` |
| 인사이트 | `/trend/` | `src/service/insight.py` |
| 뉴닉 웹 트렌드 | `newneek.co/category/trend` — 뉴스레터 보완용 웹 섹션. Playwright로 리스팅(`/@핸들/article/<id>` 카드)만 렌더링, 상세는 공개 REST `api.newneek.co/product/v1/articles/<id>` (contentPlain 전문 포함) | `src/service/newneek.py` |
| Eyesmag | 패션 카테고리. 공개 API `/api/v1/posts` (서버가 카테고리 파라미터 무시 → 최신 60건 받아 카테고리 id 444/445/509로 클라이언트 필터). 본문=TIPTAP JSON text 노드 | `src/service/eyesmag.py` |
| 패션비즈 | `fashionbiz.co.kr` — `server-sitemap.xml` 최신 ~28건 + 기사 페이지 RSC(T-청크, hex=UTF-8 바이트 길이) 파싱. ⚠️ 카테고리 메타 비노출 → 카테고리 필터 불가(전체 최신 수집) | `src/service/fashionbiz.py` |
| Vogue | `/fashion` `/beauty` `/living` — 각 페이지 ld+json ItemList로 리스팅, 기사 페이지 og 메타·`<p>`로 본문 보강. IG 대체용 | `src/service/vogue.py` |
| 구글 트렌드 KR | 한국 급상승 RSS — 일일 누적 21일 history | `src/service/gtrends.py` |

⚠️ 네이버 데이터랩은 사용자 요청으로 **소스에서 제외** (코드 모듈은 남아있되 collect 진입점 없음).

## 실제 런타임 아키텍처
- **수집**: `src/core/collect.py` — Playwright headless (캐릿용 지속 프로필 `profile/`) + urllib (외부 소스). SINCE_DATE = 오늘-21일 컷오프 적용. `src/data/collected_<날짜>.json` 출력. `src/data/seen.json`으로 글별 처음 포착일 추적.
- **본문·이미지 분석**: `src/service/content_analyzer.py` — **Gemini 3.5 flash** vision으로 본문 텍스트 + 첨부 이미지 종합 분석. article_id 규칙은 `article_id_from_url()` 공용 함수 — 날짜 permalink(보그 `/2026/08/03/슬러그`)는 연도 오인 방지 위해 슬러그 기반 id, build_dashboard hero 매칭도 같은 함수 사용. URL 단위 영구 캐시(`src/data/article_content_analysis.json`). 본문 → `src/data/articles/<id>.txt`, 이미지 → `src/data/article_images/<id>/img_*.jpg`. 결과 JSON 필드: `url`, `image_urls`, `body_text`, `one_line_summary`, `full_description`, `image_by_image[]`, `topics`, `brands_products`, `is_sponsored`, `marketing_insight` 등.
- **대시보드**: `src/service/build_dashboard.py` + `dashboard_template.html` → `docs/dashboard.html`. 모든 카드 표시(광고 제외 조건은 제거됨). "⭐ 교차검증 트렌드" 섹션은 `cross_trends.json`(Gemini 교차분석)에서 2개+ 소스 트렌드를 읽어 렌더링 — 옛 하드코딩 컨셉 리스트는 21일 윈도우가 흐르면 매칭이 0으로 붕괴해서 제거(2026-07-08).
- **트렌드 리포트 발송**: `src/service/send_report.py` — `cross_trends.json`을 슬랙 mrkdwn으로 정리해 `SLACK_WEBHOOK_URL`로 발송. `--dry`로 미리보기. 트렌드별 키워드/무엇/왜/출처/예시글 링크.
- **(삭제됨) 점수화·옛 다이제스트**: `score.py`·`deliver.py` 파일 삭제, 파이프라인에서 제외. 옛 `docs/review/*.md`(digest·deepread) 전부 삭제.
- **스케줄러** (둘 다 AC1145 로그인 시 실행):
  - `FF-Trend-Daily` (매일 **08:00**) → `run_daily.py`: 수집→대시보드1차→분석→cross_trends→대시보드2차 (대시보드가 오늘자 cross_trends를 임베드하도록 cross_trends가 먼저).
  - `FF-Trend-Report` (매일 **08:30**) → `send_report.py`: 트렌드 리포트 슬랙 발송. (08:00 수집이 끝난 뒤 30분 버퍼)
  - `FF-Trend-DB-Send` (매일 **08:35**) → `send_db.py`: `trends.db`를 슬랙 채널에 파일 업로드. ⚠️ incoming webhook은 파일 못 보냄 → **봇 토큰 필요**: `.env`의 `SLACK_BOT_TOKEN`(xoxb, scope `files:write`)·`SLACK_DB_CHANNEL`(채널ID, 봇을 /invite 해둘 것). 토큰 없으면 SKIP. 슬랙 최신 업로드 API(getUploadURLExternal→completeUploadExternal) 사용.

## 캐시 파일 (`src/data/`)
- `careet_body_cache.json` — 캐릿 본문 영구 캐시
- `slab20_body_cache.json` — 20대연구소 본문
- `the_edit_date_cache.json` — The Edit 본문+날짜
- `heypop_body_cache.json` — HeyPop 본문
- `maily_image_cache.json` — 마케팅레시피 og:image
- `stibee_image_cache.json` — 고슴이 image+body
- `google_trends_history.json` — 구글 트렌드 21일 누적
- `newneek_body_cache.json` — 뉴닉 기사 상세(제목·본문·썸네일)
- `fashionbiz_body_cache.json` — 패션비즈 기사(제목·날짜·이미지·본문)
- `vogue_meta_cache.json` — Vogue 기사(날짜·이미지·본문)
- `article_content_analysis.json` — Gemini 분석 결과 (success/error 모두 저장, error는 다음 실행에 재시도)

## 핵심 게이트차 (중요)
- 캐릿 = **유료 미디어**. 내부 분석용만, 무단 재배포·원문 복붙 금지. 본문 10% 초과 인용 불가.
- **기기 4개 제한 + 신규기기 이메일 OTP.** 기기 등록은 *자동화 그 브라우저(`profile/`)* 에서 해야 유효. 슬롯 꽉 차면 삭제 먼저.
- 프로세스 `-Force` kill 금지 → 세션 저장 전 날아감.
- 로그인 판별: `/MyPage/Membership` 리다이렉트로.
- OTP 전달: 번호 받으면 `printf '코드' > <프로젝트루트>/.otp`.
- **광고 제외 조건은 제거됨** (사용자 요청). is_ad 마킹은 정보로만 남고 필터 안 함.

## 셀렉터
로그인 `#Email`/`#PCode`/`#AutoLogin`/`#btnNext` · 기기삭제 `button.btn.acc` · 인증번호 `#AuthCode` · 기기이름 `#Name` · 캐릿 글카드 `a[href="/숫자"]` (시리즈 페이지에서도 같은 패턴).

## 실행
- `venv\Scripts\python.exe src\core\run_daily.py` — 전체 파이프라인 한 번에 (수집→분석→대시보드→cross_trends)
- `venv\Scripts\python.exe src\service\send_report.py` — 트렌드 리포트 슬랙 발송 (`--dry` 미리보기)
- `venv\Scripts\python.exe src\core\collect.py` — 수집만
- `venv\Scripts\python.exe src\service\content_analyzer.py --all` — dashboard.html의 모든 URL 분석 (캐시 hit 자동 스킵)
- `venv\Scripts\python.exe src\service\build_dashboard.py` — 대시보드 빌드
- 세션 만료 시 `src\service\setup_profile.py`

## 동료와 데이터 공유 (SQLite DM 방식)
- `src/service/trenddb.py` — 분석 JSON(`src/data/analysis/*.json`)을 `trends.db`(SQLite 파일 1개)로 만들고, 동료가 DM으로 보낸 `.db`와 합친다.
- 기준키 = **article_id(파일명)**. 같은 글을 둘 다 모아도 자동 중복제거. `owners` 칸에 수집자 이름 누적(합집합).
- **날짜 4칸**: `date`(원문 발행일) · `first_seen`(최초 포착일, seen.json 기반·캐릿 위주) · `db_added`(DB 최초 등록일, 모든 소스 공통 = 일자별 누적 축) · `updated_at`(분석 갱신일). merge 규칙: 내용은 `updated_at` 최신 우선, 날짜(`first_seen`/`db_added`)는 **더 이른 값 보존**, `owners`는 합집합. 옛 DB는 export/merge 시 자동 마이그레이션(칸 추가+백필). **누적은 기본 동작** — export는 추가만 하고 삭제 안 함(수집 14일 창은 대시보드 현재뷰에만 적용, DB는 영구 누적).
- **PC별 이름표**: `set-owner <이름>`을 PC마다 1회 실행 → `trenddb_owner.txt`에 저장. 레이첼 PC=`rachel`, 데이빗 PC=`david`. 이후 `export`는 그 이름을 자동 부착. `merge`는 받은 파일의 이름표를 **그대로 보존**(보내는 쪽에서 올바르게 찍혀오므로 --as 불필요).
- body_text는 저장 안 함(캐릿 유료). `*.db`·`trenddb_owner.txt`는 .gitignore됨 — git push 금지, DM으로만 교환.
- 명령: `set-owner <이름>`(1회) → 매일 `export` → 받으면 `merge <동료.db>` → `stats` / (선택) `to-json <out.json>` / 단독 PC는 `export --from <폴더>`로 분석폴더 지정 가능.

## Google Sheets 공유 시트 (단일 소스, "시트가 주인") — 현재 운영 방식
- `src/service/sheets_push.py` — 로컬 `trends.db`를 Google Sheets 공유 시트에 **append(새 글만)**. rachel·david가 **같은 시트에 push + 시트에서 직접 편집 → 한 곳에서 같이 봄/고침(merge 단계 없음)**.
- **정책 = 시트가 주인(append-only)**: 시트에 없는 article_id 행만 맨 아래 추가. **이미 있는 행은 절대 수정/삭제 안 함** → 사람이 분류·요약을 고쳐써도 보존.
- **칸 구조**: 자동 칸 A~N = 제목·article_id·URL·카테고리·한줄요약·토픽·브랜드·마케팅인사이트·발행일·최초포착일·DB등록일·갱신일·수집자·광고(Y/공백). 사람 칸 O~ = 메모·활용아이디어·상태(최초 헤더 생성 시 같이 적어둠, 이후 안 건드림). ⚠️ A~N 순서 변경·삭제 금지(append가 왼쪽부터 채움), 새 칸은 항상 오른쪽.
- 중복기준 article_id(B열). topics/brands는 JSON배열 → "a, b, c"로 평탄화. `--dry`(미리보기)·`--limit N`(테스트).
- 인증 = **구글 서비스계정**. 추가 pip 설치 없음(`google.oauth2.service_account`+`requests` 기존 존재). `.env`: `GOOGLE_SA_KEY`(키 경로, 기본 `gcp_sa.json`)·`SHEETS_TREND_ID`(스프레드시트 ID)·`SHEETS_TAB`(기본 `trends`). `gcp_sa.json`은 .gitignore, **DM으로만 교환**(rachel/david 같은 키 공유, 시트는 서비스계정 이메일에 편집자 공유). `run_daily.py` 7단계에서 자동 push.
- (보관) `src/service/notion_push.py` — 옛 Notion 공유 DB push. Sheets로 대체됨, 코드/`.env`(TEAM_NOTION_TOKEN·NOTION_TREND_DB_ID)는 남겨둠.

## .env (gitignore됨)
`CAREET_EMAIL`, `CAREET_PASSWORD`, `ANTHROPIC_API_KEY` (legacy score용), `GEMINI_API_KEY` (분석용), `SLACK_WEBHOOK_URL`.
