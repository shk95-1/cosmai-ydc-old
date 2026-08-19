#!/usr/bin/env python3
"""분기별 주제 트렌드를 자기완결 HTML 한 장으로 뽑는다.

주제는 topics.py의 `match_topics`가 정한다. 키워드를 손으로 넘기지 않는 이유:
사전이 두 개가 되면 경계 매칭(`PA` -> `coupang` 오탐 16%)이 한쪽에만 적용된다.

외부 리소스를 참조하지 않는다. 사설망에서도 그대로 뜨고, 열어본 시각이
제3자에게 새지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import html
from collections import defaultdict
from pathlib import Path

from topics import TOPICS
from topics import match_topics
from trend import quarter


def latest_views(path: Path) -> dict[str, int]:
    """video_id별 최신 조회수. 같은 영상이 여러 번 수집됐으면 마지막 것만 쓴다.

    trend.py v0.2가 조회수를 쓰지 않게 되면서 이 함수를 여기로 옮겼다.
    이 파일만 쓰는 함수이므로 여기 두는 것이 맞다.
    """
    best: dict[str, tuple[str, int]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            video_id, collected_at = row["video_id"], row["collected_at"]
            views = int(row["view_count"] or 0)
            if video_id not in best or collected_at > best[video_id][0]:
                best[video_id] = (collected_at, views)
    return {video_id: views for video_id, (_, views) in best.items()}


def series(run_dir: Path) -> tuple[list[str], dict[str, dict[str, float]], dict[str, int]]:
    views = latest_views(run_dir / "video_metrics.csv")
    total: dict[str, int] = defaultdict(int)
    channels: dict[str, set[str]] = defaultdict(set)
    hits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    hit_views: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    with (run_dir / "videos.csv").open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            month = row["analysis_month"]
            if not month:
                continue
            q = quarter(month)
            total[q] += 1
            channels[q].add(row["channel_id"])
            text = f"{row['title_normalized']} {row['description_normalized']}"
            for topic in match_topics(text):
                hits[topic][q] += 1
                hit_views[topic][q] += views.get(row["video_id"], 0)

    quarters = sorted(total)
    shares = {
        topic: {q: hits[topic].get(q, 0) / total[q] for q in quarters}
        for topic in hits
    }
    return quarters, shares, dict(total)


def sparkline(values: list[float], ceiling: float, width: int = 132, height: int = 30) -> str:
    """모든 행이 같은 y축(ceiling)을 쓴다. 행끼리 높이를 비교할 수 있어야 한다."""
    if len(values) < 2 or ceiling <= 0:
        return ""
    step = width / (len(values) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - (v / ceiling) * (height - 4) - 2:.1f}"
        for i, v in enumerate(values)
    )
    last_x, last_y = points.split()[-1].split(",")
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-hidden="true">'
        f'<polyline points="{points}" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2.6" fill="currentColor"/></svg>'
    )


def render(run_dir: Path, quarters, shares, total) -> str:
    note = {t["topic"]: t["note"] for t in TOPICS}
    ceiling = max((v for row in shares.values() for v in row.values()), default=0.0)
    ordered = sorted(
        shares, key=lambda t: shares[t][quarters[-1]] - shares[t][quarters[0]], reverse=True
    )

    rows = []
    for topic in ordered:
        vals = [shares[topic][q] for q in quarters]
        delta = vals[-1] - vals[0]
        cells = "".join(f"<td class=num>{v:.3f}</td>" for v in vals)
        sign = "up" if delta > 0.02 else "down" if delta < -0.02 else "flat"
        rows.append(
            f"<tr><th>{html.escape(topic)}<small>{html.escape(note[topic])}</small></th>"
            f"<td class=spark>{sparkline(vals, ceiling)}</td>{cells}"
            f"<td class='num {sign}'>{delta:+.3f}</td></tr>"
        )

    heads = "".join(f"<th class=num>{q}</th>" for q in quarters)
    denom = "".join(f"<td class=num>{total[q]}</td>" for q in quarters)
    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>선크림 주제 트렌드 — {html.escape(run_dir.name)}</title>
<style>
:root {{ color-scheme: light dark;
  --bg:#fbfbfa; --panel:#fff; --line:#e4e4e1; --ink:#1a1a18; --dim:#6b6b66;
  --up:#a03434; --down:#2f6f4f; --flat:#8a8a84; }}
@media (prefers-color-scheme: dark) {{ :root {{
  --bg:#17181a; --panel:#1f2124; --line:#2e3135; --ink:#e8e8e4; --dim:#9a9a93;
  --up:#e08585; --down:#7fc9a0; --flat:#757570; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; padding:24px; background:var(--bg); color:var(--ink);
  font:14px/1.55 ui-sans-serif,system-ui,"Segoe UI",sans-serif }}
h1 {{ font-size:17px; margin:0 0 4px }}
.src {{ color:var(--dim); font-size:12px; margin-bottom:18px }}
.warn {{ border-left:3px solid var(--up); background:var(--panel); padding:10px 14px;
  margin:0 0 18px; font-size:13px; max-width:900px }}
table {{ border-collapse:collapse; background:var(--panel); border:1px solid var(--line);
  border-radius:8px; overflow:hidden; font-variant-numeric:tabular-nums }}
th,td {{ padding:8px 12px; border-bottom:1px solid var(--line); text-align:left }}
thead th {{ font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--dim) }}
tbody th {{ font-weight:600; max-width:230px }}
tbody th small {{ display:block; font-weight:400; color:var(--dim); font-size:11px; line-height:1.35 }}
.num {{ text-align:right; font-variant-numeric:tabular-nums }}
.spark {{ color:var(--dim); padding:4px 12px; width:150px }}
.up {{ color:var(--up); font-weight:600 }}
.down {{ color:var(--down); font-weight:600 }}
.flat {{ color:var(--flat) }}
tfoot td,tfoot th {{ color:var(--dim); font-size:12px; border-top:2px solid var(--line) }}
tr:last-child td, tr:last-child th {{ border-bottom:none }}
</style>
<h1>선크림 주제 트렌드 — 분기별 언급 점유율</h1>
<p class=src>출처: YouTube Data API v3 · {html.escape(run_dir.name)} · 주제 사전 topics.py ·
값은 <code>해당 주제 언급 영상 / 분기 전체 영상</code></p>
<div class=warn><b>이 숫자를 절대 추세로 읽지 마세요.</b> 분모는 검색어 6개 × 월별 상한 10편으로
모은 결과라 실제 발행량이 아닙니다. {quarters[0]}·{quarters[-1]}는 두 달치 부분 분기입니다.
채널 업로드 전수 수집(<code>collect_channel_uploads.py</code>) 후 재산출이 필요합니다.</div>
<table>
<thead><tr><th>주제</th><th>추이</th>{heads}<th class=num>변화</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
<tfoot><tr><th>분모 (분기 전체 영상)</th><td></td>{denom}<td></td></tr></tfoot>
</table>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="분기별 주제 트렌드 HTML 리포트")
    ap.add_argument("run_dir", type=Path, help="정규화된 run 디렉터리")
    ap.add_argument("-o", "--output", type=Path, default=Path("reports/trend_report.html"))
    args = ap.parse_args()

    quarters, shares, total = series(args.run_dir)
    assert quarters, "분기가 하나도 없습니다 — analysis_month가 비었는지 확인하세요"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(args.run_dir, quarters, shares, total), encoding="utf-8")
    print(f"[report] {args.output} — 주제 {len(shares)}개 × 분기 {len(quarters)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
