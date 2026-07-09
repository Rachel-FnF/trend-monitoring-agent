# 📊 트렌드 통합 DB(구글시트) — 데이빗 합치기 가이드

레이첼·데이빗이 **같은 구글시트 하나**에서 트렌드를 같이 봅니다.
데이빗은 **자기 PC에서 분석한 데이터를 `trends.db`(SQLite)로 뽑아 → 시트에 올리면(push)** 끝.

- **시트**: 트렌드 통합 DB (rachel + david)
  https://docs.google.com/spreadsheets/d/1w7qX0tpfOI8FbNUDs740tQ7uobGIhuol46WflZc8ENk/edit
  → davidjo0326@gmail.com 으로 **편집자 초대 메일** 발송됨. 링크 클릭하면 바로 편집 가능.
- 예전처럼 `.db` 를 슬랙 DM으로 보내 레이첼이 merge 할 필요 **없음**. 내가 직접 시트에 올림 = 합쳐짐.
- **"시트가 주인"**: 한 번 올라간 글은 자동화가 다시 안 건드림 → 시트에서 분류·요약 고쳐쓰거나 **메모/활용아이디어/상태** 칸 채워도 그대로 보존.

---

## 🟦 처음 한 번만 세팅

### ① 라이브러리 설치 (명령창에서 1회)
```powershell
pip install google-auth requests
```

### ② 레이첼이 DM으로 보내주는 파일 2개를 한 폴더에 두기
- `데이빗_sheets_push.py` (push 스크립트)
- `gcp_sa.json` (구글 인증 키 — **외부 유출 금지**, 비공개/DM로만 받기)
- 내 `trends.db` 까지 **셋이 같은 폴더**에 있으면 제일 편함 (예: `C:\트렌드\`)

> 🔑 `gcp_sa.json` 은 이 시트에만 쓸 수 있는 제한된 키예요. 그래도 비밀번호처럼 — 공개 채널/외부 메일 금지.

---

## 🟩 매번: 내 트렌드를 시트에 올리기

### ① (기존처럼) 내 분석결과로 DB 뽑기
```powershell
python trenddb.py export --from "C:\내SNS분석폴더"
```
→ `trends.db` 생성 (내 `david` 이름표로 자동 부착)

### ② 시트에 올리기 (새 한 줄!)
```powershell
python 데이빗_sheets_push.py
```
→ `완료: 시트에 추가 OO / 이미있음(건너뜀) OO` 나오면 성공. 시트 새로고침하면 내 글이 맨 아래 쌓여 있어요.

> 💡 같은 글은 article_id 기준 자동 중복 제거. 여러 번 돌려도 안전 — 새 글만 추가됩니다.
> trends.db 가 다른 폴더면: `python 데이빗_sheets_push.py "C:\경로\trends.db"`

### (선택) 먼저 미리보기
```powershell
python 데이빗_sheets_push.py --dry
```
→ 실제로 안 올리고 "추가예정 OO건"만 보여줌.

---

## 📐 시트에 들어가는 칸 (참고)

`trends.db` 의 칸이 자동으로 아래 시트 컬럼에 매핑됩니다:

| 시트 열 | trends.db 칸 |
|---|---|
| 제목 / article_id / URL | title / article_id / url |
| 카테고리 / 한줄요약 | content_category / one_line_summary |
| 토픽 / 브랜드 | topics / brands_products |
| 마케팅인사이트 | marketing_insight |
| 발행일 / 최초포착일 / DB등록일 / 갱신일 | date / first_seen / db_added / updated_at |
| 수집자 | owners (david) |
| 광고 | is_sponsored (Y/공백) |
| **메모 / 활용아이디어 / 상태** | (없음 — **사람이 시트에서 직접 채우는 칸**, 자동화가 안 건드림) |

> ⚠️ **article_id 충돌 주의**: 중복 합치기 기준이 article_id 예요. 레이첼은 웹 글번호를 씁니다.
> 데이빗 SNS 데이터의 id가 숫자만이라 겹칠 수 있으면, trenddb export 시 **출처 접두어**(예 `ig_`, `x_`, `tt_`)를 붙여 겹치지 않게 하세요.

---

## ❓ 자주 나는 오류
| 메시지 | 해결 |
|---|---|
| `라이브러리가 없습니다` | `pip install google-auth requests` 다시 실행 |
| `서비스계정 키 없음: ...gcp_sa.json` | `gcp_sa.json` 을 스크립트와 같은 폴더에 두기 |
| `trends.db 를 찾을 수 없습니다` | `trends.db` 를 같은 폴더에 두거나, 명령 뒤에 db 경로 붙이기 |
| `403 / PERMISSION_DENIED` | 시트 편집자 초대(davidjo0326 메일) 수락했는지 확인 |

---

## 📌 정리 (치트시트)
```powershell
# 처음 1회
pip install google-auth requests
#  + 같은 폴더에: 데이빗_sheets_push.py, gcp_sa.json

# 매번
python trenddb.py export --from "C:\내SNS분석폴더"
python 데이빗_sheets_push.py
```

> 참고: 기존 슬랙 `.db` DM/merge 방식도 백업으로 살아 있어요. 하지만 이제 **시트 push가 메인** — 합치는 단계가 사라졌습니다.
