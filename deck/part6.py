PART6 = r'''
# ── D. 파이프라인이 조용히 만든 답 8건 (04 구현·검증) ─────────
sd = blank_from(prs, 6, 16, "04  구현 · 검증", "파이프라인이 조용히 만든 답 — 8건",
                "여덟 건 모두 예외도 경고도 없이 통과했고 결과가 그럴듯했습니다. 그래서 검사를 코드에 박았습니다.")
TRAPS = [
    ("채널당 수집 상한 10", "월별 집계가 매달 10건 근처", "재수집 + 쿼터 산식"),
    ("정렬 없는 offset 페이징", "외부에서 재현 실패 제기", "reproduce.py"),
    ("색인의 91%가 짧은 댓글", "소스별로 나눠 질의", "소스별 쿼터 검색"),
    ("정답은 doc_id · 결과는 chunk_id", "점수가 항상 0.000", "계약 검증기 11종"),
    ("정규화 전 본문으로 인코딩된 벡터", "프로브 코사인 0.9986", "텍스트 지문 대조"),
    ("경고를 축 전체가 아니라 한 행에만 적용", "잔존율 재측정 (20.6% vs 19.0%)", "논문 축 전체 철회"),
    ("두 글자 별칭이 다른 성분에 걸림", "--audit 로 키별 성분명 출력", "별칭 사전 교체"),
    ("원인을 잘못된 기준선에 귀속", "옛 벡터를 되살려 직접 비교", "기준선 명시"),
]
HD = [("무엇이 관측값이 됐나", 0.50, 4.75), ("어떻게 잡았나", 5.35, 3.85),
      ("지금 막는 장치", 9.30, 3.53)]
for h, hx, hw in HD:
    _txt(sd, hx + 0.16, 2.28, hw - 0.24, 0.26, h, size=10, color=NOTE, bold=True)
for i, (what, how, guard) in enumerate(TRAPS):
    ry = 2.62 + i * 0.50
    panel(sd, 0.50, ry, 12.33, 0.44,
          fill=("FFFFFF" if i % 2 else "FAF9FC"), line="E9E6F0", radius=0.05)
    _bar(sd, 0.62, ry + 0.14, 0.16, 0.16, S1 if i < 6 else S2)
    _txt(sd, 0.88, ry, 4.35, 0.44, what, size=9.5, color=INK, bold=True)
    _txt(sd, 5.51, ry, 3.65, 0.44, how, size=9.5, color=DIM)
    _txt(sd, 9.46, ry, 3.25, 0.44, guard, size=9.5, color=DIM)
_txt(sd, 0.50, 6.70, 12.33, 0.30,
     "마지막 두 건은 이미 발표 자료에 실려 있던 우리 결론을 철회한 건입니다 — "
     "시카 41.1% → 35.0% · 벡터 하락 원인은 접두어가 아니라 코퍼스 혼합.",
     size=9.5, color=NOTE)
print("D  함정 8건")


# ── C. 검색 평가 — 지표를 골라 인용하면 승자가 바뀐다 (04) ─────
sc = blank_from(prs, 6, 18, "04  구현 · 검증", "검색 성능 — 어느 지표를 보느냐로 승자가 바뀐다",
                "그래서 두 지표를 같이 싣습니다. 한쪽만 적으면 반대 결론이 나옵니다.")
legend(sc, 0.50, 2.20, [("BM25 (어휘)", S1), ("e5 Vector (의미)", S2),
                        ("Hybrid RRF", S3)], size=9.5, gap=2.0)

panel(sc, 0.50, 2.56, 6.05, 2.05, fill="FAF9FC", line="E2DEEA", radius=0.03)
_txt(sc, 0.72, 2.66, 5.6, 0.26, "literal  —  글자가 겹치는 질의 (61건)", size=11,
     color=INK, bold=True)
_txt(sc, 0.72, 2.94, 5.6, 0.22, "P@10  상위 10칸이 실제로 정답인 비율", size=9, color=NOTE)
hbar(sc, 0.78, 3.20, 5.5, [("BM25", 0.841, S1), ("Vector", 0.541, S2),
                           ("Hybrid", 0.662, S3)],
     lab_w=1.05, val_w=0.70, row_h=0.24, bar_h=0.125, max_v=1.0, size=9.5)
_txt(sc, 0.72, 3.94, 5.6, 0.22, "Hit@10  상위 10칸에 정답이 하나라도 있는 비율", size=9, color=NOTE)
hbar(sc, 0.78, 4.16, 5.5, [("BM25", 93, S1), ("Vector", 89, S2), ("Hybrid", 95, S3)],
     unit="%", lab_w=1.05, val_w=0.70, row_h=0.135, bar_h=0.09, max_v=100, size=8.5)

panel(sc, 6.78, 2.56, 6.05, 2.05, fill="FAF9FC", line="E2DEEA", radius=0.03)
_txt(sc, 7.00, 2.66, 5.6, 0.26, "held-out  —  글자가 안 겹치는 질의 (60건)", size=11,
     color=INK, bold=True)
_txt(sc, 7.00, 2.94, 5.6, 0.22, "P@10  임베딩이 실제로 기여한 몫", size=9, color=NOTE)
hbar(sc, 7.06, 3.20, 5.5, [("BM25", 0.0, S1), ("Vector", 0.038, S2),
                           ("Hybrid", 0.028, S3)],
     lab_w=1.05, val_w=0.70, row_h=0.24, bar_h=0.125, max_v=0.05, size=9.5)
_txt(sc, 7.00, 3.94, 5.6, 0.22, "Hit@10", size=9, color=NOTE)
hbar(sc, 7.06, 4.16, 5.5, [("BM25", 0, S1), ("Vector", 13, S2), ("Hybrid", 10, S3)],
     unit="%", lab_w=1.05, val_w=0.70, row_h=0.135, bar_h=0.09, max_v=100, size=8.5)

panel(sc, 0.50, 4.78, 12.33, 1.78, fill="FFFFFF", line="DCD8E4", radius=0.03)
NOTES = [
    (S1, "정확 명칭은 BM25 를 쓴다",
     "P@10 0.841 로 압도. 성분명·보고번호·SPF 처럼 정확 일치가 정답인 질의."),
    (S2, "이름 없는 표현은 벡터가 맡는다",
     "「톤 업」·「눈 시림」처럼 공백이 든 별칭에서 BM25 는 0점이고 벡터는 찾는다. "
     "다만 P@10 0.038 — 열 번 물어 여덟 번은 못 찾는다."),
    (S3, "Hybrid 는 쓰지 않는다",
     "literal Hit@10 만 1위(95%)다. P@10 은 0.662 로 BM25 에 0.179 뒤지고 "
     "held-out 도 0.028 로 벡터에 뒤진다 — RRF 가 순위만 보고 확신도를 버리기 때문."),
]
ny = 4.92
for col, head, body in NOTES:
    _bar(sc, 0.68, ny + 0.05, 0.06, 0.18, col)
    _txt(sc, 0.84, ny, 3.55, 0.24, head, size=10.5, color=INK, bold=True)
    _txt(sc, 4.45, ny, 8.15, 0.48, body, size=9.5, color=DIM)
    ny += 0.56
_txt(sc, 0.50, 6.68, 12.33, 0.30,
     "e5all 벡터 306,178 · 08.27 재측정 · retrieval_eval.py 로 재현됩니다. "
     "근거는 합치지 않고 나란히 놓습니다 — 소스를 합산하지 않은 것과 같은 논리입니다.",
     size=9.5, color=NOTE)
print("C  검색 평가")
'''
