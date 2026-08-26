#!/usr/bin/env python3
"""질의 라우팅. **LLM 을 안 쓴다** — 규칙이라 결정적이고 왜 그렇게 갔는지 항상 말할 수 있다.

수호님 `router.py` 를 받아 세 곳을 고쳤다.

**① 성분명 목록을 토크나이저 사전에서 성분표로 바꿨다.**
`seeds/ingredient_dictionary.tsv` 는 **Kiwi 토크나이저 사전**이고 담론어가 일부러
들어 있다(`선크림`·`백탁`·`톤업`). 그걸 "성분명 목록" 으로 쓰면 자연어 질의가 전부
BM25 로 간다. 실측으로 **자연어 10개 중 7개가 오라우팅**됐다.

    선크림 루틴 알려줘        -> ['선크림','루틴']  -> bm25   (벡터로 가야 한다)
    백탁 관련해서 소비자들이     -> ['백탁']         -> bm25
    끈적이지 않는 선크림 추천    -> ['선크림']        -> bm25

정본은 성분표(`data/external/product_ingredient_function_repaired.csv`)의
`ingredient` 컬럼이다. 거기서 **주제 별칭을 빼고** 마커(`*`·`+`)를 정리해 1,851종.

**② `multi_source` 를 실제로 만든다.** 수호님 독스트링이 규칙 7 로 약속했는데
코드는 안 만들고 있었다(`force_multi_source` 로 손으로 켜야 했다). 그래서 그의
검증 케이스 "백탁 관련해서 소비자들이" 가 라우터를 우회했고, 위 오라우팅이
테스트에 안 걸렸다.

정확 신호와 자연어 신호가 **같이** 있으면 둘 다 돌려 나란히 놓는다. 이진 라우팅으로는
`콜라겐 들어간 제품 뭐가 좋아` 를 못 푼다 — `콜라겐` 은 진짜 성분이면서 담론어다.
길이나 빈도로 갈라 보려 했는데 안 갈렸다(콜라겐 담론/제품 비율 281, 판테놀 7).
**갈라지지 않으면 고르지 말고 둘 다 낸다.** 소스를 합산하지 않는 것과 같은 논리다.

**③ pandas 를 걷어냈다.** CSV 두 개 읽는 데 필요 없다. 우리 리포는 `csv` 만 쓴다.

사용법:
    python -m rag.router --demo
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

csv.field_size_limit(10 ** 8)

HERE = Path(__file__).resolve().parent

REG_NO = re.compile(r"(?<!\d)\d{10}(?!\d)")
SPF_PA = re.compile(r"SPF\s*\d{1,3}\+?|PA\s*\+{1,4}", re.IGNORECASE)

# 시점 표현. 텍스트 검색이 아니라 `report_date` 메타데이터 필터로 간다 —
# 어떤 검색기로도 "최근" 을 못 푼다(수호님 판단, 맞다)
TEMPORAL = {
    "이번 달": 30, "최신": 90, "신상": 90,
    "최근": 180, "요즘": 180, "요새": 180, "근래": 180,
    "신제품": 180, "새로 나온": 180, "올해": 365,
}

# 자연어로 볼 최소 길이. 서술어가 없어도 이만큼 길면 문장으로 본다
NATURAL_CHARS = 14


@dataclass
class Route:
    query: str
    route: str                       # bm25 | vector | multi_source | temporal_filter
    ingredients: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    reg_no: list[str] = field(default_factory=list)
    spf: list[str] = field(default_factory=list)
    window_days: int | None = None
    residual: str = ""
    natural: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {**self.__dict__}


def _load(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"{path} 가 없다. `python -m rag.build_lexicon` 로 만든다")
    return json.loads(path.read_text(encoding="utf-8"))


class Router:
    """규칙 라우터. 사전은 한 번만 읽고 길이 내림차순으로 훑는다."""

    def __init__(self, lexicon: Path = HERE):
        self.ingredients = sorted(_load(lexicon / "ingredients.json"),
                                  key=len, reverse=True)
        self.brands = sorted(_load(lexicon / "brands.json"), key=len, reverse=True)
        self._kiwi = None

    # ---- 자연어 판정 -------------------------------------------------
    def is_natural(self, query: str) -> bool:
        """서술어 어미가 있으면 문장이다. Kiwi 가 판정한다 — 손 규칙으로 안 한다.

        `백탁이 심해요` 는 12자인데 문장이고 `에칠헥실트리아존` 은 9자인데 낱말이다.
        길이만으로는 안 갈린다.
        """
        if self._kiwi is None:
            import bm25
            self._kiwi = bm25.kiwi()
        tags = {t.tag.split("-")[0] for t in self._kiwi.tokenize(query)}
        if tags & {"VA", "VV", "EF", "EC", "VCP", "VCN"}:
            return True
        return len(query) >= NATURAL_CHARS

    # ---- 사전 매칭 ---------------------------------------------------
    @staticmethod
    def _find(query: str, vocab: list[str]) -> list[str]:
        """긴 이름부터 찾고 찾은 자리는 지운다. 안 지우면 부분문자열이 겹쳐 센다."""
        found, rest = [], query
        for term in vocab:
            if term in rest:
                found.append(term)
                rest = rest.replace(term, " ")
        return found

    # ---- 라우팅 ------------------------------------------------------
    def classify(self, query: str) -> Route:
        reg = REG_NO.findall(query)
        spf = SPF_PA.findall(query)
        ing = self._find(query, self.ingredients)
        brand = self._find(query, self.brands)
        natural = self.is_natural(query)
        exact = bool(reg or spf or ing or brand)

        hit = next((k for k in sorted(TEMPORAL, key=len, reverse=True) if k in query), None)
        if hit:
            return Route(query=query, route="temporal_filter",
                         ingredients=ing, brands=brand, reg_no=reg, spf=spf,
                         window_days=TEMPORAL[hit],
                         residual=query.replace(hit, "").strip(),
                         natural=natural,
                         reason=f"시점 표현 `{hit}` — 텍스트 검색이 아니라 report_date "
                                f"기준 최근 {TEMPORAL[hit]}일 필터다. 어떤 검색기로도 "
                                f"이 유형은 못 푼다")

        parts = []
        if reg:
            parts.append(f"등록번호 {reg}")
        if spf:
            parts.append(f"SPF/PA {spf}")
        if ing:
            parts.append(f"성분명 {ing}")
        if brand:
            parts.append(f"브랜드 {brand}")

        # **등록번호·SPF 는 자연어 여지가 없다.** 10자리 보고번호는 유일 식별자고
        # `SPF50 PA++++` 는 표기 그대로 찾는 것이다. 길이가 길어도 조회 질의다 —
        # 이걸 안 걸면 `보고번호 2018008612`(17자)가 길이 규칙에 걸려 multi_source 로 간다
        unique_id = bool(reg or spf)
        if exact and natural and not unique_id:
            return Route(query=query, route="multi_source",
                         ingredients=ing, brands=brand, reg_no=reg, spf=spf,
                         natural=True,
                         reason="정확 신호(" + ", ".join(parts) + ")와 자연어 신호가 "
                                "같이 있다 — **둘 다 돌려 소스별로 나란히 놓는다.** "
                                "하나를 고르면 반드시 한쪽을 잃는다")
        if exact:
            return Route(query=query, route="bm25",
                         ingredients=ing, brands=brand, reg_no=reg, spf=spf,
                         natural=False,
                         reason="정확 일치가 정답인 질의: " + ", ".join(parts) +
                                " — BM25 (literal P@10 0.841)")
        return Route(query=query, route="vector", natural=natural,
                     reason="정확 신호가 없다 — 이름 없는 표현으로 본다. 벡터로 간다 "
                            "(heldout 에서 BM25 는 0.000, 벡터만 0.038)")

    # ---- 시점 필터 ---------------------------------------------------
    def temporal(self, decision: Route, k: int = 8,
                 items: Path = HERE / "mfds_items.csv") -> dict:
        """`report_date` 메타데이터 필터. 텍스트 검색이 아니다.

        **결과를 "트렌드 상승" 으로 읽으면 안 된다.** 최근 N일에 등록된 목록일 뿐이다.
        """
        rows = []
        with items.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                d = (row.get("report_date") or "")[:10]
                if len(d) == 10:
                    rows.append((d, row))
        if not rows:
            return {"window": "(데이터 없음)", "n_total_in_window": 0, "results": []}
        newest = max(d for d, _r in rows)
        y, m, dd = (int(x) for x in newest.split("-"))
        cutoff = (date(y, m, dd) - timedelta(days=decision.window_days or 180)).isoformat()
        picked = sorted((r for d, r in rows if d >= cutoff),
                        key=lambda r: r["report_date"], reverse=True)

        # 시점 표현을 뗀 나머지에 성분·브랜드가 있으면 품목명으로 좁힌다.
        # **품목명 문자열 포함 여부만 본다** — 성분표 조인이 아니라 얕은 매칭이다
        sub = self.classify(decision.residual) if decision.residual else None
        terms = [t for t in ((sub.ingredients + sub.brands) if sub else [])]
        if terms:
            narrowed = [r for r in picked
                        if any(t in (r.get("ITEM_NAME") or "") for t in terms)]
            if narrowed:
                picked = narrowed
        return {"window": f"{cutoff} ~ {newest} (최근 {decision.window_days}일)",
                "n_total_in_window": len(picked),
                "narrowed_by": terms,
                "results": picked[:k]}


def demo() -> None:
    r = Router()
    cases = [
        ("에칠헥실트리아존", "bm25"),
        ("보고번호 2018008612", "bm25"),
        ("SPF50 PA++++ 제품", "bm25"),
        ("보고번호 2018008612 이거 언제 등록된 품목이야", "bm25"),
        ("판테놀", "bm25"),
        ("하얗게 뜨는 거 없는 자외선 차단제", "vector"),
        ("눈이 시리고 따가워요", "vector"),
        ("백탁 관련해서 소비자들이 뭐라고 해", "vector"),
        ("끈적이지 않는 선크림 추천", "vector"),
        ("백탁이 심해요", "vector"),
        ("판테놀 쓰는 선크림", "multi_source"),
        ("콜라겐 들어간 제품 뭐가 좋아", "multi_source"),
        ("최근에 나온 무기자차 선크림", "temporal_filter"),
        ("요즘 나이아신아마이드 들어간 신제품", "temporal_filter"),
    ]
    wrong = []
    for q, want in cases:
        got = r.classify(q)
        if got.route != want:
            wrong.append((q, want, got.route))
    assert not wrong, wrong

    # **자연어 판정이 길이가 아니라 서술어로 간다는 것** — 이게 핵심이다
    assert r.is_natural("백탁이 심해요"), "서술어가 있으면 문장이다"
    assert not r.is_natural("에칠헥실트리아존"), "긴 낱말은 문장이 아니다"

    # 유일 식별자가 있으면 문장이어도 조회다. 안 걸면 길이 규칙에 걸려 multi_source 로 간다
    d = r.classify("보고번호 2018008612 이거 언제 등록된 품목이야")
    assert d.route == "bm25" and d.natural is False, (d.route, d.natural)

    # 성분명 목록에 담론어가 섞이면 안 된다. 섞이면 자연어가 전부 bm25 로 간다
    for word in ("선크림", "백탁", "톤업", "썬크림"):
        assert word not in r.ingredients, f"{word} 는 담론어다. 성분명 목록에 있으면 안 된다"

    # 시점 필터는 목록만 낸다
    t = r.temporal(r.classify("최근에 나온 무기자차 선크림"), k=3)
    assert t["n_total_in_window"] > 0 and len(t["results"]) <= 3, t["n_total_in_window"]
    print(f"demo ok — 라우팅 {len(cases)}건 · 성분명 {len(r.ingredients):,}종 · "
          f"브랜드 {len(r.brands):,}개 · 시점 창 {t['window']}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", nargs="?")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo or not a.query:
        demo()
        return 0
    d = Router().classify(a.query)
    print(f"[{d.route}] {a.query}")
    print(f"  {d.reason}")
    if d.route == "temporal_filter":
        print(f"  잔여 질의 {d.residual!r} · 창 {d.window_days}일")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
