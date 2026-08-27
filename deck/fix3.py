from pathlib import Path
p = Path("build.py"); s = p.read_text(encoding="utf-8")
n = 0
def rep(a, b):
    global s, n
    assert a in s, f"못 찾음:\n{a[:120]}"
    s = s.replace(a, b, 1); n += 1

# ── 카드 — 막대 스케일을 카드별로, 활용법은 위쪽 정렬 ─────────
rep('''def card_panel(sl, x, y, w, h, name, kind, kind_col, bars, extra, use):
    """카드 한 장 — 이름 · 유형 · 수치 시각화 · 활용법. 원문은 싣지 않고 GUI 로 넘긴다."""''',
    '''def card_panel(sl, x, y, w, h, name, kind, kind_col, bars, extra, use, mx=None):
    """카드 한 장 — 이름 · 유형 · 수치 시각화 · 활용법. 원문은 싣지 않고 GUI 로 넘긴다.

    **막대 상한은 카드마다 따로 잡는다.** 100% 로 고정하면 7~17% 값이 전부
    선처럼 보인다. 카드는 자기 안에서 비교하는 물건이고 모든 막대에 값을
    직접 적으므로, 카드끼리 길이를 견주는 오독은 나지 않는다.
    """''')
rep('''    hbar(sl, x + 0.22, y + 0.58, w - 0.44, bars, unit="%",
         lab_w=1.30, val_w=0.72, row_h=0.245, bar_h=0.125, max_v=100.0, size=9)''',
    '''    top = mx or (max(b[1] for b in bars) * 1.18) or 1.0
    hbar(sl, x + 0.22, y + 0.58, w - 0.44, bars, unit="%",
         lab_w=1.30, val_w=0.80, row_h=0.26, bar_h=0.13, max_v=top, size=9.5)''')
rep('''    ey = y + 0.58 + len(bars) * 0.245 + 0.04
    _txt(sl, x + 0.22, ey, w - 0.44, 0.26, extra, size=8.5, color=GREEN)
    _bar(sl, x + 0.22, ey + 0.36, 0.06, 0.16, kind_col)
    _txt(sl, x + 0.38, ey + 0.30, w - 0.60, 0.28, "이걸로 무엇을 하나", size=9,
         color=INK, bold=True)
    _txt(sl, x + 0.38, ey + 0.60, w - 0.62, h - (ey - y) - 0.66, use,
         size=9, color=DIM)''',
    '''    ey = y + 0.58 + len(bars) * 0.26 + 0.06
    _txt(sl, x + 0.22, ey, w - 0.44, 0.44, extra, size=8.5, color=GREEN,
         anchor=MSO_ANCHOR.TOP)
    ey += 0.50
    _bar(sl, x + 0.22, ey + 0.05, 0.06, 0.16, kind_col)
    _txt(sl, x + 0.38, ey, w - 0.60, 0.24, "이걸로 무엇을 하나", size=9.5,
         color=INK, bold=True)
    _txt(sl, x + 0.38, ey + 0.28, w - 0.62, y + h - ey - 0.42, use,
         size=9.5, color=DIM, anchor=MSO_ANCHOR.TOP)''')
rep('CW6, CH6, CX0 = 3.94, 4.10, 0.50', 'CW6, CH6, CX0 = 3.94, 3.92, 0.50')

# 주제 카드 — 세 카드가 같은 척도(리뷰 최대 16.89 + 제품 32.9)를 쓰면 혼합자차만 길어진다.
# 주제 셋은 20%, 혼합자차는 제품 축이라 따로 40% 를 쓴다.
rep('''for i, (nm, kd, kc, bars, extra, use) in enumerate(CARDS_T):
    card_panel(se, CX0 + i * (CW6 + CGAP), 2.35, CW6, CH6, nm, kd, kc, bars, extra, use)''',
    '''for i, (nm, kd, kc, bars, extra, use) in enumerate(CARDS_T):
    card_panel(se, CX0 + i * (CW6 + CGAP), 2.35, CW6, CH6, nm, kd, kc, bars,
               extra, use, mx=(40.0 if nm == "혼합자차" else 20.0))''')
rep('''for i, (nm, kd, kc, bars, extra, use) in enumerate(CARDS_I):
    card_panel(sf, CX0 + i * (CW6 + CGAP), 2.35, CW6, CH6, nm, kd, kc, bars, extra, use)''',
    '''for i, (nm, kd, kc, bars, extra, use) in enumerate(CARDS_I):
    card_panel(sf, CX0 + i * (CW6 + CGAP), 2.35, CW6, CH6, nm, kd, kc, bars,
               extra, use, mx=80.0)''')
rep('_txt(se, 0.50, 6.58, 12.33, 0.42,', '_txt(se, 0.50, 6.42, 12.33, 0.55,')
rep('_txt(sf, 0.50, 6.58, 12.33, 0.42,', '_txt(sf, 0.50, 6.42, 12.33, 0.55,')

# MSO_ANCHOR 를 build.py 에서 쓸 수 있게 한다
rep('from pptx.enum.text import PP_ALIGN',
    'from pptx.enum.text import PP_ALIGN, MSO_ANCHOR')

# 아키텍처 왼쪽 패널 — 아래 빈칸을 줄인다
rep('''set_text(shp(s, "Text 8"),
         ["· 원본은 지우지 않고 플래그만 붙인다",''',
    '''shp(s, "Text 8").top = Inches(3.05)
set_text(shp(s, "Text 8"),
         ["· 원본은 지우지 않고 플래그만 붙인다",''')

p.write_text(s, encoding="utf-8")
print(f"build.py {n}곳 수정")
