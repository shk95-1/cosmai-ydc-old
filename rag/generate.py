#!/usr/bin/env python3
"""LLM 답변 생성. 수호님 `generate.py` 의 프롬프트를 받아 다듬었다.

**LLM 은 결론을 만들지 않는다.** 규칙이 후보와 수치를 정하고, 검색이 근거를 찾고,
LLM 은 그 근거를 문장으로 묶는 마지막 층이다. 그래서 이 파일에는 판단이 없다 —
프롬프트와 호출만 있다.

**키가 없어도 쓸모가 있다.** 키 없이 돌리면 조립된 프롬프트와 근거를 그대로 낸다.
GUI 는 그것만으로도 동작한다 — 사람이 근거를 직접 읽는 게 이 프로젝트의 기본이다.

수호님 판단 중 가장 좋았던 것: **`조심해라` 대신 `크소나이드: 0건` 을 준다.**
두루뭉술한 지시보다 확인 가능한 사실이 훨씬 강하게 작동하고, 실제 호출로
"제공된 데이터로는 답할 수 없습니다" 를 받아 내셨다. 그걸 그대로 유지했다.

사용법:
    python -m rag.generate --demo
    python -m rag.generate --query "판테놀 쓰는 선크림"      # 키 없으면 프롬프트만
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1200

SYSTEM = """당신은 화장품 트렌드·성분 데이터 어시스턴트입니다. 아래를 반드시 지키세요.

1. **제공된 근거에 있는 내용만** 답하세요. 근거에 없는 사실을 추측하거나 만들지 마세요.
2. 모든 사실 주장 뒤에 `[출처: doc_id]` 를 붙이세요.
3. 근거가 부족하면 "제공된 데이터로는 답할 수 없습니다" 라고 명시하세요. 억지로 답하지 마세요.
4. 근거가 여러 소스에서 왔으면 **섞어서 결론 내지 말고 소스별로 구분**해 제시하세요.
   BM25 점수와 벡터 코사인은 척도가 달라 비교할 수 없습니다 — 점수 수치를 순위 근거로
   언급하지 마세요.
5. 식약처(mfds) 데이터는 **"등록·보고됨" 사실만** 말하세요. 효과나 안전성을 보증하는
   것처럼 말하지 마세요. 보고는 효과 입증이 아닙니다.
6. 성분과 소비자 반응 사이의 **인과를 단정하지 마세요.** "~라는 언급이 있었다" 로만
   서술하세요.
7. 시점 필터(`temporal_filter`) 결과는 "최근 N일에 등록된 목록" 이지 **"트렌드가
   상승했다" 가 아닙니다.** 판정을 만들지 마세요.
8. 벡터 검색은 `heldout Hit@10 13%` 로 **열 번 물어 아홉 번은 놓칩니다.** 질의와
   무관해도 코사인이 높게 나올 수 있습니다(e5 의 알려진 한계). 그래서 아래
   **"질의 토큰별 코퍼스 등장 문서 수(df)"** 를 먼저 확인하세요.
   - 핵심 명사(성분명·고유명사)의 df 가 0 이면 그 단어는 **코퍼스에 전혀 없습니다.**
     검색 결과가 나왔어도 그 단어와 무관하게 우연히 벡터가 가까운 문서일 뿐입니다.
   - 그 경우 결과 텍스트를 실제로 읽고 질의의 핵심 개념과 관련이 있는지 직접
     판단하세요. 없으면 "제공된 데이터로는 답할 수 없습니다" 라고 답하고, **df 가 0 인
     단어가 있다는 사실 자체도 답변에 쓰세요.**
9. 이 데이터로 **미래를 예측하지 마세요.** 후향 검증에서 상승 지속 적중률이 22%,
   기저율이 47% 였습니다. "지금 이런 비대칭이 있다" 까지만 말하세요.
10. 논문·연구 동향은 **쓰지 마세요.** 검색어가 화장품을 세지 않아 축 전체를 중지했습니다.
"""


def build_prompt(ctx: dict) -> str:
    """검색 문맥을 프롬프트로 묶는다. **여기서 판단하지 않는다.**"""
    lines = [f"질문: {ctx['query']}", "",
             f"라우팅: {ctx['route']}", f"라우팅 근거: {ctx['reason']}", ""]

    if ctx.get("gated"):
        lines += ["근거: 없음",
                  f"차단 사유: {ctx.get('gate_reason','')}",
                  "", "규칙 3 에 따라 답할 수 없다고 답하세요."]
        return "\n".join(lines)

    groups = ctx.get("groups")
    if groups:
        lines.append("근거 (소스별):")
        for src, hits in groups.items():
            if not hits:
                continue
            lines.append(f"  [{src}]")
            for h in hits:
                lines.append(f"    - [{h['doc_id']}] {h['text']}")
        v = ctx.get("vector") or {}
        if v.get("hits"):
            lines.append("  [벡터 검색 — 의미 유사]")
            for h in v["hits"]:
                lines.append(f"    - [{h['doc_id']}] ({h['source']}) {h['text']}")
    else:
        ev = ctx.get("evidence") or []
        lines.append(f"근거 {len(ev)}건:" if ev else "근거: 없음")
        for h in ev:
            src = f"({h['source']}) " if h.get("source") else ""
            lines.append(f"  - [{h['doc_id']}] {src}{h['text']}")

    if ctx["route"] == "temporal_filter":
        t = ctx.get("temporal") or {}
        lines += ["", f"기간: {t.get('window','?')} · 창 안 전체 "
                      f"{t.get('n_total_in_window',0)}건"]
        if t.get("narrowed_by"):
            lines.append(f"품목명 문자열로 좁힌 항목: {t['narrowed_by']} "
                         f"(성분표 조인이 아니라 얕은 매칭)")

    df = ctx.get("token_df") or []
    if df:
        lines += ["", "질의 토큰별 코퍼스 등장 문서 수:"]
        for t in df:
            flag = "   ← 코퍼스에 전혀 없음" if t["df"] == 0 else ""
            lines.append(f"  {t['token']}: {t['df']:,}건{flag}")

    if ctx.get("note"):
        lines += ["", f"이 결과의 한계: {ctx['note']}"]
    if not ctx.get("evidence"):
        lines += ["", "주의: 근거가 비어 있습니다. 규칙 3 을 적용하세요."]
    return "\n".join(lines)


def api_key() -> str | None:
    """환경변수 우선, 없으면 `.env`. **값을 로그에 찍지 않는다.**"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'") or None
    return None


def generate(ctx: dict, key: str | None = None, model: str = MODEL) -> dict:
    """근거가 0 이면 LLM 을 부르지 않는다 — 규칙 3 을 코드가 먼저 적용한다."""
    prompt = build_prompt(ctx)
    out = {"prompt": prompt, "answer": "", "executed": False, "note": "",
           "model": model, "citations": [h["doc_id"] for h in ctx.get("evidence", [])]}

    if not ctx.get("evidence"):
        out["answer"] = "제공된 데이터로는 답할 수 없습니다. 관련 근거를 찾지 못했습니다."
        out["executed"] = True
        out["note"] = "근거 0건 — LLM 호출 없이 규칙 3 을 코드가 적용했다"
        return out

    key = key or api_key()
    if not key:
        out["note"] = ("ANTHROPIC_API_KEY 가 없다. 프롬프트와 근거만 낸다 — "
                       "**사람이 근거를 직접 읽는 것이 이 프로젝트의 기본이다.**")
        return out
    try:
        import anthropic
    except ImportError:
        out["note"] = "anthropic 패키지가 없다. `pip install anthropic` 후 다시."
        return out

    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(model=model, max_tokens=MAX_TOKENS, system=SYSTEM,
                                 messages=[{"role": "user", "content": prompt}])
    out["answer"] = msg.content[0].text
    out["executed"] = True
    return out


def demo() -> None:
    # 프롬프트 조립만 점검한다. LLM 도 벡터도 안 부른다
    gated = {"query": "크소나이드 함유 제품", "route": "vector", "reason": "r",
             "gated": True, "gate_reason": "질의 토큰이 색인에 없다 ['크소나이드']",
             "evidence": [], "token_df": [{"token": "크소나이드", "df": 0}]}
    p = build_prompt(gated)
    assert "근거: 없음" in p and "규칙 3" in p, p
    g = generate(gated, key="ignored-근거가-0이라-안-부른다")
    assert g["executed"] and "답할 수 없습니다" in g["answer"], g
    assert "규칙 3 을 코드가 적용" in g["note"]

    multi = {"query": "판테놀 쓰는 선크림", "route": "multi_source", "reason": "r",
             "groups": {"ingredient": [{"doc_id": "ING:판테놀#0", "source": "ingredient",
                                        "score": 1.0, "text": "성분명 판테놀"}],
                        "commerce_review": []},
             "vector": {"hits": [{"doc_id": "yc:1#0", "source": "youtube_comment",
                                  "score": 0.9, "text": "판테놀 좋아요"}]},
             "evidence": [{"doc_id": "ING:판테놀#0", "source": "ingredient",
                           "score": 1.0, "text": "성분명 판테놀"}],
             "token_df": [{"token": "판테놀", "df": 1557}],
             "note": "소스별 점수를 비교하지 말 것"}
    p2 = build_prompt(multi)
    assert "[ingredient]" in p2 and "벡터 검색" in p2, p2
    assert "1,557건" in p2, p2
    # 근거가 있고 키가 없으면 프롬프트만 낸다
    g2 = generate(multi, key=None)
    assert not g2["executed"] and "직접 읽는 것" in g2["note"], g2

    # 시스템 프롬프트에 우리 원칙이 다 들어 있어야 한다
    for must in ("doc_id", "Hit@10 13%", "22%", "논문", "인과", "섞어서"):
        assert must in SYSTEM, must
    print("demo ok — 프롬프트 조립 3종 · 시스템 프롬프트 규칙 10개")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--query")
    p.add_argument("--k", type=int, default=6)
    p.add_argument("--no-vectors", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo or not a.query:
        demo()
        return 0
    from rag.engine import Engine
    from rag.router import Router
    ctx = Engine(load_vectors=not a.no_vectors).answer_context(a.query, Router(), a.k)
    res = generate(ctx)
    if a.json:
        print(json.dumps({"context": ctx, **res}, ensure_ascii=False, indent=2))
        return 0
    print(f"[{ctx['route']}] 근거 {ctx['evidence_count']}건")
    print()
    print(res["answer"] or res["prompt"])
    if res["note"]:
        print()
        print(f"({res['note']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
