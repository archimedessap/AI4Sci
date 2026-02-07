#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paper_db import clear_paper_tags, connect, init_db, set_paper_tag, upsert_tag_def

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"


def iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def norm_text(v: Any) -> str:
    if not isinstance(v, str):
        return ""
    return v.strip()


def compile_patterns(parts: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in parts), re.I | re.M)


METHOD_DEFS: list[dict[str, Any]] = [
    {
        "tag": "cnn",
        "label": "CNN / Convolution",
        "description": "Convolutional neural networks (ResNet/UNet/etc).",
        "patterns": [r"\\bcnn\\b", r"convolutional", r"\\bresnet\\b", r"\\bu[- ]?net\\b"],
    },
    {
        "tag": "gnn",
        "label": "GNN / Graph NN",
        "description": "Graph neural networks (GCN/GraphSAGE/etc).",
        "patterns": [r"\\bgnn\\b", r"graph neural", r"graph convolution", r"\\bgcn\\b", r"\\bgraphsage\\b"],
    },
    {
        "tag": "transformer",
        "label": "Transformer / Attention",
        "description": "Transformer-based models (BERT/T5/attention).",
        "patterns": [r"transformer", r"self[- ]?attention", r"\\bbert\\b", r"\\bt5\\b", r"\\bvit\\b"],
    },
    {
        "tag": "llm",
        "label": "LLM / Foundation Model",
        "description": "Large language / foundation models (GPT/ChatGPT/prompting).",
        "patterns": [
            r"large language model",
            r"\\bllm\\b",
            r"\\bgpt[- ]?\\d*\\b",
            r"chatgpt",
            r"language model",
            r"in[- ]context",
            r"prompt(ing)?",
            r"retrieval[- ]augmented|\\brag\\b",
            r"instruction[- ]tuning",
        ],
    },
    {
        "tag": "diffusion",
        "label": "Diffusion Model",
        "description": "Diffusion/score-based generative models (DDPM/etc).",
        "patterns": [r"diffusion model", r"denoising diffusion", r"score[- ]based", r"\\bddpm\\b"],
    },
    {
        "tag": "rl",
        "label": "Reinforcement Learning",
        "description": "RL / control policy learning.",
        "patterns": [r"reinforcement learning", r"\\brl\\b", r"actor[- ]critic", r"q[- ]learning", r"policy gradient"],
    },
    {
        "tag": "bayesian",
        "label": "Bayesian / Probabilistic",
        "description": "Bayesian/probabilistic models (GP/VI/etc).",
        "patterns": [r"bayesian", r"gaussian process|\\bgp\\b", r"variational inference", r"probabilistic"],
    },
    {
        "tag": "causal",
        "label": "Causal",
        "description": "Causal inference/discovery (SCM/do-calculus).",
        "patterns": [r"\\bcausal\\b", r"causal inference", r"causal discovery", r"structural causal", r"do[- ]calculus"],
    },
    {
        "tag": "symbolic",
        "label": "Symbolic / Program",
        "description": "Symbolic regression / program synthesis / genetic programming.",
        "patterns": [r"symbolic", r"symbolic regression", r"program synthesis", r"genetic programming"],
    },
    {
        "tag": "pinn",
        "label": "Physics-Informed NN",
        "description": "PINNs / physics-informed learning.",
        "patterns": [r"physics[- ]informed", r"\\bpinns?\\b"],
    },
    {
        "tag": "neural_operator",
        "label": "Neural Operator",
        "description": "Neural operators (FNO/DeepONet/etc).",
        "patterns": [r"neural operator", r"fourier neural operator|\\bfno\\b", r"deeponet"],
    },
]


def build_matchers() -> list[tuple[str, re.Pattern[str], str, str]]:
    out: list[tuple[str, re.Pattern[str], str, str]] = []
    for d in METHOD_DEFS:
        out.append((d["tag"], compile_patterns(d["patterns"]), d["label"], d.get("description") or ""))
    return out


def detect_methods(*, title: str, abstract: str, concepts: str) -> dict[str, float]:
    t = f"{title}\\n{abstract}".strip()
    c = concepts.strip()
    t_low = t.lower()
    c_low = c.lower()

    out: dict[str, float] = {}
    matchers = build_matchers()

    for tag, rx, _, _ in matchers:
        score = 0.0
        # prefer concept matches if available
        if c and rx.search(c_low):
            score = max(score, 0.88)
        if title and rx.search(title):
            score = max(score, 0.78)
        if abstract and rx.search(abstract):
            score = max(score, 0.68)
        # small bump if multiple occurrences in full text
        if score > 0 and t_low:
            hits = len(rx.findall(t_low))
            if hits >= 2:
                score = min(0.95, score + 0.05)
        if score > 0:
            out[tag] = round(score, 3)

    # Hybrid tag if multiple distinct methods detected.
    if len(out) >= 2:
        best = max(out.values()) if out else 0.0
        out["hybrid"] = round(min(0.9, 0.55 + 0.25 * best + 0.05 * (len(out) - 2)), 3)

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Tag AI method types for papers in the SQLite library.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--limit", type=int, default=0, help="Process only top N papers by citations (0 = all).")
    ap.add_argument("--min-confidence", type=float, default=0.65, help="Minimum confidence to store a tag (default: 0.65).")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing method tags for processed papers.")
    ap.add_argument("--only-missing", action="store_true", help="Only tag papers without any method tags yet.")
    args = ap.parse_args()

    con = connect(args.db)
    init_db(con)
    now = iso_now()

    # Register method tag definitions.
    for d in METHOD_DEFS:
        upsert_tag_def(
            con,
            tag_type="method",
            tag=str(d["tag"]),
            label=str(d.get("label") or d["tag"]),
            description=str(d.get("description") or ""),
        )
    upsert_tag_def(con, tag_type="method", tag="hybrid", label="Hybrid / Multi-method", description="Multiple method families detected.")
    con.commit()

    existing_with_any: set[str] = set()
    if args.only_missing:
        rows = con.execute(
            "SELECT DISTINCT openalex_id FROM paper_tags WHERE tag_type = 'method';"
        ).fetchall()
        existing_with_any = {str(r[0]) for r in rows if r and r[0]}
    elif args.overwrite and int(args.limit) <= 0:
        # Fast path: overwrite full DB without per-paper deletes.
        con.execute("DELETE FROM paper_tags WHERE tag_type = 'method';")
        con.commit()

    limit_sql = f"LIMIT {int(args.limit)}" if int(args.limit) > 0 else ""
    cursor = con.execute(
        f"""
        SELECT
          p.openalex_id,
          p.title,
          p.abstract,
          GROUP_CONCAT(c.display_name, ' ') AS concept_names
        FROM papers p
        LEFT JOIN paper_concepts pc ON pc.openalex_id = p.openalex_id
        LEFT JOIN concepts c ON c.concept_id = pc.concept_id
        GROUP BY p.openalex_id
        ORDER BY COALESCE(p.cited_by_count, 0) DESC, COALESCE(p.publication_year, 0) DESC
        {limit_sql};
        """
    )

    processed = 0
    wrote = 0
    skipped = 0
    min_conf = float(args.min_confidence)
    batch = 0

    for r in cursor:
        openalex_id = norm_text(r[0])
        if not openalex_id:
            continue
        if args.only_missing and openalex_id in existing_with_any:
            skipped += 1
            continue

        title = norm_text(r[1])
        abstract = norm_text(r[2])
        concepts = norm_text(r[3])

        if args.overwrite:
            clear_paper_tags(con, openalex_id=openalex_id, tag_type="method")

        tags = detect_methods(title=title, abstract=abstract, concepts=concepts)
        kept = {k: v for k, v in tags.items() if float(v) >= min_conf}

        for tag, conf in sorted(kept.items(), key=lambda kv: (-kv[1], kv[0])):
            set_paper_tag(
                con,
                openalex_id=openalex_id,
                tag_type="method",
                tag=tag,
                confidence=float(conf),
                source="heuristic",
                updated_at=now,
            )
            wrote += 1

        processed += 1
        batch += 1
        if batch >= 500:
            con.commit()
            batch = 0
            if processed % 2000 == 0:
                print(f"[ok] processed={processed} wrote_tags={wrote} skipped={skipped}")

    con.commit()
    con.close()

    print(f"[done] processed={processed} wrote_tags={wrote} skipped={skipped} min_conf={min_conf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
