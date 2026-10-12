"""
Retrieval evaluation: semantic-only vs hybrid (title-number match + semantic) vs hybrid+rerank (optional).

Usage (inside the api container):
    python -m app.evaluation.run_eval [--k 5] [--dataset PATH] [--out /tmp/eval_results.json]

For every question it retrieves the top-k chunks in both modes and records the rank of the
first expected document. Reports hit-rate@k and MRR overall and per question type.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import get_conn
from app.evaluation.metrics import first_hit_rank, group_summary, summarize
from app.rag.retrieval import retrieve_chunks

DEFAULT_DATASET = Path(__file__).with_name("dataset.json")


def build_modes(rerank_model: str = "") -> dict[str, tuple[bool, str]]:
    """mode name -> (hybrid, rerank_model). The rerank mode only exists when a model is set."""
    modes: dict[str, tuple[bool, str]] = {"semantic": (False, ""), "hybrid": (True, "")}
    if rerank_model:
        modes["hybrid+rerank"] = (True, rerank_model)
    return modes


async def evaluate(
    questions: list[dict], k: int, modes: dict[str, tuple[bool, str]], rerank_candidates: int = 20
) -> list[dict]:
    settings = get_settings()
    rows: list[dict] = []
    async with get_conn() as conn:
        for q in questions:
            for mode, (hybrid, rerank_model) in modes.items():
                chunks = await retrieve_chunks(
                    conn,
                    question=q["question"],
                    embedding_model=settings.embedding_model,
                    embedding_dim=settings.embedding_dim,
                    k=k,
                    hybrid=hybrid,
                    rerank_model=rerank_model,
                    rerank_candidates=rerank_candidates,
                )
                titles = [c["title"] for c in chunks]
                rows.append(
                    {
                        "id": q["id"],
                        "type": q["type"],
                        "verified": q.get("verified", False),
                        "mode": mode,
                        "question": q["question"],
                        "expected": q["expected_titles"],
                        "retrieved_titles": titles,
                        "rank": first_hit_rank(titles, q["expected_titles"]),
                    }
                )
    return rows


def _print_report(rows: list[dict], k: int, modes: dict) -> dict:
    report: dict = {"k": k, "modes": {}}
    print(f"\n{'question':<16} {'type':<11} {'ok':<3} " + "  ".join(f"{m:>8}" for m in modes))
    by_q: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_q.setdefault(r["id"], {})[r["mode"]] = r
    for qid, modes in by_q.items():
        first = next(iter(modes.values()))
        cells = [
            f"{('#' + str(modes[m]['rank'])) if modes[m]['rank'] else 'miss':>8}" for m in modes
        ]
        flag = "yes" if first["verified"] else "?"
        print(f"{qid:<16} {first['type']:<11} {flag:<3} " + "  ".join(cells))

    misses = [r for r in rows if r["rank"] is None]
    if misses:
        print("\nMisses (expected -> what was retrieved):")
        for r in misses:
            distinct = list(dict.fromkeys(r["retrieved_titles"]))[:3]
            print(f"  [{r['mode']}] {r['id']}: {r['expected']} -> {distinct or 'nothing'}")

    print(f"\nhit-rate@{k} / MRR   (verified = expected document confirmed in the DB)")
    for mode in modes:
        mrows = [r for r in rows if r["mode"] == mode]
        vrows = [r for r in mrows if r["verified"]]
        overall = summarize([r["rank"] for r in mrows])
        verified = summarize([r["rank"] for r in vrows])
        per_type = group_summary(mrows, "type")
        report["modes"][mode] = {"overall": overall, "verified_only": verified, "by_type": per_type}
        print(
            f"  {mode:<9} all: {overall['hit_rate']:.0%} / {overall['mrr']:.3f} (n={overall['n']})"
            f"   verified: {verified['hit_rate']:.0%} / {verified['mrr']:.3f} (n={verified['n']})"
        )
        for t, s in per_type.items():
            print(f"            {t:<11} {s['hit_rate']:.0%} / {s['mrr']:.3f} (n={s['n']})")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--rerank-model",
        default=None,
        help="also evaluate hybrid+rerank with this model (default: RERANK_MODEL from the environment)",
    )
    parser.add_argument("--out", type=Path, default=Path("/tmp/eval_results.json"))
    args = parser.parse_args()

    questions = json.loads(args.dataset.read_text(encoding="utf-8"))["questions"]
    settings = get_settings()
    rerank_model = settings.rerank_model if args.rerank_model is None else args.rerank_model
    modes = build_modes(rerank_model)
    rows = asyncio.run(evaluate(questions, args.k, modes, settings.rerank_candidates))
    report = _print_report(rows, args.k, modes)
    try:
        args.out.write_text(
            json.dumps({"summary": report, "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nDetails written to {args.out}")
    except OSError as exc:
        print(f"\n(could not write {args.out}: {exc})")
    sys.exit(0)


if __name__ == "__main__":
    main()
