#!/usr/bin/env python3
"""벡터 검색 유사도 하한선을 **평가셋으로** 잡는다. 표본 6개로 정하면 안 된다.

수호님이 임시로 0.865 를 넣으셨는데 표본 6개짜리라 근거가 약하다고 하셨다.
우리 평가 질의 61개와, 코퍼스에 없는 가짜 성분명으로 분포를 재서 다시 잡는다.

**e5 코사인은 좁은 띠에 뭉쳐 있다.** 문서-문서가 아니라 질의-문서라 0.78~0.92
사이에 거의 다 들어온다. 그래서 "하한선이 있으면 좋겠다" 가 아니라 **분포가 실제로
갈리는지** 부터 재야 한다. 갈리지 않으면 하한선은 무관한 결과를 통과시키면서
맞는 결과를 자르는 쪽으로만 작동한다.

판정 기준을 미리 정한다.
  분리가 된다   가짜 질의의 최고 코사인 < 진짜 질의의 최저 코사인
  쓸 수 있다    두 분포가 겹치더라도 오탐을 절반 이상 자르면서 정탐을 90% 이상 남긴다
  못 쓴다       위 둘 다 아니면 하한선을 쓰지 않고 **소스 라우팅과 원문 확인**으로 간다

사용법:
    python vector_threshold.py
    python vector_threshold.py --demo
"""
from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

csv.field_size_limit(10 ** 8)

# 코퍼스에 없는 가짜 성분명. **있는지 먼저 확인한다** — 있으면 가짜가 아니다.
# 실제 성분명처럼 보이게 만들었다(접미사 `-사이드`·`-오일`·`추출물`).
# df=0 인 토큰을 "없는 이름" 으로 볼 최소 길이. 실측으로 정했다 — 위 df_gate 참조
ZERO_DF_MINLEN = 4

FAKE = [
    "퀀텀펩타이드사이드", "하이드로실록산잔텀", "메가비타플렉소사이드",
    "젤라토프로틴추출물", "네오콜라제닌오일", "울트라세라마이덤",
    "포토리포좀아쿠아", "바이오크리스탈렌", "трансдермалин",
    "zylophosphatide", "neocryolipide", "hydraxanthenol",
]


def load_texts(chunks: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in chunks:
        if not f.exists():
            continue
        for row in csv.DictReader(f.open(encoding="utf-8-sig", newline="")):
            out[row["chunk_id"]] = row["text"]
    return out


def real_queries() -> list[tuple[str, str]]:
    """평가셋과 같은 질의를 쓴다 — 주제 별칭. 사람이 고르지 않는다."""
    import retrieval_eval
    return retrieval_eval.queries("literal")


def top_scores(vectors, queries: list[str], k: int = 1) -> list[tuple[str, float]]:
    out = []
    for q in queries:
        hits = vectors.search(q, k)
        out.append((q, hits[0][1] if hits else 0.0))
    return out


def verdict(real: list[float], fake: list[float]) -> tuple[str, float | None]:
    """미리 정한 기준으로 판정한다. 결과를 보고 기준을 만들지 않는다."""
    if not real or not fake:
        return ("측정 불가", None)
    if max(fake) < min(real):
        return ("분리됨", (max(fake) + min(real)) / 2)
    # 겹친다 — 정탐 90% 를 남기는 가장 높은 문턱을 찾아 오탐을 얼마나 자르는지 본다
    keep = sorted(real)[max(0, int(len(real) * 0.10) - 1)]
    cut = sum(1 for f in fake if f < keep) / len(fake)
    if cut >= 0.5:
        return ("겹치지만 쓸 수 있음", keep)
    return ("못 씀", keep)


def run(vectors_path: Path, chunks: list[Path]) -> int:
    from hybrid import Vectors
    v = Vectors(vectors_path)
    texts = load_texts(chunks)

    # 가짜가 정말 코퍼스에 없나. 있으면 가짜 질의가 아니다
    present = [f for f in FAKE if any(f in t for t in texts.values())]
    fake = [f for f in FAKE if f not in present]
    print(f"벡터 {len(v.ids):,}청크 · 본문 {len(texts):,}건")
    if present:
        print(f"[제외] 코퍼스에 실제로 있는 가짜 후보 {present}")
    print(f"가짜 질의 {len(fake)}개 · 진짜 질의 {len(real_queries())}개")

    real = top_scores(v, [q for _t, q in real_queries()])
    fk = top_scores(v, fake)

    def stat(rows, label):
        xs = sorted(s for _q, s in rows)
        print(f"\n{label}  n={len(xs)}")
        print(f"  최소 {xs[0]:.4f} · 25% {xs[len(xs)//4]:.4f} · 중앙 "
              f"{statistics.median(xs):.4f} · 75% {xs[3*len(xs)//4]:.4f} · 최대 {xs[-1]:.4f}")
        return xs

    r = stat(real, "진짜 질의 (주제 별칭) 최고 코사인")
    print("  가장 낮은 5개: " + " ".join(f"{q}={s:.3f}" for q, s in sorted(real, key=lambda x: x[1])[:5]))
    f = stat(fk, "가짜 질의 (없는 성분명) 최고 코사인")
    print("  가장 높은 5개: " + " ".join(f"{q}={s:.3f}" for q, s in sorted(fk, key=lambda x: -x[1])[:5]))

    kind, thr = verdict(r, f)
    print()
    print(f"판정: **{kind}**" + (f" · 문턱 후보 {thr:.4f}" if thr else ""))
    print(f"  진짜 최소 {min(r):.4f} · 가짜 최대 {max(f):.4f} · "
          f"겹침 {'있음' if max(f) >= min(r) else '없음'}")
    if thr:
        lost = sum(1 for x in r if x < thr)
        cut = sum(1 for x in f if x < thr)
        print(f"  문턱 {thr:.4f} 적용 시 — 진짜 {lost}/{len(r)}개 잘림 · "
              f"가짜 {cut}/{len(f)}개 차단")
    print()
    print("수호님 임시값 0.865 로는:")
    print(f"  진짜 {sum(1 for x in r if x < 0.865)}/{len(r)}개 잘림 · "
          f"가짜 {sum(1 for x in f if x < 0.865)}/{len(f)}개 차단")
    return 0


def df_gate(query: str, index) -> tuple[bool, str]:
    """**코사인 대신 이걸 쓴다.** 질의 토큰이 색인에 하나도 없으면 근거가 없다.

    코사인 하한선은 못 쓴다 — 실측으로 진짜 질의(0.798~0.916)와 가짜 질의
    (0.826~0.867) 분포가 거의 완전히 겹친다. 0.865 를 걸면 가짜 11/12 를 막지만
    **정탐 43/61(70%)도 함께 버린다.** e5 질의-문서 코사인이 좁은 띠에 뭉쳐 있고,
    없는 성분명도 "화학 성분 이름처럼 생긴" 문서와 0.85 쯤 나오기 때문이다.

    문서빈도는 갈린다. 실측:

        가짜 12개 중 11개  토큰 df 가 전부 0        -> 차단
        진짜 61개 중  1개  토큰 df 가 전부 0        -> `재도포`. **코퍼스에 실제로
                                                     0건이라 차단이 맞다**
        토큰이 0개인 질의   `톤 업`·`땀에`·키릴 문자   -> df 판정 대상이 아니다

    마지막 갈래를 차단하면 안 된다. 공백이 든 별칭은 **벡터가 이기는 자리**다
    (`톤 업` P@10 1.0). 그래서 "토큰이 있는데 df 가 전부 0" 일 때만 막는다.
    """
    import bm25
    toks = set(bm25.tokenize_query(query))
    if not toks:
        return (True, "토큰 없음 — df 로 판정할 수 없다. 벡터에 맡긴다")
    dfs = {t: len(index.postings.get(t, ())) for t in toks}
    if max(dfs.values()) == 0:
        return (False, f"질의 토큰이 색인에 없다 {sorted(dfs)} — 근거 없음")
    # **문장 속에 섞인 가짜 이름도 막는다** (08.26). 위 규칙은 "전부 0" 만 막아서
    # `크소나이드 함유 제품 있어` 를 통과시켰다 — `제품`(df 30,061)·`함유`(454)가
    # 있으니까. 수호님이 미결로 남겨 둔 자리다.
    #
    # 실측으로 문턱을 정했다. `len >= 4` 인 토큰 하나라도 df=0 이면 막는다.
    #
    #   규칙                  진짜 61   문장 7   가짜 15
    #   전부 0 (초판)          1 막힘    0 막힘   10 막힘
    #   하나라도 0 · len>=3    1 막힘    0 막힘   14 막힘
    #   하나라도 0 · len>=4    0 막힘    0 막힘   14 막힘   <- 정탐 손실이 없다
    #
    # 4글자로 자르는 이유는 짧은 성분명(`루틴`·`산소`)이 부분문자열로 df=0 이 될 수
    # 있어서다. 못 막는 하나는 키릴 문자 질의인데 그건 토큰이 0개라 위에서 걸러진다
    missing = sorted(t for t, v in dfs.items() if v == 0 and len(t) >= ZERO_DF_MINLEN)
    if missing:
        return (False, f"코퍼스에 없는 이름이 섞여 있다 {missing} — "
                       f"검색 결과가 나와도 그 이름과 무관한 문서다")
    return (True, f"df 최대 {max(dfs.values()):,}")


def demo() -> None:
    assert verdict([0.9, 0.91], [0.8, 0.81])[0] == "분리됨"
    # 겹치면 정탐 90% 를 남기는 문턱에서 오탐이 절반 이상 잘려야 쓸 수 있다
    k, t = verdict([0.90] * 9 + [0.70], [0.60] * 8 + [0.95, 0.95])
    assert k == "겹치지만 쓸 수 있음", (k, t)
    k2, _ = verdict([0.90] * 9 + [0.70], [0.85] * 10)
    assert k2 == "못 씀", k2
    assert verdict([], [0.5])[0] == "측정 불가"

    class FakeIndex:
        postings = {"백탁": [1, 2, 3], "선크림": [4], "제품": list(range(50)),
                    "함유": list(range(9))}
    ok, why = df_gate("백탁", FakeIndex())
    assert ok and "3" in why, (ok, why)
    # 색인에 없는 말은 막는다 — 토큰이 하나뿐이라 "전부 0" 규칙에 걸린다
    bad, why2 = df_gate("퀀텀펩타이드사이드", FakeIndex())
    assert not bad and "근거 없음" in why2, (bad, why2)
    # **문장 속에 섞인 가짜 이름도 막는다.** 이게 08.26 에 새로 막은 자리다
    bad3, why3 = df_gate("크소나이드 함유 제품", FakeIndex())
    assert not bad3 and "없는 이름이 섞여" in why3, (bad3, why3)
    # 짧은 토큰은 안 막는다 — 부분문자열로 df=0 이 될 수 있다
    ok4, _ = df_gate("백탁 제품", FakeIndex())
    assert ok4
    print("demo ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vectors", type=Path, default=Path(".cache/vectors/e5all"))
    p.add_argument("--chunks", action="append", type=Path)
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0
    chunks = a.chunks or [Path("reports/chunks_youtube.csv"),
                          Path("reports/chunks_commerce.csv"),
                          Path("reports/chunks_ingredient_mfds.csv")]
    return run(a.vectors, chunks)


if __name__ == "__main__":
    raise SystemExit(main())
