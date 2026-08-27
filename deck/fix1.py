from pathlib import Path

# ── pptlib: 소수점 자리수 옵션 + 셀 색 지정 ──────────────────
p = Path("pptlib.py"); s = p.read_text(encoding="utf-8")

s = s.replace(
    'def hbar(slide, x, y, w, rows, unit="", lab_w=1.35, val_w=0.95,\n'
    '         row_h=0.34, bar_h=0.15, max_v=None, size=10.5, track=False):',
    'def hbar(slide, x, y, w, rows, unit="", lab_w=1.35, val_w=0.95,\n'
    '         row_h=0.34, bar_h=0.15, max_v=None, size=10.5, track=False, dec=None):')
s = s.replace(
    '        txt = f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"',
    '        if dec is not None:\n'
    '            txt = f"{v:,.{dec}f}"\n'
    '        elif isinstance(v, float):\n'
    '            txt = f"{v:,.2f}".rstrip("0").rstrip(".")\n'
    '        else:\n'
    '            txt = f"{v:,}"')

# 표 — 마지막 열의 판정 색을 값에 맞춰 다시 칠한다.
# 양식의 마지막 행이 '미달'(빨강)이라 행을 복제하면 전부 빨강이 된다.
s = s.replace(
    'def fill_table(shape, rows, size=12.0, head_size=12.5, row_h=None):',
    'VERDICT = {"달성": "2E7D32", "미달": "C62828", "부분": "8A5A0F", "참고": "5A5A5A"}\n\n\n'
    'def fill_table(shape, rows, size=12.0, head_size=12.5, row_h=None,\n'
    '               widths=None, verdict_col=None):')
s = s.replace(
    """    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = t.cell(ri, ci)
            set_text(cell, str(val), size=(head_size if ri == 0 else size))
        if row_h:
            t.rows[ri].height = row_h""",
    """    if widths:
        for ci, wv in enumerate(widths):
            t.columns[ci].width = Inches(wv)
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = t.cell(ri, ci)
            col = None
            if ri and verdict_col is not None and ci == verdict_col:
                col = VERDICT.get(str(val).strip())
            set_text(cell, str(val), size=(head_size if ri == 0 else size),
                     color=col)
        if row_h:
            t.rows[ri].height = row_h""")
p.write_text(s, encoding="utf-8")
print("pptlib 수정")
