# 트렌드 모니터링 Agent

13개 큐레이션·검색 소스에서 트렌드 글을 **매일 자동 수집**하고, Gemini vision으로 **본문+이미지를 종합 분석**해 **구글 공유 시트에 누적**하는 에이전트.

> 최종 산출물 = 구글 시트 하나. 팀원들이 같은 시트를 보고, 시트에서 직접 메모·상태를 편집한다.
> (대시보드·교차검증·슬랙 발송은 2026-08-19 정리에서 제거 — git 히스토리에 보존)

## 무엇을 하나
매일 오전 8시(Windows 작업 스케줄러 `FF-Trend-Daily`) → `run_daily.py` 4단계:
1. **수집** — 13개 소스에서 최근 21일 글 → `src/data/collected/collected_<날짜>.json`
2. **분석** — 글별 본문+이미지를 Gemini 3.5 flash vision으로 종합 분석 (URL 단위 영구 캐시, 새 글만 비용 발생) → `src/data/analysis/<글ID>.json`
3. **DB 누적** — 분석 결과를 `trends.db`(SQLite)에 upsert
4. **시트 push** — 구글 공유 시트에 **새 글만 append** (기존 행은 절대 안 건드림 → 사람 편집 보존)

## 수집 소스 (13종)
캐릿(Playwright 로그인) · 고구마팜 · 마케팅레시피 · 20대연구소 · 고슴이의 비트 · The Edit · HeyPop · 인사이트 · 뉴닉 웹 · Eyesmag · 패션비즈 · Vogue · 구글 트렌드 KR
— 소스별 URL·수집 방식·캐시는 `CLAUDE.md`의 소스 표 참조.

## 실행
```bat
:: 전체 파이프라인 (수집→분석→DB→시트)
venv\Scripts\python.exe src\core\run_daily.py

:: 개별 단계
venv\Scripts\python.exe src\core\collect.py
venv\Scripts\python.exe src\service\content_analyzer.py --all
venv\Scripts\python.exe src\service\trenddb.py export
venv\Scripts\python.exe src\service\sheets_push.py        :: --dry 미리보기
```

## 최초 1회 / 캐릿 세션 만료 시
```bat
venv\Scripts\python.exe src\service\setup_profile.py
```
→ 계정 메일로 온 **인증번호(OTP)** 를 프로젝트 루트 `.otp` 파일로 전달하면 기기 등록 완료. (수집이 `SESSION_INVALID`로 실패하면 재실행)

## 설정 (`.env`)
```
CAREET_EMAIL / CAREET_PASSWORD   # 캐릿 로그인
GEMINI_API_KEY                   # 분석 (필수)
GOOGLE_SA_KEY                    # 서비스계정 키 경로 (기본 gcp_sa.json)
SHEETS_TREND_ID / SHEETS_TAB     # 공유 시트 ID · 탭명(기본 trends)
```

## 문서
- `CLAUDE.md` — 기술 명세 (소스·캐시·정책 전부)
- `docs/HANDOVER.md` — 운영 인계 (일일 확인법·장애 대응·PC 이관)
- `docs/handover-simple.html` — 인수인계 안내서 (☀️ 일상 안내 + 📦 상세 매뉴얼 2탭)

## 주의
- 캐릿은 **유료 미디어** — 수집물은 내부 분석용으로만, 외부 재배포 금지 (본문 10% 초과 인용 불가). 시트·DB에도 본문 전문은 저장하지 않는다.
- `.env`·`gcp_sa.json`·`*.db`·`profile/`·`src/data/`는 `.gitignore` — git 커밋 절대 금지, 전달은 DM으로만.
