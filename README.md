# YouTube Data Collector

화장품 트렌드 PoC용 YouTube Data API v3 수집기입니다.

검색어별 영상 ID를 수집하고, 영상 메타데이터·조회수·좋아요·댓글 수와 댓글 본문을 저장합니다. API 응답 원본도 JSONL로 남기므로 이후 전처리 결과를 추적할 수 있습니다.

## 1. 수집 범위

- 키워드 검색 결과
- 영상 제목·설명·채널·게시일·태그·길이
- 조회수·좋아요·댓글 수
- 유료 프로모션 표시 여부(응답에 제공되는 경우)
- 최상위 댓글
- 선택적으로 댓글의 전체 답글
- 실행 조건·수집량·API 호출 횟수

작성자 이름은 저장하지 않습니다. 작성자 채널 ID가 제공되면 SHA-256 해시 일부만 저장합니다.

## 2. API 키 만들기

1. Google Cloud Console에서 프로젝트를 만듭니다.
2. `YouTube Data API v3`를 활성화합니다.
3. `APIs & Services → Credentials → Create credentials → API key`에서 키를 생성합니다.
4. 가능하면 API 제한을 `YouTube Data API v3`로 설정합니다.

공식 문서:

- https://developers.google.com/youtube/v3/getting-started
- https://developers.google.com/youtube/v3/docs/search/list
- https://developers.google.com/youtube/v3/docs/videos/list
- https://developers.google.com/youtube/v3/docs/commentThreads/list

## 3. 설치

PowerShell 기준입니다.

```powershell
cd youtube-data-collector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

외부 패키지는 필요하지 않으며 Python 3.10 이상만 설치되어 있으면 됩니다.

`.env`를 열어 발급받은 키를 넣습니다.

```env
YOUTUBE_API_KEY=발급받은_키
```

`.env`는 GitHub에 올리면 안 됩니다.

## 4. 먼저 소량 테스트

```powershell
python youtube_collector.py `
  --query "선크림 백탁" `
  --published-after 2026-07-01 `
  --published-before 2026-08-18 `
  --max-videos-per-query 5 `
  --max-comments-per-video 20
```

정상 작동을 확인한 뒤 범위를 늘립니다.

```powershell
python youtube_collector.py `
  --queries-file queries.example.txt `
  --published-after 2026-05-01 `
  --published-before 2026-08-18 `
  --max-videos-per-query 25 `
  --max-comments-per-video 100
```

답글까지 수집하려면 `--include-replies`를 추가합니다.

```powershell
python youtube_collector.py `
  --queries-file queries.example.txt `
  --max-videos-per-query 10 `
  --max-comments-per-video 100 `
  --include-replies
```

## 5. 결과 구조

```text
data/youtube/run_YYYYMMDDTHHMMSSZ/
├── manifest.json
├── errors.jsonl                 # 오류가 발생한 경우 생성
├── raw/
│   ├── search_responses.jsonl
│   ├── video_responses.jsonl
│   └── comment_responses.jsonl
└── processed/
    ├── videos.csv
    └── comments.csv
```

CSV는 Excel에서 한글이 깨지지 않도록 UTF-8 BOM 형식으로 저장됩니다.

## 6. 주요 옵션

| 옵션 | 의미 | 기본값 |
|---|---|---:|
| `--query` | 검색어, 여러 번 사용 가능 | 없음 |
| `--queries-file` | 한 줄에 검색어 하나인 파일 | 없음 |
| `--published-after` | 시작일 또는 RFC3339 시각 | 없음 |
| `--published-before` | 종료일 또는 RFC3339 시각 | 없음 |
| `--max-videos-per-query` | 검색어별 영상 수 | 25 |
| `--max-comments-per-video` | 영상별 댓글·답글 합계 상한 | 100 |
| `--include-replies` | 답글까지 별도 API로 수집 | 사용 안 함 |
| `--order` | `date`, `relevance`, `viewCount` 등 | `date` |
| `--region-code` | 시청 가능 지역 | `KR` |
| `--language` | 검색 관련성 언어 | `ko` |
| `--output-dir` | 결과 저장 상위 경로 | `data/youtube` |

`--published-before 2026-08-18`처럼 날짜만 입력하면 UTC 기준 해당 날짜 23:59:59로 처리됩니다.

## 7. 프로젝트에서 사용할 때 주의점

- 검색 결과는 YouTube 전체 게시물의 완전한 모집단이 아닙니다.
- `regionCode=KR`은 한국에서 시청 가능한 결과를 제한하는 값이지, 한국인이 제작한 영상만 보장하는 조건이 아닙니다.
- `relevanceLanguage=ko`를 사용해도 다른 언어 영상이 반환될 수 있습니다.
- 검색어별 결과가 중복될 수 있으므로 영상 ID 기준으로 통합합니다.
- 조회수·좋아요 수는 수집 시점의 스냅샷이므로 `collected_at`과 함께 사용해야 합니다.
- 댓글이 비활성화된 영상은 `errors.jsonl`에 이유를 기록하고 건너뜁니다.
- 트렌드 수치 산출 시 검색어와 수집 조건을 실행마다 고정해야 비교가 가능합니다.

## 8. 테스트

API 키 없이 유틸리티 함수 테스트를 실행할 수 있습니다.

```powershell
python -m unittest discover -s tests -v
```
