# 작업 규칙과 정본 — 이 파일이 기억의 정본이다

> 메모리 도구에 의존하지 않는다. **중요한 것은 전부 이 파일에 적는다.**
> 세션이 바뀌면 여기부터 읽는다.

---

## 1. 지켜야 할 규칙

| 규칙 | 내용 |
|---|---|
| 말투 | 사용자에게는 **한국어 존댓말**. 예외 없다 |
| 기억 | **md 파일이 정본이다.** 메모리 도구에 의존하지 않는다 |
| 단위 작업 종료 시 | **어태커 프롬프트를 낸다** — `ATTACK.md` 참조. 새 세션이 그 작업을 공격할 수 있게 |
| 만들기 전에 | 제안성 발언에 **바로 파일을 만들지 않는다.** 먼저 상의한다 |
| "추후에" 항목 | `C:\Users\Admin\Downloads\LATER.txt` 에 추가 (리포 밖에서 별도 관리) |
| 커밋 | 코드 완료 시 알아서 커밋·푸시한다 |

## 2. 환경

```
python      C:/Users/Admin/miniconda3/python.exe    (PATH 의 python 은 스토어 스텁)
DB          http://100.106.220.24:3000              PostgREST, 스키마 trend_radar / tubedepth
            노출 안 된 스키마: academic (논문) ← 현준님께 노출 요청 중
DGX 앱      http://100.96.113.69:8800               현준님. 여기서는 ping 이 안 간다
설치된 것    kiwipiepy 0.23.2 · numpy 2.5.1
없는 것      torch · transformers · sentence-transformers  (인코딩은 GPU 머신에서)
```

## 3. 정본 (이게 아니면 숫자가 어긋난다)

| 무엇 | 정본 |
|---|---|
| 수집 run | `data/panel/run_20260819T053057Z` + `run_20260819T054559Z` **둘만.** `data/youtube/` 를 넣으면 댓글이 60,311 → 60,435 가 되고 커밋 산출물과 어긋난다 |
| 성분 원본 | `data/external/product_ingredient_function_repaired.csv` (31,246행 / 577제품). 수호님 복구본. 이전 판 30,097행을 대체 |
| 성분·식약처 청크 | **수호님 생성기.** `reports/chunks_ingredient_mfds.csv` (`repair_chunks.py` 로 계약 수리). 내 `ingredient_chunks.py` 는 물러났다 |
| 유튜브 청크 | `reports/chunks_youtube.csv` 278,916 |
| 커머스 리뷰 청크 | `reports/chunks_commerce.csv` 18,476 |
| 성분 사전 | `seeds/ingredient_dictionary.tsv` 1,877행 |
| 청크 길이 상한 | **500자** (팀 합의 08.24). e5 512토큰 대비 여유 |

### 재현 시 반드시 같아야 하는 값

```
선크림 장문 964편 · 댓글 60,348건 · 중복 제외 60,311건
지표·판정 338행 (13주제 × 13분기 × 2소스) · 판정된 셀 64
τ = 0.35 · DIFFUSION_TAU = 0.089 · MIN_DOCUMENT_COUNT = 5
```

`python reproduce.py data/panel/run_A data/panel/run_B` 가 이걸 검사한다.

## 4. 세 번 밟은 함정 — **파이프라인이 조용히 답을 만든다**

| 언제 | 무엇이 관측값이 됐나 | 어떻게 알았나 |
|---|---|---|
| 수집 초기 | 채널당 **수집 상한 10** | 월별 집계가 매달 10건 근처 |
| 08.23 | **추출 방법** (정렬 없는 offset 페이징) | 현준님이 재현 안 된다고 알려줌 |
| 08.24 | **소스 비율** (색인 92%가 짧은 댓글) | 소스별로 나눠 물어보니 드러남 |

셋 다 **오류가 안 나고 결과가 그럴듯했다.** 그래서 자기 검사를 코드에 박는다.

```
행수 대조     서버 count=exact 와 안 맞으면 중단          commerce_ranking.fetch
재현성 검사    커밋된 338행이 지금 코드로 재생성되는지        reproduce.py
계약 검증기    청크 위반 11종                            chunks.py --validate
기저율 병기    적중률만 내는 검증은 검증이 아니라 홍보         backtest.py
캐시 키       사전·설정·파일 해시를 다 넣는다               bm25.build
--demo       거의 모든 스크립트                          데이터 없이 로직 점검
```

**캐시 키에 설정을 빠뜨려 옛 색인을 쓴 실수를 두 번 했다** (USER_WORD_SCORE, 사전 해시).
새 설정을 넣으면 캐시 키도 같이 넣는다.

## 5. 결론에 쓰는 숫자

| 발견 | 값 |
|---|---|
| 광고·협찬 | 964편 중 **465편(48.2%)**. 신고 필드만 보면 254편 — 절반 놓침 |
| 광고 빼면 | 판정 64셀 중 **19셀 뒤집힘** → 빼지 않고 필터 민감으로 표시 |
| 후향 검증 | 기준 A 27% · B 64% · **기저율 47%**. 상승 계열 9건은 A 22% |
| 혼합자차 | 제품 32.9% vs 댓글 1.21% (**27.1배**) — 표현 공백 |
| 백탁 | 영상 0.31% · 댓글 2.56% · **커머스 리뷰 12.09%** |
| 나이아신아마이드 | 375제품(69.4%) · 배합순위 중앙 **9위** |
| 아데노신 | 374제품(69.3%) · 배합순위 중앙 **33위** · 고함량 0% |
| 사전 밖 성분 | **11종** (성분표엔 있고 우리 사전엔 없음). 자동 추가 안 함 |
| 커머스 랭킹 6일 | 100위권 중앙 **38계단** · 신규 진입 111건 (실제 변동) |
| 검색 평가 | literal P@10 **0.862** · heldout **0.000** (구조적 바닥선) |
| 성분 사전 효과 | 성분명 한 토큰 비율 41% → **100%** (1,108종 살아남) |

**우리 지표는 서술 도구이고 예측 도구가 아니다.** 카드는 "뜰 것이다"가 아니라
"지금 이런 비대칭이 있다"로 쓴다.

## 6. 역할과 미결

| 사람 | 담당 |
|---|---|
| 김시현(나) | 유튜브·시계열, 판정·검증·근거 추적 |
| 석현 | 커머스 수집기·DB 파이프라인 + LLM |
| 현준 | NAVER·논문, DGX LLM 앱 (고정 쿼리 8개) |
| 수호 | 성분·식약처 매핑, 성분 청크 생성기 |

팀명 COSMAI · 4인 (08.20 이용찬 이탈) · 발표 08.26

### 미결

- **`academic` 스키마 노출** ← 논문을 우리 쪽에 붙이는 유일한 경로. 가장 급함
- LLM 앱이 둘 — 같은 질문에 다른 숫자가 나오면 발표에서 문제. 현준님 앱이 보던
  행 수가 서버의 절반이었다(80,102 vs 173,007)
- daisomall 카테고리 세분화 / `rank_delta` 계산 방식 (석현님)
- 수호님 생성기에서 `doc_id` 분리 + 길이 상한 500
- 벡터 임베딩 — 청크·평가기·인코더 준비 완료. `heldout` 0 을 넘으면 채택

## 7. 주요 명령

```bash
# 지표 → 판정
python trend.py data/panel/run_20260819T053057Z data/panel/run_20260819T054559Z --out reports/trend_sunscreen_v0.2.csv
python judge.py reports/trend_sunscreen_v0.2.csv --out reports/trend_judgement_v0.2.csv

# 검증
python reproduce.py    data/panel/run_20260819T053057Z data/panel/run_20260819T054559Z
python spam_ad_flags.py data/panel/run_20260819T053057Z data/panel/run_20260819T054559Z
python backtest.py     data/panel/run_20260819T053057Z data/panel/run_20260819T054559Z
python -m unittest discover -s tests

# 청크 → 검색
python chunks.py                      # 유튜브
python commerce_chunks.py             # 커머스 리뷰
python repair_chunks.py 받은파일.csv    # 남의 청크 계약 수리
python chunks.py --validate 파일.csv
python bm25.py --query "판테놀 쓰는 선크림" --per-source --top 2
python retrieval_eval.py --engine bm25 --mode heldout

# 임베딩 (GPU 머신)
pip install sentence-transformers
python encode_chunks.py --chunks reports/chunks_youtube.csv --chunks reports/chunks_commerce.csv
python retrieval_eval.py --engine hybrid --mode heldout

# 화면·카드
python dashboard.py
python cards.py
```

첫 BM25 색인은 4~5분(형태소 분석), 이후 캐시에서 4초.

## 8. 문서

| 무엇 | 어디 |
|---|---|
| 전체 흐름 (수집→검색) | `reports/전체_흐름.md` |
| 팀 공유 현황 | `reports/유튜브파트_현황_공유.md` |
| 임베딩·검색 계획 | `reports/임베딩_검색_계획.md` |
| 커머스 정정 | `reports/커머스_랭킹_데이터_이슈.md` |
| 유튜브 기준 | `reports/유튜브_기준_요약.md` |
| 팀 합의 | `reports/TEAM_DECISIONS_v0.2.md` |
| 어태커 프롬프트 | `ATTACK.md` |
