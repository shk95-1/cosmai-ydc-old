from pathlib import Path
p = Path("build.py"); s = p.read_text(encoding="utf-8")
n = 0
def rep(a, b):
    global s, n
    assert a in s, f"못 찾음: {a[:80]}"
    s = s.replace(a, b, 1); n += 1

# 팀 카드 — 담당별 산출물 한 줄씩 더한다 (양식 상자 높이를 건드리지 않고 채운다)
TEAM_ADD = {
    '      "· 검증·근거 추적, RAG 통합과 GUI"]),':
    '      "· 검증·근거 추적, RAG 통합과 GUI",\n'
    '      "· 결론 3건 철회 — 성분 오매칭 · 논문 축 · 기준선"]),',
    '      "· 리뷰 청크 18,476 · LLM 앱"]),':
    '      "· 리뷰 청크 18,476 · LLM 앱",\n'
    '      "· 랭킹 6일 추적 — 100위권 중앙 38계단 이동"]),',
    '      "· BM25 소스 우선순위 라우팅"]),':
    '      "· BM25 소스 우선순위 라우팅",\n'
    '      "· 청크 재인코딩으로 동명 20그룹 분리"]),',
    '      "· 논문 축 모집단 오염 검증"]),':
    '      "· 논문 축 모집단 오염 검증",\n'
    '      "· PubMed 1월 아티팩트 측정 (1.65~2.40배)"]),',
    '      "· 해당 축은 검증 실패로 HOLD"]),':
    '      "· 해당 축은 검증 실패로 HOLD",\n'
    '      "· 08.20 이탈 후 4인으로 진행"]),',
    '      "· 산출물 리뷰"]),':
    '      "· 산출물 리뷰",\n'
    '      "· 도메인 검토 — 광민감성 등 카드 한계 판단"]),',
}
for a, b in TEAM_ADD.items():
    rep(a, b)
rep('        set_text(shp(s, d), detail, color=INK, size=10.5)',
    '        set_text(shp(s, d), detail, color=INK, size=10, spacing=1.34)\n'
    '        shp(s, d).height = Inches(1.60)')

# 24 한계 — 상자 아래 빈칸에 닫는 줄을 넣는다 (양식이 요구한 리소스·기간)
rep('drop_guides(s)\nprint("18 한계·계획")',
    '''drop_guides(s)
_txt(s, 0.88, 5.24, 5.24, 0.90,
     ["답할 수 없는 질문 — 매출·가격 비교 · 미래 예측 · 논문 근거 요구.",
      "이 셋은 근거를 찾아도 답을 만들지 않고 거부합니다. 거부가 기능입니다."],
     size=9.5, color=INK, anchor=MSO_ANCHOR.TOP)
_txt(s, 7.21, 5.24, 5.24, 0.90,
     ["필요 리소스 — 1·2번은 추가 수집 1주(현준·석현), 3번은 수작업 2일,",
      "4번은 파이프라인 수정 2일. 5번은 프로토콜 합의가 선행돼야 합니다."],
     size=9.5, color=INK, anchor=MSO_ANCHOR.TOP)
print("18 한계·계획")''')

p.write_text(s, encoding="utf-8")
import ast; ast.parse(s)
print(f"{n}곳 수정")
