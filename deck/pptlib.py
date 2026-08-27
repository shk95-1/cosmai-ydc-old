"""양식 pptx 를 우리 내용으로 채우는 최소 도구.

**왜 python-pptx 의 `text_frame.text = ...` 를 안 쓰나.** 그 대입은 런을 전부
지우고 새 런을 만든다 — 양식이 문단마다 넣어 둔 폰트·크기·색이 함께 날아간다.
그래서 첫 문단을 **서식 기증자** 로 삼아 XML 을 복제하고 글자만 바꾼다.
"""
from __future__ import annotations

import copy
import re

from pptx.oxml.ns import qn
from pptx.util import Pt
from pptx.dml.color import RGBColor

GREEN = "76B900"      # NVIDIA 강조색
INK = "1A1A1A"        # 본문 (양식의 8C8C8C 는 안내문 색이라 내용에 쓰면 안 읽힌다)
DIM = "5A5A5A"        # 보조 설명
NOTE = "7A7A7A"       # 각주
WHITE = "FFFFFF"


def shp(slide, name):
    for s in slide.shapes:
        if s.name == name:
            return s
    raise KeyError(f"{name} 없음 — 슬라이드 도형: {[s.name for s in slide.shapes]}")


def drop(slide, *names):
    """안내문·예시 도형을 지운다. 양식이 '작성 후 삭제하세요' 라고 적어 둔 것들."""
    want = set(names)
    for s in list(slide.shapes):
        if s.name in want:
            s._element.getparent().remove(s._element)
            want.discard(s.name)
    if want:
        raise KeyError(f"삭제 대상 없음: {want}")


def drop_guides(slide):
    """양식이 '작성 후 삭제하세요' 라고 적어 둔 것 전부 — 예시 문구와 ※ 안내.

    이름이 아니라 **색과 글자**로 찾는다. 슬라이드마다 도형 이름이 달라서
    이름으로 지우면 한 장만 고쳐도 KeyError 가 난다.
    """
    for s in list(slide.shapes):
        if not s.has_text_frame:
            continue
        txt = s.text_frame.text.strip()
        if txt.startswith("※"):
            s._element.getparent().remove(s._element)
            continue
        # **페이지 번호도 B5B5B5 다.** 색만 보고 지우면 26장 전부에서 번호가 사라진다
        if re.fullmatch(r"\d{1,2}", txt) and s.top is not None                 and abs(s.top / 914400 - 7.05) < 0.08:
            continue
        cols = set()
        for para in s.text_frame.paragraphs:
            for r in para.runs:
                try:
                    cols.add(str(r.font.color.rgb))
                except Exception:
                    pass
        if cols and cols <= {"B5B5B5"}:
            s._element.getparent().remove(s._element)


def drop_examples(slide):
    """색이 B5B5B5 인 도형 = 양식의 '예)' 문구. 색으로 찾으면 이름을 안 외워도 된다."""
    for s in list(slide.shapes):
        if not s.has_text_frame:
            continue
        cols = set()
        for para in s.text_frame.paragraphs:
            for r in para.runs:
                try:
                    cols.add(str(r.font.color.rgb))
                except Exception:
                    pass
        if cols and cols <= {"B5B5B5"}:
            s._element.getparent().remove(s._element)


def set_text(shape, lines, color=None, size=None, bold=None, spacing=None):
    """문단 목록으로 글자를 바꾼다. 첫 문단의 서식을 그대로 물려준다."""
    if isinstance(lines, str):
        lines = [lines]
    tf = shape.text_frame
    body = tf._txBody
    paras = body.findall(qn("a:p"))
    if not paras:
        raise ValueError(f"{shape.name}: 문단이 없다")
    donor = copy.deepcopy(paras[0])
    # 기증자를 런 하나로 줄인다 — 줄바꿈(a:br)·여분 런은 버린다
    for tag in ("a:r", "a:br", "a:fld"):
        for e in donor.findall(qn(tag))[1:] if tag == "a:r" else donor.findall(qn(tag)):
            donor.remove(e)
    if donor.find(qn("a:r")) is None:
        raise ValueError(f"{shape.name}: 서식을 물려줄 런이 없다")

    for p in paras:
        body.remove(p)
    for ln in lines:
        p = copy.deepcopy(donor)
        p.find(qn("a:r")).find(qn("a:t")).text = ln
        body.append(p)

    for para in tf.paragraphs:
        if spacing is not None:
            para.line_spacing = spacing
        for r in para.runs:
            if color:
                r.font.color.rgb = RGBColor.from_string(color)
            if size:
                r.font.size = Pt(size)
            if bold is not None:
                r.font.bold = bold
    return shape


def fit(shape, size, spacing=None):
    for para in shape.text_frame.paragraphs:
        if spacing is not None:
            para.line_spacing = spacing
        for r in para.runs:
            r.font.size = Pt(size)


def add_rows(table, n):
    """표에 행을 더한다. 마지막 행을 복제해 서식(테두리·채움)을 잇는다."""
    tbl = table._tbl
    donor = tbl.findall(qn("a:tr"))[-1]
    for _ in range(n):
        tbl.append(copy.deepcopy(donor))


VERDICT = {"달성": "2E7D32", "미달": "C62828", "부분": "8A5A0F", "참고": "5A5A5A"}


def fill_table(shape, rows, size=12.0, head_size=12.5, row_h=None,
               widths=None, verdict_col=None):
    """헤더 1행 + 본문. 행 수가 부족하면 늘리고, 남으면 지운다."""
    t = shape.table
    tbl = t._tbl
    have = len(t.rows)
    need = len(rows)
    if need > have:
        add_rows(t, need - have)
    elif need < have:
        for tr in tbl.findall(qn("a:tr"))[need:]:
            tbl.remove(tr)
    if widths:
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
            t.rows[ri].height = row_h


def dup_slide(prs, src_index, dest_index=None):
    """슬라이드를 복제한다. 양식 레이아웃이 하나뿐이라 도형 트리를 그대로 옮긴다."""
    src = prs.slides[src_index]
    new = prs.slides.add_slide(prs.slide_layouts[0])
    for s in list(new.shapes):
        s._element.getparent().remove(s._element)
    tree = new.shapes._spTree
    for s in src.shapes:
        tree.append(copy.deepcopy(s._element))
    bg = src._element.find(qn("p:bg"))
    if bg is not None:
        new._element.insert(0, copy.deepcopy(bg))
    if dest_index is not None:
        move_slide(prs, len(prs.slides) - 1, dest_index)
        return prs.slides[dest_index]
    return new


def move_slide(prs, frm, to):
    lst = prs.slides._sldIdLst
    ids = list(lst)
    lst.remove(ids[frm])
    lst.insert(to, ids[frm])


def renumber(prs):
    """페이지 번호를 다시 매긴다. 슬라이드를 끼워 넣으면 어긋난다."""
    for i, s in enumerate(prs.slides, 1):
        for sh in s.shapes:
            if not sh.has_text_frame:
                continue
            if sh.top is None or abs(sh.top / 914400 - 7.05) > 0.05:
                continue
            if re.fullmatch(r"\d{1,2}", sh.text_frame.text.strip()):
                set_text(sh, str(i))


# ─────────────────────────────────────────────────────────────────
# 시각화 — 네이티브 도형으로 그린다
#
# **왜 이미지가 아니라 도형인가.** 이미지로 넣으면 팀원이 숫자를 못 고치고,
# 한글 폰트가 없는 PC 에서 렌더가 깨진다. 도형은 파워포인트가 직접 그린다.
# **왜 pptx 차트가 아닌가.** 가로 막대에 직접 라벨을 붙이고 축을 지우려면
# 차트 옵션을 열 개 넘게 만져야 한다. 사각형 두 개가 더 확실하다.
# ─────────────────────────────────────────────────────────────────
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# 계열 색 — 라이트 배경 기준으로 색각 검증(validate_palette)을 통과한 조합
S1, S2, S3 = "5B3FD6", "C2410C", "0284A8"
TRACK = "E9E6F0"      # 막대 배경(전체 대비 눈금)


def _txt(slide, x, y, w, h, text, size=11, color=INK, bold=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, font="Arial"):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    lines = text if isinstance(text, (list, tuple)) else [text]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = font
        r.font.color.rgb = RGBColor.from_string(color)
    return box


def _bar(slide, x, y, w, h, color):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                               Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = RGBColor.from_string(color)
    s.line.fill.background()
    s.shadow.inherit = False
    try:                       # 모서리 반경 — 막대 두께의 절반 정도만
        s.adjustments[0] = 0.35
    except Exception:
        pass
    return s


def hbar(slide, x, y, w, rows, unit="", lab_w=1.35, val_w=0.95,
         row_h=0.34, bar_h=0.15, max_v=None, size=10.5, track=False, dec=None):
    """가로 막대 + 직접 라벨. rows = [(라벨, 값, 색), ...]

    직접 라벨을 붙이므로 축이 필요 없다 — 축을 지우면 눈이 막대 길이만 본다.
    """
    plot = w - lab_w - val_w
    mx = max_v or max((r[1] for r in rows), default=1) or 1
    for i, (k, v, c) in enumerate(rows):
        cy = y + i * row_h
        _txt(slide, x, cy, lab_w - 0.12, row_h, k, size=size, color=DIM,
             align=PP_ALIGN.RIGHT)
        if track:
            _bar(slide, x + lab_w, cy + (row_h - bar_h) / 2, plot, bar_h, TRACK)
        bw = max(0.03, plot * v / mx) if v > 0 else 0
        if bw:
            _bar(slide, x + lab_w, cy + (row_h - bar_h) / 2, bw, bar_h, c)
        if dec is not None:
            txt = f"{v:,.{dec}f}"
        elif isinstance(v, float):
            txt = f"{v:,.2f}".rstrip("0").rstrip(".")
        else:
            txt = f"{v:,}"
        _txt(slide, x + lab_w + bw + 0.08, cy, val_w, row_h, txt + unit,
             size=size, color=INK, bold=True)
    return y + len(rows) * row_h


def legend(slide, x, y, items, size=9.5, gap=1.55):
    """계열 이름 — 막대가 두 계열 이상이면 반드시 붙인다(색만으로 구분 금지)."""
    cx = x
    for label, color in items:
        d = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   Inches(cx), Inches(y + 0.055), Inches(0.11), Inches(0.11))
        d.fill.solid()
        d.fill.fore_color.rgb = RGBColor.from_string(color)
        d.line.fill.background()
        d.shadow.inherit = False
        _txt(slide, cx + 0.18, y, gap - 0.2, 0.22, label, size=size, color=DIM)
        cx += gap
    return y + 0.24


def panel(slide, x, y, w, h, fill="FFFFFF", line="DCD8E4", radius=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                               Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = RGBColor.from_string(fill)
    s.line.color.rgb = RGBColor.from_string(line)
    s.line.width = Pt(0.75)
    s.shadow.inherit = False
    if radius is not None:
        try:
            s.adjustments[0] = radius
        except Exception:
            pass
    return s


def arrow(slide, x, y, w, h=0.0, color="BDB7CC"):
    s = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y),
                               Inches(w), Inches(max(h, 0.14)))
    s.fill.solid()
    s.fill.fore_color.rgb = RGBColor.from_string(color)
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def blank_from(prs, src_index, dest_index, section, title, sub):
    """헤더만 남긴 빈 슬라이드. 양식에 없는 시각화 장을 더할 때 쓴다.

    양식 안내문("슬라이드 추가는 자유이나 목차 항목은 삭제하지 않습니다")을 따른다 —
    목차 6절 구조는 그대로 두고, 그 안에 장을 끼운다.
    """
    new = dup_slide(prs, src_index, dest_index)
    keep = {}
    for s in new.shapes:
        if not s.has_text_frame:
            continue
        top = s.top / 914400
        if abs(top - 0.40) < 0.06 and s.left / 914400 < 1.0:
            keep["section"] = s
        elif abs(top - 0.36) < 0.06:
            keep["brand"] = s
        elif abs(top - 0.92) < 0.06:
            keep["title"] = s
        elif abs(top - 1.68) < 0.06:
            keep["sub"] = s
        elif abs(top - 7.05) < 0.06 and s.text_frame.text.strip().isdigit():
            keep["page"] = s
    for s in list(new.shapes):
        if s not in keep.values():
            s._element.getparent().remove(s._element)
    set_text(keep["section"], section)
    set_text(keep["title"], title)
    set_text(keep["sub"], sub, color=DIM)
    return new


def drop_soft(slide, *names):
    """있으면 지우고 없으면 넘어간다. drop_guides 가 먼저 치웠을 수 있다."""
    want = set(names)
    for s in list(slide.shapes):
        if s.name in want:
            s._element.getparent().remove(s._element)
