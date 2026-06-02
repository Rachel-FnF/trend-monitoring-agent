# CLAUDE.md — 트렌드 모니터링 Agent (AI 작업 컨텍스트)

이 파일은 Claude/AI 에이전트가 이 프로젝트를 다룰 때 참고하는 컨텍스트다.

## 목적
캐릿(careet.net) 트렌드를 매일 수집 → F&F 적합성 점수화 → 다이제스트 생성. 트렌드를 *일찍* 잡고 *선별*하는 게 핵심.

## 실제 런타임 아키텍처
- 수집: `src/core/collect.py` — Playwright **headless**, 전용 지속 프로필 `profile/`로 로그인 유지. 홈·`/MicroTrend`·키워드 10개 버티컬 스크랩 → `src/data/collected_<날짜>.json`. `src/data/seen.json`으로 글별 처음 포착일 추적(시점 축).
- 점수화: `src/core/score.py` — Anthropic API(`claude-sonnet-4-6`). collected JSON을 F&F 6기준으로 채점 → `docs/review/digest_<날짜>.md`.
- 오케스트레이션: `src/core/run_daily.py` — collect→score 순차 실행, `src/data/run.log` 기록.
- 인증/기기등록: `src/service/setup_profile.py` — 1회/세션만료 시. 자동 로그인→기기1개 삭제→인증번호 발송→`.otp` 대기→입력→등록.
- 스케줄러: Windows 작업 스케줄러 `FF-Trend-Daily` (매일 09:00, run_daily.py).
- ⚠️ **Hermes는 `%LOCALAPPDATA%\hermes`에 설치돼 있으나 이 파이프라인엔 미사용.** (Playwright+Claude API 직결이 더 안정적이라.)

## 핵심 게이트차 (중요)
- 캐릿 = **유료 미디어**. 내부 분석용만, 무단 재배포·원문 복붙 금지.
- **기기 4개 제한 + 신규기기 이메일 OTP.** 기기 등록은 반드시 *자동화 그 브라우저(`profile/`)* 에서 해야 유효(사용자 본인 Chrome에서 하면 안 붙음). 슬롯 꽉 차면 삭제 먼저.
- 프로세스 `-Force` kill 금지 → 세션 저장 전 날아감. 지속 프로필이면 창 닫혀도 보존됨.
- 로그인 판별: `/MyPage/Membership` 리다이렉트로(in/out/gate). 홈의 '로그아웃' 링크는 로그아웃 상태에도 있어 오탐.
- OTP 전달: 사용자가 번호 알려주면 `printf '코드' > <프로젝트루트>/.otp`.

## 셀렉터
로그인 `#Email`/`#PCode`/`#AutoLogin`/`#btnNext` · 기기삭제 `button.btn.acc` · 인증번호 `#AuthCode` · 기기이름 `#Name` · 글카드 `a[href="/숫자"]`+라벨 `span.cate` · 글제목 `h3.content-title`.

## 브랜드 / 점수화
→ `docs/reference/ff-rubric.md`. 캐릿 사이트 구조 → `docs/reference/careet-structure.md`.

## 실행
`venv\Scripts\python.exe src\core\run_daily.py` (수집+점수화). 세션 만료 시 `src\service\setup_profile.py`.

## .env (gitignore됨)
`CAREET_EMAIL`, `CAREET_PASSWORD`, `ANTHROPIC_API_KEY`.
