#!/usr/bin/env python3
"""성분 축 Opportunity Card. `cards.py` 와 같은 원칙, 다른 단위다.

`cards.py` 는 **주제**(백탁·눈시림)를 다룬다. 이건 **성분**(엑소좀·판테놀)을 다룬다.
단위가 다르면 근거도 칸도 다르다 — 주제 카드는 갭·구성비·velocity 로 서고, 성분
카드는 논문 배수·검색 배수·배합순위·고함량으로 선다. 그래서 파일을 나눴다.

`cards.py` 독스트링이 예약해 둔 유형이 하나 있었다.

    선행 연구 기회   논문 계열이 앞서고 소비자 언급이 낮다  ← 논문 데이터 미도착, 보류

논문이 도착해서 구현했는데(08.25 오전), **같은 날 오후에 다시 닫혔다.**

현준님이 `(skin)` 필터를 철회하셨고, 우리가 쓰던 순수 검색어도 못 쓴다는 걸
잔존율로 확인했다 — `(skin)` 을 붙이면 남는 비율이다.

    엑소좀 20.6% · 트라넥삼산 30.7% · 콜라겐 33.3% · 나이아신아마이드 33.4%
    아데노신은 19.0% 였고 현준님이 그래서 막으셨다. **엑소좀이 같은 자리다.**

**진짜 문제는 분모와 분자가 다른 모집단이라는 것이다.** 분자는 `exosome` 처럼
전분야 검색어(잔존율 20~48%)인데 분모 `cosmetic` 은 화장품 검색어다. 그 둘로
나눈 배수는 아무 것도 뜻하지 않는다.

(초판은 "`cosmetic` 잔존율이 100.1% 라서" 를 근거로 적었는데 **그건 근거가 안 된다.**
필터가 `AND (skin OR cosmetic OR dermatology)` 이고 검색어가 `cosmetic` 이라
필터가 아무것도 못 걸러내는 항등식이다. 100 을 넘는 0.1% 는 두 계열을 다른 시점에
받은 색인 드리프트다. 결론은 위 문장으로 서고 100.1% 는 안 쓴다.)

그래서 `cross_source.PAPER_HOLD = True` 다. 논문 칸이 비어서 들어오고 유형이
자동으로 내려간다. **스위치만 내리면 되는 게 아니었다** — `build()` 가 논문 CSV 를
직접 읽어 카드에 배수를 인쇄하고 있었다(08.26 발견). 이제 `PAPER_HOLD` 를 본다.

설계 원칙은 `cards.py` 와 같다.
  1. 유형은 규칙이 정한다. LLM 이 "이건 기회야"라고 판단하지 않는다.
  2. 수치는 `reports/cross_source_ingredient.csv` 에서 그대로 가져온다. 새로 계산하지 않는다.
  3. 근거를 짚을 수 없으면 카드로 만들지 않는다. 처방 0% 는 **"577제품 전수에서 0건"**
     이라는 확인 가능한 음성 근거로 선다.
  4. 한계를 카드 안에 넣는다. `ratio_usable=False`·색인 이견·1월 아티팩트를 숨기지 않는다.

유형 다섯 개. 논문 축이 중지된 지금 **뜨는 것은 셋뿐이다.**

    선행 연구 기회    논문·검색이 같이 오르는데 처방에 없다        논문 중지로 안 뜬다
    수요 선행 공백    검색만 오르고 처방이 0                     기회
    함량 공백        널리 채택했는데 고함량으로는 안 쓴다          기회 — 가장 확실하다
    유행 반증        검색은 급증인데 논문이 뒷걸음                논문 중지로 안 뜬다
    처방 기준선      널리 쓰고 고함량으로도 쓴다                  비교 기준. 기회가 아니다

**레티날은 처방 0% 다.** 08.26 에 성분표 매칭을 고쳤더니 그렇게 됐다 — 그전에는
`레티놀` 을 같이 세서 1.2% 로 보였는데 성분표에 `레티날` 은 **0건**이다. 그래서
검색 287배 · 처방 0% 로 `수요 선행 공백` 의 대표가 된다.

**규칙에서 빼지 않는다.** 광민감성 때문에 선케어 배합이 어렵다는 건 도메인 지식이고
우리가 측정한 값이 아니다. 손으로 빼면 "결과를 보고 기준 만들기" 가 된다.
대신 **그 카드의 한계에 왜 쫓지 말아야 하는지를 적는다.**

사용법:
    python ingredient_cards.py
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from cross_source import PAPER_HOLD

csv.field_size_limit(10 ** 8)

# 임계값. 결과를 보고 정하지 않았다 — 대조표를 만들 때 쓴 값과 같다
SEARCH_SURGE = 20.0        # 검색 급증으로 볼 최소 배수 (기준_세럼 대비)
PRESCRIBE_ABSENT = 1.0     # 처방에 없다고 볼 최대 채택률 %
PRESCRIBE_WIDE = 30.0      # 널리 채택했다고 볼 최소 채택률 %
HIGH_DOSE_SHALLOW = 5.0    # 얕게 쓴다고 볼 최대 고함량 비율 %
HIGH_DOSE_DEEP = 50.0      # 깊게 쓴다고 볼 최소 고함량 비율 %
PAPER_AHEAD = 1.0          # 화장품 분야 평균. 이걸 넘으면 분야보다 빨리 큰다
PAPER_BEHIND = 0.9         # 이 아래면 뒤처진다
PAPER_GAP = 0.3            # 두 색인이 이만큼 벌어지면 논문을 인용하지 않는다

# 성분표에서 그 성분을 찾을 이름 조각. cross_source.py 의 INGREDIENT_KEYS 와 같아야 한다
KEYS = {
    "PDRN": ("피디알엔", "pdrn", "폴리데옥시리보뉴클레오타이드"),
    "엑소좀": ("엑소좀", "exosome"),
    "트라넥삼산": ("트라넥삼산",),
    "레티날": ("레티날",),          # 성분표에 `레티놀` 은 별개 성분이다
    "시카센텔라": ("병풀", "센텔라", "마데카", "아시아티코", "아시아틱"),
    "나이아신아마이드": ("나이아신아마이드",),
    "히알루론산": ("하이알루로", "히알루론"),
    "펩타이드": ("펩타이드",),
    "콜라겐": ("콜라겐",),
    "판테놀": ("판테놀",),
}

# 논문 검색어. cross_source.py 의 PAPER_QUERY 와 같아야 한다
PAPER_QUERY = {
    "PDRN": "polydeoxyribonucleotide", "엑소좀": "exosome",
    "트라넥삼산": "tranexamic acid", "레티날": "retinaldehyde",
    "시카센텔라": "centella asiatica", "나이아신아마이드": "niacinamide",
    "히알루론산": "hyaluronic acid", "콜라겐": "collagen", "판테놀": "panthenol",
}


def read(path: Path) -> list[dict]:
    """`#` 주석 줄은 건너뛴다. 현준님 CSV 는 머리에 주의사항이 붙어 있다."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader([l for l in handle if not l.startswith("#")]))


def num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def classify(row: dict) -> tuple[str, str] | None:
    """(유형, 배정 근거). 어느 규칙에도 안 걸리면 None — 카드로 만들지 않는다."""
    search = num(row["naver_growth_x"])
    pct = num(row["formula_pct"])
    high = num(row["high_dose_pct"])
    epmc, pubmed = row["paper_epmc"], row["paper_pubmed"]
    usable = row["paper_usable"] == "true"
    has_paper = epmc != "" and pubmed != ""
    e, p = num(epmc), num(pubmed)
    agree = has_paper and abs(e - p) <= PAPER_GAP

    # **처방과 무관한 규칙이라 먼저 본다.** 이건 "검색과 연구가 어긋난다" 는 주장이고
    # 그 성분이 처방에 몇 % 들었는지와 상관이 없다. 처방 문턱을 걸면 레티날(1.2%)이
    # 빠지는데, 문턱을 올려 맞추는 건 결과를 보고 기준을 만드는 것이다
    if search >= SEARCH_SURGE and usable and agree and max(e, p) < PAPER_BEHIND:
        return ("유행 반증",
                f"검색 {search:.0f}배인데 논문은 {e:.2f}·{p:.2f} 로 분야 평균에 뒤짐")

    if search >= SEARCH_SURGE and pct <= PRESCRIBE_ABSENT:
        # 논문이 같은 방향이면 근거가 셋이다. 아니면 둘이다. 그 차이를 유형으로 남긴다
        if usable and agree and min(e, p) > PAPER_AHEAD:
            return ("선행 연구 기회",
                    f"논문 {e:.2f}·{p:.2f} 둘 다 화장품 분야 평균 초과 · "
                    f"검색 {search:.0f}배 · 처방 {pct:.1f}%")
        why = ("논문 축 중지" if PAPER_HOLD else
               "논문 표본 부족" if has_paper and not usable else "논문 검색어 없음")
        return ("수요 선행 공백", f"검색 {search:.0f}배 · 처방 {pct:.1f}% · {why}")

    if pct >= PRESCRIBE_WIDE and high <= HIGH_DOSE_SHALLOW:
        return ("함량 공백",
                f"채택 {pct:.1f}%({row['formula_products']}제품)인데 "
                f"배합순위 중앙 {row['median_order']}위 · 고함량 {high:.0f}%")

    if pct >= HIGH_DOSE_DEEP and high >= HIGH_DOSE_DEEP:
        return ("처방 기준선",
                f"채택 {pct:.1f}% · 배합순위 중앙 {row['median_order']}위 · 고함량 {high:.0f}%")
    return None


def products_with(rows: list[dict], keys: tuple[str, ...], limit: int = 3) -> list[str]:
    """그 성분이 든 실제 제품명. **중앙값 근처를 뽑는다.**

    앞선 것부터 뽑으면 안 된다. `함량 공백` 카드는 "배합순위 중앙 46위 · 고함량 0%"
    를 주장하는데 근거로 **배합 1순위 제품**이 실리면 카드가 스스로를 반박한다
    (히알루론산에서 실제로 그랬다). 대표값 근처를 싣고 극단은 예외로 따로 밝힌다.
    """
    best: dict[str, int] = {}
    low = [k.lower() for k in keys]
    for r in rows:
        if not any(k in r["ingredient"].lower() for k in low):
            continue
        try:
            order = int(r["ingredient_order"])
        except (TypeError, ValueError):
            continue
        name = r["product_name"]
        if name not in best or order < best[name]:
            best[name] = order
    ordered = sorted(best.items(), key=lambda kv: kv[1])
    if not ordered:
        return []
    start = max(0, len(ordered) // 2 - limit // 2)
    lines = [f"{n} — 배합 {o}순위" for n, o in ordered[start:start + limit]]
    if len(ordered) > limit:
        top_name, top_order = ordered[0]
        lines.append(f"(가장 앞선 제품은 배합 {top_order}순위 — {top_name}. "
                     f"전체 {len(ordered)}제품 중 예외다)")
    return lines


def build(reports: Path, formula: Path, papers: Path) -> list[dict]:
    # 논문 축이 중지되면 `cross_source_ingredient.csv` 의 논문 칸이 비어서 들어온다.
    # classify() 가 빈 칸을 이미 다루므로(has_paper False) 따로 분기하지 않는다 —
    # 엑소좀은 `선행 연구 기회`에서 `수요 선행 공백`으로 내려가고, 레티날의
    # `유행 반증`은 사라진다. **그게 맞는 동작이다.** 논문 없이는 그 주장을 못 한다.
    rows = read(reports / "cross_source_ingredient.csv")
    formula_rows = read(formula) if formula.exists() else []
    total_products = len({r["product_name"] for r in formula_rows})
    raw: dict[tuple[str, str], dict] = {}
    if papers.exists():
        raw = {(r["query"], r["source"]): r for r in read(papers)}

    cards = []
    for row in rows:
        got = classify(row)
        if not got:
            continue
        kind, basis = got
        name = row["ingredient"]
        pct = num(row["formula_pct"])

        # ---- 근거. 짚을 수 없으면 카드로 만들지 않는다 ----
        evidence = []
        if pct > 0 and formula_rows:
            hits = products_with(formula_rows, KEYS.get(name, (name,)))
            if hits:
                evidence.append(("성분표 실제 제품", hits,
                                 "data/external/product_ingredient_function_repaired.csv"))
        elif formula_rows:
            evidence.append(("성분표 전수 조회",
                             [f"선케어 {total_products}제품 · 31,246행에서 **0건**. "
                              f"이름 조각 {', '.join(KEYS.get(name, (name,)))} 로 찾았다"],
                             "data/external/product_ingredient_function_repaired.csv"))
        evidence.append(("NAVER 검색",
                         [f"기준_세럼 대비 지수 {row['naver_index_recent']} · "
                          f"2016년 대비 {row['naver_growth_x']}배 · 성분 그룹 {row['naver_rank']}위"],
                         "3002 포트 raw_item.payload · 128개월"))
        # **`PAPER_HOLD` 를 안 보면 철회한 배수가 카드에 근거로 인쇄된다.**
        # 08.26 에 실제로 그랬다 — 카드 3장에 EPMC 2.45 / PubMed 1.92 가
        # "근거" 로 실려 있었고 보정 줄은 `->  / ` 로 깨져 있었다
        q = None if PAPER_HOLD else PAPER_QUERY.get(name)
        if q and (q, "europepmc") in raw:
            e_raw, p_raw = raw[(q, "europepmc")], raw[(q, "pubmed")]
            evidence.append((f"논문 `{q}`",
                             [f"원본 배수 EPMC {e_raw['growth']} / PubMed {p_raw['growth']}",
                              f"`cosmetic`(2.10 / 1.44)으로 보정 → "
                              f"{row['paper_epmc']} / {row['paper_pubmed']}",
                              f"2019 월평균 {e_raw['avg_2019']} / {p_raw['avg_2019']} · "
                              f"배수 사용 가능 {e_raw['ratio_usable']}"],
                             "slopindustries/cosmai-ml · datasets/papers/"))
        evidence.append(("담론 언급 청크 수 — **선크림 문맥이 아니다**",
                         [f"유튜브 {int(num(row['talk_youtube'])):,} · "
                          f"커머스 리뷰 {int(num(row['talk_commerce'])):,}",
                          "유튜브 색인 278,916청크 전체에서 센 값이다. 선크림 영상만이 "
                          "아니라 그 채널의 다른 제품 소개까지 들어 있다"],
                         "reports/chunks_youtube.csv · chunks_commerce.csv"))
        if not evidence:
            continue

        # ---- 한계. 숨기지 않는다 ----
        limits = []
        if PAPER_HOLD:
            limits.append("논문 축을 쓰지 않는다 — 검색어가 화장품을 세지 않는다"
                          "(잔존율 20~48%). **검색어가 없는 게 아니라 우리가 내린 것**이다. "
                          "검증 프로토콜 후 `cross_source.PAPER_HOLD` 로 재개한다")
        elif row["paper_usable"] == "false":
            limits.append("논문 배수를 쓸 수 없다 — 2019 기준선이 월 5편 미만이라 "
                          "연 두세 편 차이가 몇 배로 보인다 (현준님 `ratio_usable=False`)")
        elif row["paper_epmc"] == "":
            limits.append("논문 검색어가 없다 — 이 성분은 연구 동향 축이 비어 있다")
        elif abs(num(row["paper_epmc"]) - num(row["paper_pubmed"])) > PAPER_GAP:
            limits.append(f"두 색인이 {abs(num(row['paper_epmc']) - num(row['paper_pubmed'])):.2f} "
                          f"갈린다 — 논문 추세는 인용하지 않는다")
        # 논문을 안 쓰면 1월 아티팩트는 이 카드와 무관하다
        if PAPER_QUERY.get(name) and not PAPER_HOLD:
            limits.append("PubMed 는 1월이 나머지 달의 1.65~2.40배다(색인 아티팩트). "
                          "여기 배수는 연 단위라 안전하지만 월별로 그리면 봉우리가 선다")
        limits.append("NAVER 성분 지수는 `기준_세럼` 대비 상대값이다. "
                      "절대 검색량이 아니고 요청이 다른 그룹과는 직접 비교할 수 없다")
        if name == "레티날":
            limits.append("성분표에 `레티날` 은 **0건**이다. 08.26 전에는 `레티놀` 을 같이 "
                          "세서 1.2% 로 보였는데 레티놀은 별개 성분이다")
            limits.append("**광민감성 때문에 선케어 배합이 어려운 성분이다.** 검색 287배·"
                          "처방 0% 는 맞지만 그 공백에는 설명이 있다. 우리가 측정한 값이 "
                          "아니라 도메인 지식이므로 규칙에서 빼지 않고 여기 적는다 — "
                          "빼면 누군가 287배를 다시 발견해서 쫓는다")
        if pct > 0:
            limits.append(f"표의 `배합순위 중앙 {row['median_order']}위` 는 성분 등장 "
                          f"**전체**의 중앙이고, 근거로 실린 제품 순번은 **제품별 최선** "
                          f"순번이다. 한 제품이 유도체까지 여러 줄 올리면 두 값이 갈린다")
        if pct > 0 and num(row["median_order"]) == 0:
            limits.append("배합순위가 비어 있다 — 순번을 못 읽은 행이다")
        limits.append("성분표는 올리브영 선케어 카테고리다. 전체 시장이 아니다")
        sun = row.get("talk_youtube_sun")
        if sun not in (None, ""):
            tot = int(num(row["talk_youtube"]))
            limits.append(f"담론 언급 수를 '선크림 담론'으로 읽지 말 것 — 색인 전체에서 "
                          f"센 값이다. **{name} 은 {tot:,}건 중 선크림 단어가 같이 있는 것이 "
                          f"{int(num(sun)):,}건**({100*num(sun)/tot:.1f}%)이다(실측)")
        else:
            limits.append("담론 언급 수를 '선크림 담론'으로 읽지 말 것 — 색인 전체에서 센 값이다")

        strength = (num(row["naver_growth_x"]) if kind in ("선행 연구 기회", "수요 선행 공백", "유행 반증")
                    else pct)
        cards.append({
            "ingredient": name, "card_type": kind, "type_basis": basis,
            "_strength": round(strength, 2),
            "paper_epmc": row["paper_epmc"], "paper_pubmed": row["paper_pubmed"],
            "paper_usable": row["paper_usable"],
            "naver_growth_x": row["naver_growth_x"], "naver_rank": row["naver_rank"],
            "formula_products": row["formula_products"], "formula_pct": row["formula_pct"],
            "median_order": row["median_order"], "high_dose_pct": row["high_dose_pct"],
            "reading": row["reading"],
            "evidence": [{"what": w, "lines": ls, "source": s} for w, ls, s in evidence],
            "limits": limits,
            "decision": "", "decision_reason": "", "next_action": "",
        })

    # 유형이 겹치지 않게 고른다. 같은 유형 카드 3장은 발표에서 한 장과 같다
    # 유형당 한 장만 낸다. 같은 유형 카드 3장은 발표에서 한 장과 같다.
    # **다만 묶인 성분 이름은 카드에 남긴다.** 논문 축이 중지되면서 엑소좀·PDRN·
    # 트라넥삼산이 한 유형으로 합쳐졌는데, 이름을 지우면 "선케어 처방 0인 성분이
    # 셋" 이라는 사실이 사라진다. 대표 한 장 + 나머지 이름이다
    picked, seen = [], {}
    for c in sorted(cards, key=lambda c: -c["_strength"]):
        if c["card_type"] in seen:
            seen[c["card_type"]].append(
                f"{c['ingredient']} (검색 {c['naver_growth_x']}배 · "
                f"처방 {c['formula_pct']}%)")
            continue
        seen[c["card_type"]] = []
        picked.append(c)
    for c in picked:
        c.pop("_strength", None)
        c["same_type_others"] = seen[c["card_type"]]
    return picked


HEADER = """# R&D Opportunity Card — 성분 축

유형은 규칙이 배정했고 모든 수치는 `reports/cross_source_ingredient.csv` 에서
그대로 가져왔다. 여기서 새로 계산한 것은 없다.

**소스를 합산하지 않는다.** 분모가 다르다 — NAVER 는 `기준_세럼` 대비 지수,
성분표는 577제품 대비 채택률이다. 크기가 아니라 **순위와 방향**을 본다.

**논문 축은 중지 상태다**(`cross_source.PAPER_HOLD`). 그래서 논문 칸이 비어 있고
`선행 연구 기회`·`유행 반증` 두 유형은 뜨지 않는다. 검증 프로토콜 후 재개한다.

**유형당 한 장만 낸다.** 같은 유형에 묶인 성분 이름은 카드에 남긴다 — 지우면
"검색은 급증인데 선케어 처방에 없는 성분이 넷" 이라는 사실이 사라진다.
"""


def render(cards: list[dict]) -> str:
    out = [HEADER]
    for i, c in enumerate(cards, 1):
        paper = (f"{c['paper_epmc']} / {c['paper_pubmed']}"
                 if c["paper_epmc"] != "" else "—")
        out += [f"## {i}. {c['ingredient']} — {c['card_type']}", "",
                f"**유형 배정 근거** {c['type_basis']}", "",
                "| | |", "|---|---|",
                f"| 논문 (EPMC / PubMed, `cosmetic` 보정) | {paper} |",
                f"| 논문 배수 사용 가능 | {c['paper_usable'] or '—'} |",
                f"| NAVER 검색 (2016년 대비) | {c['naver_growth_x']}배 · 성분 그룹 {c['naver_rank']}위 |",
                f"| 선케어 처방 | {c['formula_products']}제품 · {c['formula_pct']}% |",
                f"| 배합순위 중앙 | {c['median_order'] or '—'}위 |",
                f"| 고함량 비율 | {c['high_dose_pct']}% |",
                ""]
        if c["reading"]:
            out += [f"**대조표 판독** {c['reading']}", ""]
        if c.get("same_type_others"):
            out += [f"**같은 유형에 묶인 성분** — 이 카드가 대표로 서 있지만 "
                    f"같은 발견이 {len(c['same_type_others'])}건 더 있습니다.", ""]
            out += [f"- {x}" for x in c["same_type_others"]] + [""]
        out += ["**근거**", ""]
        for e in c["evidence"]:
            out += [f"- **{e['what']}** — `{e['source']}`"]
            out += [f"    - {l}" for l in e["lines"]]
        out += ["", "**한계**", ""] + [f"- {x}" for x in c["limits"]] + [""]
        out += ["**검토** accept / watch / reject — 사유와 다음 작업을 여기에 적는다.",
                "", "---", ""]
    return "\n".join(out)


def demo() -> None:
    base = {"naver_index_recent": "1", "naver_rank": "1", "talk_youtube": "0",
            "talk_commerce": "0", "reading": "", "formula_products": "0",
            "median_order": "", "ingredient": "x"}

    # 논문 둘 다 1 초과 + 검색 급증 + 처방 없음 -> 근거 셋. 가장 강한 유형
    r = {**base, "naver_growth_x": "52", "formula_pct": "0.2", "high_dose_pct": "0",
         "paper_epmc": "1.17", "paper_pubmed": "1.33", "paper_usable": "true"}
    assert classify(r)[0] == "선행 연구 기회"

    # 같은 조건인데 논문을 못 쓰면 유형이 내려간다 — 근거 하나가 비었음을 유형에 남긴다
    assert classify({**r, "paper_usable": "false"})[0] == "수요 선행 공백"

    # 검색은 급증인데 논문이 뒷걸음 -> 경고 카드
    assert classify({**r, "paper_epmc": "0.53", "paper_pubmed": "0.46"})[0] == "유행 반증"

    # **처방이 있어도 유행 반증은 잡혀야 한다.** 레티날이 1.2% 라 처방 문턱(1.0)을
    # 넘는데, 이 규칙은 검색과 연구의 어긋남이라 처방과 무관하다
    assert classify({**r, "paper_epmc": "0.53", "paper_pubmed": "0.46",
                     "formula_pct": "1.2"})[0] == "유행 반증"
    # 반대로 검색이 안 늘었으면 논문이 뒤처져도 카드가 아니다 — 어긋남이 없다
    assert classify({**r, "naver_growth_x": "2", "paper_epmc": "0.53",
                     "paper_pubmed": "0.46", "formula_pct": "1.2"}) is None

    # 두 색인이 갈리면(0.37) 선행 연구로 올리지 않는다. 한쪽만 보고 결론 낼 수 없다
    assert classify({**r, "paper_epmc": "1.00", "paper_pubmed": "0.63"})[0] == "수요 선행 공백"

    # 널리 채택했는데 고함량이 없으면 함량 공백
    r2 = {**base, "naver_growth_x": "2.2", "formula_pct": "60", "high_dose_pct": "0",
          "paper_epmc": "1.16", "paper_pubmed": "1.31", "paper_usable": "true"}
    assert classify(r2)[0] == "함량 공백"

    # 널리 쓰고 깊게도 쓰면 기회가 아니라 기준선
    assert classify({**r2, "formula_pct": "69.3", "high_dose_pct": "69"})[0] == "처방 기준선"

    # 아무 데도 안 걸리면 카드로 만들지 않는다
    assert classify({**base, "naver_growth_x": "1.8", "formula_pct": "13.5",
                     "high_dose_pct": "0", "paper_epmc": "", "paper_pubmed": "",
                     "paper_usable": ""}) is None

    # **중앙값 근처를 실어야 한다.** 앞선 것부터 실으면 함량 공백 카드가 자기를 반박한다
    rows = [{"product_name": n, "ingredient": "판테놀", "ingredient_order": str(o)}
            for n, o in [("A", 1), ("B", 20), ("C", 30), ("D", 40), ("E", 50)]]
    got = products_with(rows, ("판테놀",))
    assert any("배합 30순위" in g for g in got), got   # 중앙(C)을 감싸는 창이다
    assert not any(g.startswith("A ") for g in got), got  # 1순위가 대표로 실리면 안 된다
    assert "예외" in got[-1] and "배합 1순위" in got[-1], got   # 극단은 숨기지 않는다

    # 같은 제품에 여러 번 나오면 가장 앞선 순번으로 한 번만 센다
    dup = [{"product_name": "B", "ingredient": "판테놀", "ingredient_order": "4"},
           {"product_name": "B", "ingredient": "판테놀유도체", "ingredient_order": "40"}]
    got1 = products_with(dup, ("판테놀",))
    assert got1 == ["B — 배합 4순위"], got1
    # **제품 수가 limit 이하면 예외 줄을 붙이지 않는다.** 붙이면 "전체 1제품 중
    # 예외다" 처럼 대표와 예외가 같은 제품이 된다 (엑소좀에서 실제로 그랬다)
    assert not any("예외" in g for g in got1), got1
    print("demo ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reports", type=Path, default=Path("reports"))
    p.add_argument("--formula", type=Path,
                   default=Path("data/external/product_ingredient_function_repaired.csv"))
    p.add_argument("--papers", type=Path, default=Path("data/external/paper_growth.csv"))
    p.add_argument("--out", type=Path,
                   default=Path("reports/opportunity_cards_ingredient.md"))
    p.add_argument("--json", type=Path,
                   default=Path("reports/opportunity_cards_ingredient.json"))
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0

    cards = build(a.reports, a.formula, a.papers)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(cards), encoding="utf-8")
    a.json.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"성분 카드 {len(cards)}건")
    for c in cards:
        paper = f"{c['paper_epmc']}/{c['paper_pubmed']}" if c["paper_epmc"] != "" else "—"
        print(f"  {c['ingredient']:<12}{c['card_type']:<12}"
              f"논문 {paper:>12} · 검색 {c['naver_growth_x']:>6}배 · "
              f"처방 {c['formula_pct']:>5}% · 고함량 {c['high_dose_pct']:>5}% · "
              f"근거 {len(c['evidence'])} · 한계 {len(c['limits'])}")
    print(f"\n{a.out}\n{a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
