# 📋 trend-monitoring-agent 프로젝트 TODO

> **운영 규칙**
> - 상태: ☐ 미완료 / 🔄 진행중 / ⏸ 블로커 / ☑ 완료 / ❌ 취소
> - "할 일 추가해줘 — [내용]" → '할 일'에 ☐ 추가 / "[항목] 완료" → ☑ + 완료 섹션
> - 레이첼이 todos.py 로 프로젝트별 취합 (슬랙에서 "프로젝트별 할일")

---

## 🔴 현재 진행 중 · 블로커

- ⏸ 블로커 — S29 멀티 토픽 글 분리 로직 방안 결정 (캐릿 '이주의 유행템' 같은 다중 토픽)
- ⏸ 블로커 — S27 HeyPop POP-UP 4건 한계 (사이트 정적 HTML) — 운영팀 문의
- ⏸ 블로커 — S28 The Edit 카테고리 확장 — 마케팅팀 확인

---

## 📋 할 일

_(없음)_

---

## 🗂 완료 / 보관

- ☑ Google Sheets 공유 시트 연동 (2026-06-16) — `sheets_push.py`(시트가 주인=append-only). GCP 프로젝트 `trend-sheets-499601`, 서비스계정 `trend-sheets-writer@...`, 키=루트 `gcp_sa.json`, Sheets+Drive API 활성. 시트 ID `1w7qX0tpfOI8FbNUDs740tQ7uobGIhuol46WflZc8ENk`(.env SHEETS_TREND_ID). run_daily 7단계 Notion→Sheets 교체. 128건 push + 중복방지 검증 완료. ⚠️ 서비스계정은 Drive 저장공간 0이라 시트 "생성" 불가 → 사람이 만들어 SA에 편집자 공유하는 구조.
- ☑ 데이빗 push 세팅 완료 (2026-06-16) — 편집자 공유(davidjo0326@gmail.com) + 파일 3개(`데이빗_sheets_push.py`·`gcp_sa.json`·`데이빗_Sheets가이드.md`) DM 전달 + 데이빗 PC 자동화(스케줄러) 설정 + 실수로 생긴 빈 스프레드시트 삭제까지 모두 완료. 레이첼·데이빗 양쪽 수집→시트 자동화 가동.
- ☑ 스케줄러 08:00 확인 (2026-06-16) — FF-Trend-Daily(08:00)/Report(08:30)/DB-Send(08:35) 모두 08:00대 정상 트리거·매일 성공 실행 확인. "로그인 시에만 실행(Interactive)" 유지(=PC 로그인 상태에서 동작) 선택. 별도 변경 불필요.
