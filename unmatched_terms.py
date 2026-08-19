#!/usr/bin/env python3
"""사전에 없는 고빈도 표현을 코퍼스에서 뽑는다. 사전 확장 후보 목록을 만드는 도구.

왜 필요한가:
`topics.py` 사전에 없는 성분·표현은 영원히 관측되지 않는다. "신규 등장" 판정이
잡을 수 있는 것은 사전에 이미 있는 주제 중 새로 뜬 것뿐이다. R&D 기회 탐색에서
이것은 실질적 제약이다.

왜 외부 성분 목록을 쓰지 않는가:
식약처 INCI 명단 같은 외부 목록을 넣으면 코퍼스에 없는 단어가 섞인다. 실측으로
확인했다 — 자외선차단 성분 11종을 넣어봤더니 아보벤존 1건, 옥토크릴렌 2건,
옥티녹세이트·호모살레이트·유비놀·유솔렉스 0건이었다. 유튜버와 소비자는
"무기자차/유기자차"라는 범주어로만 말하고 개별 필터 이름은 쓰지 않는다.
`topics.py`가 이미 같은 이유로 추측 별칭 18개를 제거한 기록이 있다.

그래서 방향을 뒤집는다: **코퍼스가 실제로 말하는 것**을 세고, 그중 사전에
없는 것을 사람에게 보여준다. 사전 등재는 사람이 결정하고 `topics.py`에서만 한다.

불용어와 조사는 lexicon.json을 쓴다. 팀 전원이 쓰는 단일 사전이므로 여기서
따로 만들지 않는다.

이 도구가 뽑을 수 있는 것과 못 하는 것 (실측 2026-08-19, 선크림 영상 962편/댓글 60,348건):

- **뽑힌다: 제품·브랜드명.** 상위 120개 중 약 45개가 브랜드·제품 라인이었다
  (딘시·어반쉐이드·구디너프·셀라보·아넷사·조선미녀·아쿠아티카·realbarrier 등).
  공백으로 분리된 고유명사라 토큰이 된다.
- **뽑히지 않는다: 성분명.** 같은 조건에서 성분 후보는 3개뿐이었다. 이유 두 가지다.
  (1) 한국어 성분명은 복합어 안에 붙는다(`센텔라아시아티카추출물`·`병풀추출물`).
      공백 기준 토큰화로는 `센텔라`가 분리되지 않는다.
  (2) 성분은 선크림뿐 아니라 화장품 전반에 나오므로 keyness가 1에 가까워 탈락한다.
      `--min-keyness 1.0`으로 풀어도 (1) 때문에 여전히 안 잡힌다.

  성분은 `topics.py`처럼 **부분문자열 매칭 + 실측 후 0건 제거** 방식으로 넣어야 한다.
  부분문자열로 재보면 코퍼스에 실제로 있다 — 센텔라·병풀·시카 279편/547건,
  히알루론산 136/194, 어성초 122/179, 세라마이드 93/152, 티트리 86/147,
  비타민C 67/284, 판테놀 52/150, 나이아신아마이드 38/268.
  ponytail: 형태소 분석기를 붙이면 (1)이 풀리지만 새 의존성이 필요하다.
  부분문자열 매칭으로 충분히 잡히므로 지금은 붙이지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from topics import TOPICS, match_topics

csv.field_size_limit(10 ** 7)

SHORTS_MAX_SECONDS = 60
SUNSCREEN_TERMS = [k.lower() for k in next(t for t in TOPICS if t["topic"] == "선크림")["ko"]]

# 한글 2~10자 또는 영문 3~20자. 숫자 단독과 한 글자는 버린다.
TOKEN_RE = re.compile(r"[가-힣]{2,10}|[A-Za-z][A-Za-z0-9]{2,19}")
# URL·해시태그·타임스탬프는 토큰화 전에 지운다. 설명란의 절반 이상이 이것들이다.
NOISE_RE = re.compile(r"https?://\S+|[#@]\S+|\d{1,2}:\d{2}(?::\d{2})?|\b\d+원\b")
# 조사 절단 규칙은 lexicon.json이 정본이다. 여기 하드코딩하지 않는다.
# 절단이 없으면 `세라마이드가`·`세라마이드는`·`세라마이드를`이 각각 다른 단어로
# 세어져 어느 것도 상위에 오지 못하고, 목록이 활용형으로 뒤덮인다(실측 200개 중 45개).
# ponytail: 규칙 기반 절단이다. 형태소 분석기가 필요해지면 여기만 바꾸면 된다.
_PARTICLE_RE: re.Pattern[str] | None = None


def build_particle_re(particles: Sequence[str]) -> re.Pattern[str]:
    """긴 조사부터 매칭해야 `에게서`가 `에`로 잘리지 않는다."""
    alts = "|".join(re.escape(p) for p in sorted(particles, key=len, reverse=True))
    return re.compile(rf"(?:{alts})$")


def load_lexicon(path: Path) -> tuple[set[str], list[str], str]:
    """(불용어, 조사, 사전 버전). protected에 있는 표현은 불용어에서 뺀다.

    팀 전원이 쓰는 단일 사전이므로 불용어·조사를 이 파일에서만 관리한다.
    반환한 버전은 실행 기록(manifest)에 남겨 결과를 재현할 수 있게 한다.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    words = {w.lower() for group in data.get("stopwords", {}).values() for w in group}
    words -= {p.lower() for p in data.get("protected", [])}
    particles = list(data.get("particles", []))
    if not particles:
        raise SystemExit(f"{path}에 particles가 없습니다. lexicon 버전을 확인하세요.")
    return words, particles, str(data.get("version", "unknown"))


def dictionary_terms() -> set[str]:
    """사전이 이미 잡는 표현. 이미 등재된 것을 후보로 내놓지 않기 위해 쓴다."""
    terms: set[str] = set()
    for entry in TOPICS:
        for term in entry["ko"] + entry["latin"] + entry["mfds_inci"]:
            terms.add(term.lower())
    return terms


def read_csv(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def tokenize(text: str) -> list[str]:
    """토큰과, 조사를 뗀 어간을 함께 낸다.

    어간만 내지 않고 둘 다 내는 이유: 조사 절단이 규칙 기반이라 `증가` -> `증`
    같은 오절단이 가능하다. 원형도 세면 오절단된 쪽은 빈도가 낮아 밀려나고
    올바른 쪽이 살아남는다. 절단 결과가 2자 미만이면 절단하지 않는다.
    """
    pattern = _PARTICLE_RE
    out: list[str] = []
    for token in TOKEN_RE.findall(NOISE_RE.sub(" ", text).lower()):
        out.append(token)
        if pattern is None:
            continue
        stem = pattern.sub("", token)
        if stem != token and len(stem) >= 2:
            out.append(stem)
    return out


def load_panel(path: Path) -> dict[str, str]:
    return {r["channel_id"]: r.get("panel_role") or "unset" for r in read_csv(path)}


class Corpus:
    """선크림 코퍼스와 그 여집합(비선크림)을 함께 센다.

    문서 빈도를 센다(한 문서에서 같은 단어가 10번 나와도 1). 설명란에 같은
    문구를 반복하는 채널 하나가 순위를 지배하지 않게 하기 위한 것이다.
    """

    def __init__(self) -> None:
        self.video_in: Counter = Counter()
        self.video_out: Counter = Counter()
        self.comment_in: Counter = Counter()
        self.comment_out: Counter = Counter()
        self.n_video_in = self.n_video_out = 0
        self.n_comment_in = self.n_comment_out = 0


def collect(run_dirs: Iterable[Path], panel: dict[str, str]) -> Corpus:
    corpus = Corpus()
    in_scope: dict[str, bool] = {}

    for run_dir in run_dirs:
        for row in read_csv(run_dir / "processed" / "videos.csv"):
            if panel.get(row["channel_id"]) != "product":
                continue
            duration = row.get("duration_seconds")
            if not duration or int(duration) <= SHORTS_MAX_SECONDS:
                continue
            text = f"{row.get('title') or ''} {row.get('description') or ''}"
            sunscreen = any(term in text.lower() for term in SUNSCREEN_TERMS)
            in_scope[row["source_item_id"]] = sunscreen
            tokens = set(tokenize(text))
            if sunscreen:
                corpus.n_video_in += 1
                corpus.video_in.update(tokens)
            else:
                corpus.n_video_out += 1
                corpus.video_out.update(tokens)

    for run_dir in run_dirs:
        path = run_dir / "processed" / "comments.csv"
        if not path.exists():
            continue
        for row in read_csv(path):
            sunscreen = in_scope.get(row["video_id"])
            if sunscreen is None:
                continue
            tokens = set(tokenize(row.get("text") or ""))
            if sunscreen:
                corpus.n_comment_in += 1
                corpus.comment_in.update(tokens)
            else:
                corpus.n_comment_out += 1
                corpus.comment_out.update(tokens)

    return corpus


def keyness(hits_in: int, n_in: int, hits_out: int, n_out: int) -> float:
    """선크림 문서에서의 출현율 ÷ 비선크림 문서에서의 출현율.

    기능어(`감사합니다`·`같아요`)는 양쪽에 같은 비율로 나오므로 1에 가깝다.
    선크림 고유 표현은 1보다 크다. 불용어 목록을 손으로 쓰지 않아도 걸러지는
    이유가 이것이다. 라플라스 보정으로 0 나눗셈을 막는다.
    """
    if n_in == 0 or n_out == 0:
        return 0.0
    return ((hits_in + 1) / (n_in + 1)) / ((hits_out + 1) / (n_out + 1))


def candidates(
    corpus: Corpus,
    stopwords: set[str],
    known: set[str],
    min_documents: int,
    min_keyness: float,
) -> list[dict[str, object]]:
    """사전에 없고 선크림 문서에 편중된 표현을 keyness 순으로 낸다."""
    rows = []
    for token in set(corpus.video_in) | set(corpus.comment_in):
        if token in stopwords:
            continue
        # 사전 표현의 부분문자열이거나 사전 표현을 포함하면 이미 잡히는 것으로 본다.
        # 조사가 붙은 형태(`차단이`)도 어간(`차단`)으로 한 번 더 본다. 이게 없으면
        # 어간은 걸러지고 활용형만 살아남는 비대칭이 생긴다.
        stem = _PARTICLE_RE.sub("", token) if _PARTICLE_RE else token
        if any(term in token or token in term for term in known):
            continue
        if len(stem) >= 2 and any(term in stem or stem in term for term in known):
            continue
        video_hits = corpus.video_in.get(token, 0)
        comment_hits = corpus.comment_in.get(token, 0)
        if video_hits + comment_hits < min_documents:
            continue
        v_key = keyness(video_hits, corpus.n_video_in, corpus.video_out.get(token, 0), corpus.n_video_out)
        c_key = keyness(comment_hits, corpus.n_comment_in, corpus.comment_out.get(token, 0), corpus.n_comment_out)
        best = max(v_key, c_key)
        if best < min_keyness:
            continue
        rows.append(
            {
                "term": token,
                "video_documents": video_hits,
                "comment_documents": comment_hits,
                "video_keyness": round(v_key, 2),
                "comment_keyness": round(c_key, 2),
            }
        )
    rows.sort(key=lambda r: -max(float(r["video_keyness"]), float(r["comment_keyness"])))
    return rows


def demo() -> None:
    global _PARTICLE_RE
    _PARTICLE_RE = build_particle_re(["은", "는", "이", "가", "을", "를", "에게서", "에"])
    # 긴 조사가 먼저 매칭돼야 한다 — `에게서`가 `에`로 잘리면 어간이 깨진다
    assert _PARTICLE_RE.sub("", "친구에게서") == "친구"
    assert tokenize("백탁 촉촉!") == ["백탁", "촉촉"]
    assert tokenize("a") == []  # 한 글자는 버린다
    assert tokenize("SPF50") == ["spf50"]
    # URL·해시태그·타임스탬프는 토큰이 되지 않는다
    assert tokenize("보세요 https://link.coupang.com/abc 여기") == ["보세요", "여기"]
    assert tokenize("#선크림추천 좋아요") == ["좋아요"]
    assert tokenize("0:35 인트로") == ["인트로"]
    # 조사를 뗀 어간이 함께 나온다 — 이게 없으면 활용형이 목록을 뒤덮는다
    assert tokenize("세라마이드가") == ["세라마이드가", "세라마이드"]
    assert tokenize("판테놀은 좋다") == ["판테놀은", "판테놀", "좋다"]
    # 오절단 방어: 절단하면 1자가 되는 경우는 절단하지 않는다
    assert tokenize("증가") == ["증가"]
    assert tokenize("여기") == ["여기"]
    # keyness: 양쪽에 같은 비율로 나오는 기능어는 1에 가깝다
    assert abs(keyness(50, 100, 50, 100) - 1.0) < 0.05
    # 선크림 쪽에만 나오면 1보다 훨씬 크다
    assert keyness(50, 100, 0, 100) > 20
    assert keyness(0, 100, 50, 100) < 0.1
    assert keyness(1, 0, 1, 0) == 0.0  # 빈 코퍼스 방어

    def corpus_of(vin, vout, n_in=100, n_out=100):
        c = Corpus()
        c.video_in, c.video_out = Counter(vin), Counter(vout)
        c.n_video_in, c.n_video_out = n_in, n_out
        c.n_comment_in = c.n_comment_out = 1
        return c

    # 사전에 이미 있는 표현은 후보에서 빠진다
    out = candidates(corpus_of({"백탁": 50, "센텔라": 40}, {}), set(), {"백탁", "촉촉"}, 10, 2.0)
    assert [r["term"] for r in out] == ["센텔라"], out
    # 불용어도 빠진다
    out = candidates(corpus_of({"추천": 99, "센텔라": 40}, {}), {"추천"}, set(), 10, 2.0)
    assert [r["term"] for r in out] == ["센텔라"], out
    # min_documents 미만도 빠진다
    assert candidates(corpus_of({"희귀어": 3}, {}), set(), set(), 10, 2.0) == []
    # keyness가 낮으면(양쪽에 고르게 나오면) 빠진다
    assert candidates(corpus_of({"같아요": 50}, {"같아요": 50}), set(), set(), 10, 2.0) == []
    print("[demo] 통과")


def main() -> int:
    parser = argparse.ArgumentParser(description="사전 확장 후보 추출 (코퍼스 기반)")
    parser.add_argument("run_dir", type=Path, nargs="*", help="수집 run 디렉터리")
    parser.add_argument("--panel", type=Path, default=Path("seeds/channels_v1.csv"))
    parser.add_argument("--lexicon", type=Path, default=Path("lexicon.json"))
    parser.add_argument("--min-documents", type=int, default=20, help="문서 빈도 하한")
    parser.add_argument("--top", type=int, default=200, help="상위 몇 개까지 낼지")
    parser.add_argument("--min-keyness", type=float, default=2.0, help="선크림 편중도 하한. 1.0이면 필터 없음")
    parser.add_argument("--out", type=Path, help="CSV 저장 경로. 없으면 표준출력")
    parser.add_argument("--demo", action="store_true", help="자체 점검만 실행")
    args = parser.parse_args()

    if args.demo:
        demo()
        return 0
    if not args.run_dir:
        parser.error("run_dir을 하나 이상 지정하세요.")

    global _PARTICLE_RE
    stopwords, particles, lexicon_version = load_lexicon(args.lexicon)
    _PARTICLE_RE = build_particle_re(particles)
    known = dictionary_terms()
    corpus = collect(list(args.run_dir), load_panel(args.panel))
    rows = candidates(corpus, stopwords, known, args.min_documents, args.min_keyness)[: args.top]

    print(
        f"[scope] 선크림 영상 {corpus.n_video_in:,}편·댓글 {corpus.n_comment_in:,}건 "
        f"vs 비선크림 영상 {corpus.n_video_out:,}편·댓글 {corpus.n_comment_out:,}건",
        file=sys.stderr,
    )
    print(
        f"[filter] lexicon v{lexicon_version} · 불용어 {len(stopwords)}개 · 조사 {len(particles)}개 · "
        f"사전 표현 {len(known)}개 · 문서빈도 >= {args.min_documents} · keyness >= {args.min_keyness}",
        file=sys.stderr,
    )

    handle = args.out.open("w", encoding="utf-8-sig", newline="") if args.out else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=["term", "video_documents", "comment_documents", "video_keyness", "comment_keyness"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if args.out:
            handle.close()
            print(f"[out] {args.out} - 후보 {len(rows)}개", file=sys.stderr)

    if args.out:
        # 실행 기록. 어떤 필터로 뽑은 목록인지 남기지 않으면 결과를 재현할 수 없다.
        manifest = {
            "tool": "unmatched_terms.py",
            "run_dirs": [str(d) for d in args.run_dir],
            "panel": str(args.panel),
            "lexicon": str(args.lexicon),
            "lexicon_version": lexicon_version,
            "filters": {
                "shorts_max_seconds": SHORTS_MAX_SECONDS,
                "panel_role": "product",
                "sunscreen_terms": SUNSCREEN_TERMS,
                "min_documents": args.min_documents,
                "min_keyness": args.min_keyness,
                "top": args.top,
                "stopword_count": len(stopwords),
                "particle_count": len(particles),
                "dictionary_term_count": len(known),
            },
            "corpus": {
                "sunscreen_videos": corpus.n_video_in,
                "sunscreen_comments": corpus.n_comment_in,
                "other_videos": corpus.n_video_out,
                "other_comments": corpus.n_comment_out,
            },
            "candidates_written": len(rows),
        }
        path = args.out.with_suffix(".manifest.json")
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[out] {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
