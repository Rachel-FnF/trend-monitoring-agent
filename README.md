# 트렌드 모니터링 Agent

캐릿(careet.net)에서 트렌드를 **매일 자동 수집**하고, **F&F 관점으로 점수화**해 "오늘의 F&F 트렌드 다이제스트"를 생성하는 에이전트.

> 목표: 트렌드를 *일찍* 포착하고, 그중 F&F(패션·뷰티)에 맞는 것만 골라 매일 자동으로 받아본다.

## 무엇을 하나
매일 오전 9시(Windows 작업 스케줄러 `FF-Trend-Daily`) →
1. **수집** — 캐릿 홈·마이크로 전광판·키워드 10개 버티컬 스크랩 → `src/data/collected_<날짜>.json`
2. **점수화** — Claude가 F&F 6기준으로 채점 → `docs/review/digest_<날짜>.md`

## 폴더 구조
```
trend-monitoring-agent/
├── README.md  CLAUDE.md  .env  .gitignore
├── docs/
│   ├── plan/        roadmap.md
│   ├── review/      digest_*.md (결과 리포트), deepread (분석)
│   └── reference/   careet-structure.md, ff-rubric.md
├── src/
│   ├── core/        collect.py · score.py · run_daily.py
│   ├── service/     setup_profile.py (캐릿 인증/기기등록)
│   ├── util/        (공통 유틸 — 추후)
│   └── data/        collected_*.json · seen.json · run.log
├── profile/         캐릿 로그인 세션(전용 브라우저, 기기등록됨) ⚠️건들지 말 것
└── venv/            파이썬 환경
```

## 실행
```bat
:: 전체(수집+점수화) 한 번
venv\Scripts\python.exe src\core\run_daily.py

:: 수집만 / 점수화만
venv\Scripts\python.exe src\core\collect.py
venv\Scripts\python.exe src\core\score.py
```
매일 자동 실행은 작업 스케줄러 `FF-Trend-Daily`에 이미 등록돼 있음.

## 최초 1회 / 세션 만료 시 (캐릿 기기 등록)
```bat
venv\Scripts\python.exe src\service\setup_profile.py
```
→ 브라우저가 열려 자동 로그인·기기 삭제·인증번호 발송까지 함. 계정 메일로 온 **인증번호(OTP)**를 확인해 전달하면 등록 완료. (수집이 `SESSION_INVALID`로 실패하면 이걸 재실행)

## 설정 (`.env`)
```
CAREET_EMAIL=...        # 캐릿 로그인 이메일
CAREET_PASSWORD=...     # 캐릿 비밀번호
ANTHROPIC_API_KEY=...   # 점수화용 Claude API 키
```

## 주의
캐릿은 유료 미디어다. 수집물은 **내부 분석용**으로만 쓰고 외부 재배포 금지.
