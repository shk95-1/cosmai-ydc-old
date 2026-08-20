# YouTube Data Collector

화장품(선크림) 트렌드 PoC용 YouTube Data API v3 수집·분석 도구입니다.

**시드 채널의 업로드를 전수 수집**하고, 사전 매칭으로 주제를 뽑아 분기 시계열을 만듭니다.
API 응답 원본을 JSONL로 남기므로 모든 숫자를 원문까지 되짚을 수 있습니다.

정의와 근거는 [`reports/TEAM_DECISIONS_v0.2.md`](reports/TEAM_DECISIONS_v0.2.md)가 정본입니다.

---

## 1. 파이프라인

```
seeds/channels_v1.csv            43채널 패널 (product 34 / expert 9)
  │
  ├─ collect_channel_uploads.py  채널 업로드 전수 + 주제 걸린 영상의 댓글
  │    → data/panel/run_*/raw/         API 응답 원본 JSONL
  │    → data/panel/run_*/processed/   videos.csv, comments.csv, channels.csv
  │    → data/panel/run_*/manifest.json  호출 수·쿼터·한계 기록
  │
  ├─ trend.py                    분기별 주제 간 구성비 + YoY velocity
  │    → reports/trend_sunscreen_v0.2.csv
  │      └─ report_trend.py      위 CSV를 자기완결 HTML로 렌더
  │           → reports/trend_report.html
  │
  └─ unmatched_terms.py          사전에 없는 고빈도 표현 후보
       → reports/dictionary_candidates_*.csv + .manifest.json
```

공용 입력 두 개:

| 파일 | 내용 |
|---|---|
| `topics.py` | 주제 사전 정본. 15개(트렌드 판정용 13개). `match_topics(text)`를 import해서 쓴다 |
| `lexicon.json` | 팀 공용 전처리 사전. 불용어·조사·별칭. 수정 시 `version`을 올린다 |

---

## 2. 왜 검색이 아니라 채널 전수인가

| | `search.list` | 채널 업로드 플레이리스트 |
|---|---|---|
| 재현율 | 손으로 고른 45편 중 **6/20 = 30%** | 전수 |
| 한도 | 쿼리당 약 500건에서 끊김 | 없음 |
| 비용 | 콜당 100유닛 | 50편당 1유닛 |
| 편향 | 오늘의 참여도 순위 = **생존편향** | 실패한 영상도 포함 |

생존편향이 결정적입니다. 검색으로 과거 분기를 조회하면 **그 뒤에 성공한 영상만** 잡히므로
"그 분기에 이 주제가 얼마나 언급됐나"를 측정할 수 없습니다.

전체 화장품 영상을 다 받는 이유는 **분모**입니다. 선크림 영상 편수만 세면 채널이 영상을
더 올려서 늘어난 것과 선크림을 더 다뤄서 늘어난 것을 구분할 수 없습니다.

---

## 3. 설치

외부 패키지가 필요 없습니다. Python 3.10 이상이면 됩니다.

```bash
python -m venv .venv
```

`.env`에 API 키를 넣습니다 (`.env.example` 참고).

```
YOUTUBE_API_KEY=...
```

### API 키 만들기

1. Google Cloud Console에서 프로젝트를 만듭니다.
2. `YouTube Data API v3`를 활성화합니다.
3. `APIs & Services → Credentials → Create credentials → API key`에서 키를 생성합니다.
4. 가능하면 API 제한을 `YouTube Data API v3`로 설정합니다.

무료입니다. 하루 10,000유닛이고, 초과하면 과금이 아니라 요청이 실패합니다.

---

## 4. 실행

### 수집

```bash
python collect_channel_uploads.py --channels-csv seeds/channels_v1.csv --seed-videos "" --published-after 2023-07-01T00:00:00Z --comments 100 --max-units 8000 --output-dir data/panel
```

`videos.csv`를 먼저 저장한 뒤 댓글 단계로 넘어갑니다. 댓글에서 쿼터가 터져도 영상은
남으므로 댓글만 다시 받으면 됩니다. 댓글은 **주제 사전에 걸린 영상만** 받습니다 —
`commentThreads`는 영상 1편당 1유닛이라 영상 목록 수집의 50배 비용입니다.

### 시계열

```bash
python trend.py data/panel/run_A data/panel/run_B --out reports/trend_sunscreen_v0.2.csv
```

run 디렉터리를 여러 개 주면 하나의 패널로 합칩니다.

### 리포트

```bash
python report_trend.py
```

### 사전 확장 후보

```bash
python unmatched_terms.py data/panel/run_A data/panel/run_B --out reports/dictionary_candidates.csv
```

### 자체 점검

```bash
python topics.py --demo && python trend.py --demo && python unmatched_terms.py --demo && python -m unittest discover -s tests
```

---

## 5. 지표 정의 요약

| 값 | 정의 |
|---|---|
| `composition` | 그 주제 mention ÷ **그 분기 전체 주제 mention** |
| `velocity_yoy` | `log(이번 분기 구성비) − log(전년 동분기 구성비)` |
| `persistence` | 최근 4분기 중 구성비 > 전체 기간 중앙값인 분기 비율 |
| `channel_diffusion` | 고유 채널 수 50% + 채널 분포 엔트로피 50% |
| `sample_ok` | `document_count >= 5`. false면 판정하지 않는다 |

네 가지가 v0.1과 다릅니다. 전부 실제 데이터가 드러낸 문제 때문입니다.

1. **문서 기준 share를 쓰지 않는다.** 유튜버 설명란 길이 중앙값이 3년간 1,253자 → 709자로
   줄어서, 분자만 줄고 분모는 그대로여서 13개 주제 중 10개가 동반 하락합니다(합계 −28.6%p).
2. **쇼츠를 분모에서 뺀다.** 쇼츠는 설명란 길이 중앙값이 0자, 매칭률 24%(장문 64%)입니다.
   쇼츠 비중이 분기마다 55%~41%로 움직여 포맷 변화가 트렌드로 위장됩니다.
3. **전년 동분기와 비교한다.** 선크림은 계절 상품입니다 — 선크림 언급 비중이 3년 연속
   Q2 최고(26.7/25.3/25.6%), Q1·Q4 최저입니다. 인접 분기를 비교하면 매년 여름에 급상승이 나옵니다.
4. **영상 설명과 댓글을 합치지 않는다.** `백탁`은 영상 설명에서 13분기 전부 표본 부족이지만
   댓글에서는 12분기가 충족됩니다. 영상은 스펙·포뮬러, 댓글은 사용감·불만을 담습니다.
   두 표에서 방향이 갈리는 주제가 제품 공백 후보입니다.

---

## 6. 개인정보

작성자 이름은 저장하지 않습니다. 작성자 채널 ID가 제공되면 SHA-256 해시 일부만 저장합니다.

---

## 7. 한계

- 모집단은 시드 채널 43개이며 전체 YouTube가 아닙니다(고정 패널). 패널 밖 신규 채널·브랜드는
  관측되지 않습니다
- 조회수·좋아요는 `collected_at` 시점 스냅샷입니다. 과거 값은 API로 복구할 수 없습니다
- 댓글은 계속 쌓이므로 최근 분기는 구조적으로 과소 집계됩니다
- 사전에 없는 성분·표현은 관측되지 않습니다. `unmatched_terms.py`가 후보를 내지만
  한국어 성분명은 복합어 안에 붙어(`센텔라아시아티카추출물`) 토큰화로는 잡히지 않습니다
- `has_paid_product_placement`는 유튜버 자체 신고 필드이므로 협찬 누락이 있습니다

---

## 8. 구 파이프라인

`youtube_collector.py`(검색 기반) → `normalize_youtube_exports.py` → `normalized/`는
초기 탐색용으로 남겨둔 것입니다. 시계열에는 쓰지 않습니다(위 2절 참고).
보관 파일은 [`_archive/README.md`](_archive/README.md)에 정리했습니다.

## 공식 문서

- https://developers.google.com/youtube/v3/getting-started
- https://developers.google.com/youtube/v3/docs/channels/list
- https://developers.google.com/youtube/v3/docs/playlistItems/list
- https://developers.google.com/youtube/v3/docs/videos/list
- https://developers.google.com/youtube/v3/docs/commentThreads/list
