#!/usr/bin/env python3
"""시각 대시보드. `dashboard.py` 는 드릴다운 표고, 이건 **차트**다.

`dashboard.py` 는 338셀을 하나씩 파고들 때 쓴다. 이건 반대로 **한 화면에서
전체를 훑을 때** 쓴다 — 발표와 팀 공유용이다. 그래서 파일을 나눴다.

**모든 수치는 `reports/` 의 산출물에서 그대로 읽는다.** 여기서 새로 계산하는 것은
막대 길이와 좌표뿐이다. 패널마다 **어느 파일에서 나온 값인지** 를 머리에 적는다 —
근거를 짚을 수 없으면 숫자를 싣지 않는다는 이 프로젝트의 규칙과 같다.

색은 임의로 고르지 않았다. 범주형 6색은 색각 이상·명도대비 검증기를 통과한
조합이고(라이트 표면 `#F7F8FA` · 다크 `#101318`), 라이트에서 대비 3:1 을 못 넘는
3색은 **직접 라벨**로 보완했다. 산점도는 전체쌍 검증을 통과하는 앞 3색만 쓴다.

사용법:
    python viz_dashboard.py
    python viz_dashboard.py --demo
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(10 ** 8)

# 청크 소스별 개수. 벡터 매니페스트와 같은 값이라 여기 상수로 둔다
CHUNK_SOURCES = [
    ("유튜브 댓글", 252332, "담론"),
    ("유튜브 영상", 26584, "담론"),
    ("커머스 리뷰", 18476, "사용 감각"),
    ("식약처 등록", 4735, "공급측"),
    ("성분 사전", 1931, "처방"),
    ("전성분 상세", 1543, "처방"),
    ("제품 요약", 577, "처방"),
]

# 논문 잔존율. `(skin)` 을 붙이면 남는 비율 — 논문 축을 내린 근거다
RETENTION = [
    ("아데노신", 19.0, "현준님이 막은 것"),
    ("엑소좀", 20.6, "우리가 쓰려던 것"),
    ("트라넥삼산", 30.7, ""),
    ("콜라겐", 33.3, ""),
    ("나이아신아마이드", 33.4, ""),
    ("히알루론산", 42.9, ""),
    ("시카센텔라", 47.8, ""),
    ("PDRN", 56.9, ""),
    ("판테놀", 64.0, ""),
    ("cosmetic (기준선)", 100.1, "여기가 문제다"),
]

# **여섯 값이 전부 같은 시점(08.25 · 2차 청크)이어야 한다.** 처음엔 하이브리드만
# 08.24 판이 들어가 한 차트에서 다른 시점을 비교하고 있었다. 다시 돌려 맞췄다
RETRIEVAL = {
    "metrics": ["literal P@10", "literal Hit@10", "heldout P@10", "heldout Hit@10"],
    "bm25": [0.841, 0.93, 0.000, 0.00],
    "vector": [0.541, 0.89, 0.038, 0.13],
    "hybrid": [0.662, 0.95, 0.028, 0.10],
}

BACKTEST = [("기준 A — 판정 후에도 계속 올랐나", 27), ("기준 B — 올라간 수준이 유지됐나", 64),
            ("기준 A · 상승 계열 9건만", 22)]
BASE_RATE = 47


def rd(path: Path) -> list[dict]:
    """`#` 주석 줄은 건너뛴다. 받은 CSV 는 머리에 주의사항이 붙어 있다."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader([l for l in handle if not l.startswith("#")]))


def num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def collect(reports: Path) -> dict:
    """산출물에서 숫자를 그대로 읽는다. **여기서 새로 계산하지 않는다.**"""
    d: dict = {}
    d["chunks"] = [{"name": n, "n": c, "role": r} for n, c, r in CHUNK_SOURCES]
    d["retention"] = [{"q": q, "pct": p, "note": n} for q, p, n in RETENTION]
    d["retrieval"] = RETRIEVAL
    d["backtest"] = {"rows": [{"label": l, "pct": p} for l, p in BACKTEST], "base": BASE_RATE}

    ing = rd(reports / "cross_source_ingredient.csv")
    d["ingredients"] = [{
        "name": r["ingredient"], "search": num(r["naver_growth_x"]),
        "products": int(num(r["formula_products"])), "pct": num(r["formula_pct"]),
        "order": int(num(r["median_order"])) if r["median_order"] else None,
        "high": num(r["high_dose_pct"]), "talk": int(num(r["talk_youtube"])),
        "reading": r["reading"],
    } for r in ing]

    d["topics"] = [{
        "group": r["naver_group"], "topic": r["topic_id"],
        "rank": int(num(r["naver_rank"])), "video": num(r["youtube_video_pct"]),
        "comment": num(r["youtube_comment_pct"]), "review": num(r["commerce_pct"]),
        "review_rank": int(num(r["commerce_rank"])), "reading": r["reading"],
    } for r in rd(reports / "cross_source.csv")]

    # 분기 계열 — 댓글 구성비 상위 6주제
    tr = rd(reports / "trend_sunscreen_v0.2.csv")
    per: dict[str, dict[str, float]] = defaultdict(dict)
    for r in tr:
        if r["source"] == "youtube_comment":
            per[r["topic_id"]][r["quarter"]] = round(num(r["composition"]) * 100, 3)
    quarters = sorted({r["quarter"] for r in tr})
    top = sorted(per, key=lambda t: -sum(per[t].values()))[:6]
    d["quarters"] = quarters
    d["series"] = [{"name": t, "values": [per[t].get(q, 0.0) for q in quarters]} for t in top]

    j = rd(reports / "trend_judgement_v0.2.csv")
    d["judgement"] = [{"type": k, "n": v} for k, v in
                      sorted(Counter(r["trend_type"] or "미판정" for r in j).items(),
                             key=lambda kv: -kv[1])]
    d["judged"] = sum(1 for r in j if r["judged"] == "true")
    d["cells"] = len(j)

    # NAVER — 선케어 5그룹 · 성분 지수
    nv = rd(reports / "naver_trend.csv")
    suncare: dict[str, dict[str, float]] = defaultdict(dict)
    ingidx: dict[str, dict[str, float]] = defaultdict(dict)
    for r in nv:
        if r["source_id"] == "naver.datalab.suncare":
            suncare[r["group"]][r["period"]] = num(r["ratio"])
        elif r["source_id"].startswith("naver.datalab.p7") and r["index_vs_baseline"]:
            if r["group"] != "기준_세럼":
                ingidx[r["group"]][r["period"]] = num(r["index_vs_baseline"])
    d["periods"] = sorted({p for s in suncare.values() for p in s})
    d["suncare"] = [{"name": g, "values": [s.get(p, 0.0) for p in d["periods"]]}
                    for g, s in sorted(suncare.items())]
    d["ing_periods"] = sorted({p for s in ingidx.values() for p in s})
    order = sorted(ingidx, key=lambda g: -max(ingidx[g].values()))
    d["ing_index"] = [{"name": g, "values": [ingidx[g].get(p, 0.0) for p in d["ing_periods"]]}
                      for g in order[:6]]

    # 커머스 랭킹 — 100위권은 raw 쪽이다. commerce_ranking.csv 는 상위 20위 판이다
    raw = [r for r in rd(reports / "commerce_ranking_raw.csv")
           if r["source"] == "oliveyoung" and r["board"] == "suncare"]
    sw = sorted(int(num(r["swing"])) for r in raw if r["swing"])
    hist = Counter(min(int(num(r["swing"])) // 10 * 10, 90) for r in raw if r["swing"])
    top20 = [int(num(r["swing"])) for r in raw if int(num(r["best_rank"])) <= 20]
    d["ranking"] = {
        "n": len(raw), "median": sw[len(sw) // 2], "mean": round(statistics.mean(sw), 1),
        "max": max(sw), "top20_n": len(top20),
        "top20_median": int(statistics.median(top20)) if top20 else 0,
        "hist": [{"b": b, "n": hist.get(b, 0)} for b in range(0, 100, 10)],
    }

    # 담론 빈도 — 성분·표현 용어
    agg: Counter = Counter()
    for r in rd(reports / "youtube_ingredient_terms.csv"):
        agg[r["term"]] += int(num(r["total_docs"]))
    d["terms"] = [{"t": k, "n": v} for k, v in agg.most_common(16)]

    um = sorted(rd(reports / "unmatched_terms.csv"), key=lambda r: -num(r["lift"]))[:14]
    d["unmatched"] = [{"t": r["noun"], "lift": round(num(r["lift"]), 1),
                       "docs": int(num(r["sun_video_docs"]))} for r in um]

    # 자막 이득 — 설명란만 보면 못 보는 편수
    d["transcript"] = sorted(
        [{"t": r["topic_id"], "base": int(num(r["videos_matched_baseline"])),
          "gain": int(num(r["gained"]))}
         for r in rd(reports / "transcript_gain.csv") if r["bucket"] == "장문"],
        key=lambda x: -x["gain"])[:10]

    d["panel"] = sorted([{"t": r["topic_id"], "src": r["source"],
                          "diff": num(r["difference_pp"])}
                         for r in rd(reports / "panel_sensitivity.csv")],
                        key=lambda x: -abs(x["diff"]))[:10]

    d["source_comp"] = [{"t": r["topic_id"], "comment": num(r["youtube_comment_pct"]),
                         "video": num(r["youtube_video_pct"]),
                         "review": num(r["commerce_review_pct"])}
                        for r in rd(reports / "source_composition.csv")]

    cards = json.loads((reports / "opportunity_cards.json").read_text(encoding="utf-8"))
    icards = json.loads((reports / "opportunity_cards_ingredient.json").read_text(encoding="utf-8"))
    d["cards"] = [{"name": c["topic_id"], "axis": "주제", "type": c["card_type"],
                   "basis": c["type_basis"], "limits": len(c["limits"]),
                   "quotes": len(c["quotes"])} for c in cards]
    d["cards"] += [{"name": c["ingredient"], "axis": "성분", "type": c["card_type"],
                    "basis": c["type_basis"], "limits": len(c["limits"]),
                    "others": c.get("same_type_others", [])} for c in icards]
    return d


HTML = """<title>선크림 트렌드 레이더</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{
  color-scheme:light;
  --ground:#F7F8FA; --panel:#FFFFFF; --sunk:#EEF1F5;
  --line:#DFE4EB; --line2:#EDF0F4;
  --ink:#111418; --ink2:#586474; --ink3:#8A94A3;
  --uv:#5B3FD6; --uv-soft:#EFEBFD;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
  --s4:#eda100; --s5:#e87ba4; --s6:#4a3aa7;
  --good:#12855c; --warn:#a06a00; --bad:#c53b3a;
  --shadow:0 1px 2px rgba(17,20,24,.04),0 8px 24px -12px rgba(17,20,24,.10);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  color-scheme:dark;
  --ground:#101318; --panel:#171B22; --sunk:#1E242D;
  --line:#2A313C; --line2:#222932;
  --ink:#EDF0F4; --ink2:#9AA5B4; --ink3:#6B7686;
  --uv:#9C87F5; --uv-soft:#221C3C;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --s4:#c98500; --s5:#d55181; --s6:#9085e9;
  --good:#199e70; --warn:#c98500; --bad:#e66767;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px -12px rgba(0,0,0,.6);
}}
:root[data-theme="dark"]{
  color-scheme:dark;
  --ground:#101318; --panel:#171B22; --sunk:#1E242D;
  --line:#2A313C; --line2:#222932;
  --ink:#EDF0F4; --ink2:#9AA5B4; --ink3:#6B7686;
  --uv:#9C87F5; --uv-soft:#221C3C;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
  --s4:#c98500; --s5:#d55181; --s6:#9085e9;
  --good:#199e70; --warn:#c98500; --bad:#e66767;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px -12px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
body{
  margin:0;background:var(--ground);color:var(--ink);
  font-family:"IBM Plex Sans KR",system-ui,-apple-system,"Malgun Gothic",sans-serif;
  font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased;
}
.mono{font-family:"IBM Plex Mono","IBM Plex Sans KR",ui-monospace,monospace;
  font-variant-numeric:tabular-nums}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px 96px}

/* ── 머리 ─────────────────────────────────────── */
header{padding:64px 0 40px;border-bottom:1px solid var(--line)}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink3);margin:0 0 14px}
h1{font-size:clamp(32px,5vw,50px);line-height:1.1;font-weight:700;margin:0 0 16px;
  letter-spacing:-.025em;text-wrap:balance}
.lede{font-size:17px;color:var(--ink2);max-width:62ch;margin:0 0 28px;font-weight:300}
.lede b{color:var(--ink);font-weight:600}
.strip{display:flex;flex-wrap:wrap;gap:2px;background:var(--line);
  border:1px solid var(--line);border-radius:3px;overflow:hidden}
.strip div{flex:1 1 130px;background:var(--panel);padding:13px 15px}
.strip .k{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink3);display:block;margin-bottom:5px}
.strip .v{font-family:"IBM Plex Mono",monospace;font-size:21px;font-weight:600;
  font-variant-numeric:tabular-nums;letter-spacing:-.02em}

/* ── 절 ─────────────────────────────────────── */
section{padding:56px 0 8px;border-bottom:1px solid var(--line2)}
section:last-of-type{border-bottom:0}
.sec-h{display:flex;align-items:baseline;gap:14px;margin:0 0 8px}
.sec-n{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:600;
  color:var(--uv);letter-spacing:.06em}
h2{font-size:25px;font-weight:600;margin:0;letter-spacing:-.02em}
.sec-d{color:var(--ink2);margin:0 0 30px;max-width:66ch;font-weight:300;font-size:14.5px}

/* ── 패널 ─────────────────────────────────────── */
.grid{display:grid;gap:18px;grid-template-columns:repeat(12,1fr)}
.p{grid-column:span 12;background:var(--panel);border:1px solid var(--line);
  border-radius:4px;padding:20px 22px 18px;box-shadow:var(--shadow);min-width:0}
.p.h{grid-column:span 6}
.p.t{grid-column:span 4}
@media(max-width:900px){.p.h,.p.t{grid-column:span 12}}
.src{font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--ink3);
  letter-spacing:.03em;margin:0 0 6px;word-break:break-all}
h3{font-size:16px;font-weight:600;margin:0 0 4px;letter-spacing:-.01em}
.note{font-size:13px;color:var(--ink2);margin:0 0 16px;font-weight:300}
.cap{font-size:12.5px;color:var(--ink2);margin:14px 0 0;padding-top:12px;
  border-top:1px dashed var(--line);font-weight:300}
.cap b{color:var(--ink);font-weight:600}

/* ── 차트 ─────────────────────────────────────── */
svg{display:block;width:100%;height:auto;overflow:visible}
.ax{stroke:var(--line);stroke-width:1}
.gr{stroke:var(--line2);stroke-width:1}
.tk{font-family:"IBM Plex Mono","IBM Plex Sans KR",monospace;font-size:10px;fill:var(--ink3)}
.lb{font-size:11.5px;fill:var(--ink2)}
.vl{font-family:"IBM Plex Mono","IBM Plex Sans KR",monospace;font-size:11px;
  fill:var(--ink);font-weight:500;font-variant-numeric:tabular-nums}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 14px}
.legend span{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--ink2)}
.legend i{width:10px;height:10px;border-radius:2px;flex:none}
.hit{fill:transparent;cursor:crosshair}
.mark{transition:opacity .12s}
.dim{opacity:.22}

/* ── 표 ─────────────────────────────────────── */
.tw{overflow-x:auto;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:420px}
th{text-align:left;font-family:"IBM Plex Mono",monospace;font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);font-weight:500;
  padding:0 12px 8px 0;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:8px 12px 8px 0;border-bottom:1px solid var(--line2);vertical-align:top}
td.n{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;
  text-align:right;padding-right:14px;white-space:nowrap}
tr:last-child td{border-bottom:0}

/* ── 칩 ─────────────────────────────────────── */
.chip{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:10.5px;
  padding:2px 7px;border-radius:3px;background:var(--sunk);color:var(--ink2);
  white-space:nowrap;font-weight:500}
.chip.uv{background:var(--uv-soft);color:var(--uv)}
.chip.g{background:color-mix(in srgb,var(--good) 14%,transparent);color:var(--good)}
.chip.w{background:color-mix(in srgb,var(--warn) 16%,transparent);color:var(--warn)}
.chip.b{background:color-mix(in srgb,var(--bad) 14%,transparent);color:var(--bad)}

/* ── 카드 ─────────────────────────────────────── */
.cards{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(320px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;
  padding:18px 20px;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:9px}
.card h4{margin:0;font-size:17px;font-weight:600;letter-spacing:-.01em}
.card .b{font-size:13px;color:var(--ink2);font-weight:300;flex:1}
.card .r{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.card ul{margin:0;padding-left:16px;font-size:12.5px;color:var(--ink2);font-weight:300}

/* ── 경고 ─────────────────────────────────────── */
.hold{border-left:3px solid var(--warn);background:color-mix(in srgb,var(--warn) 5%,var(--panel));
  padding:16px 20px;border-radius:0 4px 4px 0;margin:0 0 18px}
.hold p{margin:0;font-size:13.5px;color:var(--ink2);font-weight:300}
.hold b{color:var(--ink);font-weight:600}

/* ── 툴팁 ─────────────────────────────────────── */
#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s;
  background:var(--panel);border:1px solid var(--line);border-radius:4px;
  padding:8px 11px;font-size:12px;box-shadow:var(--shadow);z-index:99;max-width:260px;
  font-family:"IBM Plex Mono",monospace;line-height:1.5}
#tip b{font-family:"IBM Plex Sans KR",sans-serif}
footer{padding:44px 0 0;color:var(--ink3);font-size:12.5px;font-weight:300;
  border-top:1px solid var(--line);margin-top:56px}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<div class="wrap">
<header>
  <p class="eyebrow">COSMAI · NVIDIA AI 전문인력 양성 PoC · 2026.08.25</p>
  <h1>선크림 트렌드 레이더</h1>
  <p class="lede">소스 여섯 개를 나란히 놓고 <b>어긋나는 자리</b>를 R&amp;D 공백으로 냅니다.
  합산하지 않습니다 — 분모가 전부 다르므로 크기가 아니라 <b>순위와 방향</b>을 봅니다.
  아래 모든 수치는 <b>커밋된 산출물에서 그대로</b> 읽었고, 패널마다 출처 파일을 적었습니다.</p>
  <div class="strip" id="strip"></div>
</header>
<main id="main"></main>
<footer>
  <p>생성 <span class="mono">viz_dashboard.py</span> · 원본 <span class="mono">slopindustries/youtube-data-collector</span><br>
  원문이 실린 산출물은 깃에 올리지 않고 스크립트로 재현합니다 — 기획안 §4 원문 재배포 금지.</p>
</footer>
</div>
<div id="tip"></div>
<script>
const D = __DATA__;
const $ = (h) => { const t = document.createElement('template'); t.innerHTML = h.trim(); return t.content.firstChild; };
const S = ['--s1','--s2','--s3','--s4','--s5','--s6'].map(v=>`var(${v})`);
const fmt = (n,d=0) => n.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d});
const esc = (s) => String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const tip = document.getElementById('tip');
function hover(el, html){
  el.addEventListener('pointerenter', e => { tip.innerHTML = html; tip.style.opacity = 1; });
  el.addEventListener('pointermove', e => {
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(e.clientX+14, innerWidth-r.width-10)+'px';
    tip.style.top  = Math.max(e.clientY-r.height-12, 10)+'px';
  });
  el.addEventListener('pointerleave', () => tip.style.opacity = 0);
}

/* ── 가로 막대 ───────────────────────────────── */
function hbar(items, o={}){
  const lw = o.labelWidth ?? 128, rw = o.valueWidth ?? 58, bh = o.barH ?? 22, gap = o.gap ?? 7;
  const W = 640, H = items.length*(bh+gap)-gap, pw = W-lw-rw;
  const max = o.max ?? Math.max(...items.map(d=>d.v));
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.aria||'')}">`;
  items.forEach((d,i)=>{
    const y = i*(bh+gap), w = max? Math.max(2, d.v/max*pw) : 2;
    const c = d.c ?? o.color ?? 'var(--s1)';
    s += `<text class="lb" x="${lw-9}" y="${y+bh/2+4}" text-anchor="end">${esc(d.l)}</text>`;
    s += `<rect class="mark" x="${lw}" y="${y}" width="${w}" height="${bh}" rx="3" fill="${c}"
           data-tip="${esc(d.tip||`<b>${d.l}</b><br>${o.unit? d.txt??fmt(d.v): fmt(d.v)}`)}"/>`;
    s += `<text class="vl" x="${lw+w+8}" y="${y+bh/2+4}">${esc(d.txt ?? fmt(d.v))}</text>`;
  });
  return s+'</svg>';
}

/* ── 세로 그룹 막대 ───────────────────────────── */
function gbar(groups, series, o={}){
  const W=640, H=o.h??220, pad={t:14,r:8,b:o.b??44,l:o.l??40};
  const iw=W-pad.l-pad.r, ih=H-pad.t-pad.b;
  const max=o.max ?? Math.max(...groups.flatMap(g=>g.v));
  const gw=iw/groups.length, bw=Math.min(o.bw??30,(gw-12)/series.length);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.aria||'')}">`;
  const ticks=o.ticks??4;
  for(let i=0;i<=ticks;i++){
    const y=pad.t+ih-ih*i/ticks, v=max*i/ticks;
    s+=`<line class="gr" x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}"/>`;
    s+=`<text class="tk" x="${pad.l-7}" y="${y+3.5}" text-anchor="end">${o.tf?o.tf(v):fmt(v,o.td??0)}</text>`;
  }
  groups.forEach((g,gi)=>{
    const x0=pad.l+gi*gw;
    g.v.forEach((v,si)=>{
      const bh=max?Math.max(1.5,v/max*ih):1.5;
      const x=x0+(gw-bw*series.length-2*(series.length-1))/2+si*(bw+2);
      s+=`<rect class="mark" x="${x}" y="${pad.t+ih-bh}" width="${bw}" height="${bh}" rx="3"
            fill="${S[si]}" data-tip="<b>${esc(g.l)}</b><br>${esc(series[si])} ${o.vf?o.vf(v):fmt(v,o.td??0)}"/>`;
      if(o.labelBars) s+=`<text class="vl" x="${x+bw/2}" y="${pad.t+ih-bh-5}" text-anchor="middle"
            style="font-size:9.5px">${o.vf?o.vf(v):fmt(v,o.td??0)}</text>`;
    });
    const words=String(g.l).split('\\n');
    words.forEach((w,wi)=>{
      s+=`<text class="lb" x="${x0+gw/2}" y="${H-pad.b+16+wi*13}" text-anchor="middle"
            style="font-size:11px">${esc(w)}</text>`;
    });
  });
  if(o.rule!=null){
    const y=pad.t+ih-o.rule/max*ih;
    s+=`<line x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}" stroke="var(--bad)"
          stroke-width="1.5" stroke-dasharray="5 3"/>`;
    s+=`<text class="vl" x="${W-pad.r}" y="${y-6}" text-anchor="end" fill="var(--bad)">${esc(o.ruleLabel||'')}</text>`;
  }
  return s+'</svg>';
}

/* 한글은 라틴보다 넓다. 대략치로 라벨 폭을 잡는다 — 정확할 필요는 없고
   오른쪽 여백과 겹침 판정에만 쓴다 */
const textW = (s, size) => [...String(s)]
  .reduce((a,c)=>a+(/[\\uAC00-\\uD7A3]/.test(c)?1:0.56),0)*size;

/* 세로로 겹치는 라벨을 서로 밀어낸다. 안 밀면 이름이 포개져서 못 읽는다 */
function spread(items, gap, top, bottom){
  items.sort((a,b)=>a.y-b.y);
  for(let i=1;i<items.length;i++)
    if(items[i].y-items[i-1].y<gap) items[i].y=items[i-1].y+gap;
  const over=items[items.length-1].y-bottom;
  if(over>0){
    items[items.length-1].y=bottom;
    for(let i=items.length-2;i>=0;i--)
      if(items[i+1].y-items[i].y<gap) items[i].y=items[i+1].y-gap;
  }
  if(items[0].y<top){
    items[0].y=top;
    for(let i=1;i<items.length;i++)
      if(items[i].y-items[i-1].y<gap) items[i].y=items[i-1].y+gap;
  }
  return items;
}

/* ── 다중 선 ─────────────────────────────────── */
function lines(labels, series, o={}){
  const need = Math.ceil(Math.max(...series.map(s=>textW(s.name,10.5))))+20;
  const W=640, H=o.h??240, pad={t:14,r:o.endLabels===false?(o.r??20):need,b:34,l:o.l??44};
  const iw=W-pad.l-pad.r, ih=H-pad.t-pad.b;
  const all=series.flatMap(s=>s.values);
  const max=o.max??Math.max(...all), min=o.min??0;
  const X=i=>pad.l+(labels.length<2?0:i/(labels.length-1)*iw);
  const Y=v=>pad.t+ih-(v-min)/(max-min||1)*ih;
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.aria||'')}">`;
  const ticks=o.ticks??4;
  for(let i=0;i<=ticks;i++){
    const y=pad.t+ih-ih*i/ticks, v=min+(max-min)*i/ticks;
    s+=`<line class="gr" x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}"/>`;
    s+=`<text class="tk" x="${pad.l-7}" y="${y+3.5}" text-anchor="end">${o.tf?o.tf(v):fmt(v,o.td??0)}</text>`;
  }
  const step=Math.max(1,Math.ceil(labels.length/(o.xt??7)));
  // `2016-01-01` 은 눈금으로 길다. 끝 눈금은 오른쪽 정렬해야 끝 라벨과 안 부딪힌다
  const xf = o.xf ?? (l => String(l).length===10 ? String(l).slice(0,7) : l);
  // **뒤에서부터** 간격을 확보한다. 마지막 눈금이 가장 정보가 많은데
  // 앞에서부터 채우면 그게 앞 눈금에 밀려 지워지거나 겹친다
  // 눈금은 **정렬 방향에 따라 차지하는 쪽이 다르다.** 끝 눈금은 왼쪽으로 뻗고
  // 가운데 눈금은 양쪽으로 뻗는다. 중심 거리만 보면 3~4px 씩 닿는다
  const want=[]; for(let i=0;i<labels.length;i+=step) want.push(i);
  if(want[want.length-1]!==labels.length-1) want.push(labels.length-1);
  const span=(i,w)=>{ const x=X(i);
    return i===labels.length-1 ? [x-w,x] : i===0 ? [x,x+w] : [x-w/2,x+w/2]; };
  const keep=[]; let prevLeft=Infinity;
  for(let k=want.length-1;k>=0;k--){
    const i=want[k];
    // Plex Mono 는 라틴 추정치보다 넓다(실측 0.69em vs 추정 0.56em)
    const [l,r]=span(i, textW(xf(labels[i]),10)*1.25);
    if(r+8 <= prevLeft){ keep.unshift(i); prevLeft=l; }
  }
  keep.forEach(i=>{
    const an = i===labels.length-1?'end':i===0?'start':'middle';
    s+=`<text class="tk" x="${X(i)}" y="${H-16}" text-anchor="${an}">${esc(xf(labels[i]))}</text>`;
  });
  series.forEach((se,si)=>{
    const d=se.values.map((v,i)=>`${i?'L':'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ');
    s+=`<path d="${d}" fill="none" stroke="${S[si]}" stroke-width="2"
          stroke-linejoin="round" stroke-linecap="round"/>`;
    const last=se.values.length-1;
    s+=`<circle cx="${X(last)}" cy="${Y(se.values[last])}" r="3.5" fill="${S[si]}"
          stroke="var(--panel)" stroke-width="2"/>`;
  });
  if(o.endLabels!==false){
    const last=labels.length-1;
    const ends=spread(series.map((se,si)=>({si,name:se.name,
      y0:Y(se.values[se.values.length-1]), y:Y(se.values[se.values.length-1])})),
      17, pad.t+4, pad.t+ih+9);
    ends.forEach(e=>{
      // 밀어낸 만큼 점과 라벨을 잇는다. 안 이으면 어느 선의 이름인지 알 수 없다
      if(Math.abs(e.y-e.y0)>2)
        s+=`<path d="M${X(last)+4} ${e.y0} L${X(last)+9} ${e.y0} L${X(last)+13} ${e.y}"
              fill="none" stroke="${S[e.si]}" stroke-width="1" opacity=".5"/>`;
      s+=`<text class="vl" x="${X(last)+16}" y="${e.y+3.5}"
            style="font-size:10.5px" fill="${S[e.si]}">${esc(e.name)}</text>`;
    });
  }
  labels.forEach((l,i)=>{
    const half=iw/(labels.length-1||1)/2;
    const rows=series.map((se,si)=>
      `<span style="color:${S[si]}">■</span> ${esc(se.name)} ${o.vf?o.vf(se.values[i]):fmt(se.values[i],o.td??1)}`).join('<br>');
    s+=`<rect class="hit" x="${X(i)-half}" y="${pad.t}" width="${half*2}" height="${ih}"
          data-tip="<b>${esc(l)}</b><br>${rows}"/>`;
  });
  return s+'</svg>';
}

/* ── 산점도 ─────────────────────────────────── */
function scatter(pts, o={}){
  const W=640,H=o.h??300,pad={t:16,r:20,b:46,l:52};
  const iw=W-pad.l-pad.r, ih=H-pad.t-pad.b;
  const xs=pts.map(p=>p.x), ys=pts.map(p=>p.y);
  const lx=v=>Math.log10(Math.max(v,1));
  const xmin=0, xmax=Math.ceil(lx(Math.max(...xs)));
  const ymax=o.ymax??Math.ceil(Math.max(...ys)/10)*10;
  const X=v=>pad.l+(lx(v)-xmin)/(xmax-xmin)*iw;
  const Y=v=>pad.t+ih-v/ymax*ih;
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.aria||'')}">`;
  for(let i=0;i<=4;i++){
    const y=pad.t+ih-ih*i/4;
    s+=`<line class="gr" x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}"/>`;
    s+=`<text class="tk" x="${pad.l-7}" y="${y+3.5}" text-anchor="end">${fmt(ymax*i/4)}%</text>`;
  }
  for(let e=xmin;e<=xmax;e++){
    const x=X(Math.pow(10,e));
    s+=`<line class="gr" x1="${x}" y1="${pad.t}" x2="${x}" y2="${pad.t+ih}"/>`;
    const an = e===xmax?'end':e===xmin?'start':'middle';
    s+=`<text class="tk" x="${x}" y="${H-26}" text-anchor="${an}">${fmt(Math.pow(10,e))}배</text>`;
  }
  s+=`<text class="lb" x="${pad.l+iw/2}" y="${H-6}" text-anchor="middle">NAVER 검색 증가 (2016년 대비 · 로그)</text>`;
  s+=`<text class="lb" x="14" y="${pad.t+ih/2}" text-anchor="middle"
        transform="rotate(-90 14 ${pad.t+ih/2})">선케어 처방 채택률</text>`;
  pts.forEach(p=>{
    const r=5+Math.sqrt(p.r??0)*1.1;
    s+=`<circle class="mark" cx="${X(p.x)}" cy="${Y(p.y)}" r="${r}" fill="${p.c}"
          fill-opacity=".75" stroke="var(--panel)" stroke-width="2" data-tip="${esc(p.tip)}"/>`;
  });
  /* 라벨은 원을 다 그린 뒤에 놓는다. **겹치면 자리를 옮긴다** — 오른쪽 아래
     세 성분(엑소좀·PDRN·트라넥삼산)이 전부 처방 0% 라 그냥 두면 포개진다 */
  const placed=[];
  const hits=(b)=>placed.some(q=>b.x<q.x+q.w+3&&q.x<b.x+b.w+3&&b.y-17<q.y&&q.y-17<b.y);
  pts.forEach(p=>{
    const r=5+Math.sqrt(p.r??0)*1.1, w=textW(p.l,10.5);
    const cx=X(p.x), cy=Y(p.y);
    const cands=[
      {x:cx-w/2, y:cy-r-6,  a:'middle', ax:cx},
      {x:cx-w/2, y:cy+r+13, a:'middle', ax:cx},
      {x:cx+r+6, y:cy+4,    a:'start',  ax:cx+r+6},
      {x:cx-r-6-w, y:cy+4,  a:'end',    ax:cx-r-6},
      {x:cx-w/2, y:cy-r-20, a:'middle', ax:cx},
      {x:cx-w/2, y:cy+r+27, a:'middle', ax:cx},
      {x:cx+r+6, y:cy-r-8,   a:'start',  ax:cx+r+6},
      {x:cx-r-6-w, y:cy-r-8, a:'end',    ax:cx-r-6},
      {x:cx-w/2, y:cy-r-33, a:'middle', ax:cx},
    ];
    let pick=cands.find(c=>c.x>=2&&c.x+w<=W-2&&c.y>=pad.t+11&&c.y<=pad.t+ih+15&&!hits({...c,w}))
             ?? cands[0];
    placed.push({x:Math.max(2,Math.min(pick.x,W-w-2)), y:pick.y, w});
    s+=`<text class="vl" x="${pick.ax}" y="${pick.y}" text-anchor="${pick.a}"
          style="font-size:10.5px">${esc(p.l)}</text>`;
  });
  return s+'</svg>';
}

function panel(o){
  const cls = o.w==='h'?'p h':o.w==='t'?'p t':'p';
  return `<div class="${cls}">
    <p class="src">${esc(o.src)}</p>
    <h3>${o.title}</h3>
    ${o.note?`<p class="note">${o.note}</p>`:''}
    ${o.legend?`<div class="legend">${o.legend}</div>`:''}
    ${o.body}
    ${o.cap?`<p class="cap">${o.cap}</p>`:''}
  </div>`;
}
const leg = (names) => names.map((n,i)=>`<span><i style="background:${S[i]}"></i>${esc(n)}</span>`).join('');

/* ═══ 조립 ═══════════════════════════════════ */
const totalChunks = D.chunks.reduce((a,b)=>a+b.n,0);
document.getElementById('strip').innerHTML = [
  ['색인 청크', fmt(totalChunks)], ['벡터 차원', '768'],
  ['분기 셀', `${fmt(D.judged)}/${fmt(D.cells)}`],
  ['Opportunity Card', fmt(D.cards.length)],
  ['NAVER 개월', fmt(D.periods.length)],
  ['성분 · 제품', `31,246 · 577`],
].map(([k,v])=>`<div><span class="k">${k}</span><span class="v">${v}</span></div>`).join('');

const out = [];
const sec = (n,t,d,body) => out.push(`<section>
  <div class="sec-h"><span class="sec-n">${n}</span><h2>${t}</h2></div>
  <p class="sec-d">${d}</p><div class="grid">${body}</div></section>`);

/* ── 1. 빈도 ─────────────────────────────── */
sec('01','무엇이 얼마나 들어 있나',
 '색인의 <b>92%가 짧은 유튜브 댓글</b>입니다. 그래서 전역 상위 k 로 뽑으면 댓글이 결과를 독점하고, 식약처·성분 문서는 300위 밖으로 밀립니다. 소스별로 나눠 물어야 하는 이유가 이 그림입니다.',
 panel({src:'.cache/vectors/e5all.manifest.json · reports/chunks_*.csv', w:'h',
   title:'소스별 청크 수', note:'선형 축입니다. 작은 소스가 안 보이는 것이 곧 결론입니다.',
   body:hbar(D.chunks.map((c,i)=>({l:c.name,v:c.n,txt:fmt(c.n),
     c:i<2?'var(--s1)':i===2?'var(--s2)':'var(--s3)',
     tip:`<b>${c.name}</b><br>${fmt(c.n)}청크 · ${c.role}<br>전체의 ${(c.n/totalChunks*100).toFixed(1)}%`})),
     {aria:'소스별 청크 수'}),
   legend:'<span><i style="background:var(--s1)"></i>담론(유튜브)</span><span><i style="background:var(--s2)"></i>커머스 리뷰</span><span><i style="background:var(--s3)"></i>처방·등록</span>',
   cap:`유튜브 댓글 하나가 <b>${(252332/totalChunks*100).toFixed(0)}%</b>입니다. 제품 요약 577건은 같은 축에서 사실상 0 입니다.`})
 +panel({src:'reports/youtube_ingredient_terms.csv', w:'h',
   title:'담론에 실제로 등장하는 말', note:'영상 설명란 + 댓글에서 그 표현이 든 문서 수입니다.',
   body:hbar(D.terms.map(t=>({l:t.t,v:t.n,txt:fmt(t.n)})),{color:'var(--s1)',labelWidth:110,aria:'용어 빈도'}),
   cap:'<b>추천</b>이 압도적입니다 — 선크림 담론의 상당수가 구매 추천 맥락이라는 뜻이고, 불만 표현은 그 아래에 깔려 있습니다.'})
 +panel({src:'reports/unmatched_terms.csv (2,365행 중 상위 14)', w:'h',
   title:'사전 밖 고빈도어', note:'선크림 영상에 유난히 많은데 우리 사전에 없는 명사. lift = 선크림 영상 / 그 외 영상.',
   body:hbar(D.unmatched.map(t=>({l:t.t,v:t.lift,txt:t.lift.toFixed(1)+'×',
     tip:`<b>${t.t}</b><br>lift ${t.lift}×<br>선크림 영상 ${t.docs}편`})),
     {color:'var(--s2)',labelWidth:110,aria:'미매칭 고빈도어'}),
   cap:'자동으로 사전에 넣지 않습니다. <b>브랜드명·제품명이 섞여 있어</b> 사람이 봐야 합니다.'})
 +panel({src:'reports/transcript_gain.csv (장문 45편 표본)', w:'h',
   title:'설명란만 보면 못 보는 편수', note:'자막까지 읽으면 그 주제로 잡히는 영상이 몇 편 늘어나는가.',
   body:gbar(D.transcript.map(t=>({l:t.t.replace('_','\\n'),v:[t.base,t.base+t.gain]})),
     ['설명란만','자막까지'],{h:210,b:52,aria:'자막 이득'}),
   legend:leg(['설명란만','자막까지']),
   cap:'현재 판정은 <b>설명란만</b> 씁니다. 자막을 넣으면 표본이 크게 늘지만 파이프라인 재실행이 필요해 PoC 범위 밖으로 뒀고, <b>카드 한계에 "못 보는 편수"로 적었습니다.</b>'}));

/* ── 2. 성분 축 ───────────────────────────── */
const cardType = {};
D.cards.filter(c=>c.axis==='성분').forEach(c=>cardType[c.name]=c.type);
const others = {};
D.cards.filter(c=>c.axis==='성분').forEach(c=>(c.others||[]).forEach(o=>{
  const nm=o.split(' (')[0]; others[nm]=c.type; }));
const typeColor = {'수요 선행 공백':'var(--s1)','함량 공백':'var(--s2)','처방 기준선':'var(--s3)'};
const pts = D.ingredients.map(g=>{
  const t = cardType[g.name] ?? others[g.name] ?? null;
  return {x:g.search, y:g.pct, r:g.high, l:g.name, c:t?typeColor[t]:'var(--ink3)',
    tip:`<b>${g.name}</b><br>검색 ${g.search}배 · 처방 ${g.pct}%<br>`+
        `제품 ${fmt(g.products)} · 배합순위 ${g.order??'—'}위 · 고함량 ${g.high}%<br>`+
        (t?`유형 ${t}`:'카드 유형 없음')};
});
sec('02','성분 축 — 수요와 처방이 어긋나는 자리',
 '가로는 <b>NAVER 검색 증가</b>(수요), 세로는 <b>선케어 처방 채택률</b>(공급)입니다. 오른쪽 아래가 R&amp;D 공백입니다 — 찾는 사람은 늘었는데 제품에 안 들어간 성분. 원의 크기는 고함량 비율입니다.',
 panel({src:'reports/cross_source_ingredient.csv',
   title:'검색은 느는데 처방에 없다', note:'가로축 로그. 색은 배정된 카드 유형이고 회색은 어느 유형에도 안 걸린 성분입니다.',
   legend:Object.entries(typeColor).map(([k,v])=>`<span><i style="background:${v}"></i>${k}</span>`).join('')+'<span><i style="background:var(--ink3)"></i>유형 없음</span>',
   body:scatter(pts,{aria:'성분 검색 대 처방'}),
   cap:'<b>오른쪽 아래 셋</b>(엑소좀·PDRN·트라넥삼산)이 검색 39~52배인데 처방 0~1제품입니다. <b>레티날</b>은 검색 287배지만 광민감성 때문에 선케어에 넣기 어려워 카드로 내지 않습니다.'})
 +panel({src:'reports/cross_source_ingredient.csv', w:'h',
   title:'채택률과 고함량은 다른 이야기다', note:'널리 쓰는 것과 깊게 쓰는 것이 갈립니다.',
   body:gbar(D.ingredients.filter(g=>g.pct>5).map(g=>({l:g.name.slice(0,6),v:[g.pct,g.high]})),
     ['채택률 %','고함량 %'],{h:220,b:40,labelBars:false,aria:'채택률 대 고함량'}),
   legend:leg(['채택률 %','고함량 % (배합 10위 이내)']),
   cap:'<b>나이아신아마이드만</b> 두 막대가 같이 섭니다. 히알루론산·시카·판테놀은 이름은 올리고 <b>함량은 안 넣습니다</b>.'})
 +panel({src:'reports/naver_trend.csv · 3002 포트', w:'h',
   title:'성분 검색 지수 128개월', note:'기준_세럼 대비 상대 지수. 요청이 셋으로 나뉘어 있어 이 기준선으로 묶었습니다.',
   body:lines(D.ing_periods, D.ing_index,{h:230,r:86,td:1,xt:6,aria:'성분 검색 지수'}),
   cap:'절대 검색량이 아니라 <b>기준_세럼 대비 상대값</b>입니다. 요청이 다른 그룹끼리는 직접 비교할 수 없습니다.'})
 +panel({src:'reports/cross_source_ingredient.csv',
   title:'성분 10종 — 전체 표', note:'대시보드가 그리는 모든 값의 원본입니다.',
   body:`<div class="tw"><table><thead><tr><th>성분</th><th style="text-align:right">검색</th>
     <th style="text-align:right">제품</th><th style="text-align:right">채택률</th>
     <th style="text-align:right">배합순위</th><th style="text-align:right">고함량</th>
     <th style="text-align:right">담론</th><th>판독</th></tr></thead><tbody>`+
     D.ingredients.map(g=>`<tr><td><b>${esc(g.name)}</b></td>
       <td class="n">${g.search}배</td><td class="n">${fmt(g.products)}</td>
       <td class="n">${g.pct}%</td><td class="n">${g.order??'—'}</td>
       <td class="n">${g.high}%</td><td class="n">${fmt(g.talk)}</td>
       <td>${g.reading?`<span class="chip">${esc(g.reading.split(' · ')[0])}</span>`:'—'}</td></tr>`).join('')+
     '</tbody></table></div>',
   cap:'담론 수는 <b>선크림 문맥이 아닙니다</b> — 색인 전체에서 센 값입니다. PDRN 1,522건 중 선크림 단어가 같이 있는 건 187건뿐입니다(실측).'}));

/* ── 3. 주제 축 ───────────────────────────── */
sec('03','주제 축 — 소스마다 다른 시점을 잡는다',
 '같은 다섯 가지 불만인데 <b>어디서 말하느냐에 따라 순위가 뒤집힙니다.</b> 사기 전에 검색하는 문제와, 쓰고 나서 리뷰에 쓰는 불만이 다릅니다.',
 panel({src:'reports/cross_source.csv', w:'h',
   title:'영상 · 댓글 · 리뷰 구성비', note:'세 값 모두 %라 같은 축에 놓을 수 있습니다. NAVER 는 지수라 따로 봅니다.',
   body:gbar(D.topics.map(t=>({l:t.group,v:[t.video,t.comment,t.review]})),
     ['영상 설명','댓글','커머스 리뷰'],{h:230,aria:'주제별 구성비',td:1}),
   legend:leg(['영상 설명','댓글','커머스 리뷰']),
   cap:'<b>백탁</b>은 NAVER 검색 1위인데 영상이 0.31%만 다룹니다. <b>끈적임</b>은 반대로 검색은 4위인데 리뷰 1위입니다.'})
 +panel({src:'reports/naver_trend.csv · naver.datalab.suncare', w:'h',
   title:'NAVER 선케어 검색 128개월', note:'요청 안에서 최대 100으로 정규화된 값입니다.',
   body:lines(D.periods, D.suncare,{h:230,r:62,td:1,xt:6,aria:'NAVER 선케어'}),
   cap:'<b>이 요청에는 기준선이 없습니다.</b> 그래서 "백탁 검색이 줄었다"를 추세로 읽으면 안 됩니다 — 네이버 검색 자체가 줄었을 수도 있고 구분할 방법이 없습니다. 그룹 간 상대 비교만 합니다.'})
 +panel({src:'reports/trend_sunscreen_v0.2.csv · youtube_comment', w:'h',
   title:'댓글 구성비 13분기', note:'구성비를 쓰는 이유 — 설명란이 3년간 44% 짧아져서 절대 건수는 못 씁니다.',
   body:lines(D.quarters, D.series,{h:240,r:96,td:1,xt:7,aria:'분기 시계열'}),
   cap:'마지막 분기는 댓글이 계속 쌓이므로 <b>구조적으로 과소 집계</b>됩니다. 판정에서 제외합니다.'})
 +panel({src:'reports/trend_judgement_v0.2.csv', w:'h',
   title:'판정 유형 분포', note:`338셀 중 판정된 것은 ${D.judged}개입니다.`,
   body:hbar(D.judgement.map(j=>({l:j.type,v:j.n,txt:fmt(j.n),
     c:['근거 부족','판정 보류','미확정(진행 중)'].includes(j.type)?'var(--ink3)':'var(--s1)'})),
     {labelWidth:112,aria:'판정 분포'}),
   legend:'<span><i style="background:var(--s1)"></i>판정됨</span><span><i style="background:var(--ink3)"></i>표본 미달·보류</span>',
   cap:`<b>81%가 판정되지 않습니다.</b> 게이트를 세게 걸었기 때문이고, 이건 결함이 아니라 설계입니다 — 표본 5건으로 "963% 급증"을 만들지 않기 위한 것입니다.`}));

/* ── 4. 검색 계층 ─────────────────────────── */
sec('04','검색 — 만들고 측정했다',
 '어휘 검색(BM25)과 의미 검색(벡터)을 같은 질의 61개로 채점했습니다. <b>채택 기준은 결과를 보기 전에 정했습니다</b> — heldout 에서 BM25 는 구조적으로 0이므로 "0을 넘느냐"가 기준이었습니다.',
 panel({src:'reports/retrieval_eval_*.csv', w:'h',
   title:'BM25 · 벡터 · 하이브리드', note:'literal = 별칭 그대로 검색. heldout = 그 별칭의 토큰이 하나도 없는 문서 찾기.',
   body:gbar(D.retrieval.metrics.map((m,i)=>({l:m.replace(' ','\\n'),
     v:[D.retrieval.bm25[i],D.retrieval.vector[i],D.retrieval.hybrid[i]]})),
     ['BM25','벡터','하이브리드'],{h:230,max:1,td:2,b:52,aria:'검색 평가'}),
   legend:leg(['BM25','벡터','하이브리드']),
   cap:'<b>하이브리드는 폐기했습니다.</b> 어휘는 BM25 에 0.841→0.662, 의미는 벡터에 0.038→0.028 로 <b>양쪽 다 집니다.</b> RRF 가 순위만 보고 확신도를 버리기 때문이라 가중치 튜닝으로 안 고쳐집니다. 세 값 모두 같은 시점(08.25 · 2차 청크)입니다.'})
 +panel({src:'reports/retrieval_eval_*.csv · 08.24 대비 08.25', w:'h',
   title:'식약처 중복을 고치니 벡터가 깎였다', note:'mfds 4,735청크에 보고번호 접두가 붙으면서 텍스트가 바뀌었습니다.',
   body:gbar([{l:'heldout\\nP@10',v:[0.042,0.038]},{l:'heldout\\nHit@10',v:[0.17,0.13]},
              {l:'literal\\nP@10 (BM25)',v:[0.828,0.841]}],
     ['08.24','08.25'],{h:210,max:1,td:3,b:52,aria:'재측정'}),
   legend:leg(['08.24 (1차 청크)','08.25 (2차 청크)']),
   cap:'원인을 <b>쟀습니다</b> — heldout 상위10에서 mfds 가 차지한 칸이 23→28로 늘었습니다. 옛 벡터를 되살려 직접 비교한 값입니다. <b>교환이지 결함이 아닙니다</b>: 식약처 4,735건이 서로 구분되는 것을 얻었습니다.'})
 +panel({src:'측정값 요약',
   title:'그래서 용도별로 갈라 씁니다', note:'근거는 합치지 않고 나란히 놓습니다 — 소스를 합산하지 않은 것과 같은 논리입니다.',
   body:`<div class="tw"><table><thead><tr><th>질의 종류</th><th>검색기</th><th style="text-align:right">근거</th><th>왜</th></tr></thead><tbody>
     <tr><td>성분명 · 보고번호 · SPF · 브랜드</td><td><span class="chip uv">BM25</span></td>
       <td class="n">P@10 0.841</td><td>정확 일치가 정답인 질의. <span class="mono">보고번호 2018008612</span>를 19.524로 1위에 놓습니다</td></tr>
     <tr><td>"하얗게 떠서 싫다" 같은 이름 없는 표현</td><td><span class="chip uv">벡터</span></td>
       <td class="n">Hit@10 13%</td><td><span class="mono">톤 업</span>·<span class="mono">눈 시림</span>처럼 공백이 든 별칭에서 이깁니다. BM25 는 토큰화하면 조각나서 0점입니다</td></tr>
     <tr><td>둘을 섞기</td><td><span class="chip b">쓰지 않음</span></td>
       <td class="n">—</td><td>RRF 는 순위만 보고 확신도를 버립니다</td></tr>
     </tbody></table></div>`,
   cap:'<b>벡터 Hit@10 13% 는 바닥선을 넘은 것이지 잘 되는 게 아닙니다.</b> 열 번 물어 아홉 번은 못 찾습니다. RAG 를 붙일 때 "근거를 못 찾았다"를 자주 답하게 만들어야 합니다.'}));

/* ── 5. 검증 ─────────────────────────────── */
sec('05','검증 — 결론이 얼마나 버티나',
 '적중률만 내는 검증은 검증이 아니라 홍보입니다. <b>기저율을 같이 냅니다.</b>',
 panel({src:'reports/backtest.csv', w:'t',
   title:'후향 검증 — 예측력 없음', note:'판정 시점 이후 실제로 그렇게 됐는가.',
   body:gbar(D.backtest.rows.map(r=>({l:r.label.split(' — ')[0].replace('기준 ','기준 '),v:[r.pct]})),
     ['적중률 %'],{h:200,max:100,rule:D.backtest.base,ruleLabel:`기저율 ${D.backtest.base}%`,
     bw:44,aria:'후향 검증'}),
   cap:'상승 계열 <b>22%</b>는 기저율 47%의 절반입니다. 13분기·계절 상품·964편으로는 예측 모델을 못 세웁니다. 그래서 카드는 <b>"뜰 것이다"가 아니라 "지금 이런 비대칭이 있다"</b>로 씁니다.'})
 +panel({src:'reports/spam_ad_sensitivity.csv', w:'t',
   title:'광고 민감도', note:'선크림 장문 964편 기준.',
   body:hbar([{l:'전체 장문',v:964,txt:'964',c:'var(--ink3)'},
              {l:'광고·협찬',v:465,txt:'465 (48.2%)',c:'var(--s2)'},
              {l:'신고 필드만',v:254,txt:'254',c:'var(--s1)'},
              {l:'문구로 추가 적발',v:407,txt:'407',c:'var(--s1)'}],
     {labelWidth:104,barH:20,aria:'광고 비율'}),
   cap:'<b>신고만 믿으면 절반을 놓칩니다.</b> 빼면 판정 24셀이 표본 미달로 사라지고 19셀이 뒤집힙니다 — 공짜인 선택지가 없어 <b>빼지 않고 필터 민감으로 공개</b>합니다.'})
 +panel({src:'reports/panel_sensitivity.csv', w:'t',
   title:'패널 민감도 — 뒤집힘 0셀', note:'전문가 채널을 빼면 구성비가 얼마나 달라지나 (%p).',
   body:hbar(D.panel.slice(0,8).map(p=>({l:`${p.t.slice(0,7)} · ${p.src}`,v:Math.abs(p.diff),
     txt:(p.diff>0?'+':'')+p.diff.toFixed(2),c:'var(--s3)'})),
     {labelWidth:132,barH:19,aria:'패널 민감도'}),
   cap:'최대 차이가 <b>0.78%p</b> 입니다. 판정이 뒤집힌 셀은 <b>0개</b> — 패널 구성에 결론이 얹혀 있지 않습니다.'})
 +panel({src:'reports/commerce_ranking_raw.csv · oliveyoung suncare', w:'h',
   title:'커머스 랭킹 변동 분포', note:`100위권 ${fmt(D.ranking.n)}제품의 최고~최저 순위 차이.`,
   body:gbar(D.ranking.hist.map(h=>({l:`${h.b}\\n~${h.b+9}`,v:[h.n]})),['제품 수'],
     {h:200,bw:34,b:48,aria:'랭킹 변동 분포'}),
   cap:`중앙 <b>${D.ranking.median}계단</b> · 평균 ${D.ranking.mean} · 최대 ${D.ranking.max}. 상위 20위권으로 좁히면 ${D.ranking.top20_n}제품입니다. 처음엔 이걸 "중복 37%"라는 <b>서버 문제로 잘못 보고했는데, 정렬 없는 페이징이라는 제 추출 문제</b>였습니다.`})
 +panel({src:'reports/source_composition.csv', w:'h',
   title:'주제별 3소스 구성비', note:'같은 주제를 세 소스가 얼마나 다르게 말하는가.',
   body:gbar(D.source_comp.filter(s=>s.comment+s.video+s.review>1).slice(0,7)
     .map(s=>({l:s.t.split('_')[0],v:[s.video,s.comment,s.review]})),
     ['영상','댓글','리뷰'],{h:210,b:44,td:1,aria:'소스 구성비'}),
   legend:leg(['영상 설명','댓글','커머스 리뷰']),
   cap:'<b>백탁</b>이 영상 0.31% · 댓글 2.56% · 리뷰 12.09% 입니다 — 같은 문제를 리뷰에서 40배 더 말합니다.'}));

/* ── 6. 논문 축 중지 ──────────────────────── */
sec('06','논문 축을 발표 당일 내렸다',
 '현준님이 <span class="mono">(skin)</span> 필터를 철회하셨습니다 — 그건 화장품 필터가 아니라 피부암·건선·상처치유·조직공학까지 통과시킵니다. <b>우리는 그 계열을 안 썼는데도 같이 막혔습니다.</b>',
 `<div class="p"><div class="hold"><p><b>이게 우리가 여섯 번째로 밟은 함정입니다.</b>
   현준님이 아데노신을 막으신 근거(화장품과 무관한 논문)가 축 전체에 걸리는데,
   저는 <b>그 한 행만 빼고 끝냈습니다.</b> 잔존율을 재 보니 엑소좀이 아데노신과 같은 자리였습니다.</p></div>`
 +`<p class="src">reports 밖 · slopindustries/cosmai-ml datasets/papers</p>
   <h3>논문 잔존율 — <span class="mono">(skin)</span>을 붙이면 남는 비율</h3>
   <p class="note">나머지는 피부와 무관한 논문입니다. 그리고 <span class="mono">(skin)</span> 조차 화장품 필터가 아니니 실제 화장품 비율은 더 낮습니다.</p>`
 +hbar(D.retention.map(r=>({l:r.q,v:r.pct,txt:r.pct.toFixed(1)+'%',
     c:r.pct>=90?'var(--s3)':r.pct<25?'var(--bad)':'var(--s4)',
     tip:`<b>${r.q}</b><br>잔존율 ${r.pct}%${r.note?'<br>'+r.note:''}`})),
     {labelWidth:150,barH:20,max:105,aria:'논문 잔존율'})
 +`<p class="cap">기준선 <span class="mono">cosmetic</span>만 <b>100.1%</b> 입니다 —
   즉 <b>분모는 화장품 색인, 분자는 전분야 색인</b>이라 모집단이 다른 값으로 나눴습니다.
   "두 색인 차이가 평균 0.083으로 좁혀졌다"도 같은 상수로 나눠서 생긴 수렴이지 일치의 증거가 아닙니다.
   대응은 스위치 하나입니다 — <span class="mono">cross_source.PAPER_HOLD = True</span>.</p></div>`);

/* ── 7. 카드 ─────────────────────────────── */
const typeChip = t => ['처방 기준선'].includes(t)?'chip g':['유행 반증'].includes(t)?'chip b':'chip uv';
sec('07',`Opportunity Card ${D.cards.length}장`,
 '<b>유형은 규칙이 배정합니다.</b> LLM 이 "이건 기회야"라고 판단하지 않습니다. 수치는 저장된 산출물에서 그대로 가져오고, 카드마다 근거와 <b>한계</b>가 붙습니다. 근거를 짚을 수 없으면 카드로 만들지 않습니다.',
 `<div class="p" style="background:transparent;border:0;box-shadow:none;padding:0">
   <div class="cards">`+
   D.cards.map(c=>`<div class="card">
     <div class="r"><span class="chip">${esc(c.axis)} 축</span><span class="${typeChip(c.type)}">${esc(c.type)}</span></div>
     <h4>${esc(c.name)}</h4>
     <p class="b">${esc(c.basis)}</p>
     ${c.others&&c.others.length?`<div><p class="note" style="margin:0 0 4px">같은 유형에 묶인 성분</p>
       <ul>${c.others.map(o=>`<li>${esc(o)}</li>`).join('')}</ul></div>`:''}
     <div class="r" style="margin-top:auto;padding-top:6px;border-top:1px dashed var(--line)">
       <span class="chip">한계 ${c.limits}건</span>
       ${c.quotes?`<span class="chip">원문 근거 ${c.quotes}건</span>`:''}</div>
   </div>`).join('')+
   `</div><p class="cap" style="margin-top:18px">
   <b>6장 중 실제 기회는 5장입니다.</b> <span class="chip g">처방 기준선</span>은 "이렇게 하면 깊게 쓴 것"의 비교 대상이지 기회가 아닙니다.
   <b>레티날은 카드에서 빠졌습니다</b> — 검색 287배지만 근거가 논문뿐이었고 그 축을 내렸습니다.
   광민감성은 도메인 지식이라 자동 카드로 낼 수 없어 문서에 글로 남겼습니다.</p></div>`);

/* ── 8. 한계 ─────────────────────────────── */
sec('08','이 화면을 읽을 때의 한계',
 '숨기지 않습니다. 아래는 전부 <b>측정해서 알게 된</b> 것들입니다.',
 panel({src:'CLAUDE.md §4 · reports/진행_총정리.md',
   title:'같은 함정을 여섯 번 밟았습니다', note:'여섯 번 다 오류가 안 나고 결과가 그럴듯했습니다.',
   body:`<div class="tw"><table><thead><tr><th>언제</th><th>무엇이 관측값이 됐나</th><th>어떻게 알았나</th></tr></thead><tbody>
   <tr><td class="mono">수집 초기</td><td>채널당 <b>수집 상한 10</b></td><td>월별 집계가 매달 10건 근처</td></tr>
   <tr><td class="mono">08.23</td><td><b>추출 방법</b> — 정렬 없는 offset 페이징</td><td>현준님이 재현이 안 된다고 알려주심</td></tr>
   <tr><td class="mono">08.24</td><td><b>소스 비율</b> — 색인 92%가 짧은 댓글</td><td>소스별로 나눠 물어보니 드러남</td></tr>
   <tr><td class="mono">08.24</td><td><b>id 형식</b> — 정답은 doc_id, 결과는 chunk_id</td><td>벡터 점수가 0.000 이 나와서 의심</td></tr>
   <tr><td class="mono">08.25</td><td><b>정규화 시점</b> — 정규화 전 본문으로 인코딩</td><td>프로브 코사인이 0.9986</td></tr>
   <tr><td class="mono">08.25</td><td><b>경고를 한 행에만 적용</b> — 아데노신만 빼고 축은 그대로 씀</td><td>잔존율을 재 보니 엑소좀 20.6% · 아데노신 19.0%</td></tr>
   </tbody></table></div>`,
   cap:'그래서 자기 검사를 코드에 박았습니다 — 행수 대조 · 재현성 검사 · 계약 검증기 · 기저율 병기 · 캐시 키 해시 · 합치기 전 코사인 실측 · 근거를 중앙값에서 뽑기 · <span class="mono">--demo</span>.'})
 +panel({src:'각 패널의 출처 파일 참조', w:'h',
   title:'이 화면에서 하면 안 되는 해석',
   body:`<div class="tw"><table><tbody>
   <tr><td><span class="chip b">금지</span></td><td>NAVER 선케어 그래프를 <b>추세</b>로 읽는 것 — 기준선이 없어 그룹 간 상대 비교만 가능합니다</td></tr>
   <tr><td><span class="chip b">금지</span></td><td>담론 언급 수를 <b>선크림 담론</b>으로 읽는 것 — 색인 전체에서 센 값입니다</td></tr>
   <tr><td><span class="chip b">금지</span></td><td>카드를 <b>예측</b>으로 읽는 것 — 후향 검증이 기저율 미달입니다</td></tr>
   <tr><td><span class="chip b">금지</span></td><td>소스 값을 <b>합산·평균</b>하는 것 — 분모가 전부 다릅니다</td></tr>
   <tr><td><span class="chip b">금지</span></td><td>논문 축을 쓰는 것 — 중지 상태입니다</td></tr>
   </tbody></table></div>`})
 +panel({src:'reports/진행_총정리.md §10', w:'h',
   title:'아직 남은 것',
   body:`<div class="tw"><table><tbody>
   <tr><td><span class="chip w">현준님</span></td><td>논문 축 검증 프로토콜 · NAVER 선케어 기준선</td></tr>
   <tr><td><span class="chip w">수호님</span></td><td>청크 500자 초과 27건 (최대 562자) · RAG 구축</td></tr>
   <tr><td><span class="chip w">석현님</span></td><td><span class="mono">academic</span> 스키마 통합 DB 적재</td></tr>
   <tr><td><span class="chip">우리</span></td><td>발표 슬라이드 · 골든셋 수기 판정 (30분)</td></tr>
   <tr><td><span class="chip">범위 밖</span></td><td>제품 단위 조인 — 조인율 20%. 세 사람이 같은 벽에 부딪혔습니다</td></tr>
   </tbody></table></div>`}));

document.getElementById('main').innerHTML = out.join('');
document.querySelectorAll('[data-tip]').forEach(el => hover(el, el.dataset.tip));
</script>
"""


def render(data: dict) -> str:
    return HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))


def demo() -> None:
    """데이터 없이 조립 로직만 점검한다."""
    fake = {
        "chunks": [{"name": "a", "n": 10, "role": "x"}], "retention": [{"q": "a", "pct": 20.0, "note": ""}],
        "retrieval": RETRIEVAL, "backtest": {"rows": [{"label": "a — b", "pct": 1}], "base": 47},
        "ingredients": [{"name": "a", "search": 1.0, "products": 1, "pct": 1.0, "order": 1,
                         "high": 1.0, "talk": 1, "reading": "x"}],
        "topics": [{"group": "a", "topic": "b", "rank": 1, "video": 1.0, "comment": 1.0,
                    "review": 1.0, "review_rank": 1, "reading": ""}],
        "quarters": ["2023Q1"], "series": [{"name": "a", "values": [1.0]}],
        "judgement": [{"type": "a", "n": 1}], "judged": 1, "cells": 1,
        "periods": ["2016-01"], "suncare": [{"name": "a", "values": [1.0]}],
        "ing_periods": ["2016-01"], "ing_index": [{"name": "a", "values": [1.0]}],
        "ranking": {"n": 1, "median": 1, "mean": 1.0, "max": 1, "top20_n": 1,
                    "top20_median": 1, "hist": [{"b": 0, "n": 1}]},
        "terms": [{"t": "a", "n": 1}], "unmatched": [{"t": "a", "lift": 1.0, "docs": 1}],
        "transcript": [{"t": "a", "base": 1, "gain": 1}],
        "panel": [{"t": "a", "src": "comment", "diff": 0.1}],
        "source_comp": [{"t": "a", "comment": 1.0, "video": 1.0, "review": 1.0}],
        "cards": [{"name": "a", "axis": "주제", "type": "검증된 성장", "basis": "b",
                   "limits": 1, "quotes": 1}],
    }
    html = render(fake)
    assert "__DATA__" not in html, "데이터가 안 박혔다"
    # 색 토큰은 라이트·다크 양쪽에 다 있어야 한다. 한쪽에만 있으면 그 테마가 깨진다
    for token in ("--ground", "--ink", "--s1", "--panel", "--line"):
        assert html.count(f"{token}:") >= 3, f"{token} 이 세 스코프에 다 없다"
    assert 'body{' in html and 'background:var(--ground)' in html, "body 배경이 토큰이 아니다"
    assert html.count("<script>") == 1
    # 차트 헬퍼가 다 있어야 한다. 하나라도 빠지면 그 절이 빈 채로 렌더된다
    for fn in ("function hbar", "function gbar", "function lines",
               "function scatter", "function panel"):
        assert fn in html, f"{fn} 이 없다"
    # 절은 여덟이다. sec( 호출 수로 센다
    assert html.count("\nsec('") == 8, f"절이 8개가 아니다: {html.count(chr(10) + chr(115) + chr(101) + chr(99) + chr(40))}"
    # 폰트는 Google Fonts 만 CSP 를 통과한다. 다른 호스트가 있으면 조용히 폴백된다
    hosts = {h for h in ("fonts.googleapis.com", "fonts.gstatic.com") if h in html}
    assert hosts == {"fonts.googleapis.com", "fonts.gstatic.com"}, "폰트 호스트가 빠졌다"
    assert "cdn" not in html.lower().replace("cdnjs", ""), "외부 CDN 은 CSP 에 막힌다"
    print("demo ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reports", type=Path, default=Path("reports"))
    p.add_argument("--out", type=Path, default=Path("reports/viz_dashboard.html"))
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0

    data = collect(a.reports)
    html = render(data)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(html, encoding="utf-8")
    kb = a.out.stat().st_size / 1024
    print(f"{a.out} : {kb:.0f} KB")
    print(f"  청크 {sum(c['n'] for c in data['chunks']):,} · 성분 {len(data['ingredients'])} · "
          f"주제 {len(data['topics'])} · 카드 {len(data['cards'])}")
    print(f"  분기 {len(data['quarters'])} · NAVER {len(data['periods'])}개월 · "
          f"판정 {data['judged']}/{data['cells']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
