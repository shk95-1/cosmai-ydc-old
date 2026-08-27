# 이어붙일 조각 — 11~20장 (양식의 아키텍처·스택·구현·난점·검증·효과·확장·한계·회고)

PART3 = '''
# ══════════════════════════════════════════════════════════════
# 11  시스템 아키텍처 — 오른쪽 영역에 도형으로 직접 그린다
# ══════════════════════════════════════════════════════════════
s = S[10]
set_text(shp(s, "Text 3"),
         "데이터가 어디서 들어와 어디로 나가는지 한 장에 담았습니다. 소스는 끝까지 합치지 않습니다.",
         color=DIM)
set_text(shp(s, "Text 7"), "설계 원칙")
set_text(shp(s, "Text 8"),
         ["· 원본은 지우지 않고 플래그만 붙인다",
          "· 소스별 분모와 수집 시점을 분리한다",
          "· doc_id 와 chunk_id 를 모두 보존한다",
          "· 질문 유형이 검색 방식을 고른다",
          "· 근거 0건이면 답을 만들지 않는다"],
         color=INK, size=10.5, spacing=1.3)
drop_guides(s)
shp(s, "Text 11")._element.getparent().remove(shp(s, "Text 11")._element)

AX, AY, AW = 4.58, 2.45, 8.25
BANDS = [
    ("수집", ["YouTube 43채널", "NAVER 128개월", "커머스 3개몰", "성분표 577제품", "식약처 4,735"], S1),
    ("정제", ["광고·중복 플래그", "공통 스키마 통일", "500자 청크 분할", "doc_id · chunk_id 보존"], S3),
    ("색인", ["BM25  형태소 + 성분사전 1,877종", "e5-base 벡터  306,178 · 768차원"], S3),
    ("라우팅", ["명칭·번호 → BM25", "이름 없는 표현 → 벡터", "둘 다 → 소스별 병렬"], S2),
    ("출력", ["근거 문서 + doc_id", "LLM 답변 (핵심·근거·한계)", "Opportunity Card 6장", "질의 GUI"], S1),
]
by = AY + 0.10
for bi, (name, items, col) in enumerate(BANDS):
    bh = 0.60
    panel(s, AX, by, AW, bh, fill="FAF9FC", line="E2DEEA", radius=0.12)
    chip = _bar(s, AX + 0.10, by + 0.13, 0.72, 0.34, col)
    _txt(s, AX + 0.10, by + 0.13, 0.72, 0.34, name, size=9.5, color=WHITE,
         bold=True, align=PP_ALIGN.CENTER)
    n = len(items)
    iw = (AW - 1.05) / n - 0.08
    for ii, it in enumerate(items):
        ix = AX + 0.95 + ii * (iw + 0.08)
        panel(s, ix, by + 0.11, iw, 0.38, fill="FFFFFF", line="DCD8E4", radius=0.14)
        _txt(s, ix + 0.06, by + 0.11, iw - 0.12, 0.38, it, size=8.5, color=INK,
             align=PP_ALIGN.CENTER)
    if bi < len(BANDS) - 1:
        arrow(s, AX + AW / 2 - 0.11, by + bh + 0.035, 0.22, 0.15)
    by += bh + 0.22
print("11 아키텍처")


# ══════════════════════════════════════════════════════════════
# 12  기술 스택 — 실제로 쓴 것만. 안 쓴 것을 적으면 시연에서 어긋난다
# ══════════════════════════════════════════════════════════════
s = S[11]
set_text(shp(s, "Text 3"),
         "실제 코드에 있는 것만 적었습니다. 버전을 남겨 재현 가능한 문서로 만들었습니다.",
         color=DIM)
STACK = [
    ("Text 8", "Text 9", "Text 10", "AI · 검색",
     "임베딩 · 형태소 · GPU",
     "multilingual-e5-base (rev d1287505) 768차원 · kiwipiepy 0.23.2 · "
     "torch 2.6.0+cu124 · RTX 4060 8GB, batch 32"),
    ("Text 13", "Text 14", "Text 15", "백엔드 · 데이터",
     "서버 · 수치 · 저장",
     "Python 3.13 · 표준 라이브러리 http.server · numpy 2.5.1 · "
     "CSV 고정 스냅샷 · PostgREST (커머스)"),
    ("Text 18", "Text 19", "Text 20", "프론트엔드",
     "질의 GUI",
     "단일 HTML + 바닐라 JS · 인라인 SVG 차트 · 외부 라이브러리 0개 "
     "(설치 없이 열리게 하는 것이 목표)"),
    ("Text 23", "Text 24", "Text 25", "검증 · 운영",
     "테스트 · 재현성 · 공유",
     "GitHub · unittest · reproduce.py 재현성 검사 · 청크 계약 검증기 11종 · "
     "fault injection · Tailscale 사내망"),
]
for t, sub, body, title, subtitle, detail in STACK:
    set_text(shp(s, t), title)
    set_text(shp(s, sub), subtitle, color=GREEN, size=11)
    set_text(shp(s, body), detail, color=INK, size=9.5, spacing=1.2)
drop_guides(s)
print("12 기술 스택")


# ══════════════════════════════════════════════════════════════
# 13  주요 기능 및 구현 결과 — 실제 답변을 그대로 옮긴다
# ══════════════════════════════════════════════════════════════
s = S[12]
set_text(shp(s, "Text 3"),
         "아래 답변은 실행 중인 서버가 실제로 낸 출력입니다. 문구를 다듬지 않았습니다.",
         color=DIM)
set_text(shp(s, "Text 7"), "구현 완료")
set_text(shp(s, "Text 8"),
         ["\u2713  소스·검색 모드 필터",
          "\u2713  질문 유형 자동 라우팅",
          "\u2713  근거 문서 + doc_id 동시 표시",
          "\u2713  Opportunity Card 6장 상세",
          "\u2713  지표 · 한계 · 답변 가능 범위",
          "\u2713  예측·인과·매출 질문 거부",
          "",
          "미구현 — 상시 배포 (지금은 로컬·사내망)"],
         color=INK, size=10, spacing=1.28)
drop_guides(s)
shp(s, "Text 11")._element.getparent().remove(shp(s, "Text 11")._element)

QX, QY, QW = 4.58, 2.45, 8.25
panel(s, QX, QY, QW, 4.15, fill="FAF9FC", line="E2DEEA", radius=0.03)
_txt(s, QX + 0.22, QY + 0.16, QW - 0.44, 0.26,
     "질의   선크림 바르면 하얗게 떠서 다시 안 살 것 같아요", size=10.5,
     color=INK, bold=True)
_txt(s, QX + 0.22, QY + 0.44, QW - 0.44, 0.24,
     "라우팅 vector  ·  근거 6건 (youtube_comment, 최고 유사도 0.900)  ·  "
     "생성 claude-sonnet-5", size=9, color=GREEN)
ANS = [
    ("핵심", ["유튜브 댓글에서 선크림을 바르면 하얗게 뜬다는 언급이 확인됩니다 "
              "[출처: youtube_comment:Ugw-atKnpXrmL724JP94AaABAg#0].",
              "다만 어떤 제품·성분이 \u201c다시 안 살 만큼\u201d 문제인지에 대한 근거는 "
              "제공된 데이터에 없습니다."]),
    ("근거 요약", ["· 백탁은 여러 댓글에서 공통으로 언급되고, 겹쳐 발라도 안 뜨는 경우가 "
                   "대조적으로 나타납니다.",
                   "· \u201c다시 안 산다\u201d는 재구매 의사 언급은 근거에 없어 이 부분은 "
                   "답할 수 없습니다."]),
    ("한계", ["이 결과는 벡터 검색(Hit@10 13%)으로 얻은 것으로, 관련 없는 문서가 섞였을 "
              "가능성이 있습니다. 근거가 모두 유튜브 댓글이라 인과관계는 판단할 수 없습니다."]),
]
ay = QY + 0.80
for head, lines in ANS:
    _bar(s, QX + 0.22, ay + 0.045, 0.06, 0.17, S1)
    _txt(s, QX + 0.38, ay, 1.4, 0.24, head, size=10, color=INK, bold=True)
    ty = ay + 0.27
    for ln in lines:
        h = 0.30 if len(ln) < 62 else (0.46 if len(ln) < 125 else 0.62)
        _txt(s, QX + 0.38, ty, QW - 0.70, h, ln, size=9, color=DIM)
        ty += h
    ay = ty + 0.14
_txt(s, QX + 0.22, QY + 3.82, QW - 0.44, 0.24,
     "근거를 못 찾으면 이 자리에 답 대신 \u2018근거 없음\u2019 과 이유가 나옵니다.",
     size=8.5, color=NOTE)
print("13 구현 결과")
'''
