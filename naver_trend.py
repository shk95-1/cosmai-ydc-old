#!/usr/bin/env python3
"""NAVER DataLab 검색 트렌드를 우리 축에 붙인다. (현준님 수집분)

어디에 있나. **3000 이 아니라 3002 포트**의 별도 PostgREST 인스턴스다.
`raw_item.payload` 가 bytea hex 라 디코드해야 JSON 이 나온다.

무엇이 있나. 2016-01 ~ 2026-08 · **128개월** · 월 단위.

    naver.datalab.suncare      백탁 · 눈시림 · 끈적임 · 밀림 · 따가움
    naver.datalab.p7.1         PDRN · 엑소좀 · 트라넥삼산 · 레티날      + 기준_세럼
    naver.datalab.p7.2         시카센텔라 · 나이아신아마이드 · 히알루론산 · 펩타이드 + 기준_세럼
    naver.datalab.p7.3         콜라겐 · 판테놀                        + 기준_세럼

**`ratio` 를 그대로 쓰면 안 된다.** DataLab 은 **요청 하나 안에서** 최대값을 100 으로
맞춘다. 실측으로 각 `source_id` 마다 100 이 정확히 한 번씩 나온다. 그래서

    같은 요청 안   그룹끼리 비교 **된다**   (백탁 36.3 vs 따가움 100)
    다른 요청 사이 비교 **안 된다**        (p7.1 의 PDRN 100 과 p7.2 의 히알루론산 100)

현준님이 `기준_세럼` 을 세 요청에 모두 넣은 이유가 이것이다. **같은 키워드가 세
요청에 있으므로 그걸 앵커로 재척도하면 요청 간 비교가 된다.**

    지수 = 그 그룹 ratio / 같은 달 기준_세럼 ratio

이러면 분자·분모가 같이 움직여 **카테고리 전체의 계절성·성장이 상쇄된다** —
우리가 `composition` 으로 설명란 길이 드리프트를 상쇄한 것과 같은 방식이다.

추출은 `commerce_ranking` 과 같은 규칙을 쓴다 — 전순서 정렬 + 행수 대조.

사용법:
    python naver_trend.py
    python naver_trend.py --offline
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = "http://100.106.220.24:3002"
PAGE = 1000
SOURCES = ["naver.datalab.suncare", "naver.datalab.suncare.v2",
           "naver.datalab.p7.1", "naver.datalab.p7.2", "naver.datalab.p7.3"]
BASELINE = "기준_세럼"          # 요청 간 재척도용 앵커
FIELDS = ["source_id", "group", "period", "ratio", "index_vs_baseline", "terms"]

# NAVER 그룹 -> 우리 주제. 이름이 거의 그대로 겹친다.
# `따가움` 과 `눈시림` 이 둘 다 `자극_눈시림` 으로 간다 — 우리 사전이 그 둘을 한
# 주제로 묶었기 때문이다. 합치지 않고 각각 남겨 두고 표시만 한다.
TOPIC_MAP = {
    "백탁": "백탁",
    "눈시림": "자극_눈시림",
    "따가움": "자극_눈시림",
    "끈적임": "끈적임_유분감",
    "밀림": "밀림_들뜸",
}


def fetch(cache: Path, offline: bool) -> dict[str, list[dict]]:
    """source_id 별 payload. 전순서 정렬 + 행수 대조를 건다."""
    if cache.exists() and offline:
        return json.loads(cache.read_text(encoding="utf-8"))
    if offline:
        raise SystemExit(f"캐시가 없다: {cache}")

    out: dict[str, list[dict]] = {}
    for source in SOURCES:
        head = urllib.request.Request(
            f"{BASE}/raw_item?source_id=eq.{source}&select=id",
            headers={"Accept": "application/json", "Prefer": "count=exact",
                     "Range": "0-0"})
        with urllib.request.urlopen(head, timeout=60) as handle:
            expected = int(handle.headers["Content-Range"].split("/")[1])

        rows, offset = [], 0
        while True:
            url = (f"{BASE}/raw_item?source_id=eq.{source}"
                   f"&select=item_key,payload,seq&order=seq.asc"
                   f"&limit={PAGE}&offset={offset}")
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as handle:
                batch = json.load(handle)
            if not batch:
                break
            rows.extend(batch)
            offset += PAGE
        if len(rows) != expected:
            raise SystemExit(f"{source} 행수가 어긋난다 — "
                             f"서버 {expected:,} vs 받은 것 {len(rows):,}")
        out[source] = [decode(r["payload"]) for r in rows]
        print(f"  {source:<28}{len(rows):>6,}건 (서버와 일치)")

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def decode(payload: str) -> dict:
    """`\\x7b22...` 형태의 bytea hex 를 JSON 으로."""
    return json.loads(bytes.fromhex(payload[2:]).decode("utf-8"))


def rescale(rows: list[dict]) -> list[dict]:
    """같은 달 `기준_세럼` 으로 나눈 지수를 붙인다. 앵커가 없으면 비운다.

    **이게 이 파일의 핵심이다.** DataLab 의 `ratio` 는 요청 안에서만 뜻이 있으므로,
    앵커로 나눠야 요청 간 비교가 된다. 그리고 나누면 카테고리 전체의 계절성이
    분자·분모에서 함께 사라진다 — 성분 자체의 상대 관심만 남는다.
    """
    anchor = {r["period"]: r["ratio"] for r in rows if r["title"] == BASELINE}
    out = []
    for row in rows:
        base = anchor.get(row["period"])
        index = (row["ratio"] / base) if base else None
        out.append({**row, "index": index})
    return out


def run(cache: Path, out: Path, offline: bool) -> int:
    print("NAVER DataLab 수신")
    data = fetch(cache, offline)

    rows = []
    for source, payloads in data.items():
        for row in rescale(payloads):
            rows.append({
                "source_id": source,
                "group": row["title"],
                "period": row["period"],
                "ratio": round(row["ratio"], 4),
                "index_vs_baseline": (round(row["index"], 4)
                                      if row["index"] is not None else ""),
                "terms": " | ".join(row.get("terms") or []),
            })
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=== 선케어 축 — 우리 주제와 같은 이름 ===")
    sun = [r for r in rows if r["source_id"] == "naver.datalab.suncare"]
    per = defaultdict(list)
    for r in sun:
        per[r["group"]].append((r["period"], r["ratio"]))
    print(f"{'NAVER 그룹':<10}{'우리 주제':<16}{'최대':>7}{'최근12개월 평균':>16}{'첫12개월 평균':>15}")
    for group, series in per.items():
        series.sort()
        values = [v for _p, v in series]
        recent = statistics.fmean(values[-12:])
        early = statistics.fmean(values[:12])
        print(f"{group:<10}{TOPIC_MAP.get(group, '—'):<16}{max(values):>7.1f}"
              f"{recent:>16.1f}{early:>15.1f}")

    print()
    print("=== 계절성 — 월별 평균 (10년) ===")
    month = defaultdict(lambda: defaultdict(list))
    for r in sun:
        month[r["group"]][r["period"][5:7]].append(r["ratio"])
    print(f"{'그룹':<10}" + "".join(f"{m:>6}" for m in
                                   [f"{i:02d}" for i in range(1, 13)]))
    for group in per:
        line = "".join(f"{statistics.fmean(month[group][f'{i:02d}']):>6.0f}"
                       for i in range(1, 13))
        print(f"{group:<10}{line}")

    print()
    print("=== 성분 — 기준_세럼 대비 지수 (요청 간 비교 가능) ===")
    ing = [r for r in rows if r["source_id"].startswith("naver.datalab.p7")
           and r["group"] != BASELINE and r["index_vs_baseline"] != ""]
    per_ing = defaultdict(list)
    for r in ing:
        per_ing[r["group"]].append((r["period"], float(r["index_vs_baseline"])))
    print(f"{'성분':<16}{'최근12개월':>12}{'2016년':>10}{'배수':>9}")
    scored = []
    for group, series in per_ing.items():
        series.sort()
        values = [v for _p, v in series]
        recent, early = statistics.fmean(values[-12:]), statistics.fmean(values[:12])
        scored.append((recent / early if early else float("inf"), group, recent, early))
    for growth, group, recent, early in sorted(scored, reverse=True):
        mark = "∞" if growth == float("inf") else f"{growth:.1f}x"
        print(f"{group:<16}{recent:>12.2f}{early:>10.2f}{mark:>9}")

    print()
    print(f"{out} 저장 — {len(rows):,}행")
    print()
    print("주의: `ratio` 는 요청 안에서만 비교된다. 요청이 다르면 "
          "`index_vs_baseline` 을 쓴다.")
    return 0


def demo() -> None:
    # bytea hex 디코드
    raw = json.dumps({"title": "백탁", "ratio": 1.0}, ensure_ascii=False)
    assert decode("\\x" + raw.encode("utf-8").hex())["title"] == "백탁"

    rows = [
        {"title": "기준_세럼", "period": "2016-01-01", "ratio": 10.0},
        {"title": "판테놀", "period": "2016-01-01", "ratio": 5.0},
        {"title": "기준_세럼", "period": "2026-08-01", "ratio": 40.0},
        {"title": "판테놀", "period": "2026-08-01", "ratio": 40.0},
    ]
    got = {(r["title"], r["period"]): r["index"] for r in rescale(rows)}
    assert got[("판테놀", "2016-01-01")] == 0.5
    assert got[("판테놀", "2026-08-01")] == 1.0
    # 앵커 자신은 항상 1 이다
    assert got[("기준_세럼", "2016-01-01")] == 1.0
    # 카테고리가 4배로 커져도 지수는 그 성장을 상쇄한다 — 이게 재척도의 요점
    assert got[("판테놀", "2026-08-01")] / got[("판테놀", "2016-01-01")] == 2.0

    # 앵커가 없는 요청은 지수를 비운다. 0 으로 채우면 없는 값이 있는 값처럼 보인다
    no_anchor = rescale([{"title": "백탁", "period": "2016-01-01", "ratio": 3.0}])
    assert no_anchor[0]["index"] is None

    assert TOPIC_MAP["눈시림"] == TOPIC_MAP["따가움"] == "자극_눈시림"
    print("demo ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", type=Path, default=Path(".cache/naver_datalab.json"))
    p.add_argument("--out", type=Path, default=Path("reports/naver_trend.csv"))
    p.add_argument("--offline", action="store_true")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0
    return run(a.cache, a.out, a.offline)


if __name__ == "__main__":
    raise SystemExit(main())
