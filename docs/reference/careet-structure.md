# 캐릿(careet.net) 구조 레퍼런스

## 주요 URL
| 용도 | 경로 |
|---|---|
| 홈 | `/` |
| 개별 글 | `/<숫자>` (예: `/1914`) |
| 로그인 | `/User/Login` |
| 기기 관리(게이트) | `/User/CheckAccess` |
| 멤버십(로그인 확인용) | `/MyPage/Membership` |
| 내 정보 수정 | `/MyPage/MyInfoLock` (비밀번호 재확인 필요) |
| 마이크로 트렌드 전광판 | `/MicroTrend` |
| 키워드별 콘텐츠 | `/TrendKeyword/TrendList?KeywordName=<섹션>&keywordSubName=<키워드>` |
| 모든 콘텐츠 | `/Content/All` |
| 요즘어 사전(유행어) | `/Dictionary` |
| 뜨는 밈 시리즈 | `/Content/Series/1` |

## 셀렉터
- 로그인: `#Email`, `#PCode`(비번), `#AutoLogin`(체크박스), `#btnNext`
- 기기 관리: 기기 삭제 `button.btn.acc`, 인증번호 입력 `#AuthCode`, 기기 이름 `#Name`, 버튼 텍스트 `인증번호 발송`/`등록 완료`
- 글 카드: `a[href]` 중 `/숫자` 형태, 트렌드 라벨 `span.cate` (`유행 예감`/`유행 중`/`유행 지남`)
- 글 제목: `h3.content-title`

## 로그인 상태 판별 (중요)
`/MyPage/Membership` 으로 이동해 최종 URL로 판단:
- `User/Login` 포함 → 로그아웃(out)
- `CheckAccess` 포함 → 로그인됐으나 기기 미등록(gate)
- `MyPage/Membership` 유지 → 정상 로그인(in)
※ 홈의 '로그아웃' 링크는 로그아웃 상태에도 DOM에 존재 → 그걸로 판별하면 오탐.

## 기기 제한 (안티-자동화)
- 동일 ID 최대 **4개 기기**. 새 기기(브라우저)로 로그인하면 `/User/CheckAccess` 게이트.
- 등록하려면: 기기 1개 삭제(슬롯 확보) → 인증번호 발송 → 계정 메일의 OTP 입력 → 기기 이름 → 등록 완료.
- **기기 인식은 세션(쿠키)별**. 등록은 반드시 *수집에 쓸 그 브라우저(지속 프로필 `profile/`)* 에서 해야 한다. 다른 브라우저(본인 Chrome 등)에서 등록하면 자동화 프로필엔 안 붙는다.
- 지속 프로필(`launch_persistent_context`)이면 창을 닫아도 쿠키가 보존된다. 단 프로세스를 `-Force` 강제종료하면 저장 전 날아갈 수 있다.

## 저작권 / ToS
유료 미디어. 무단 전재·재배포 금지, 본문 10% 초과 인용 불가, 인용 시 출처 표기. 자동 스크랩은 약관 위반·계정 차단 리스크 → 본인 계정·내부 분석용 한정, 정중한 속도.
