# 트렌드 모니터링 Agent — 인계 문서 (HANDOVER)

> 이 문서 하나로 "이게 뭔지 → 매일 뭘 확인하면 되는지 → 고장 나면 어떻게 하는지 → 다른 PC로 옮기는 법"까지 커버한다.
> Claude Code가 있다면 `/trend-status` 라고 치면 아래 상태점검·장애대응을 AI가 대신 해준다.

---

## 1. 이게 뭐 하는 시스템인가

캐릿·고구마팜·뉴닉·Vogue 등 **13개 트렌드 소스를 매일 아침 자동 수집**해서, Gemini로 본문·이미지를 분석하고, **구글 공유 시트에 누적**한다:

```
[13개 소스] ──수집──▶ collected_<날짜>.json ──분석(Gemini)──▶ 분석 JSON
                                                        │
                                                        ▼
                                              로컬 DB (trends.db)
                                                        │
                                                        ▼
                                  구글 시트 (새 글만 append, 팀 공유) ★ 최종 산출물
```

- **구글 시트가 팀의 단일 소스**: 시트의 기존 행은 절대 덮어쓰지 않으므로(append-only) 사람이 시트에서 메모·상태를 직접 편집해도 안전하다.
- 전 과정이 Windows 예약작업 하나로 무인 실행된다. 평소에는 아무것도 안 해도 된다.
- (대시보드·교차검증·슬랙 발송 기능은 2026-08-19 정리에서 제거 — 필요하면 git 히스토리에서 복원)

## 2. 자동 실행 스케줄 (Windows 작업 스케줄러)

| 작업명 | 매일 | 실행 스크립트 | 하는 일 |
|---|---|---|---|
| `FF-Trend-Daily` | 08:00 | `src\core\run_daily.py` | 수집→분석(Gemini)→trends.db→구글시트 push |

⚠️ **PC가 켜져 있고 해당 계정으로 로그인된 상태**여야 돈다. 휴가 등으로 PC를 꺼두면 그날 수집은 건너뛰며, 다음 실행 때 최근 21일 윈도우 내 글은 자동 보충된다.

## 3. 매일 아침 정상 확인법 (코드 몰라도 됨)

**구글 시트**: 맨 아래에 오늘 날짜(DB등록일 칸)의 새 행이 추가됐는가 — 이것 하나면 충분하다.

이상하면 → 4번 증상별 대응 또는 Claude Code에서 `/trend-status`.

## 4. 증상별 대응표

| 증상 | 원인(대부분) | 조치 |
|---|---|---|
| 시트에 오늘 행이 없음 | PC 꺼짐/로그인 안 됨, 또는 push 실패 | PC 켜고 로그인 → 수동 실행(아래 5번). `sheets_push.py`는 append-only라 몇 번 돌려도 중복 없음 |
| 수집 실패 (run.log에 collect exit=1) | **캐릿 세션 만료** | `setup_profile.py` 재로그인 (아래 6번) |
| 분석 단계 실패 | Gemini API 키·쿼터 | `.env`의 `GEMINI_API_KEY` 확인. 실패분은 다음 실행 때 자동 재시도 |
| trenddb export 실패 (database is locked) | trends.db를 다른 프로그램이 열어둠 | DB Browser 등 닫고 재실행 |
| 시트 push가 SKIP | 키·설정 누락 | SKIP 메시지에 원인 표시됨 — `.env`의 `GOOGLE_SA_KEY`/`SHEETS_TREND_ID` 확인 |

로그 위치: `src\data\run.log` — 각 단계의 exit 코드가 날짜와 함께 남는다.

## 5. 수동 실행 명령 모음

모두 프로젝트 루트에서, 반드시 venv의 파이썬으로:

```powershell
# 전체 파이프라인 (수집→분석→DB→시트까지 한 번에)
venv\Scripts\python.exe src\core\run_daily.py

# 시트 push만 (미리보기: --dry)
venv\Scripts\python.exe src\service\sheets_push.py

# 캐릿 재로그인 (세션 만료 시)
venv\Scripts\python.exe src\service\setup_profile.py
```

## 6. 캐릿 재로그인 (제일 자주 겪을 일)

캐릿은 유료 멤버십 + **기기 4대 제한 + 신규 기기 이메일 OTP**라서 세션이 만료되면 사람 손이 한 번 필요하다.

1. `venv\Scripts\python.exe src\service\setup_profile.py` 실행
2. 로그인 진행 중 **인증번호 요구** 시: 캐릿 계정 이메일로 온 코드를 확인해 프로젝트 루트에 `.otp` 파일로 저장 (내용 = 코드 숫자만)
3. **기기 슬롯이 꽉 찼다**고 나오면: 기존 기기를 먼저 삭제한 뒤 진행
4. 완료 후 `run_daily.py`를 수동 실행해 그날 분량 보충

주의:
- 기기 등록은 자동화가 쓰는 그 브라우저 프로필(`profile\` 폴더)에서 해야 유효하다. 일반 크롬에서 로그인해봐야 소용없다.
- 브라우저/파이썬 프로세스를 **강제 종료(-Force)하지 말 것** — 세션이 저장되기 전에 날아간다.

## 7. 다른 PC로 이관하는 절차 (체크리스트)

코드는 git에 있지만, **비밀키·브라우저 프로필·예약작업은 git 밖**에 있다. 순서대로:

### 7-1. 구 PC에서 챙겨갈 것 (DM/USB로만 — 절대 git 금지)

- [ ] `.env` 파일 (캐릿 계정, Gemini 키, 시트 ID)
- [ ] `gcp_sa.json` (구글 서비스계정 키)
- [ ] `trends.db` (누적 DB — 새로 시작해도 시트에는 남아있으므로 선택)
- [ ] `trenddb_owner.txt` (수집자 이름표 — 없으면 새 PC에서 `trenddb.py set-owner <이름>` 1회)
- [ ] 의존성 목록: 구 PC에서 `venv\Scripts\pip.exe freeze > requirements.txt` 실행해서 같이 가져갈 것
- [ ] (선택) `src\data\` 폴더 통째 — 본문 캐시를 가져가면 첫 실행 때 재수집·재분석 비용을 아낌

### 7-2. 새 PC 셋업

- [ ] git clone (또는 폴더 복사) → 프로젝트 루트 확정
- [ ] `python -m venv venv` → `venv\Scripts\pip.exe install -r requirements.txt`
- [ ] `venv\Scripts\playwright.exe install chromium`
- [ ] `.env`·`gcp_sa.json`을 프로젝트 루트에 배치
- [ ] **캐릿 기기 등록**: `setup_profile.py` 실행 → 이메일 OTP → 필요시 구 PC 기기 슬롯 삭제 (6번 절차와 동일. **이관에서 제일 까다로운 단계**)
- [ ] 테스트: `run_daily.py` 수동 실행 → run.log 전 단계 exit=0 확인 → `sheets_push.py --dry`로 시트 연결 확인

### 7-3. 예약작업 등록 (새 경로로)

관리자 PowerShell에서, `$ROOT`만 새 경로로 바꿔 실행:

```powershell
$ROOT = "C:\Users\<사용자>\Agent\trend-monitoring-agent"
$PY = "$ROOT\venv\Scripts\python.exe"
schtasks /Create /F /TN FF-Trend-Daily /SC DAILY /ST 08:00 /TR "`"$PY`" `"$ROOT\src\core\run_daily.py`""
```

- [ ] 다음날 아침 3번(정상 확인법)으로 검증
- [ ] 구 PC의 예약작업 삭제: `schtasks /Delete /F /TN FF-Trend-Daily`

### 7-4. 인계 전 결정할 것

- [ ] **캐릿 유료 계정 명의** — 계정 이메일로 OTP가 오므로, 계정 주인이 바뀌면 새 계정으로 프로필 셋업을 처음부터 다시 해야 한다
- [ ] 구글 시트·서비스계정 편집 권한

## 8. 보안·이용 규칙 (반드시 지킬 것)

- **캐릿은 유료 미디어** — 수집 본문은 내부 분석용으로만. 외부 재배포·원문 복붙 금지 (10% 초과 인용 불가).
- `.env`, `gcp_sa.json`, `*.db`는 **git에 절대 커밋 금지** (.gitignore에 이미 등록됨). 전달은 DM으로만.
- 커밋 전 `git status`로 민감 파일이 스테이징됐는지 확인하는 습관.

---
*상세 아키텍처·소스별 수집 방식·캐시 구조는 `CLAUDE.md` 참조. 이 문서는 운영 관점만 담는다.*
