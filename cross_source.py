#!/usr/bin/env python3
"""소스를 나란히 놓고 어긋나는 자리를 찾는다. **합산하지 않는다.**

왜 합산하지 않나. 소스마다 분모가 다르다 — NAVER 는 검색량 지수, 유튜브는 13주제
대비 구성비, 성분표는 577제품 대비 채택률, 커머스는 리뷰 건수다. 더하거나 평균
내면 그 순간 의미가 없어진다. 그래서 **크기가 아니라 순위와 방향**을 본다.
`ingredient_axis.py` 가 제품·담론 순위를 비교한 것과 같은 방식이다.

두 개를 낸다.

  주제 축   백탁·눈시림 등 5개를 NAVER(10년) · 유튜브(13분기) · 커머스 리뷰로
  성분 축   10개 성분을 NAVER 검색 · 선케어 처방 채택률·배합순위 · 담론 언급으로

**어긋나는 자리가 R&D 공백이다.** 검색은 느는데 처방에 없는 성분, 리뷰에는 많은데
영상에는 없는 불만 — 예측이 아니라 현재 상태의 비대칭이라 후향 검증에서 살아남는
종류다.

주의 세 가지.

1. **NAVER `ratio` 는 요청 안에서만 비교된다.** 선케어 5개는 한 요청이라 서로
   비교되지만, 성분은 세 요청에 흩어져 있어 `기준_세럼` 대비 지수를 쓴다.
2. **선케어 요청에는 기준선이 없다.** 그래서 "백탁 검색이 줄었다" 를 추세로 읽으면
   안 된다 — 네이버 검색 자체가 줄었을 수도 있고 구분할 방법이 없다. 그룹 간
   상대 비교만 한다.
3. **`눈시림` 과 `따가움` 이 둘 다 우리 `자극_눈시림` 으로 간다.** 합치지 않고
   각각 남긴다. 합치면 NAVER 쪽만 두 배가 된다.

사용법:
    python cross_source.py
"""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(10 ** 8)

TOPIC_ROWS = [
    # (NAVER 그룹, 우리 주제, 담론에서 셀 표현)
    ("백탁", "백탁", ("백탁", "하얗게", "하얘")),
    ("눈시림", "자극_눈시림", ("눈시림", "눈 시림", "눈시려", "눈 시려")),
    ("따가움", "자극_눈시림", ("따가", "따갑")),
    ("끈적임", "끈적임_유분감", ("끈적", "번들", "유분")),
    ("밀림", "밀림_들뜸", ("밀림", "밀려", "들뜸", "뭉침")),
]

# NAVER 성분 그룹 -> 성분표에서 찾을 이름 조각. 소문자 부분문자열로 본다.
INGREDIENT_KEYS = {
    "PDRN": ("피디알엔", "pdrn", "폴리데옥시리보뉴클레오타이드"),
    "엑소좀": ("엑소좀", "exosome"),
    "트라넥삼산": ("트라넥삼산",),
    "레티날": ("레티날", "레티놀"),
    "시카센텔라": ("센텔라", "시카"),
    "나이아신아마이드": ("나이아신아마이드",),
    "히알루론산": ("하이알루로", "히알루론"),
    "펩타이드": ("펩타이드",),
    "콜라겐": ("콜라겐",),
    "판테놀": ("판테놀",),
}

TOPIC_FIELDS = ["naver_group", "topic_id", "naver_recent", "naver_rank",
                "youtube_video_pct", "youtube_comment_pct", "comment_rank",
                "commerce_pct", "commerce_rank", "reading"]
ING_FIELDS = ["ingredient", "naver_index_recent", "naver_growth_x", "naver_rank",
              "paper_epmc", "paper_pubmed", "paper_usable",
              "formula_products", "formula_pct", "median_order", "high_dose_pct",
              "talk_youtube", "talk_commerce", "reading"]

# NAVER 그룹 -> 논문 검색어. 현준님 데이터(slopindustries/cosmai-ml)의 query 값이다.
# 엑소좀·펩타이드는 검색어가 없어 빈칸으로 둔다 — 0 으로 채우면 없는 값이 있는
# 값처럼 보인다.
# `레티날` 은 `retinaldehyde` 다. `retinol` 이 아니다 — 현준님이 갈라 주셨다.
# 다만 성분표 쪽 `INGREDIENT_KEYS` 는 레티놀까지 세는데, 그건 제품 수를 후하게
# 잡는 방향이라 "처방에 거의 없다" 는 결론을 약하게 만들 뿐 뒤집지 않는다.
PAPER_QUERY = {
    "PDRN": "polydeoxyribonucleotide",
    "엑소좀": "exosome",
    "트라넥삼산": "tranexamic acid",
    "레티날": "retinaldehyde",
    "시카센텔라": "centella asiatica",
    "나이아신아마이드": "niacinamide",
    "히알루론산": "hyaluronic acid",
    "콜라겐": "collagen",
    "판테놀": "panthenol",
}
PAPER_BASELINE = "cosmetic"      # 색인 자체의 성장률. 이걸로 나눠야 비교가 된다
PAPER_GAP = 0.3                  # 두 색인 보정 배수가 이만큼 벌어지면 진짜 이견


def read(path: Path) -> list[dict]:
    """`#` 주석 줄은 건너뛴다. 현준님 CSV 는 머리에 주의사항이 붙어 있다."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader([l for l in handle if not l.startswith("#")]))


def paper_growth(rows: list[dict]) -> dict[str, dict]:
    """검색어 -> 소스별 **보정 배수**. 원본 배수를 그대로 쓰면 안 된다.

    두 색인의 성장률이 다르다 — Europe PMC 는 프리프린트를 포함해 전체가 2.10배
    커졌고 PubMed 는 1.44배다. 그래서 어떤 성분이든 EPMC 쪽 배수가 크게 나온다.
    `cosmetic` 검색어로 나누면 색인 성장이 상쇄되고 **두 소스가 사실상 일치한다**
    (실측으로 표본 충분한 10개의 차이 평균 0.083 · 최대 0.363).

    NAVER 의 `기준_세럼`, 우리 `composition` 과 같은 방식이다.

    `ratio_usable` 이 False 면 2019 기준선이 월 5편 미만이라 배수가 잡음이다.
    현준님이 표시해 두셨고 30행 중 8행이 걸린다. 그대로 존중한다.
    """
    by = {(r["query"], r["source"]): r for r in rows}
    base = {}
    for source in {r["source"] for r in rows}:
        anchor = by.get((PAPER_BASELINE, source))
        if anchor:
            base[source] = float(anchor["growth"])
    out: dict[str, dict] = defaultdict(dict)
    for (query, source), row in by.items():
        if query == PAPER_BASELINE or source not in base:
            continue
        out[query][source] = {
            "growth": float(row["growth"]) / base[source],
            "usable": row.get("ratio_usable") == "True",
        }
    return out


def naver_series(rows: list[dict], source: str) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        if row["source_id"] != source:
            continue
        out[row["group"]].append((row["period"], float(row["ratio"])))
    for series in out.values():
        series.sort()
    return out


def naver_index(rows: list[dict]) -> dict[str, tuple[float, float]]:
    """성분 -> (최근 12개월 지수, 2016년 대비 배수). 기준_세럼 대비 값을 쓴다."""
    per: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        if not row["source_id"].startswith("naver.datalab.p7"):
            continue
        if row["group"] == "기준_세럼" or not row["index_vs_baseline"]:
            continue
        per[row["group"]].append((row["period"], float(row["index_vs_baseline"])))
    out = {}
    for group, series in per.items():
        series.sort()
        values = [v for _p, v in series]
        recent = statistics.fmean(values[-12:])
        early = statistics.fmean(values[:12])
        out[group] = (recent, (recent / early) if early else float("inf"))
    return out


def count_terms(texts: list[str], terms: tuple[str, ...]) -> int:
    """그 표현이 든 청크 수. 한 청크에 여러 번 나와도 한 번만 센다."""
    return sum(1 for t in texts if any(term in t for term in terms))


def ranks(values: dict[str, float]) -> dict[str, int]:
    """큰 값이 1위. 비교는 크기가 아니라 순위로 한다."""
    order = sorted(values, key=lambda k: -values[k])
    return {k: i + 1 for i, k in enumerate(order)}


def topic_table(naver: list[dict], trend: list[dict],
                youtube: list[str], commerce: list[str]) -> list[dict]:
    series = naver_series(naver, "naver.datalab.suncare")
    recent = {g: statistics.fmean([v for _p, v in s][-12:]) for g, s in series.items()}
    n_rank = ranks(recent)

    # 유튜브는 확정된 마지막 분기의 구성비를 쓴다. 미확정 분기는 과소 집계된다
    quarters = sorted({r["quarter"] for r in trend})
    last = quarters[-2] if len(quarters) > 1 else quarters[-1]
    comp: dict[tuple[str, str], float] = {}
    for r in trend:
        if r["quarter"] == last:
            comp[(r["source"], r["topic_id"])] = float(r["composition"] or 0) * 100

    talk_c = {g: count_terms(commerce, terms) for g, _t, terms in TOPIC_ROWS}
    c_rank = ranks({k: float(v) for k, v in talk_c.items()})
    yt_rank = ranks({g: comp.get(("youtube_comment", t), 0.0)
                     for g, t, _terms in TOPIC_ROWS})

    rows = []
    for group, topic, terms in TOPIC_ROWS:
        video = comp.get(("youtube_video", topic), 0.0)
        comment = comp.get(("youtube_comment", topic), 0.0)
        pct = 100 * talk_c[group] / len(commerce) if commerce else 0.0
        reading = []
        if n_rank[group] <= 2 and c_rank[group] >= 4:
            reading.append("검색 상위인데 리뷰에서는 적게 말함")
        if pct > 0 and video < 0.5 and comment > video * 3:
            reading.append("영상은 안 다루는데 댓글·리뷰에는 있음")
        rows.append({
            "naver_group": group, "topic_id": topic,
            "naver_recent": round(recent[group], 2), "naver_rank": n_rank[group],
            "youtube_video_pct": round(video, 2),
            "youtube_comment_pct": round(comment, 2),
            "comment_rank": yt_rank[group],
            "commerce_pct": round(pct, 2), "commerce_rank": c_rank[group],
            "reading": " · ".join(reading),
        })
    return rows


def ingredient_table(naver: list[dict], formula: list[dict],
                     youtube: list[str], commerce: list[str],
                     papers: dict[str, dict]) -> list[dict]:
    index = naver_index(naver)
    n_rank = ranks({g: v[0] for g, v in index.items()})

    products = defaultdict(set)
    orders: dict[str, list[int]] = defaultdict(list)
    for row in formula:
        name = row["ingredient"].replace(" ", "").lower()
        try:
            order = int(row["ingredient_order"])
        except (TypeError, ValueError):
            continue
        for group, keys in INGREDIENT_KEYS.items():
            if any(k in name for k in keys):
                products[group].add(row["product_name"])
                orders[group].append(order)
    total = len({r["product_name"] for r in formula})

    rows = []
    for group in INGREDIENT_KEYS:
        recent, growth = index.get(group, (0.0, 0.0))
        names = products[group]
        order = sorted(orders[group])
        median = order[len(order) // 2] if order else None
        high = (100 * sum(1 for o in order if o <= 10) / len(order)) if order else 0.0
        terms = (group,) + INGREDIENT_KEYS[group]
        talk_y = count_terms(youtube, terms)
        talk_c = count_terms(commerce, terms)

        paper = papers.get(PAPER_QUERY.get(group, ""), {})
        epmc, pubmed = paper.get("europepmc", {}), paper.get("pubmed", {})
        usable = bool(epmc.get("usable")) and bool(pubmed.get("usable"))

        reading = []
        if epmc and pubmed and usable:
            gap = abs(epmc["growth"] - pubmed["growth"])
            if gap > PAPER_GAP:
                reading.append("두 색인이 갈린다 — 한쪽만 보고 결론 내지 말 것")
            elif epmc["growth"] < 0.9 and pubmed["growth"] < 0.9:
                reading.append("논문은 화장품 분야 평균보다 뒤처짐")
        elif epmc:
            reading.append("논문 표본 부족 — 배수를 쓰면 안 됨")
        if growth >= 20 and len(names) <= 5:
            reading.append("검색 급증인데 선케어 처방에 없음 — 카테고리 밖 성분")
        elif len(names) / total > 0.3 and high < 10:
            reading.append("널리 쓰지만 고함량으로는 안 씀")
        elif len(names) / total > 0.3 and high >= 50:
            reading.append("널리 쓰고 고함량으로도 씀")
        rows.append({
            "ingredient": group,
            "naver_index_recent": round(recent, 2),
            "naver_growth_x": ("∞" if growth == float("inf") else round(growth, 1)),
            "naver_rank": n_rank.get(group, 0),
            "paper_epmc": (round(epmc["growth"], 2) if epmc else ""),
            "paper_pubmed": (round(pubmed["growth"], 2) if pubmed else ""),
            "paper_usable": ("" if not epmc else ("true" if usable else "false")),
            "formula_products": len(names),
            "formula_pct": round(100 * len(names) / total, 1),
            "median_order": median if median is not None else "",
            "high_dose_pct": round(high, 0),
            "talk_youtube": talk_y, "talk_commerce": talk_c,
            "reading": " · ".join(reading),
        })
    rows.sort(key=lambda r: -float(r["naver_index_recent"]))
    return rows


def run(naver_csv: Path, trend_csv: Path, formula_csv: Path,
        yt_csv: Path, cm_csv: Path, paper_csv: Path, out: Path) -> int:
    naver = read(naver_csv)
    trend = read(trend_csv)
    formula = read(formula_csv)
    youtube = [r["text"] for r in read(yt_csv)]
    commerce = [r["text"] for r in read(cm_csv)]
    papers = paper_growth(read(paper_csv)) if paper_csv.exists() else {}
    if not papers:
        print(f"[경고] 논문 데이터가 없다: {paper_csv}. 성분 표의 그 칸이 빈다")
    print(f"NAVER {len(naver):,} · 지표 {len(trend):,} · 성분표 {len(formula):,} · "
          f"유튜브 청크 {len(youtube):,} · 리뷰 청크 {len(commerce):,}")

    topics = topic_table(naver, trend, youtube, commerce)
    print()
    print("=== 주제 축 — 소스마다 분모가 다르므로 순위를 본다 ===")
    print(f"{'NAVER':<8}{'우리 주제':<16}{'NAVER':>8}{'순위':>5}"
          f"{'영상%':>7}{'댓글%':>7}{'순위':>5}{'리뷰%':>7}{'순위':>5}")
    for r in topics:
        print(f"{r['naver_group']:<8}{r['topic_id']:<16}{r['naver_recent']:>8.1f}"
              f"{r['naver_rank']:>5}{r['youtube_video_pct']:>7.2f}"
              f"{r['youtube_comment_pct']:>7.2f}{r['comment_rank']:>5}"
              f"{r['commerce_pct']:>7.2f}{r['commerce_rank']:>5}")
    for r in topics:
        if r["reading"]:
            print(f"    {r['naver_group']} — {r['reading']}")

    ing = ingredient_table(naver, formula, youtube, commerce, papers)
    print()
    print("=== 성분 축 — 논문(보정) · NAVER 검색 · 선케어 처방 · 담론 ===")
    print(f"{'성분':<16}{'EPMC':>7}{'PubMed':>8}{'검색':>8}{'제품':>6}{'비율':>7}"
          f"{'배합순위':>9}{'고함량':>7}{'담론':>8}")
    for r in ing:
        epmc = f"{r['paper_epmc']:>7}" if r["paper_epmc"] != "" else f"{'-':>7}"
        pm = f"{r['paper_pubmed']:>8}" if r["paper_pubmed"] != "" else f"{'-':>8}"
        print(f"{r['ingredient']:<16}{epmc}{pm}"
              f"{str(r['naver_growth_x'])+'x':>8}{r['formula_products']:>6}"
              f"{r['formula_pct']:>6.1f}%{str(r['median_order'] or '-'):>9}"
              f"{r['high_dose_pct']:>6.0f}%{r['talk_youtube']:>8,}")
    print()
    for r in ing:
        if r["reading"]:
            print(f"    {r['ingredient']:<16}{r['reading']}")

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TOPIC_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(topics)
    ing_out = out.with_name(out.stem + "_ingredient.csv")
    with ing_out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ING_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ing)
    print()
    print(f"{out} · {ing_out} 저장")
    print("주의: NAVER 선케어 요청에는 기준선이 없다. 그룹 간 상대 비교만 하고 "
          "추세로 읽지 않는다.")
    return 0


def demo() -> None:
    assert ranks({"a": 3.0, "b": 1.0, "c": 2.0}) == {"a": 1, "c": 2, "b": 3}
    # 한 청크에 여러 번 나와도 한 번만 센다
    assert count_terms(["백탁 백탁 백탁", "촉촉"], ("백탁",)) == 1
    assert count_terms(["하얗게 뜬다"], ("백탁", "하얗게")) == 1
    assert count_terms([], ("백탁",)) == 0

    rows = [{"source_id": "naver.datalab.p7.1", "group": "PDRN",
             "period": "2016-01-01", "ratio": "1", "index_vs_baseline": "0.1"},
            {"source_id": "naver.datalab.p7.1", "group": "PDRN",
             "period": "2026-08-01", "ratio": "9", "index_vs_baseline": "0.4"},
            {"source_id": "naver.datalab.p7.1", "group": "기준_세럼",
             "period": "2016-01-01", "ratio": "1", "index_vs_baseline": "1.0"}]
    idx = naver_index(rows)
    assert "기준_세럼" not in idx, "앵커 자신은 성분이 아니다"
    assert abs(idx["PDRN"][0] - 0.25) < 1e-9, idx        # (0.1+0.4)/2
    assert abs(idx["PDRN"][1] - 1.0) < 1e-9, idx         # 표본이 12 미만이면 같은 창

    # 논문 배수는 색인 성장률로 나눠야 비교가 된다
    pg = paper_growth([
        {"query": "cosmetic", "source": "europepmc", "growth": "2.0",
         "ratio_usable": "True"},
        {"query": "cosmetic", "source": "pubmed", "growth": "1.0",
         "ratio_usable": "True"},
        {"query": "x", "source": "europepmc", "growth": "4.0",
         "ratio_usable": "True"},
        {"query": "x", "source": "pubmed", "growth": "2.0",
         "ratio_usable": "False"},
    ])
    assert "cosmetic" not in pg, "기준선 자신은 성분이 아니다"
    assert pg["x"]["europepmc"]["growth"] == 2.0        # 4.0 / 2.0
    assert pg["x"]["pubmed"]["growth"] == 2.0           # 2.0 / 1.0 — 보정하면 일치
    assert pg["x"]["pubmed"]["usable"] is False, "표본 부족 표시를 존중해야 한다"

    # 눈시림과 따가움이 같은 주제로 가지만 행은 따로 남아야 한다
    topics = [t for _g, t, _x in TOPIC_ROWS]
    assert topics.count("자극_눈시림") == 2
    assert len(TOPIC_ROWS) == 5
    print("demo ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--naver", type=Path, default=Path("reports/naver_trend.csv"))
    p.add_argument("--trend", type=Path,
                   default=Path("reports/trend_sunscreen_v0.2.csv"))
    p.add_argument("--formula", type=Path,
                   default=Path("data/external/product_ingredient_function_repaired.csv"))
    p.add_argument("--youtube", type=Path, default=Path("reports/chunks_youtube.csv"))
    p.add_argument("--commerce", type=Path, default=Path("reports/chunks_commerce.csv"))
    p.add_argument("--papers", type=Path,
                   default=Path("data/external/paper_growth.csv"))
    p.add_argument("--out", type=Path, default=Path("reports/cross_source.csv"))
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0
    return run(a.naver, a.trend, a.formula, a.youtube, a.commerce, a.papers,
               a.out)


if __name__ == "__main__":
    raise SystemExit(main())
