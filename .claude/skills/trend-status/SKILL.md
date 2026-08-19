---
name: trend-status
description: 트렌드 모니터링 파이프라인 상태 점검·장애 진단·복구 안내. "오늘 수집 잘 됐어?", "푸시 확인해줘", "시트에 오늘 글이 없어", "캐릿 로그인/세션 만료", "파이프라인 상태 확인" 같은 요청에 사용. 로그 확인 → 시트 교차검증 → 원인 진단 → 복구 절차 안내까지 수행한다.
---

# 트렌드 파이프라인 상태 점검

이 프로젝트는 매일 아침 Windows 예약작업으로 자동 실행된다:

| 작업명 | 시각 | 스크립트 | 하는 일 |
|---|---|---|---|
| FF-Trend-Daily | 08:00 | `src/core/run_daily.py` | 수집→분석(Gemini)→trends.db→구글시트 push |

최종 산출물 = 구글 공유 시트. (대시보드·교차검증·슬랙 발송은 2026-08-19 제거됨)

모든 파이썬 실행은 반드시 venv 절대경로로: `<프로젝트루트>\venv\Scripts\python.exe`

## 점검 절차 (순서대로)

### 1단계: 오늘 파이프라인이 돌았는지 — run.log

```powershell
Get-Content "<프로젝트루트>\src\data\run.log" -Tail 25
```

정상 판정 기준:
- 오늘 날짜의 `=== run_daily start ===` ~ `=== run_daily done ===` 쌍이 있다
- 각 단계가 `exit=0` (collect / content_analyzer / trenddb export / sheets_push)

오늘 start 자체가 없으면 → 예약작업이 안 돈 것. `Get-ScheduledTaskInfo FF-Trend-Daily`로 LastRunTime·LastTaskResult 확인. PC가 꺼져 있었거나 로그인 전이었을 가능성이 크다. 수동 실행으로 보충:
```powershell
& "<프로젝트루트>\venv\Scripts\python.exe" "<프로젝트루트>\src\core\run_daily.py"
```

### 2단계: 시트에 실제로 들어갔는지 — 교차 확인

로그 exit=0이어도 시트 상태를 반드시 교차 확인한다:

```powershell
& "<프로젝트루트>\venv\Scripts\python.exe" "<프로젝트루트>\src\service\sheets_push.py" --dry
```

- `추가예정 0` → 정상 (로컬 DB 전체가 시트에 반영됨)
- `추가예정 N > 0` → 시트에 빠진 글이 있음. `--dry` 없이 재실행하면 밀린 글이 들어간다 (append-only라 중복·덮어쓰기 위험 없음).

### 3단계: 이상 발견 시 — 증상별 진단

**collect.py exit≠0 (수집 실패)** — 대부분 캐릿 세션 만료다.
1. 사용자에게 알리고 재로그인 절차 진행: `& "<venv python>" "<프로젝트루트>\src\service\setup_profile.py"`
2. 캐릿은 기기 4대 제한 + 신규 기기 이메일 OTP. 로그인 중 인증번호를 요구하면 사용자에게 이메일로 온 코드를 물어보고, 받은 코드를 프로젝트 루트의 `.otp` 파일에 저장한다 (`printf '코드' > .otp`).
3. 기기 슬롯이 꽉 찼다는 화면이 나오면 기존 기기 삭제 먼저 (버튼 셀렉터 `button.btn.acc`).
4. ⚠️ Playwright/크롬 프로세스를 `-Force`로 죽이지 말 것 — 세션 저장 전에 날아간다.
5. 재로그인 성공 후 run_daily.py를 수동 실행해 오늘분을 보충한다.

**sheets_push SKIP 메시지** — 메시지에 원인이 적혀 있다:
- `서비스계정 키 없음` → `.env`의 `GOOGLE_SA_KEY` 경로와 `gcp_sa.json` 존재 확인
- `SHEETS_TREND_ID 필요` → `.env`에 스프레드시트 ID 없음
- `trends.db 없음` → `trenddb.py export` 먼저 실행

**trenddb export 실패 (database is locked)** — DB Browser 등이 trends.db를 열어두고 있는 것. 닫고 재실행.

**content_analyzer 실패** — Gemini API 문제(키 만료·쿼터). `.env`의 `GEMINI_API_KEY` 확인. 분석 실패분은 캐시에 error로 남아 다음 실행 때 자동 재시도되므로, 일시적 오류면 조치 불필요.

### 4단계: 결과 보고

사용자에게 다음을 요약해 보고한다:
- 오늘 파이프라인 실행 여부와 각 단계 결과
- 시트 반영 상태 (추가예정 / 이미있음 건수)
- 이상이 있었다면: 원인, 수행한 조치, 사용자가 직접 해야 할 일(OTP 입력 등)

## 게이트차 (주의사항)

- 캐릿은 유료 미디어 — 본문을 외부에 재배포·복붙하지 않는다 (내부 분석용).
- `.env`, `gcp_sa.json`, `trends.db`는 git에 절대 커밋하지 않는다.
- 진단 중 파일을 삭제하거나 캐시를 임의로 비우지 않는다 — 캐시(`src/data/*_cache.json`)는 재수집 비용을 막는 자산이다.
