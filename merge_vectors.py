#!/usr/bin/env python3
"""남이 인코딩한 벡터를 우리 것과 합친다. **합치기 전에 같은 공간인지 증명한다.**

왜 필요한가. 수호님이 성분·식약처 8,786청크를 따로 인코딩해 보내셨다. 계획서는
"인코딩은 한 사람이 한 번에" 였는데, 그 이유는 **정확성이 아니라 속도와 설정
불일치 위험**이었다. e5 는 코퍼스에 fit 되지 않으므로 **같은 모델·같은 설정이면
누가 인코딩하든 같은 벡터 공간**에 놓인다. 수호님이 그걸 정확히 지적하셨다.

그래도 **믿지 않고 잰다.** 설정이 어긋나도 오류가 안 나고 코사인은 숫자가 나온다.

    ① 매니페스트 대조     모델 · 프리픽스 · L2 · dtype · 차원
    ② 가중치 지문 대조     model.safetensors 의 sha256[:16]
    ③ **실측**            같은 텍스트를 우리가 인코딩해 코사인을 잰다. 1.0 이어야 한다

실측으로 8건 전부 정확히 1.000000 이었고 가중치 지문도 `a18a44fad1d0b46d` 로
일치했다. 수호님이 리비전 해시를 몰라 남기신 대체 지문이 정확히 그 역할을 했다.

`chunk_id` 는 다를 수 있다. 수호님 것은 생성기의 해시 id 이고 우리는
`repair_chunks.py` 로 `{doc_id}#{ordinal}` 로 다시 붙였다. **본문으로 잇는다** —
`normalize_text` 를 통과시키면 양쪽이 같은 문자열이 된다(실측 8,786건 전부 매칭).

사용법:
    python merge_vectors.py --incoming <수호님폴더> --chunks reports/chunks_ingredient_mfds.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from trend import normalize_text

csv.field_size_limit(10 ** 8)

# 이 값들이 다르면 벡터를 합칠 수 없다. 하나라도 어긋나면 멈춘다.
MUST_MATCH = ("model", "doc_prefix", "l2_normalized", "dtype", "dim")
PROBE = 8            # 실측 표본 수. 8건이면 설정 불일치는 반드시 드러난다
COSINE_FLOOR = 0.999


def read_incoming(folder: Path) -> tuple[np.ndarray, list[str], dict, list[dict]]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    vectors = np.load(folder / "vectors.npy")
    ids = [l.strip() for l in (folder / "chunk_ids.txt").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    chunk_files = sorted(folder.glob("chunks_*.csv"))
    if not chunk_files:
        raise SystemExit(f"본문 CSV 가 없다: {folder}. 본문 없이는 id 를 이을 수 없다")
    with chunk_files[0].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(vectors) != len(ids):
        raise SystemExit(f"벡터 {len(vectors)} 와 id {len(ids)} 개수가 다르다")
    return vectors, ids, manifest, rows


def normalized(manifest: dict) -> dict:
    """매니페스트 키 이름이 사람마다 다르다. 비교 가능한 형태로 맞춘다."""
    return {
        "model": manifest.get("model") or manifest.get("model_name"),
        "doc_prefix": manifest.get("doc_prefix") or manifest.get("prefix"),
        "l2_normalized": manifest.get("l2_normalized"),
        "dtype": manifest.get("dtype"),
        "dim": manifest.get("dim"),
    }


def compare_settings(ours: dict, theirs: dict) -> list[str]:
    a, b = normalized(ours), normalized(theirs)
    return [f"{k}: 우리 {a[k]!r} vs 받은 것 {b[k]!r}"
            for k in MUST_MATCH if a[k] != b[k]]


def weight_fingerprint(model: str) -> str | None:
    """로컬 HF 캐시의 가중치 지문. 리비전 해시를 모를 때 이게 대신한다."""
    root = Path.home() / ".cache/huggingface/hub" / (
        "models--" + model.replace("/", "--"))
    hits = list(root.rglob("model.safetensors"))
    if not hits:
        return None
    return hashlib.sha256(hits[0].read_bytes()).hexdigest()[:16]


def link_by_text(theirs: list[dict], ours: list[dict],
                 ids: list[str]) -> tuple[list[tuple[str, int]], int]:
    """(우리 chunk_id, 그쪽 벡터 행 번호). 본문으로 잇는다.

    id 로 이으면 안 된다 — 생성기의 해시 id 와 우리가 다시 붙인 id 가 다르다.
    본문은 `normalize_text` 를 통과시키면 양쪽이 같아진다.
    """
    row_of = {cid: i for i, cid in enumerate(ids)}
    by_text: dict[str, str] = {}
    for row in theirs:
        by_text.setdefault(normalize_text(row["text"]), row["chunk_id"])
    pairs, missing = [], 0
    for row in ours:
        cid = by_text.get(row["text"])
        if cid is None or cid not in row_of:
            missing += 1
            continue
        pairs.append((row["chunk_id"], row_of[cid]))
    return pairs, missing


def probe(model_name: str, texts: list[str], prefix: str,
          vectors: np.ndarray, rows: list[int]) -> list[float]:
    """같은 텍스트를 우리가 인코딩해 코사인을 잰다. **이게 진짜 검증이다.**"""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    mine = model.encode([prefix + t for t in texts], convert_to_numpy=True)
    mine = mine.astype(np.float32)
    mine /= np.linalg.norm(mine, axis=1, keepdims=True)
    return [float(mine[i] @ vectors[rows[i]]) for i in range(len(rows))]


def run(incoming: Path, chunks: Path, base: Path, out: Path, skip_probe: bool) -> int:
    vectors, ids, their_manifest, their_rows = read_incoming(incoming)
    our_manifest = json.loads(base.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    print(f"받은 것 {vectors.shape} · 우리 {our_manifest['count']:,} x {our_manifest['dim']}")

    print()
    print("① 설정 대조")
    problems = compare_settings(our_manifest, their_manifest)
    if problems:
        print("[실패] 설정이 다르다 — 합치면 안 된다")
        for p in problems:
            print(f"    {p}")
        return 1
    for key in MUST_MATCH:
        print(f"    {key:<16}{normalized(our_manifest)[key]}")

    print()
    print("② 가중치 지문")
    ours = weight_fingerprint(normalized(our_manifest)["model"])
    theirs = their_manifest.get("model_weight_sha256_16")
    print(f"    우리 {ours} · 받은 것 {theirs}")
    if ours and theirs and ours != theirs:
        print("[실패] 가중치가 다르다. 같은 이름이어도 다른 모델이다")
        return 1

    with chunks.open(encoding="utf-8-sig", newline="") as handle:
        our_rows = list(csv.DictReader(handle))
    pairs, missing = link_by_text(their_rows, our_rows, ids)
    # ids.index 를 반복하면 8,786^2 이 된다. 사전으로 한 번에 만든다
    row_of = {cid: i for i, cid in enumerate(ids)}
    their_text = {row_of[r["chunk_id"]]: r["text"] for r in their_rows
                  if r["chunk_id"] in row_of}
    text_of = {r["chunk_id"]: r["text"] for r in our_rows}
    print()
    print(f"③ 본문으로 id 연결 — {len(pairs):,}건 매칭 · {missing}건 실패")
    if missing:
        print("[실패] 본문이 안 맞는 청크가 있다. 같은 청크 파일이 아니다")
        return 1

    # 본문이 정규화로 바뀌는 청크는 **그의 벡터를 쓰면 안 된다.** 그는 정규화 전
    # 본문으로 인코딩했으므로 텍스트가 다르고, 따라서 벡터도 다르다(실측 0.9986).
    # 이 값은 오류로 안 잡히고 순위만 조용히 흔들린다. 그래서 그만큼만 다시 만든다.
    stale = [(cid, row) for cid, row in pairs
             if their_text[row] != normalize_text(their_text[row])]
    print()
    print(f"④ 정규화로 본문이 바뀌는 청크 {len(stale)}건 — 다시 인코딩한다")
    if stale:
        print("    (그가 정규화 전 본문으로 인코딩했다. 텍스트가 다르면 벡터도 다르다)")

    if not skip_probe:
        # 다시 인코딩할 행은 표본에서 뺀다. 그건 이미 다르다는 걸 아는 행이라,
        # 넣으면 "같은 공간인가" 라는 이 검사의 질문이 흐려진다
        stale_rows = {row for _cid, row in stale}
        clean = [(cid, row) for cid, row in pairs if row not in stale_rows]
        step = max(1, len(clean) // PROBE)
        sample = clean[::step][:PROBE]
        texts = [text_of[cid] for cid, _row in sample]
        cosines = probe(normalized(our_manifest)["model"], texts,
                        normalized(our_manifest)["doc_prefix"],
                        vectors, [row for _cid, row in sample])
        print()
        print(f"⑤ 실측 — 본문이 같은 {len(cosines)}건의 코사인")
        for (cid, _row), cos in zip(sample, cosines):
            print(f"    {cos:.6f}  {cid[:56]}")
        if min(cosines) < COSINE_FLOOR:
            print(f"[실패] 최소 {min(cosines):.6f} < {COSINE_FLOOR}. 같은 공간이 아니다")
            return 1
        print(f"    최소 {min(cosines):.6f} — 같은 공간이다")

    ours_vectors = np.load(base.with_suffix(".npy"))
    with base.with_suffix(".ids.csv").open(encoding="utf-8", newline="") as handle:
        our_ids = [r["chunk_id"] for r in csv.DictReader(handle)]
    add_ids = [cid for cid, _row in pairs]
    overlap = set(our_ids) & set(add_ids)
    if overlap:
        print(f"[실패] id 가 겹친다 {len(overlap)}건. 같은 청크를 두 번 넣게 된다")
        return 1

    take = vectors[[row for _cid, row in pairs]].copy()
    if stale:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(normalized(our_manifest)["model"])
        prefix = normalized(our_manifest)["doc_prefix"]
        where = {row: i for i, (_cid, row) in enumerate(pairs)}
        texts = [text_of[cid] for cid, _row in stale]
        fresh = model.encode([prefix + t for t in texts], convert_to_numpy=True)
        fresh = fresh.astype(np.float32)
        fresh /= np.linalg.norm(fresh, axis=1, keepdims=True)
        for k, (_cid, row) in enumerate(stale):
            take[where[row]] = fresh[k]
        print(f"    {len(stale)}건 교체 완료")

    merged = np.vstack([ours_vectors, take])
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out.with_suffix(".npy"), merged)
    with out.with_suffix(".ids.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["chunk_id"])
        writer.writerows([[i] for i in our_ids + add_ids])
    manifest = {
        **our_manifest,
        "count": len(merged),
        "merged_from": [
            {"owner": "시현", "count": len(our_ids)},
            {"owner": their_manifest.get("source_owner", "?"), "count": len(add_ids),
             "weight_sha256_16": theirs,
             "verified_cosine_min": None if skip_probe else round(min(cosines), 6),
             "reencoded_for_normalization": len(stale)},
        ],
    }
    out.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"[통과] {len(our_ids):,} + {len(add_ids):,} = {len(merged):,} → {out}.npy")
    return 0


def demo() -> None:
    ours = {"model": "e5", "doc_prefix": "passage: ", "l2_normalized": True,
            "dtype": "float32", "dim": 768}
    same = {"model_name": "e5", "prefix": "passage: ", "l2_normalized": True,
            "dtype": "float32", "dim": 768}
    assert compare_settings(ours, same) == [], compare_settings(ours, same)
    # 프리픽스가 다르면 오류 없이 순위만 나빠진다. 반드시 잡아야 한다
    assert compare_settings(ours, {**same, "prefix": "query: "})
    assert compare_settings(ours, {**same, "l2_normalized": False})
    assert compare_settings(ours, {**same, "dim": 384})

    theirs = [{"chunk_id": "Cabc", "text": "백탁  없이"},      # 공백 2개
              {"chunk_id": "Cdef", "text": "촉촉"}]
    our_rows = [{"chunk_id": "d#0", "text": "백탁 없이"},
                {"chunk_id": "e#0", "text": "촉촉"}]
    pairs, missing = link_by_text(theirs, our_rows, ["Cabc", "Cdef"])
    assert missing == 0 and pairs == [("d#0", 0), ("e#0", 1)], (pairs, missing)
    # 본문이 다르면 이을 수 없다고 말해야 한다. 조용히 버리면 안 된다
    _p, miss = link_by_text(theirs, [{"chunk_id": "x#0", "text": "다른 말"}], ["Cabc", "Cdef"])
    assert miss == 1
    print("demo ok")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--incoming", type=Path, help="manifest·vectors·ids·chunks 가 든 폴더")
    p.add_argument("--chunks", type=Path,
                   default=Path("reports/chunks_ingredient_mfds.csv"))
    p.add_argument("--base", type=Path, default=Path(".cache/vectors/e5base"))
    p.add_argument("--out", type=Path, default=Path(".cache/vectors/e5all"))
    p.add_argument("--skip-probe", action="store_true",
                   help="실측 코사인 검증을 건너뛴다. 권하지 않는다")
    p.add_argument("--demo", action="store_true")
    a = p.parse_args()
    if a.demo:
        demo()
        return 0
    if not a.incoming:
        p.error("--incoming 을 주거나 --demo 를 쓴다")
    return run(a.incoming, a.chunks, a.base, a.out, a.skip_probe)


if __name__ == "__main__":
    raise SystemExit(main())
