#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
DEFAULT_OUT_JSON = ROOT / "web" / "data" / "domain_extra_metrics.json"
DEFAULT_OUT_MD = ROOT / "web" / "data" / "domain_extra_metrics.md"


def iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def norm_text(s: str | None) -> str:
    return (s or "").strip().lower()


def compile_or_keywords(keywords: list[str]) -> re.Pattern[str]:
    # Use word-ish boundaries where possible but keep robust for hyphenated phrases.
    parts = []
    for k in keywords:
        k = k.strip().lower()
        if not k:
            continue
        parts.append(re.escape(k))
    if not parts:
        return re.compile(r"a^")  # never matches
    return re.compile("|".join(parts), flags=re.I)


# Heuristic signals (fast, explainable). These are meant to be *separate* from discovery depth.
TOOLING_KEYWORDS = [
    "dataset",
    "benchmark",
    "corpus",
    "database",
    "knowledge base",
    "repository",
    "open source",
    "open-source",
    "software",
    "package",
    "library",
    "toolbox",
    "tool",
    "framework",
    "pipeline",
    "platform",
    "workflow",
    "pretrained model",
    "pre-trained model",
]

AUTONOMY_KEYWORDS = [
    "closed loop",
    "closed-loop",
    "autonomous",
    "self-driving",
    "self driving",
    "robotic",
    "robot",
    "lab automation",
    "automated experiment",
    "automated experimentation",
    "high-throughput",
    "high throughput",
    "active learning",
    "bayesian optimization",
    "in the loop",
    "in-the-loop",
]


@dataclass(frozen=True)
class Leaf:
    id: str
    name: str


def build_tree(base: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]], dict[str, list[str]]]:
    root_id = str(base.get("rootId") or "ai4sci")
    nodes: dict[str, dict[str, Any]] = base.get("nodes") or {}
    children: dict[str, list[str]] = {nid: [] for nid in nodes.keys()}
    for nid, node in nodes.items():
        pid = node.get("parentId")
        if isinstance(pid, str) and pid in children:
            children[pid].append(nid)
    for pid in children:
        children[pid].sort(key=lambda cid: (nodes.get(cid) or {}).get("order") or 0)
    return root_id, nodes, children


def leaf_domains(base: dict[str, Any]) -> list[Leaf]:
    root_id, nodes, children = build_tree(base)

    def descendants(start: str) -> set[str]:
        out: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            stack.extend(children.get(cur, []))
        return out

    excluded: set[str] = set()
    if "methods" in nodes:
        excluded = descendants("methods")

    leaves: list[Leaf] = []
    for nid, node in nodes.items():
        if nid == root_id:
            continue
        if nid in excluded:
            continue
        if children.get(nid):
            continue
        name = node.get("name")
        leaves.append(Leaf(id=nid, name=name if isinstance(name, str) and name.strip() else nid))
    leaves.sort(key=lambda d: d.id)
    return leaves


def query_paper_flags(con: sqlite3.Connection) -> tuple[dict[str, bool], dict[str, bool]]:
    tooling_re = compile_or_keywords(TOOLING_KEYWORDS)
    autonomy_re = compile_or_keywords(AUTONOMY_KEYWORDS)

    is_tooling: dict[str, bool] = {}
    is_autonomy: dict[str, bool] = {}

    rows = con.execute("SELECT openalex_id, title, abstract FROM papers;").fetchall()
    for r in rows:
        pid = str(r["openalex_id"])
        text = (norm_text(r["title"]) + " " + norm_text(r["abstract"])).strip()
        is_tooling[pid] = bool(tooling_re.search(text))
        is_autonomy[pid] = bool(autonomy_re.search(text))
    return is_tooling, is_autonomy


def build_markdown(out: dict[str, Any], base: dict[str, Any], *, top_n: int) -> str:
    nodes = base.get("nodes") or {}
    entries = out.get("nodes") or {}
    rows: list[tuple[float, str, dict[str, Any]]] = []
    for did, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        stats = entry.get("stats") or {}
        total = stats.get("totalPapersApprox") or stats.get("totalPapers") or 0
        try:
            total_i = int(total)
        except Exception:
            total_i = 0
        if total_i <= 0:
            continue
        rows.append((float(total_i), str(did), entry))
    rows.sort(reverse=True, key=lambda t: t[0])

    def nm(did: str) -> str:
        n = nodes.get(did) or {}
        name = n.get("name")
        return name if isinstance(name, str) and name.strip() else did

    lines: list[str] = []
    lines.append("# Domain Extra Metrics (Tooling & Autonomy)")
    lines.append("")
    lines.append(f"- Generated: {out.get('generatedAt')}")
    lines.append(f"- DB: `{out.get('db', {}).get('path')}`")
    lines.append("")
    lines.append("说明：这是基于标题+摘要关键词的启发式统计，用来把“工具/基础设施”和“闭环自治”从“发现深度”里剥离出来。")
    lines.append("")

    lines.append("## Top domains by DB volume (sample)")
    lines.append("")
    for _, did, entry in rows[: max(1, int(top_n))]:
        tooling = entry.get("tooling", 0.0)
        autonomy = entry.get("autonomy", 0.0)
        stats = entry.get("stats") or {}
        total = stats.get("totalPapersApprox") or stats.get("totalPapers") or 0
        lines.append(
            f"- {nm(did)} ({did}) — total≈{total} | tooling={round(float(tooling)*100)}% | autonomy={round(float(autonomy)*100)}%"
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute per-domain tooling/autonomy metrics from the local paper DB.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--base", type=Path, default=BASE_JSON, help="Base taxonomy JSON (default: web/data/base.json)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_JSON, help="Output JSON path.")
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD, help="Output Markdown path (set to '' to disable).")
    ap.add_argument("--top-md", type=int, default=24, help="Top N domains to include in Markdown.")
    args = ap.parse_args()

    base = load_json(args.base)
    root_id, nodes, children = build_tree(base)
    leaves = leaf_domains(base)

    con = connect(args.db)
    try:
        # Build per-paper flags once, then aggregate by domain.
        is_tooling, is_autonomy = query_paper_flags(con)

        totals: dict[str, int] = defaultdict(int)
        tooling_hits: dict[str, int] = defaultdict(int)
        autonomy_hits: dict[str, int] = defaultdict(int)

        rows = con.execute("SELECT openalex_id, domain_id FROM paper_domains;").fetchall()
        for r in rows:
            pid = str(r["openalex_id"])
            did = str(r["domain_id"])
            totals[did] += 1
            if is_tooling.get(pid, False):
                tooling_hits[did] += 1
            if is_autonomy.get(pid, False):
                autonomy_hits[did] += 1

        leaf_ids = {d.id for d in leaves}
        leaf_metrics: dict[str, dict[str, Any]] = {}
        for did in sorted(leaf_ids):
            total = totals.get(did, 0)
            tool = tooling_hits.get(did, 0)
            auto = autonomy_hits.get(did, 0)
            tool_r = (tool / total) if total > 0 else 0.0
            auto_r = (auto / total) if total > 0 else 0.0
            leaf_metrics[did] = {
                "tooling": round(clamp01(tool_r), 6),
                "autonomy": round(clamp01(auto_r), 6),
                "stats": {
                    "totalPapers": int(total),
                    "toolingPapers": int(tool),
                    "autonomyPapers": int(auto),
                },
            }

        # Aggregate to all nodes (macro/mid) using weighted mean of descendant leaves.
        def leaf_descendants(start: str) -> list[str]:
            out: list[str] = []
            stack = [start]
            seen: set[str] = set()
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                ch = children.get(cur, [])
                if not ch:
                    if cur in leaf_ids:
                        out.append(cur)
                    continue
                for c in ch:
                    stack.append(c)
            return out

        all_ids = list(nodes.keys())
        out_nodes: dict[str, Any] = {}
        for nid in all_ids:
            desc = leaf_descendants(nid)
            if not desc:
                continue
            weights: list[float] = []
            tool_vals: list[float] = []
            auto_vals: list[float] = []
            total_approx = 0
            for did in desc:
                m = leaf_metrics.get(did)
                if not m:
                    continue
                st = (m.get("stats") or {}).get("totalPapers") or 0
                try:
                    st_i = int(st)
                except Exception:
                    st_i = 0
                w = math.sqrt(max(1, st_i))
                weights.append(w)
                tool_vals.append(float(m.get("tooling") or 0.0))
                auto_vals.append(float(m.get("autonomy") or 0.0))
                total_approx += st_i

            if not weights:
                continue
            den = sum(weights) or 1.0
            tool = sum(w * v for w, v in zip(weights, tool_vals)) / den
            auto = sum(w * v for w, v in zip(weights, auto_vals)) / den
            out_nodes[nid] = {
                "tooling": round(clamp01(tool), 6),
                "autonomy": round(clamp01(auto), 6),
                "stats": {
                    "leafDomains": int(len(desc)),
                    "totalPapersApprox": int(total_approx),
                },
            }

        out = {
            "version": "0.1",
            "generatedAt": iso_now(),
            "db": {"path": str(args.db)},
            "keywords": {
                "tooling": TOOLING_KEYWORDS,
                "autonomy": AUTONOMY_KEYWORDS,
            },
            "nodes": out_nodes,
        }
        save_json(args.out, out)

        out_md: Path | None = args.out_md
        if isinstance(args.out_md, Path) and str(args.out_md) == "":
            out_md = None
        if out_md:
            save_text(out_md, build_markdown(out, base, top_n=int(args.top_md)))

        print(f"[done] wrote {args.out}" + (f" and {out_md}" if out_md else ""))
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())

