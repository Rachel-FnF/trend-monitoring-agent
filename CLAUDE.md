# CLAUDE.md — 트렌드 모니터링 Agent (AI 작업 컨텍스트)

이 파일은 Claude/AI 에이전트가 이 프로젝트를 다룰 때 참고하는 컨텍스트다.

## 목적
13개 큐레이션·검색 소스를 매일 수집 → 21일 윈도우로 필터 → Gemini vision으로 본문+이미지 종합 분석 → **구글 공유 시트에 새 글만 append(영구 누적)**. 트렌드를 *일찍* 잡고 *맥락 함께* 보는 게 핵심. 최종 산출물은 구글 시트 하나 — 팀이 같은 시트를 보고, 시트에서 직접 편집한다.

> **2026-08-19 정리**: 대시보드(build_dashboard)·교차검증(cross_trends)·슬랙 발송(send_report/send_db)·레거시(enrich·notion_push·weekly_slack·backfill_hero·model_compare) 전부 제거. 필요하면 git 히스토리(커밋 1588827 이전)에서 복원 가능. 분석기의 글 목록 입력은 대시보드 HTML 파싱 → `article_items.collect_items()` 직접 호출로 대체됨.

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

⚠️ 네이버 데이터랩은 사용자 요청으로 **소스에서 제외**.

## 실제 런타임 아키텍처 (4단계)
- **1) 수집**: `src/core/collect.py` — Playwright headless (캐릿용 지속 프로필 `profile/`) + urllib (외부 소스). SINCE_DATE = 오늘-21일 컷오프. `src/data/collected/collected_<날짜>.json` 출력. `src/data/seen.json`으로 글별 처음 포착일 추적.
- **2) 분석**: `src/service/content_analyzer.py --all` — 글 목록은 `src/service/article_items.py`의 `collect_items()`(수집 스냅샷 + 외부 소스 실시간 fetch → 정규화·21일 필터)에서 직접 취득. **Gemini 3.5 flash** vision으로 본문 텍스트 + 첨부 이미지(최대 12장) 종합 분석. article_id 규칙은 `article_id_from_url()` — 날짜 permalink(보그 `/2026/08/03/슬러그`)는 연도 오인 방지 위해 슬러그 기반 id. URL 단위 영구 캐시(`src/data/article_content_analysis.json`, error도 저장 → 다음 실행 재시도). 본문 → `src/data/articles/<id>.txt`, 이미지 → `src/data/article_images/<id>/img_*.jpg`, 글별 분석 → `src/data/analysis/<id>.json`, raw 카드 → `src/data/raw/<id>.json`. 결과 필드: `url`, `image_urls`, `body_text`, `one_line_summary`, `full_description`, `image_by_image[]`, `topics`, `brands_products`, `is_sponsored`, `marketing_insight` 등.
- **3) DB 누적**: `src/service/trenddb.py export` — `src/data/analysis/*.json` → `trends.db`(SQLite) upsert. 날짜 4칸: `date`(발행일)·`first_seen`(최초 포착, seen.json)·`db_added`(DB 등록일)·`updated_at`(갱신일). 영구 누적(export는 추가만, 삭제 안 함). body_text는 저장 안 함(캐릿 유료).
- **4) 시트 push**: `src/service/sheets_push.py` — `trends.db`를 구글 공유 시트에 **append(새 글만)**. **정책 = 시트가 주인(append-only)**: 시트에 없는 article_id 행만 맨 아래 추가, 기존 행 절대 수정/삭제 안 함 → 사람이 분류·요약 고쳐써도 보존. 자동 칸 A~N(제목·article_id·URL·카테고리·한줄요약·토픽·브랜드·마케팅인사이트·발행일·최초포착일·DB등록일·갱신일·수집자·광고Y/공백), 사람 칸 O~(메모·활용아이디어·상태). ⚠️ A~N 순서 변경·삭제 금지, 새 칸은 오른쪽에만. 중복기준 article_id(B열). 인증 = 구글 서비스계정(`.env`: `GOOGLE_SA_KEY`(기본 `gcp_sa.json`)·`SHEETS_TREND_ID`·`SHEETS_TAB`(기본 `trends`)). `--dry` 미리보기·`--limit N` 테스트. `gcp_sa.json`은 .gitignore, DM으로만 교환, 시트는 서비스계정 이메일에 편집자 공유.
- **스케줄러**: `FF-Trend-Daily` (매일 **08:00**, AC1145 로그인 시) → `run_daily.py` 위 4단계. 이것 하나뿐.
- **광고 제외 조건 없음** (사용자 요청). is_sponsored 마킹은 정보로만.

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

## 셀렉터
로그인 `#Email`/`#PCode`/`#AutoLogin`/`#btnNext` · 기기삭제 `button.btn.acc` · 인증번호 `#AuthCode` · 기기이름 `#Name` · 캐릿 글카드 `a[href="/숫자"]` (시리즈 페이지에서도 같은 패턴).

## 실행
- `venv\Scripts\python.exe src\core\run_daily.py` — 전체 파이프라인 (수집→분석→DB→시트)
- `venv\Scripts\python.exe src\core\collect.py` — 수집만
- `venv\Scripts\python.exe src\service\content_analyzer.py --all` — 오늘 글 목록 전체 분석 (캐시 hit 자동 스킵)
- `venv\Scripts\python.exe src\service\trenddb.py export` — DB 누적만
- `venv\Scripts\python.exe src\service\sheets_push.py` — 시트 push만 (`--dry` 미리보기)
- 세션 만료 시 `src\service\setup_profile.py`

## trenddb 부가 명령 (동료 DB 합치기 — 필요 시)
`set-owner <이름>`(PC당 1회, `trenddb_owner.txt`) · `merge <동료.db>`(article_id 중복제거, owners 합집합, 날짜는 이른 값 보존) · `stats` · `to-json <out.json>`. `*.db`·`trenddb_owner.txt`는 .gitignore — DM으로만 교환.

## .env (gitignore됨)
`CAREET_EMAIL`, `CAREET_PASSWORD`, `GEMINI_API_KEY` (분석용, 필수), `GOOGLE_SA_KEY`, `SHEETS_TREND_ID`, `SHEETS_TAB`. (`SINCE_DATE`로 수집 컷오프 임시 override 가능)
