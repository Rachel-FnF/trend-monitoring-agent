# 트렌드 모니터링 Agent

8개 큐레이션·검색 소스에서 트렌드를 **매일 자동 수집**하고, Gemini vision으로 **본문+이미지를 종합 분석**해 대시보드 카드로 표시하는 에이전트.

> 목표: 트렌드를 *일찍* 포착하고, 본문·이미지 맥락까지 함께 보여 한눈에 파악한다.

## 무엇을 하나
매일 오전 9시(Windows 작업 스케줄러 `FF-Trend-Daily`) →
1. **수집** — 8개 소스(아래 표)에서 최근 14일 글 → `src/data/collected_<날짜>.json`
2. **분석** — 각 글의 본문 텍스트 + 첨부 이미지를 Gemini 3.5 flash vision으로 종합 분석 → `src/data/article_content_analysis.json`
3. **대시보드** — 카드형 HTML 빌드 → `docs/dashboard.html`

## 수집 소스 (사용자가 좁힌 범위)
| 소스 | 범위 | 모듈 |
|---|---|---|
| 캐릿 | 시리즈 3개 — 요즘뜨는밈·Z세대 최신근황·이주의 유행템 | `collect.py` (Playwright, 로그인) |
| 고구마팜 | 트렌드 RSS | `gogumafarm.py` |
| 마케팅레시피(maily) | 카테고리 = **한-입 트렌드**만 | `maily_marketingrecipe.py` |
| 20대연구소 | NewsLetter 페이지 | `slab20.py` |
| 뉴닉 고슴이의 비트 | 전체 (광고 포함) | `stibee_gosumi.py` |
| The Edit(디에디트) | STYLE 카테고리 (패션+뷰티) | `the_edit.py` |
| HeyPop | POP-UP 카테고리 | `heypop.py` |
| 인사이트 | 트렌드 | `insight.py` |
| 구글 트렌드 KR | 한국 급상승 RSS — 14일 누적 | `gtrends.py` |

> 네이버 데이터랩은 사용자 요청으로 제외됨. F&F 적합성 점수화도 일반 트렌드 다이제스트로 전환됨.

## 폴더 구조
```
trend-monitoring-agent/
├── README.md  CLAUDE.md  .env  .gitignore
├── docs/
│   ├── dashboard.html              ← 결과 대시보드
│   ├── plan/        roadmap.md
│   ├── review/      digest_*.md (legacy 점수화 다이제스트)
│   └── reference/   careet-structure.md, ff-rubric.md
├── src/
│   ├── core/        collect.py · score.py(legacy) · run_daily.py
│   ├── service/     content_analyzer.py · build_dashboard.py · 8개 소스 모듈 · setup_profile.py · deliver.py
│   ├── util/
│   └── data/
│       ├── collected_*.json              ← 일일 수집 원본
│       ├── article_content_analysis.json ← Gemini 분석 결과 (URL 단위 영구 캐시)
│       ├── articles/<id>.txt             ← 본문 텍스트
│       ├── article_images/<id>/img_*.jpg ← 본문 이미지
│       ├── *_body_cache.json             ← 소스별 본문/이미지 캐시
│       └── seen.json · google_trends_history.json
├── profile/         캐릿 로그인 세션 ⚠️건들지 말 것
└── venv/            파이썬 환경
```

## 실행
```bat
:: 수집
venv\Scripts\python.exe src\core\collect.py

:: 본문+이미지 분석 (dashboard.html의 모든 카드 URL 대상, 캐시 hit 자동 스킵)
venv\Scripts\python.exe src\service\content_analyzer.py --all

:: 대시보드 빌드
venv\Scripts\python.exe src\service\build_dashboard.py

:: (legacy) F&F 점수화 다이제스트 — 사용자 요청으로 더 이상 자동 실행 안 함
venv\Scripts\python.exe src\core\score.py
```

매일 자동 실행은 작업 스케줄러 `FF-Trend-Daily`에 이미 등록돼 있음.

## 최초 1회 / 세션 만료 시 (캐릿 기기 등록)
```bat
venv\Scripts\python.exe src\service\setup_profile.py
```
→ 브라우저가 열려 자동 로그인·기기 삭제·인증번호 발송까지 함. 계정 메일로 온 **인증번호(OTP)** 를 확인해 전달하면 등록 완료. (수집이 `SESSION_INVALID`로 실패하면 이걸 재실행)

## 설정 (`.env`)
```
CAREET_EMAIL=...            # 캐릿 로그인 이메일
CAREET_PASSWORD=...         # 캐릿 비밀번호
ANTHROPIC_API_KEY=...       # (legacy) score.py용
GEMINI_API_KEY=...          # 본문+이미지 vision 분석용 (필수)
SLACK_WEBHOOK_URL=...       # 다이제스트 슬랙 전달
```

## 분석 결과 JSON 필드
`article_content_analysis.json`의 각 글:
- `url`, `article_id`, `source`, `model`, `analyzed_at`
- `image_urls[]` — 다운로드된 본문 이미지 원본 URL (image_by_image 인덱스와 일치)
- `body_text` — 본문 텍스트 6000자
- `one_line_summary`, `full_description` — 한국어 요약
- `image_by_image[]` — 이미지별 묘사
- `content_category`, `content_format`, `topics[]`, `brands_products[]`, `people[]`
- `scene_setting`, `text_in_media[]`, `mood_tone`
- `is_sponsored`, `sponsorship_note` — 광고 판단(정보로만 사용, 필터 안 함)
- `marketing_insight`, `target_audience`

## 주의
- 캐릿은 **유료 미디어**. 수집물은 내부 분석용으로만 쓰고 외부 재배포 금지, 본문 10% 초과 인용 불가.
- 광고 제외 조건은 제거됨 — 광고로 분류된 글도 대시보드에 그대로 표시 (분류 결과는 `is_sponsored` 필드에 정보로 남음).
- `profile/`·`src/data/`·`.env` 및 `docs/dashboard.html`·`docs/review/digest_*.md`는 `.gitignore` 적용됨 (캐릿 발췌 포함).
