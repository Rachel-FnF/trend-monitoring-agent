"""Score the day's collected careet trends against the F&F rubric and write a Tier digest.
Reads data/collected_<today>.json, calls Claude (Anthropic API), writes data/digest_<today>.md.
"""
import sys, json, datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DATA = ROOT / "src" / "data"
TODAY = datetime.date.today().isoformat()
COLLECTED = DATA / f"collected_{TODAY}.json"
OUT = ROOT / "docs" / "review" / f"digest_{TODAY}.md"
MODEL = "claude-sonnet-4-6"

if not COLLECTED.exists():
    print("NO_COLLECTED:", COLLECTED); sys.exit(2)
data = json.loads(COLLECTED.read_text(encoding="utf-8"))

lines = ["## 마이크로 트렌드 전광판 (최조기 신호)"]
for m in data.get("micro_trends", []):
    lines.append(f"- {m.get('datetime','')} | {m.get('name','')} | 출처:{','.join(m.get('sources', []))}")
lines.append("\n## 구글 트렌드 (한국 급상승 검색어 — 분야 필터 없는 raw 순위표. 패션·뷰티와 무관한 키워드 다수 포함됨)")
for g in data.get("google_trends", []):
    nz = " / ".join(g.get("news", []))
    lines.append(f"- {g.get('term','')} ({g.get('traffic','')})" + (f" · 뉴스: {nz}" if nz else ""))
lines.append("\n## 네이버 쇼핑 인기검색어 (대중·전연령 실구매 수요)")
for c in data.get("naver_shopping", []):
    if c.get("keywords"):
        lines.append(f"- [{c.get('category','')}] {', '.join(c['keywords'])}")
lines.append("\n## 고구마팜 트렌드 (MZ 큐레이션 — 캐릿과 결 같음, 교차검증 가점)")
for g in data.get("gogumafarm", []):
    cats = ",".join(g.get("categories", [])[:3])
    lines.append(f"- {g.get('date','')} | {g.get('title','')} (cat:{cats})")
    if g.get("excerpt"):
        lines.append(f"    └ {g['excerpt'][:500]}")
lines.append("\n## 마케팅레시피 (Z세대 마케팅 인사이트·사례 — 실행 아이디어 단서)")
for m in data.get("marketingrecipe", []):
    lines.append(f"- {m.get('date','')} [{m.get('category','')}] {m.get('title','')}")
    if m.get("subtitle"):
        lines.append(f"    └ {m['subtitle']}")
lines.append("\n## 20대연구소 칼럼 (검증된 세대 분석 — 참고 레퍼런스·트렌드 검증용)")
for s in data.get("slab20", []):
    lines.append(f"- {s.get('date','')} [{s.get('type','')}] {s.get('title','')}")
lines.append("\n## 뉴닉 '고슴이의 비트' (MZ 라이프스타일 큐레이션, is_ad=True는 광고)")
for k in data.get("gosumi", []):
    ad = "(광고)" if k.get("is_ad") else ""
    lines.append(f"- {k.get('date','')} {ad} {k.get('title','')}")
lines.append("\n## The Edit · 디에디트 (라이프스타일 큐레이션 — STYLE/EAT/TECH/LIFE/CULTURE)")
for t in data.get("the_edit", []):
    cat = f"[{t.get('category','')}]" if t.get('category') else ""
    lines.append(f"- {t.get('date','')} {cat} {t.get('title','')}")
    if t.get("excerpt"):
        lines.append(f"    └ {t['excerpt']}")
lines.append("\n## HeyPop · 헤이팝 (팝업·공간·디자인·전시 트렌드)")
for h in data.get("heypop", []):
    cats = ",".join(h.get("categories", [])[:3])
    lines.append(f"- [{cats}] {h.get('title','')}")
    if h.get("excerpt"):
        lines.append(f"    └ {h['excerpt']}")
lines.append("\n## Insight · 인사이트 트렌드 뉴스 (패션·뷰티·셀럽·이슈, 일반 뉴스 매체)")
for s in data.get("insight", []):
    lines.append(f"- {s.get('date','')} {s.get('title','')}")
    if s.get("excerpt"):
        lines.append(f"    └ {s['excerpt']}")
lines.append("\n## 콘텐츠 글")
for a in data.get("articles", []):
    kw = ",".join(a.get("keywords", []))
    label = f"[{a['label']}]" if a.get("label") else ""
    lines.append(f"- [{a.get('id')}] {a.get('date','')} {label} {a.get('title','')} (키워드:{kw})")
    if a.get("body_excerpt"):
        lines.append(f"    └ 본문: {a['body_excerpt'][:1400]}")
catalog = "\n".join(lines)

PROMPT = f"""너는 F&F(한국 패션·뷰티 기업)의 트렌드 애널리스트다. 아래 캐릿 수집 데이터로 '오늘의 F&F 트렌드 다이제스트'를 작성하라.

[F&F] 브랜드: MLB·MLB Kids·Discovery Expedition·Duvetica·Sergio Tacchini(패션/스포츠), F&CO·헤트라스(뷰티/향기). MLB는 중국 사업이 핵심. 타깃 10~50대.

[작성 원칙 — 매우 중요]
1. 점수·숫자 매기기 금지. 대신 **실제 기사 내용을 충실히 요약**하고, **왜 지금 떠오르는지**를 기사 근거로 설명하는 데 집중하라.
2. 각 트렌드는 아래 카드 형식으로. 표(table)는 절대 쓰지 마라.
3. '무엇'·'왜 뜨나'는 본문(└)이 있으면 그걸 근거로 구체적으로(등장 브랜드·제품·수치·사례 포함).
3-1. 본문이 없는 항목(특히 전광판 미세트렌드)은 **web_search 도구로 그 트렌드 이름을 검색**해 무엇인지·왜 뜨는지 실제 자료로 파악한 뒤 요약하라. '무엇' 끝에 `(출처: 도메인)`을 붙여라. 검색해도 불명확하면 "확인 필요"로 적고 추측하지 마라. (모든 항목을 검색할 필요는 없고, 본문 없는 트렌드 위주로.)
4. 순서는 F&F 연관도 + 시점(유행예감>유행중, 전광판 신착 우선)으로. 단 점수는 표기하지 마라.
5. 가독성 최우선: 짧은 문장, **굵은 키워드**, 불릿.

[출력 — 한국어 마크다운]
# 🎯 오늘의 F&F 트렌드 다이제스트 — {TODAY}
> **오늘 한눈에:** 오늘 가장 중요한 트렌드 2~3개를 한 문장으로 압축.

## 🔥 지금 주목 (이른 신호 · F&F 연관 높음)
*6~8개. 각 항목을 아래 카드로:*
### {{번호}}. {{트렌드명}}  ·  {{유행예감/유행중/유행지남 또는 전광판}}  ·  {{날짜·소스}}  [글id]
- **무엇** — 기사 내용 2~3문장 요약 (구체적으로)
- **왜 뜨나** — 부상 이유 1~2문장 (기사 근거)
- **F&F 포인트** — {{연관 브랜드}}: 한 줄 실행 아이디어

## ✅ 함께 볼 신호
*4~8개:* `- **{{트렌드명}}** ({{시점}}) [id] — 한두 문장 요약 + 왜 뜨는지 + F&F 한 줄`

## 📌 참고 레퍼런스
`- **{{제목}}** [id] — F&F 활용 포인트 한 줄`

## ⏸ 이번엔 패스
F&F 무관(디저트·음식·일반 밈 등)을 한 줄로 묶어서.

## 💡 이번 주 모니터링 포인트
2~3개 불릿.

[규칙] 캐릿은 유료 자료 → 원문 복붙 말고 본인 표현으로 요약. **광고·협찬·순수 홍보성(브랜드 보도자료/PR) 콘텐츠는 트렌드가 아니므로 다루지 말고 '이번엔 패스'로 묶어라**(단, 광고/마케팅 트렌드를 *분석·해설*한 에디토리얼은 유효한 트렌드 콘텐츠이니 포함). 구글 트렌드 항목은 **분야 필터 없이 들어온 raw 데이터**다 — 한국 사람들이 오늘 가장 많이 검색한 상위 키워드 전체이며, 패션·뷰티 카테고리로 좁혀진 게 아니다. → F&F 관련(패션·뷰티·셀럽·IP·중국·상품)만 골라 다루고, 주식 종목코드·정치·일반 사건사고·로또·게임·외국어 키워드는 '이번엔 패스'로 묶어라(뉴스 제목이 맥락 단서). 네이버 쇼핑 인기검색어는 대중·전연령 실구매 수요 신호다 → 급상승·신규·브랜드명·특이 아이템 위주로 해석하고(특히 40~50대·대중 시사점, 캐릿 신호와 교차검증 시 가점), 티셔츠·샴푸처럼 상시 일반 키워드는 굳이 다루지 마라.

[추가 소스 해석 규칙]
- **고구마팜**: 캐릿과 결이 같은 MZ 큐레이션 — 같은 트렌드가 캐릿과 동시에 잡히면 교차검증으로 신뢰도 ↑하고 카드에 `[캐릿+고구마팜]` 같은 태그 표기. 본문 excerpt가 풍부하므로 적극 활용.
- **마케팅레시피**: '무엇이 뜨는가'보다 '마케터가 어떻게 활용했는가'에 집중. 카드 안 '왜 뜨나'·'F&F 포인트'에서 실행 인사이트 단서로 활용. 새 트렌드 자체 발굴 소스로도 가능.
- **20대연구소**: 검증된 세대 분석·인사이트형 — 트렌드 카드보다는 '참고 레퍼런스'/'모니터링 포인트' 섹션을 보강하는 쪽. 인포그래픽/뉴스레터는 데이터 기반 시사점.
- **고슴이의 비트(뉴닉)**: `(광고)` 표기 있으면 무조건 '이번엔 패스'. 그 외는 MZ 라이프스타일 보조 신호. 제목만 있어 깊이 다루지 말고 '함께 볼 신호'에 짧게.
- **The Edit(디에디트)**: 라이프스타일·소비 큐레이션 — 카테고리(STYLE·EAT·TECH·LIFE·CULTURE)로 분야가 명확. STYLE/CULTURE은 F&F 패션 직결, EAT는 F&B 콜라보 단서, TECH/LIFE는 라이프스타일 시사. 제품 추천·리뷰 톤이라 '왜 뜨나'에 실용 단서 풍부.
- **HeyPop(헤이팝)**: 팝업·공간·전시·디자인 트렌드 전문 — F&F 매장·VMD·체험 전략에 직결. 카테고리 태그(Exhibition·Culture·Style·Gourmet 등) 그대로 활용. 카드에 `[헤이팝]` 명시해 공간·체험 시사로 활용.
- **Insight(인사이트)**: 일반 뉴스 매체의 트렌드 카테고리 — 큐레이션이 아닌 뉴스라 깊이가 얕고 가십·이슈 비중 높음. F&F 직접 관련(패션·뷰티·셀럽·중국·콜라보)만 골라 다루고, 일반 사건사고·정치·연예가십은 패스. 단 산업 동향(예: 코스맥스 K-뷰티, 노스페이스, 패션협회 AI 등)은 좋은 신호.

=== 수집 데이터 ===
{catalog}"""

client = anthropic.Anthropic()
msg = client.messages.create(model=MODEL, max_tokens=6000,
                             tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
                             messages=[{"role": "user", "content": PROMPT}])
digest = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
_i = digest.find("# 🎯")  # strip the model's pre-digest search narration
if _i > 0:
    digest = digest[_i:]
digest = digest.strip() + "\n"
OUT.write_text(digest, encoding="utf-8")
print("WROTE", OUT, f"({len(digest)} chars)")
