#!/usr/bin/env python3
"""검색 실행. 수호님 `search_v2.py` 를 받아 두 곳을 고쳤다.

**① `os.chdir` 를 없앴다.** 그의 판은 임포트 시점에 작업 디렉터리를 바꿨다.
`bm25.py` 가 사전을 `seeds/...` 상대경로로 찾기 때문인데, 임포트가 프로세스
전역 상태를 바꾸면 GUI 서버처럼 여러 모듈이 함께 도는 곳에서 조용히 깨진다.
대신 **리포 루트를 인자로 받아 그 안에서만** 상대경로를 쓴다.

**② 근거에 원문 위치를 붙인다.** `doc_id` 만으로는 사람이 못 찾는다.
`chunk_id` → `doc_id` → 소스 → 원문 스니펫까지 같이 낸다. URL 이 아니라
`doc_id` 를 추적 키로 쓰는 것은 팀 합의다 — `product.url` 은 6,083개 중
285개뿐이고 계약상 nullable 이다.

검색 라우팅은 `rag.router` 가 정하고 여기서는 실행만 한다.

    bm25            정확 일치가 정답인 질의
    vector          이름 없는 표현. `df_gate` 로 근거 없는 질의를 먼저 막는다
    multi_source    둘 다 돌려 소스별로 나란히
    temporal_filter `report_date` 메타데이터 필터 (라우터가 직접 처리)

**소스별로 나눠 뽑는 이유.** 색인의 92%가 짧은 유튜브 댓글이라 전역 상위 k 를
쓰면 `mfds` 는 전역 293위, `ingredient` 는 300위 밖으로 밀린다.

사용법:
    python -m rag.engine --demo
    python -m rag.engine --query "판테놀 쓰는 선크림"
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

csv.field_size_limit(10 ** 8)

ROOT = Path(__file__).resolve().parent.parent

# BM25 색인에 넣을 것. 유튜브·커머스는 `common/document.csv` 로 들어온다
BM25_CHUNKS = [Path("reports/chunks_ingredient_mfds.csv")]
# 본문 조회용. 벡터 결과가 유튜브를 가리키므로 여기엔 다 있어야 한다
BODY_CHUNKS = [Path("reports/chunks_ingredient_mfds.csv"),
               Path("reports/chunks_commerce.csv"),
               Path("reports/chunks_youtube.csv")]
VECTORS = Path(".cache/vectors/e5all")
SNIPPET = 240


class Engine:
    """BM25 + 벡터. **리포 루트 안에서만 상대경로를 쓴다** — chdir 하지 않는다."""

    def __init__(self, root: Path = ROOT, vectors: Path | None = None,
                 load_vectors: bool = True):
        self.root = Path(root).resolve()
        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        import bm25
        self.bm25 = bm25

        cwd = Path.cwd()
        try:
            # `bm25.build` 안의 사전 경로가 상대경로다. 이 블록에서만 바꾸고 되돌린다
            import os
            os.chdir(self.root)
            self.index, self.origin = bm25.build(
                Path("common"), None, Path(".cache/bm25"), BM25_CHUNKS)
            self.body: dict[str, str] = {}
            ids, texts, _o = bm25.load_documents(Path("common"), None)
            self.body.update(zip(ids, texts))
            cids, ctexts, corigin = bm25.load_chunks(BODY_CHUNKS)
            self.body.update(zip(cids, ctexts))
            self.full_origin = {**self.origin, **corigin}
            self.vectors = None
            if load_vectors:
                from hybrid import Vectors
                self.vectors = Vectors(vectors or VECTORS)
        finally:
            import os
            os.chdir(cwd)

    # ---- 근거 한 건 ---------------------------------------------------
    def _hit(self, doc_id: str, score: float) -> dict:
        text = self.body.get(doc_id, "")
        return {"doc_id": doc_id,
                "source": self.full_origin.get(doc_id, "?"),
                "score": round(float(score), 4),
                "text": " ".join(text.split())[:SNIPPET],
                "truncated": len(text) > SNIPPET}

    # ---- 검색 ---------------------------------------------------------
    def bm25_search(self, query: str, k: int = 8) -> dict:
        hits = [self._hit(d, s) for d, s in self.index.search(query, k)]
        return {"kind": "bm25", "gated": False, "hits": hits,
                "note": "정확 일치. 점수는 BM25 라 벡터 점수와 비교할 수 없다"}

    def per_source(self, query: str, k: int = 3) -> dict:
        found = self.bm25.by_source(self.index, self.origin, query, k)
        return {"kind": "bm25_per_source", "gated": False,
                "groups": {src: [self._hit(d, s) for d, s in hits]
                           for src, hits in found.items()},
                "note": "소스별 상위 k. 전역 상위 k 는 짧은 댓글이 독점한다"}

    def vector_search(self, query: str, k: int = 8) -> dict:
        """**`gated` 와 `unavailable` 을 섞지 않는다.**

        둘 다 "결과 0건" 이지만 뜻이 정반대다.

            gated       질의 토큰이 코퍼스에 없다 — **판단**이다. 근거가 없는 게 맞다
            unavailable 벡터를 안 올렸다 — **운영 상태**다. 근거가 없는지는 알 수 없다

        섞으면 `백탁이 심해요`(df 338)에 "근거 없음" 이라고 거짓을 말한다.
        """
        from vector_threshold import df_gate
        ok, why = df_gate(query, self.index)
        if not ok:
            return {"kind": "vector", "gated": True, "unavailable": False,
                    "hits": [], "reason": why,
                    "note": "질의 토큰이 색인에 없다. 코사인이 나와도 근거가 아니다"}
        if self.vectors is None:
            return {"kind": "vector", "gated": False, "unavailable": True,
                    "hits": [], "reason": why,
                    "note": "벡터를 안 올렸다 — `--vectors` 로 켜야 이 질의를 푼다. "
                            "**근거가 없는 게 아니라 못 찾은 것이다**"}
        hits = [self._hit(d, s) for d, s in self.vectors.search(query, k)]
        return {"kind": "vector", "gated": False, "unavailable": False, "hits": hits,
                "reason": why,
                "note": "heldout Hit@10 13% — 열 번 물어 아홉 번은 못 찾는다"}

    def token_df(self, query: str) -> list[dict]:
        """질의 토큰별 코퍼스 등장 문서 수.

        **"조심해라" 보다 이게 강하다** (수호님 판단, 맞다). `크소나이드: 0건` 같은
        확인 가능한 사실을 주면 LLM 이 스스로 판단한다.
        """
        toks = sorted(set(self.bm25.tokenize_query(query)))
        return [{"token": t, "df": len(self.index.postings.get(t, ()))} for t in toks]

    # ---- 라우팅까지 한 번에 -------------------------------------------
    def answer_context(self, query: str, router, k: int = 8) -> dict:
        """라우팅 + 검색 + 근거를 한 덩어리로. GUI·LLM 이 이걸 받는다."""
        d = router.classify(query)
        out: dict = {"query": query, "route": d.route, "reason": d.reason,
                     "matched": {"ingredients": d.ingredients, "brands": d.brands,
                                 "reg_no": d.reg_no, "spf": d.spf},
                     "token_df": self.token_df(query)}
        if d.route == "temporal_filter":
            t = router.temporal(d, k)
            out["temporal"] = t
            out["evidence"] = [
                {"doc_id": f"MFDS:{r.get('COSMETIC_REPORT_SEQ','?')}",
                 "source": "mfds", "score": None,
                 "text": f"{r.get('ITEM_NAME','')} · {r.get('ENTP_NAME','')} · "
                         f"{str(r.get('report_date',''))[:10]}", "truncated": False}
                for r in t["results"]]
            out["note"] = ("최근 N일에 등록된 목록이다. **트렌드 상승이 아니다.** "
                           "품목명 문자열 포함 여부만 본 얕은 매칭이다")
        elif d.route == "bm25":
            r = self.bm25_search(query, k)
            out["evidence"] = r["hits"]
            out["note"] = r["note"]
        elif d.route == "multi_source":
            r = self.per_source(query, max(2, k // 4))
            out["groups"] = r["groups"]
            out["evidence"] = [h for hits in r["groups"].values() for h in hits]
            v = self.vector_search(query, k)
            out["vector"] = v
            if not v["gated"] and not v.get("unavailable"):
                out["evidence"] += v["hits"]
            out["note"] = ("정확 신호와 자연어 신호가 같이 있어 둘 다 돌렸다. "
                           "**소스별 점수를 비교하지 말 것** — 척도가 다르다")
        else:
            v = self.vector_search(query, k)
            out["evidence"] = v["hits"]
            out["gated"] = v["gated"]
            out["unavailable"] = v.get("unavailable", False)
            out["gate_reason"] = v.get("reason", "")
            out["note"] = v["note"]
        out["evidence_count"] = len(out.get("evidence", []))
        return out


def demo() -> None:
    """벡터 없이 로직만 점검한다. 벡터는 900MB 라 데모에서 안 올린다."""
    eng = Engine(load_vectors=False)
    from rag.router import Router
    r = Router()

    a = eng.answer_context("보고번호 2018008612", r, k=3)
    assert a["route"] == "bm25", a["route"]
    assert a["evidence_count"] > 0, a
    assert a["evidence"][0]["doc_id"].startswith("MFDS:"), a["evidence"][0]

    b = eng.answer_context("최근에 나온 무기자차 선크림", r, k=3)
    assert b["route"] == "temporal_filter" and b["evidence_count"] > 0
    assert "트렌드 상승이 아니다" in b["note"]

    c = eng.answer_context("판테놀 쓰는 선크림", r, k=8)
    assert c["route"] == "multi_source" and "groups" in c

    # 없는 성분은 df 가 0 이라 게이트가 막는다
    d = eng.answer_context("크소나이드 함유 제품 있어", r, k=3)
    dfs = {t["token"]: t["df"] for t in d["token_df"]}
    assert any(v == 0 for v in dfs.values()), dfs
    # **문장 속에 섞인 가짜 이름을 막는다** — 08.26 에 `df_gate` 를 강화한 자리다.
    # 그전에는 `제품`(df 30,061)·`함유`(454)가 있어서 통과했다(수호님 §8-1 미결)
    assert d["gated"] is True and d["unavailable"] is False, d
    assert "없는 이름이 섞여" in d["gate_reason"], d["gate_reason"]

    # **있는 말인데 벡터를 안 올린 경우는 `gated` 가 아니다.** 섞으면 거짓을 말한다
    e = eng.answer_context("백탁이 심해요", r, k=3)
    assert e["gated"] is False, "df 338 인데 gated 면 안 된다"
    assert e["unavailable"] is True, "벡터를 안 올렸으면 unavailable 이다"
    assert "못 찾은 것" in e["note"], e["note"]
    print(f"demo ok — 색인 {eng.index.n:,}문서 · 본문 {len(eng.body):,}건 · "
          f"라우팅 4종 확인")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--query")
    p.add_argument("--k", type=int, default=6)
    p.add_argument("--no-vectors", action="store_true")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo or not a.query:
        demo()
        return 0
    from rag.router import Router
    eng = Engine(load_vectors=not a.no_vectors)
    ctx = eng.answer_context(a.query, Router(), a.k)
    print(f"[{ctx['route']}] {a.query}")
    print(f"  {ctx['reason']}")
    print(f"  근거 {ctx['evidence_count']}건 · {ctx['note']}")
    if ctx.get("gated"):
        print(f"  [차단] {ctx['gate_reason']}")
    for h in ctx.get("evidence", [])[:8]:
        sc = f"{h['score']:.3f}" if h["score"] is not None else "   —"
        print(f"    {sc}  [{h['source']}] {h['doc_id'][:30]:<30} {h['text'][:60]}")
    zero = [t["token"] for t in ctx["token_df"] if t["df"] == 0]
    if zero:
        print(f"  [주의] 코퍼스에 없는 토큰: {zero}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
