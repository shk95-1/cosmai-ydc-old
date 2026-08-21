# YouTube 공통 스키마 인계 — 백엔드·RAG 통합(⑤) 용

작성 2026-08-20 · 유튜브 채널·시계열 담당(②) 김시현
생성 스크립트 `to_common_schema.py` · 원본 `run_20260819T053057Z`, `run_20260819T054559Z`
이 문서는 `common/youtube_common_v1.zip` 과 같이 움직입니다.

---

## 0. 한 줄 요약

유튜브 영상 13,979편과 댓글 247,338건을 **문서 1건 = 1행**으로 바꿔 놓은 것입니다.
다른 소스도 **같은 3개 표 형태로 맞추면 그게 통합**이고, 지표 계산식을 한 번만 쓰면
전 소스에 돌아갑니다.

## 1. 파일 3개

| 파일 | 행 수 | 한 행이 뜻하는 것 |
|---|---|---|
| `document.csv` | 261,317 | 문서 1건. 영상과 댓글이 같은 표에 |
| `mention.csv` | 105,358 | (문서, 주제) 1건 |
| `channel.csv` | 43 | 채널 1개. `panel_role` 이 여기 |
| `manifest.json` | — | 규칙·건수·재현 방법 (기계 판독용) |

**왜 한 표가 아닌가.** 하나는 한 문서가 여러 주제에 걸리기 때문입니다. 영상 하나에
백탁·촉촉함·무기자차가 같이 나오는데, 문서 행에 넣으면 한 칸에 쉼표로 이어 붙여야 하고
셀 때마다 문자열을 쪼개야 합니다. 또 하나는 `panel_role` 이 채널 속성이라, 문서마다
넣으면 26만 번 중복되고 역할 하나 바꾸려면 26만 행을 고쳐야 합니다.

## 2. `document.csv` 컬럼

| 컬럼 | 값 | 비고 |
|---|---|---|
| `doc_id` | `youtube_video:ID` / `youtube_comment:ID` | 기본키 |
| `source` | `youtube_video` / `youtube_comment` | |
| `source_item_id` | video_id / comment_id | `source`+`source_item_id` 가 유일키 |
| `content_type` | `video_long` / `video_short` / `video_unknown` / `comment` | 60초 기준. unknown 은 라이브 등 6편 |
| `parent_item_id` | 댓글이면 부모 video_id | **분기 계산에 필수** |
| `channel_id` | 영상의 채널. 댓글도 부모 채널로 채움 | `channel.csv` 조인 키 |
| `published_at` | ISO8601 UTC | 댓글은 자기 시각이라 분기에 쓰면 안 됨 |
| `url` | 근거 링크 | |
| `text` | 영상 = 제목+설명, 댓글 = 본문 | 정규화 완료(§5) |
| `quality_flags` | 빈칸 / `empty_text` / `duplicate_in_parent` | 집계 제외 판단용 |
| `source_metadata` | JSON | `tags`·`duration_seconds`·`view_count`·`like_count`·`has_paid_product_placement`·`is_reply` 등 |

가변 API 필드를 컬럼으로 올리지 않고 JSON 에 둔 이유는 컬럼 하나 때문에 스키마를
바꾸지 않으려는 것입니다. 100건 넣어보고 불편한 필드가 있으면 그때 올립니다.

## 3. `mention.csv` 컬럼

`doc_id` · `topic_id` · `topic_type` · `trend_use` · `matched_term` · `span_start`

`trend_use=false` 인 2개는 `선크림`(93% 등장)과 `추천_재구매`(76%)입니다. 판별력이 없어
판정에서 뺐고, **`선크림` 은 모집단 필터로 씁니다**(§6). `matched_term`·`span_start` 는
근거 카드에서 걸린 표현을 하이라이트할 때 씁니다. 같은 주제가 여러 번 나오면 **첫 등장만**
기록했습니다.

## 4. 반드시 지켜야 할 규칙 3개

### (1) 분기는 저장하지 않았습니다

`published_at` 의 연·월로 계산합니다(수집 13,979편 전부 `analysis_month` 와 일치 확인).

**댓글은 자기 `published_at` 을 쓰면 안 됩니다.** 3년 전 영상에 어제 댓글이 달립니다.
댓글 시각으로 나누면 "그 분기에 큰 영상 하나가 올라온 것"이 "그 주제 급증"으로 보입니다.
`parent_item_id` 로 부모 영상에 조인해 **부모의 분기**를 씁니다.

```sql
SELECT c.doc_id, v.published_at AS quarter_basis
FROM document c
JOIN document v ON v.source_item_id = c.parent_item_id AND v.source = 'youtube_video'
WHERE c.source = 'youtube_comment';
```

### (2) 판정 분모는 `video_long` + `panel_role='product'` 만

쇼츠는 설명 길이 중앙값 0자·주제 매칭률 24.3%(장문 991자·64.4%)이고, 분기별 쇼츠 비중이
55%→41% 로 움직여서 한 분모에 넣으면 **포맷 선택 변화만으로 모든 주제 값이 흔들립니다.**
`video_unknown` 은 양쪽에서 제외합니다.

`expert` 9채널을 뺀 것은 결론에 영향이 없습니다 — 넣고 빼서 재보니 판정 22셀 중 뒤집힘
0개, 최대 차이 0.58%p 였습니다(`reports/panel_sensitivity.csv`).

### (3) 언급량은 `quality_flags` 가 빈 문서만

`duplicate_in_parent` 는 같은 영상 안에서 정규화 후 동일한 댓글입니다. 행을 지우지 않은
이유는 기획안 §4 가 삭제 대신 플래그 보존과 포함·제외 비교를 요구하기 때문입니다.
영상 간 중복은 표시하지 않습니다 — 다른 영상의 같은 말은 각각 실제 반응입니다.

## 5. 텍스트 정규화

```
HTML 엔티티 해제 → 유니코드 NFKC → 제어문자 제거 → 연속 공백 1칸
```

`trend.py` 의 `normalize_text` 하나만 씁니다. **소스마다 정규화가 다르면 소스 간 비교가
무의미해지므로** 다른 소스도 이 함수를 import 하시는 게 좋습니다.

## 6. 제대로 넣었는지 확인하는 값

| 확인 | 기대값 |
|---|---|
| `panel_role='product'` 34채널의 `video_long` 중 `선크림` 주제가 걸린 문서 | **964** |
| 그 영상들을 `parent_item_id` 로 갖는 댓글 전체 | **60,348** |
| 그중 `quality_flags` 가 빈 것 | **60,311** |

```sql
SELECT COUNT(DISTINCT d.doc_id)
FROM document d
JOIN channel c ON c.channel_id = d.channel_id
JOIN mention m ON m.doc_id = d.doc_id
WHERE d.content_type='video_long' AND c.panel_role='product' AND m.topic_id='선크림';
```

`content_type` 분포도 맞춰보세요 — `video_long` 7,085 / `video_short` 6,888 /
`video_unknown` 6 / `comment` 247,338.

## 7. 아직 정해지지 않은 것 2개

**태그를 판정 텍스트에 넣을지.** 기획안 문장은 "제목+설명+태그"인데 계산은 제목+설명만
씁니다. 태그를 넣으면 모집단이 **964 → 1,019편**이 되고 모든 구성비가 움직입니다.
태그는 `source_metadata.tags` 에 보존돼 있어 **재수집 없이** 바꿀 수 있습니다.

**기획안의 962편은 옛 값입니다.** 지금 스크립트를 돌리면 964편입니다. 보고서에는 964.

## 8. 같이 보면 좋은 것

| 무엇 | 어디 |
|---|---|
| 유튜브 기준·트렌드 정의 요약 | `reports/유튜브_기준_요약.md` |
| 지표 정의 전문 | `reports/TEAM_DECISIONS_v0.2.md` |
| 주제 사전 | `topics.py` — `match_topics()` 를 **공통으로** import |
| 지표 시계열 / 판정 | `reports/trend_sunscreen_v0.2.csv` / `trend_judgement_v0.2.csv` |

사전 수정은 `topics.py` 에서만 합니다. 소스마다 다른 사전을 쓰면 구성비를 비교할 수 없습니다.

## 9. 막히면

`manifest.json` 에 규칙·건수·재현 방법이 기계 판독 형태로 다 있습니다. §6 의 세 숫자가
안 맞으면 적재 과정 문제이니 바로 알려주세요.
