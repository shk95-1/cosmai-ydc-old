from pathlib import Path
p = Path("build.py"); s = p.read_text(encoding="utf-8")
n = 0

def rep(a, b):
    global s, n
    assert a in s, f"못 찾음:\n{a[:110]}"
    s = s.replace(a, b, 1); n += 1

# ── 15 검증 표 — 열 폭 · 판정 색 · 각주 위치 ──────────────────
rep('], size=10.5, head_size=11.5, row_h=Inches(0.44))\ntbl.top = Inches(2.45)',
    '], size=10.5, head_size=11.5, row_h=Inches(0.40),\n'
    '   widths=[2.55, 2.85, 4.95, 1.98], verdict_col=3)\ntbl.top = Inches(2.45)')
rep('["Literal Hit@10", "90% 이상", "BM25 93% · Vector 89% · Hybrid 95%", "달성"],',
    '["Literal Hit@10", "90% 이상", "BM25 93%  ·  Vector 89%  ·  Hybrid 95%", "달성"],')
rep('    ["Literal P@10", "0.9 미만이면 토큰화 의심",\n'
    '     "BM25 0.841 · Vector 0.541 · Hybrid 0.662", "참고"],',
    '    ["Literal P@10", "0.9 미만이면 토큰화 의심",\n'
    '     "BM25 0.841  ·  Vector 0.541  ·  Hybrid 0.662", "참고"],')
rep('["청크 계약", "위반 0건", "11종 검사 통과 · 500자 초과 27건 잔존", "부분"],',
    '["청크 계약", "위반 0건", "11종 검사 통과 · 500자 초과 27건", "부분"],')
rep('shp(s, "Text 6").top = Inches(6.20)\n_txt(s, 0.50, 6.52, 12.33, 0.55,',
    'shp(s, "Text 6").top = Inches(6.42)\n_txt(s, 0.50, 6.70, 12.33, 0.48,')
rep('     "미달 원인 — held-out 정답은 유튜브·커머스 문서인데 색인의 91%가 유튜브 문서라 "\n'
    '     "상위 10칸이 짧은 댓글로 채워집니다. Hybrid 를 안 쓰는 이유도 이 표에 있습니다 — "\n'
    '     "Hit@10 만 1위이고 P@10 은 BM25 에 0.179 뒤집니다.",\n'
    '     size=10, color=INK)',
    '     "미달 원인 — held-out 정답은 유튜브·커머스 문서인데 색인의 91%가 유튜브 문서라 "\n'
    '     "상위 10칸이 짧은 댓글로 채워집니다.",\n'
    '     size=9.5, color=INK)')

# ── A 채널마다 다른 신호 — 3주제로 줄이고 배지를 오른쪽으로 ────
rep('''    _txt(sl, x, y, w, 0.24, name, size=11.5, color=INK, bold=True)
    if note:
        _txt(sl, x + 1.15, y, w - 1.15, 0.24, note, size=8.5, color=GREEN)''',
    '''    _txt(sl, x, y, w * 0.62, 0.24, name, size=11.5, color=INK, bold=True)
    if note:
        _txt(sl, x + w * 0.62, y, w * 0.36, 0.24, note, size=9, color=GREEN,
             bold=True, align=PP_ALIGN.RIGHT)''')
rep('''         unit="%", lab_w=1.05, val_w=0.72, row_h=0.22, bar_h=0.115,
         max_v=24.0, size=9)
    return y + 0.26 + 3 * 0.22''',
    '''         unit="%", lab_w=1.05, val_w=0.72, row_h=0.245, bar_h=0.125,
         max_v=18.0, size=9.5)
    return y + 0.26 + 3 * 0.245''')
rep('panel(sa, 0.50, 2.52, 6.05, 4.10, fill="FAF9FC", line="E2DEEA", radius=0.02)',
    'panel(sa, 0.50, 2.52, 6.05, 3.62, fill="FAF9FC", line="E2DEEA", radius=0.02)')
rep('panel(sa, 6.78, 2.52, 6.05, 4.10, fill="FAF9FC", line="E2DEEA", radius=0.02)',
    'panel(sa, 6.78, 2.52, 6.05, 3.62, fill="FAF9FC", line="E2DEEA", radius=0.02)')
rep('''for nm, v, c, r, nt in [("백탁", 0.31, 2.56, 12.09, "39배"),
                        ("발림성", 5.86, 5.43, 16.53, ""),
                        ("끈적임·유분감", 6.48, 9.97, 16.71, ""),
                        ("자극·눈시림", 7.10, 12.39, 16.89, "")]:
    yy = topic_block(sa, 0.78, yy, 5.5, nm, v, c, r, nt) + 0.13''',
    '''for nm, v, c, r, nt in [("백탁", 0.31, 2.56, 12.09, "영상의 39배"),
                        ("끈적임·유분감", 6.48, 9.97, 16.71, "+10.2%p"),
                        ("자극·눈시림", 7.10, 12.39, 16.89, "+9.8%p")]:
    yy = topic_block(sa, 0.78, yy, 5.5, nm, v, c, r, nt) + 0.16''')
rep('''for nm, v, c, r, nt in [("톤업·메이크업베이스", 13.89, 9.34, 1.16, "-12.7%p"),
                        ("무기자차", 10.18, 12.84, 0.62, ""),
                        ("지속력·워터프루프", 8.95, 4.62, 0.18, ""),
                        ("SPF · PA", 4.94, 1.44, 0.36, "")]:
    yy = topic_block(sa, 7.06, yy, 5.5, nm, v, c, r, nt) + 0.13''',
    '''for nm, v, c, r, nt in [("톤업·메이크업베이스", 13.89, 9.34, 1.16, "-12.7%p"),
                        ("무기자차", 10.18, 12.84, 0.62, "-9.6%p"),
                        ("지속력·워터프루프", 8.95, 4.62, 0.18, "-8.8%p")]:
    yy = topic_block(sa, 7.06, yy, 5.5, nm, v, c, r, nt) + 0.16''')
rep('''_txt(sa, 0.50, 6.70, 12.33, 0.30,
     "source_composition.csv · 13주제 전수 · 세 열 모두 같은 분모(주제 분류된 문서)입니다. "''',
    '''_txt(sa, 0.50, 6.28, 12.33, 0.62,
     "「백탁」은 판매자가 거의 말하지 않는데 구매자가 가장 많이 말합니다. "
     "반대로 「톤업」은 영상이 앞서고 리뷰에는 거의 없습니다 — 한 채널만 보면 반대 결론이 나옵니다.\n"
     "source_composition.csv · 13주제 전수 · 세 열 모두 같은 분모(주제 분류된 문서)입니다. "''')

# ── C 검색 평가 — 소수 3자리, Hit 블록 여유 ──────────────────
for x0 in ("0.78", "7.06"):
    rep(f'hbar(sc, {x0}, 3.20, 5.5,', f'hbar(sc, {x0}, 3.18, 5.5,')
rep('     lab_w=1.05, val_w=0.70, row_h=0.24, bar_h=0.125, max_v=1.0, size=9.5)',
    '     lab_w=1.05, val_w=0.70, row_h=0.245, bar_h=0.125, max_v=1.0, size=9.5,\n'
    '     dec=3)')
rep('     lab_w=1.05, val_w=0.70, row_h=0.24, bar_h=0.125, max_v=0.05, size=9.5)',
    '     lab_w=1.05, val_w=0.70, row_h=0.245, bar_h=0.125, max_v=0.05, size=9.5,\n'
    '     dec=3)')
rep('panel(sc, 0.50, 2.56, 6.05, 2.05,', 'panel(sc, 0.50, 2.56, 6.05, 2.16,')
rep('panel(sc, 6.78, 2.56, 6.05, 2.05,', 'panel(sc, 6.78, 2.56, 6.05, 2.16,')
for x0 in ("0.72", "7.00"):
    rep(f'_txt(sc, {x0}, 3.94, 5.6, 0.22,', f'_txt(sc, {x0}, 3.98, 5.6, 0.22,')
for x0 in ("0.78", "7.06"):
    rep(f'hbar(sc, {x0}, 4.16, 5.5,', f'hbar(sc, {x0}, 4.20, 5.5,')
rep('panel(sc, 0.50, 4.78, 12.33, 1.78,', 'panel(sc, 0.50, 4.92, 12.33, 1.70,')
rep('ny = 4.92', 'ny = 5.04')

p.write_text(s, encoding="utf-8")
print(f"build.py {n}곳 수정")
