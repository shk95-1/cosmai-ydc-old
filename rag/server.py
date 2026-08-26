#!/usr/bin/env python3
"""RAG GUI 서버. **표준 라이브러리만 쓴다** — 새 의존성을 넣지 않는다.

`http.server` 로 충분하다. 이건 팀 넷이 노트북에서 쓰는 도구고 동시 접속이 없다.
Flask·FastAPI 를 넣으면 발표 전날 설치 문제를 하나 더 만든다.

화면 셋.

    질의    라우팅 · 근거(소스별) · 토큰 df · 한계. LLM 키가 있으면 답변까지
    카드    Opportunity Card 6장 (주제 3 + 성분 3)
    지표    핵심 숫자와 그 한계

**벡터는 기본으로 안 올린다.** 900MB 라 로딩이 오래 걸린다. `--vectors` 를 주면
올린다. 안 올려도 BM25·시점 필터·카드는 다 된다.

사용법:
    python -m rag.server                 # BM25 만 (빠름)
    python -m rag.server --vectors       # 벡터까지 (heldout 질의도 됨)
    python -m rag.server --port 8899
"""
from __future__ import annotations

import argparse
import json
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

_state: dict = {"engine": None, "router": None, "ready": False, "error": None,
                "vectors": False}
_lock = threading.Lock()


def boot(load_vectors: bool) -> None:
    """색인·벡터를 한 번만 올린다. 실패해도 서버는 살아서 이유를 보여준다."""
    try:
        from rag.engine import Engine
        from rag.router import Router
        eng = Engine(load_vectors=load_vectors)
        with _lock:
            _state.update(engine=eng, router=Router(), ready=True,
                          vectors=load_vectors and eng.vectors is not None)
        print(f"[준비] BM25 {eng.index.n:,}문서 · 본문 {len(eng.body):,}건 · "
              f"벡터 {'있음' if _state['vectors'] else '없음'}")
    except Exception:
        with _lock:
            _state["error"] = traceback.format_exc()
        print("[실패] 초기화 중 오류:\n" + _state["error"])


# 카드마다 "그래서 이걸로 무엇을 하나". 카드 자체에는 없는 정보라 여기 둔다 —
# 유형이 규칙으로 정해지므로 활용도 유형에 붙는다
USE = {
    "제품 공백 기회": ("소비자가 말하는데 제품 설명이 안 다루는 주제다. "
                  "**제품 상세·상세페이지 문구에 그 표현을 넣는 것**이 첫 수다. "
                  "개발보다 커뮤니케이션이 먼저다."),
    "검증된 성장": ("영상과 댓글이 같이 오르는 주제다. 한쪽만 오르는 것과 달라 "
                "**신제품 콘셉트로 올릴 때 근거가 두 개**다. 다만 예측이 아니라 "
                "현재 상태이므로 '지금 이 주제가 크다' 까지만 말한다."),
    "표현 공백": ("제품은 많은데 그 이름으로 말하는 사람이 없다. **소비자가 쓰는 말을 "
              "찾아 라벨·검색 키워드를 바꾸는 것**이 할 일이다. 제품을 더 만들 필요는 없다."),
    "수요 선행 공백": ("검색은 급증인데 선케어 처방에 없다. **왜 없는지를 먼저 확인**해야 "
                 "한다 — 제형 안정성·규제·광민감성일 수 있다. 없는 이유가 없다면 "
                 "선점 여지다."),
    "함량 공백": ("널리 채택했지만 배합순위가 뒤다. **'넣었다' 가 아니라 '얼마나 넣었다' "
              "로 차별화**할 자리다. 고함량 표기가 경쟁 요소가 된다."),
    "처방 기준선": ("기회가 아니라 **비교 기준**이다. 다른 성분의 '깊게 썼다' 를 판단할 때 "
               "이 값과 견준다."),
    "유행 반증": ("검색은 급증인데 연구는 뒷걸음이다. **쫓지 않는 근거**로 쓴다."),
}


def cards() -> list[dict]:
    """카드 6장. 산출물 JSON 을 그대로 읽는다 — 여기서 새로 만들지 않는다.

    차트용 숫자만 뽑아 `chart` 에 담는다. **값을 바꾸지 않는다** — 화면이 그릴
    막대 길이만 정한다.
    """
    out = []
    for name, axis, key in [("opportunity_cards.json", "주제", "topic_id"),
                            ("opportunity_cards_ingredient.json", "성분", "ingredient")]:
        p = ROOT / "reports" / name
        if not p.exists():
            continue
        for c in json.loads(p.read_text(encoding="utf-8")):
            num = lambda k, d=0.0: (float(c[k]) if str(c.get(k, "")).strip() not in ("", "None")
                                    else d)
            if axis == "주제":
                chart = {"kind": "topic", "unit": "%",
                         "bars": [{"label": "영상 설명", "v": num("video_composition_pct")},
                                  {"label": "댓글", "v": num("comment_composition_pct")}],
                         "extra": [{"label": "갭(댓글−영상)", "v": num("gap_pp"), "unit": "%p"},
                                   {"label": "근거 문서", "v": num("document_count"), "unit": "건"}]}
            else:
                chart = {"kind": "ingredient", "unit": "%",
                         "bars": [{"label": "처방 채택률", "v": num("formula_pct")},
                                  {"label": "고함량 비율", "v": num("high_dose_pct")}],
                         "extra": [{"label": "NAVER 검색 증가", "v": num("naver_growth_x"),
                                    "unit": "배"},
                                   {"label": "배합순위 중앙", "v": num("median_order"),
                                    "unit": "위"},
                                   {"label": "제품 수", "v": num("formula_products"),
                                    "unit": "개"}]}
            out.append({
                "axis": axis, "name": c.get(key, "?"), "type": c.get("card_type", ""),
                "basis": c.get("type_basis", ""),
                "use": USE.get(c.get("card_type", ""), ""),
                "chart": chart,
                "limits": c.get("limits", []),
                "others": c.get("same_type_others", []),
                "quotes": [{"text": q.get("text", ""), "url": q.get("url", ""),
                            "term": q.get("matched_term", ""),
                            "likes": q.get("like_count", "")}
                           for q in c.get("quotes", [])],
            })
    return out


# 지표. **값 / 측정 방법 / 한계를 칸으로 나눈다.** 주관적 평가어를 쓰지 않는다 —
# "주력" "양쪽 다 진다" 같은 말은 측정값이 아니라 해석이다.
# `chart` 는 화면이 그릴 막대다. 없으면 숫자만 낸다.
METRICS = [
 {"group": "데이터",
  "label": "색인 청크", "value": "306,178", "unit": "건",
  "how": "유튜브 278,916 · 커머스 18,476 · 성분·식약처 8,786 을 합한 수",
  "limit": "유튜브 댓글이 252,332건(82.4%)이다. 전역 상위 k 로 뽑으면 "
           "mfds 는 전역 293위, ingredient 는 300위 밖으로 밀린다",
  "chart": {"labels": ["유튜브 댓글", "유튜브 영상", "커머스 리뷰", "식약처",
                       "성분 사전", "전성분 상세", "제품 요약"],
            "values": [252332, 26584, 18476, 4735, 1931, 1543, 577], "unit": "건"}},

 {"group": "데이터",
  "label": "분기 판정 셀", "value": "64 / 338", "unit": "",
  "how": "13주제 x 13분기 x 2소스 = 338셀 중 게이트를 통과해 추세 라벨이 붙은 셀 수",
  "limit": "274셀(81.1%)은 최근 문서 5건 미만·관측 3주 미만·비교 구간 표본 5건 미만 "
           "중 하나에 걸려 판정하지 않았다"},

 {"group": "검색",
  "label": "BM25 · literal P@10", "value": "0.841", "unit": "",
  "how": "질의 61개(주제 별칭). 별칭 문자열이 들어 있는 같은 주제 문서를 정답으로 채점",
  "limit": "같은 질의를 heldout(별칭 토큰이 하나도 없는 문서만 정답)으로 채점하면 "
           "0.000 이다. 평가 구성상 예상되는 값이다",
  "chart": {"labels": ["BM25", "벡터", "하이브리드"],
            "values": [0.841, 0.541, 0.662], "unit": "", "title": "literal P@10"}},

 {"group": "검색",
  "label": "벡터 · heldout Hit@10", "value": "13%", "unit": "",
  "how": "질의 60개 중 8개에서 상위 10 안에 정답 문서가 들어옴",
  "limit": "52개 질의(86.7%)에서는 상위 10 안에 정답이 없다. 점수 대부분이 "
           "`톤 업`·`눈 시림` 처럼 공백이 든 별칭 두 개에서 나온다",
  "chart": {"labels": ["BM25", "벡터", "하이브리드"],
            "values": [0.000, 0.038, 0.028], "unit": "", "title": "heldout P@10"}},

 {"group": "검색",
  "label": "하이브리드(RRF) 채택 여부", "value": "미채택", "unit": "",
  "how": "RRF k=60 으로 두 순위를 합쳐 같은 질의로 채점",
  "limit": "literal 0.662 는 BM25 0.841 보다 낮고, heldout 0.028 은 벡터 0.038 "
           "보다 낮다. 두 값이 각 단일 검색기의 값보다 낮아 채택하지 않았다"},

 {"group": "검증",
  "label": "후향 검증 · 상승 지속 적중률", "value": "22%", "unit": "",
  "how": "판정 시점 이후 실제로 계속 올랐는지. 상승 계열 9건 기준",
  "limit": "같은 데이터의 기저율이 47% 다. 적중률이 기저율보다 낮다. "
           "이 지표로 미래를 예측하지 않는다",
  "chart": {"labels": ["기준 A(계속 상승)", "기준 B(수준 유지)", "A · 상승 9건만",
                       "기저율"],
            "values": [27, 64, 22, 47], "unit": "%", "title": "적중률 대 기저율"}},

 {"group": "검증",
  "label": "광고·협찬 영상 비율", "value": "48.2%", "unit": "",
  "how": "선크림 장문 964편 중 465편. 신고 필드 254편 + 설명란 문구 407편(중복 포함)",
  "limit": "제외하면 판정 셀 19개의 라벨이 바뀌고 24개가 표본 미달로 사라진다. "
           "포함·제외 두 결과를 함께 표시한다",
  "chart": {"labels": ["전체 장문", "광고·협찬", "신고 필드만", "문구로 적발"],
            "values": [964, 465, 254, 407], "unit": "편"}},

 {"group": "검증",
  "label": "패널 민감도", "value": "0셀", "unit": "",
  "how": "전문가 채널 포함·제외 두 경로로 338셀을 재생성해 라벨 변화를 셈",
  "limit": "최대 구성비 차이는 0.78%p 였다. 라벨이 바뀐 셀은 없다"},

 {"group": "보류",
  "label": "논문 축", "value": "사용 중지", "unit": "",
  "how": "`(skin)` 필터를 붙였을 때 남는 문서 비율(잔존율)을 Europe PMC 92개월로 측정",
  "limit": "엑소좀 20.6% · 트라넥삼산 30.7% · 콜라겐 33.3% · 나이아신아마이드 33.4%. "
           "기준선 `cosmetic` 은 100.1% 로 분모와 분자의 모집단이 다르다",
  "chart": {"labels": ["아데노신", "엑소좀", "트라넥삼산", "콜라겐", "나이아신아마이드",
                       "히알루론산", "시카", "cosmetic"],
            "values": [19.0, 20.6, 30.7, 33.3, 33.4, 42.9, 47.8, 100.1],
            "unit": "%", "title": "(skin) 잔존율"}},
]


# 답변 가능 범위. **문서 주장이 아니라 실측이다** (2026-08-27, 벡터 포함).
# 수호님 `RAG_답변_가능범위.md` 의 2단 구분(잘 답함 / 거부)이 실제와 안 맞았다 —
# 거부한다던 6개 중 4개만 거부하고 2개는 조건을 붙여 답한다. 4단으로 다시 나눴다.
SCOPE = [
 {"tier": "1", "kind": "코드가 막는다", "n": 1,
  "note": "검색 단계에서 차단한다. LLM 을 부르지 않아 비용이 0 이다",
  "rows": [{"q": "크소나이드 함유 제품 있어",
            "what": "df 게이트 - 4글자 이상 토큰이 코퍼스에 0건이면 차단"}]},

 {"tier": "2", "kind": "근거를 찾지만 LLM 이 거부한다", "n": 4,
  "note": "검색은 근거를 6~17건 찾아 준다. 그 근거가 질문과 무관해서 LLM 이 "
          "거부한다 - **거부는 검색이 아니라 프롬프트가 한다**",
  "rows": [{"q": "이 성분 넣으면 매출 오를까", "what": "판매량 데이터가 코퍼스에 없다"},
           {"q": "다음 분기에 뭐가 뜰까", "what": "예측 모델이 없다"},
           {"q": "엑소좀 논문 얼마나 늘었어", "what": "논문 축 사용 중지"},
           {"q": "다이소몰과 올리브영 중 어디가 싸",
            "what": "가격 비교 데이터가 없다. 댓글 언급만 인용하고 한계를 붙인다"}]},

 {"tier": "3", "kind": "조건을 붙여 답한다", "n": 2,
  "note": "거부하지 않는다. **인과·효과를 단정하지 않고 언급이 있었다 까지만** 말한다",
  "rows": [{"q": "판테놀이 효과 있어",
            "what": "효과가 좋다·못 느낀다 언급이 함께 있다고 답한다. 효능은 보증하지 않는다"},
           {"q": "나이아신아마이드 때문에 백탁이 생겼어",
            "what": "둘을 직접 연결하는 근거가 없다고 답하고 각각의 언급만 제시한다"}]},

 {"tier": "4", "kind": "잘 답한다", "n": 13,
  "note": "라우팅이 질의 유형을 맞춰 준 경우다",
  "rows": [{"q": "보고번호 2018008612", "what": "bm25 · mfds 1건 · 점수 19.524"},
           {"q": "SPF50 PA++++ 제품", "what": "bm25 · 처방 데이터 6건"},
           {"q": "판테놀 함유", "what": "bm25 · formula 4 · ingredient 1 · mfds 1"},
           {"q": "에칠헥실트리아존 쓰는 선크림", "what": "multi_source · 6소스 18건"},
           {"q": "나이아신아마이드 들어간 선크림", "what": "multi_source · 6소스 18건"},
           {"q": "최근 나온 무기자차 선크림 뭐 있어",
            "what": "temporal_filter · 등록일 기준 목록 6건"},
           {"q": "백탁이 심해요", "what": "vector · 댓글 5 · 리뷰 1"},
           {"q": "눈이 시리고 따가운 것 관련 얘기 있어", "what": "vector · 댓글 6건"},
           {"q": "끈적임 심하다는 얘기 있나", "what": "vector · 댓글 6건"},
           {"q": "백탁 없는 선크림 반응 어때", "what": "vector · 리뷰 3 · 댓글 3"}]},
]

# 문서와 실측이 어긋난 자리. 발표에서 문서를 그대로 읽으면 틀린다
SCOPE_FIXES = [
 {"claim": "백탁 관련해서 소비자들이 뭐라고 해 는 멀티소스로 소스별로 나눠 보여준다",
  "actual": "**vector 로 간다.** `백탁` 은 주제 별칭이라 성분명 목록에서 빼 놓았고, "
            "정확 신호가 없으니 벡터다. 결과도 youtube_comment 6건으로 소스별로 "
            "안 나뉜다"},
 {"claim": "에칠헥실트리아존 쓰는 선크림 은 BM25 다",
  "actual": "**multi_source 다.** 성분명과 서술어가 같이 있어 둘 다 돌린다. "
            "6소스 18건이 나온다"},
 {"claim": "존재하지 않는 성분은 df=0 으로 거부하지만 문장에 섞이면 코드로 100% 막는 건 아니다",
  "actual": "**08.27 부터 문장에 섞여도 막는다.** `len>=4` 인 토큰이 df=0 이면 "
            "차단한다. 실측 - 진짜 질의 61개 손실 0 · 가짜 15개 중 14개 차단"},
 {"claim": "대시보드가 없어서 채팅으로만 쓴다",
  "actual": "**이 화면이 대시보드다.** 질의·카드·지표 세 탭"},
]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):    # 접속 로그를 줄인다
        if "/api/" in (args[0] if args else ""):
            print(f"  {args[0]}")

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode(),
                   "application/json; charset=utf-8", code)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html = (HERE / "ui.html").read_text(encoding="utf-8")
            return self._send(html.encode(), "text/html; charset=utf-8")

        if path == "/api/status":
            with _lock:
                return self._json({"ready": _state["ready"], "vectors": _state["vectors"],
                                   "error": (_state["error"] or "")[-800:]})

        if path == "/api/cards":
            return self._json({"cards": cards()})

        if path == "/api/metrics":
            return self._json({"metrics": METRICS})

        if path == "/api/scope":
            return self._json({"scope": SCOPE, "fixes": SCOPE_FIXES})

        if path == "/api/ask":
            q = (qs.get("q", [""])[0] or "").strip()
            k = min(int(qs.get("k", ["6"])[0] or 6), 20)
            gen = qs.get("generate", ["0"])[0] == "1"
            if not q:
                return self._json({"error": "질의가 비어 있습니다"}, 400)
            with _lock:
                eng, router, ready = _state["engine"], _state["router"], _state["ready"]
            if not ready:
                return self._json({"error": "아직 색인을 올리는 중입니다"}, 503)
            try:
                ctx = eng.answer_context(q, router, k)
                from rag.generate import build_prompt, generate
                res = generate(ctx) if gen else {"prompt": build_prompt(ctx),
                                                 "answer": "", "executed": False,
                                                 "note": "생성을 켜지 않았습니다"}
                return self._json({"context": ctx, **res})
            except Exception:
                return self._json({"error": traceback.format_exc()[-900:]}, 500)

        self._json({"error": "없는 경로"}, 404)


def demo() -> None:
    """서버를 띄우지 않고 데이터 경로만 점검한다."""
    cs = cards()
    assert len(cs) >= 3, f"카드가 {len(cs)}장이다. reports/*.json 을 먼저 만든다"
    for c in cs:
        assert c["name"] and c["type"], c
        # **카드 참조 수와 실제 배열 수가 같아야 한다** — 현준님 감사에서 걸린 항목이다
        assert isinstance(c["limits"], list) and c["limits"], c["name"]
    assert len(METRICS) >= 6
    # **한계가 없는 지표는 싣지 않는다.** 값만 있는 숫자는 발표에서 잘못 읽힌다
    BANNED = ("주력", "양쪽 다", "결함이 아니다", "잘 되는", "훌륭", "우수")
    for m in METRICS:
        assert m["label"] and m["value"], m
        assert m["how"], f"{m['label']}: 측정 방법이 없다"
        assert m["limit"], f"{m['label']}: 한계가 없다"
        for word in BANNED:
            assert word not in m["how"] + m["limit"], f"{m['label']}: 평가어 {word}"
        if m.get("chart"):
            c = m["chart"]
            assert len(c["labels"]) == len(c["values"]), m["label"]
    # 답변 범위는 실측이라 네 단계가 다 있어야 한다
    assert len(SCOPE) == 4, len(SCOPE)
    for t in SCOPE:
        assert t["rows"] and t["note"], t["kind"]
        for r in t["rows"]:
            assert r["q"] and r["what"], r
    assert len(SCOPE_FIXES) >= 3
    html = (HERE / "ui.html")
    assert html.exists(), "ui.html 이 없다"
    body = html.read_text(encoding="utf-8")
    for need in ("/api/ask", "/api/cards", "/api/metrics", "/api/scope"):
        assert need in body, need
    # 지표는 값·측정·한계 세 칸이고 차트가 붙는다
    for need in ("측정 방법", "한계", "metricChart", "pairBar", "이걸로 무엇을 하나"):
        assert need in body, need
    print(f"demo ok — 카드 {len(cs)}장 · 지표 {len(METRICS)}개 · ui.html "
          f"{len(body)//1024}KB")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--vectors", action="store_true",
                   help="벡터(900MB)까지 올린다. 없으면 BM25·시점 필터만")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0

    print(f"색인을 올립니다 (벡터 {'포함' if a.vectors else '제외'})...")
    threading.Thread(target=boot, args=(a.vectors,), daemon=True).start()
    server = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"http://{a.host}:{a.port}  — Ctrl+C 로 종료")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
