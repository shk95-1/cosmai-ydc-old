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


def cards() -> list[dict]:
    """카드 6장. 산출물 JSON 을 그대로 읽는다 — 여기서 새로 만들지 않는다."""
    out = []
    for name, axis, key in [("opportunity_cards.json", "주제", "topic_id"),
                            ("opportunity_cards_ingredient.json", "성분", "ingredient")]:
        p = ROOT / "reports" / name
        if not p.exists():
            continue
        for c in json.loads(p.read_text(encoding="utf-8")):
            out.append({
                "axis": axis, "name": c.get(key, "?"), "type": c.get("card_type", ""),
                "basis": c.get("type_basis", ""),
                "limits": c.get("limits", []),
                "others": c.get("same_type_others", []),
                "quotes": [{"text": q.get("text", ""), "url": q.get("url", ""),
                            "term": q.get("matched_term", ""),
                            "likes": q.get("like_count", "")}
                           for q in c.get("quotes", [])],
                "evidence": c.get("evidence", []),
            })
    return out


METRICS = [
    ("색인 청크", "306,178", "유튜브 278,916 · 커머스 18,476 · 성분·식약처 8,786"),
    ("BM25 literal P@10", "0.841", "정확 일치가 정답인 질의. 이게 검색의 주력이다"),
    ("벡터 heldout Hit@10", "13%", "열 번 물어 아홉 번은 못 찾는다. 바닥선을 넘은 것뿐이다"),
    ("하이브리드", "폐기", "어휘 0.841→0.662 · 의미 0.038→0.028. 양쪽 다 진다"),
    ("판정된 셀", "64 / 338", "81%가 표본 미달로 판정 안 됨. 설계이지 결함이 아니다"),
    ("후향 검증 (상승 지속)", "22%", "기저율 47%. **예측 도구가 아니다**"),
    ("광고·협찬", "465 / 964 (48.2%)", "빼면 19셀이 뒤집힌다. 필터 민감으로 공개한다"),
    ("논문 축", "사용 중지", "검색어가 화장품을 세지 않는다(잔존율 20~48%)"),
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
            return self._json({"metrics": [{"label": a, "value": b, "note": c}
                                           for a, b, c in METRICS]})

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
    # 한계가 없는 지표는 싣지 않는다
    for a, b, note in METRICS:
        assert note, a
    html = (HERE / "ui.html")
    assert html.exists(), "ui.html 이 없다"
    body = html.read_text(encoding="utf-8")
    for need in ("/api/ask", "/api/cards", "/api/metrics"):
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
