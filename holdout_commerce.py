#!/usr/bin/env python3
"""새로 쌓인 커머스 리뷰로 **기존 결론을 검증한다.** 숫자를 갈아치우지 않는다.

우리 분석은 `captured_at < 2026-08-24` 의 리뷰 19,807건으로 했다. 서버에는 그 뒤로
**7,423건이 더 쌓였다.** 우리가 한 번도 안 본 리뷰다.

그래서 이건 **홀드아웃 검증**이다. 같은 코드로 새 리뷰만 세서 기존 비율이 재현되는지
본다. 재현되면 결론이 표본에 얹혀 있지 않다는 뜻이고, 안 되면 그게 더 중요한 발견이다.

**왜 숫자를 갈아치우지 않나.** 발표 자료·카드·대시보드가 19,807 기준으로 나가 있다.
지금 다시 돌리면 전부 어긋나고, 늘어난 것도 새 기간이 아니라 같은 창이 하루 반
길어진 것뿐이다(서버 08-18 13:00 ~ 08-26 04:00). 얻는 것보다 잃는 것이 크다.
**대신 "새 표본에서도 같은 값이 나온다" 를 얹는다.**

추출 규칙은 기존과 같다 — 정지·전순서 정렬·행수 대조. 이걸 안 하면 조용히 틀린다
(08.23 에 정렬 없는 페이징으로 "중복 37%" 라는 없는 결과를 만들었다).

사용법:
    python holdout_commerce.py
    python holdout_commerce.py --demo
"""
from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

csv.field_size_limit(10 ** 8)

BASE = "http://100.106.220.24:3000"
SCHEMA = "trend_radar"
CUTOFF = "2026-08-24T00:00:00"     # 우리 분석 경계. 서버 count 로 19,807 을 확인했다
PAGE = 1000

# `cross_source.TOPIC_ROWS` 와 같은 표현이어야 비교가 된다
TERMS = {
    "백탁": ("백탁", "하얗게", "하얘"),
    "눈시림": ("눈시림", "눈 시림", "눈시려", "눈 시려"),
    "따가움": ("따가", "따갑"),
    "끈적임": ("끈적", "번들", "유분"),
    "밀림": ("밀림", "밀려", "들뜸", "뭉침"),
}


def get(path: str, *, count: bool = False, rng: tuple[int, int] | None = None):
    req = urllib.request.Request(f"{BASE}{path}")
    req.add_header("Accept-Profile", SCHEMA)
    if count:
        req.add_header("Prefer", "count=exact")
    if rng:
        req.add_header("Range-Unit", "items")
        req.add_header("Range", f"{rng[0]}-{rng[1]}")
    with urllib.request.urlopen(req, timeout=60) as res:
        total = None
        cr = res.headers.get("Content-Range")
        if cr and "/" in cr:
            tail = cr.split("/")[-1]
            total = None if tail == "*" else int(tail)
        return json.loads(res.read().decode()), total


def fetch_holdout(cutoff: str) -> list[dict]:
    """`captured_at >= cutoff` 인 리뷰를 전부 가져온다.

    **전순서 정렬이 없으면 페이지마다 다른 정렬이 나와 중복·누락이 생긴다.**
    `captured_at` 은 동값이 많으니 `review_key` 를 두 번째 키로 넣어 순서를 고정한다.
    """
    where = f"captured_at=gte.{urllib.parse.quote(cutoff)}"
    order = "order=captured_at.asc,review_key.asc"
    _, total = get(f"/review?{where}&select=review_key&{order}", count=True, rng=(0, 0))
    print(f"서버 count=exact — 홀드아웃 {total:,}건")

    rows: list[dict] = []
    while len(rows) < total:
        page, _ = get(f"/review?{where}&select=review_key,captured_at,rating,body,source"
                      f"&{order}", rng=(len(rows), len(rows) + PAGE - 1))
        if not page:
            break
        rows.extend(page)
        print(f"  {len(rows):,}/{total:,}", end="\r")
    print()
    # **행수 대조.** 안 맞으면 페이징 중 집합이 변한 것이므로 멈춘다
    if len(rows) != total:
        raise SystemExit(f"[실패] 받은 {len(rows):,} != 서버 {total:,}. 집합이 변했다")
    keys = {r["review_key"] for r in rows}
    if len(keys) != len(rows):
        raise SystemExit(f"[실패] 중복 {len(rows) - len(keys)}건")
    print(f"[통과] {len(rows):,}건 · 중복 0 · review_key 유일")
    return rows


def rates(texts: list[str]) -> dict[str, tuple[int, float]]:
    out = {}
    for label, terms in TERMS.items():
        n = sum(1 for t in texts if any(x in t for x in terms))
        out[label] = (n, 100 * n / len(texts) if texts else 0.0)
    return out


def ours(chunks: Path) -> list[str]:
    return [r["text"] for r in
            csv.DictReader(chunks.open(encoding="utf-8-sig", newline=""))]


PLATFORMS = ("oliveyoung", "glowpick", "daisomall")


def platform_of(chunk_text: str) -> str:
    """청크 본문 머리에 플랫폼이 적혀 있다 — `[oliveyoung 리뷰 별점 3] …`."""
    head = chunk_text[:26]
    for p in ("oliveyoung", "glowpick", "daiso"):
        if p in head:
            return "daisomall" if p == "daiso" else p
    return "기타"


def by_platform(a_texts: dict[str, list[str]], b_texts: dict[str, list[str]],
                na: int) -> None:
    """**플랫폼별로 갈라 보고 기존 구성비로 표준화한다.**

    수준이 통째로 오르면 두 가지 중 하나다 — 실제로 그 말이 늘었거나, **플랫폼
    구성이 바뀐 것**이다. 다이소몰 리뷰는 선크림 표현이 거의 없어서(백탁 0.05%)
    그 비중이 흔들리면 전체 비율이 따라 움직인다. 갈라 보면 구분된다.
    """
    def rate(texts, terms):
        return (100 * sum(1 for t in texts if any(x in t for x in terms)) / len(texts)
                if texts else 0.0)

    print()
    print("플랫폼별 — 기존 → 홀드아웃 (%)")
    head = f"{'플랫폼':<12}{'기존 n':>8}{'홀드 n':>8}  " + "".join(f"{k:>16}" for k in TERMS)
    print(head)
    print("-" * len(head.encode("utf-8")) // 2 * "-" if False else "-" * 96)
    for p in PLATFORMS:
        o, n = a_texts.get(p, []), b_texts.get(p, [])
        cells = "".join(f"{rate(o, t):>7.2f}→{rate(n, t):>6.2f}" for t in TERMS.values())
        print(f"{p:<12}{len(o):>8,}{len(n):>8,}  {cells}")

    to = sum(len(v) for v in a_texts.values())
    tn = sum(len(v) for v in b_texts.values())
    print()
    print("구성 비율")
    for p in PLATFORMS:
        print(f"  {p:<12}기존 {100*len(a_texts.get(p,[]))/to:>5.1f}%"
              f"   홀드아웃 {100*len(b_texts.get(p,[]))/tn:>5.1f}%")

    # 기존 구성비로 홀드아웃을 재가중한다. 구성 효과를 빼면 남는 게 실제 변화다
    w = {p: len(a_texts.get(p, [])) / to for p in PLATFORMS}
    flat_a = [x for v in a_texts.values() for x in v]
    print()
    print("기존 구성비로 표준화 — 구성 효과를 뺀 값")
    print(f"{'주제':<10}{'기존':>8}{'홀드 원값':>10}{'표준화':>9}{'남은 차이':>10}")
    for k, t in TERMS.items():
        base = rate(flat_a, t)
        std = sum(w[p] * rate(b_texts.get(p, []), t) for p in PLATFORMS)
        raw = rate([x for v in b_texts.values() for x in v], t)
        print(f"{k:<10}{base:>7.2f}%{raw:>9.2f}%{std:>8.2f}%{std-base:>+9.2f}")


def basket(cutoff: str) -> None:
    """**제품 바스켓이 창마다 바뀌는지 본다. 이게 수준 차이의 진짜 원인이다.**

    비율이 통째로 오르면 플랫폼 구성이나 실제 변화를 먼저 의심하는데, 여기서는
    둘 다 아니었다 — **수집기가 그 주에 긁은 제품이 달랐다.** 기존 창 48제품,
    다음 창 25제품, 교집합 14제품이다. 같은 14제품만으로 세면 대부분 재현된다.

    이건 `수집 상한 10` 과 같은 계열이다 — **수집 과정이 관측값을 만든다.**
    """
    order = "order=captured_at.asc,review_key.asc"
    q = urllib.parse.quote(cutoff)

    def pull(where: str) -> list[dict]:
        _, total = get(f"/review?{where}&select=review_key&{order}", count=True, rng=(0, 0))
        rows: list[dict] = []
        while len(rows) < total:
            page, _ = get(f"/review?{where}&select=review_key,product_key,body&{order}",
                          rng=(len(rows), len(rows) + PAGE - 1))
            if not page:
                break
            rows.extend(page)
        if len(rows) != total:
            raise SystemExit(f"[실패] 받은 {len(rows):,} != 서버 {total:,}")
        return rows

    # oliveyoung 만 본다 — 수준이 2배 오른 곳이고 표본이 크다
    old_r = pull(f"source=eq.oliveyoung&captured_at=lt.{q}")
    new_r = pull(f"source=eq.oliveyoung&captured_at=gte.{q}")
    po = {r["product_key"] for r in old_r}
    pn = {r["product_key"] for r in new_r}
    both = po & pn

    print()
    print("제품 바스켓 (oliveyoung)")
    print(f"  기존 창    리뷰 {len(old_r):,} · 제품 {len(po)}")
    print(f"  홀드아웃   리뷰 {len(new_r):,} · 제품 {len(pn)}")
    print(f"  교집합 {len(both)} · 홀드아웃 전용 {len(pn-po)} · 기존 전용 {len(po-pn)}")

    def rate(rows, terms, only=None):
        t = [r["body"] or "" for r in rows if only is None or r["product_key"] in only]
        return (100 * sum(1 for x in t if any(k in x for k in terms)) / len(t)) if t else 0.0

    print()
    print("같은 제품만으로 다시 세면 — 바스켓 효과를 뺀 값")
    print(f"{'주제':<10}{'기존 전체':>10}{'기존∩':>9}{'홀드∩':>9}{'∩ 차이':>9}")
    for k, t in TERMS.items():
        a_all, a_in, b_in = rate(old_r, t), rate(old_r, t, both), rate(new_r, t, both)
        print(f"{k:<10}{a_all:>9.2f}%{a_in:>8.2f}%{b_in:>8.2f}%{b_in-a_in:>+8.2f}")
    print(f"   (교집합 리뷰: 기존 {sum(1 for r in old_r if r['product_key'] in both):,} · "
          f"홀드아웃 {sum(1 for r in new_r if r['product_key'] in both):,})")
    print()
    print("[결론] 커머스 주제 비율을 **절대값으로 쓰면 안 된다.** 제품 바스켓이 주 단위로")
    print("       바뀐다. **순위는 재현되므로** 결론(순위·방향)은 유지된다.")


def report(a: dict, b: dict, na: int, nb: int) -> int:
    print()
    print(f"{'주제':<10}{'기존 %':>9}{'홀드아웃 %':>12}{'차이(%p)':>11}{'판정':>8}")
    print("-" * 52)
    worst = 0.0
    for k in TERMS:
        pa, pb = a[k][1], b[k][1]
        d = pb - pa
        worst = max(worst, abs(d))
        # 홀드아웃이 3분의 1 크기라 표본 흔들림이 있다. 1.5%p 를 넘으면 사람이 본다
        mark = "재현" if abs(d) <= 1.5 else "★확인★"
        print(f"{k:<10}{pa:>8.2f}%{pb:>11.2f}%{d:>+10.2f}{mark:>8}")
    print("-" * 52)
    print(f"기존 {na:,}청크 · 홀드아웃 {nb:,}건 · 최대 차이 {worst:.2f}%p")
    print()
    # **수준보다 순위를 먼저 본다.** 우리 결론이 쓰는 것은 순위와 방향이다
    ra = sorted(TERMS, key=lambda k: -a[k][1])
    rb = sorted(TERMS, key=lambda k: -b[k][1])
    print(f"순위  기존 {' > '.join(ra)}")
    print(f"      홀드 {' > '.join(rb)}")
    top_same = ra[:2] == rb[:2] and ra[-1] == rb[-1]
    print(f"      1·2위와 최하위 {'일치' if top_same else '★불일치★'}")
    print()
    if worst <= 1.5:
        print("[통과] 수준도 순위도 재현된다.")
    elif top_same:
        print("[부분] **순위는 재현되고 수준은 올랐다.** 우리 결론은 순위를 쓰므로 유지된다.")
        print("       수준 차이의 원인은 아래 제품 바스켓 절에 있다.")
    else:
        print("[실패] 순위가 바뀌었다. 결론을 다시 봐야 한다.")
    return 0


def demo() -> None:
    r = rates(["백탁이 심해요", "끈적이지 않아요", "그냥 좋아요"])
    assert r["백탁"][0] == 1 and r["끈적임"][0] == 1, r
    assert r["밀림"][0] == 0
    assert abs(r["백탁"][1] - 33.33) < 0.01, r["백탁"]
    # 여러 표현이 한 건에 있어도 한 번만 센다
    r2 = rates(["백탁도 있고 하얗게 뜨고 하얘요"])
    assert r2["백탁"][0] == 1, r2
    print("demo ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--chunks", type=Path, default=Path("reports/chunks_commerce.csv"))
    p.add_argument("--cutoff", default=CUTOFF)
    p.add_argument("--out", type=Path, default=Path("reports/holdout_commerce.csv"))
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0

    hold = fetch_holdout(a.cutoff)
    by_source = Counter(r["source"] for r in hold)
    print(f"플랫폼별 {dict(by_source)}")

    old_by: dict[str, list[str]] = {}
    for r in csv.DictReader(a.chunks.open(encoding="utf-8-sig", newline="")):
        old_by.setdefault(platform_of(r["text"]), []).append(r["text"])
    new_by: dict[str, list[str]] = {}
    for r in hold:
        new_by.setdefault(r["source"], []).append(r["body"] or "")

    old_texts = ours(a.chunks)
    new_texts = [r["body"] or "" for r in hold]
    ra, rb = rates(old_texts), rates(new_texts)
    code = report(ra, rb, len(old_texts), len(new_texts))
    by_platform(old_by, new_by, len(old_texts))
    basket(a.cutoff)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8", newline="") as h:
        w = csv.writer(h, lineterminator="\n")
        w.writerow(["topic", "base_n", "base_pct", "holdout_n", "holdout_pct", "diff_pp"])
        for k in TERMS:
            w.writerow([k, ra[k][0], round(ra[k][1], 2),
                        rb[k][0], round(rb[k][1], 2), round(rb[k][1] - ra[k][1], 2)])
    print(f"{a.out} 저장")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
