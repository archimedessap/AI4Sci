#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
OUT_JSON = ROOT / "web" / "data" / "problem_method_map.json"
OUT_MD = ROOT / "web" / "data" / "problem_method_map.md"


@dataclass(frozen=True)
class LeafDomain:
    id: str
    name: str
    macro_id: str
    macro_name: str
    mid_id: str
    mid_name: str
    path: list[str]
    order_key: tuple[int, ...]


@dataclass(frozen=True)
class Method:
    tag: str
    label: str
    description: str
    count: int


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


def build_children(nodes: dict[str, Any]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {nid: [] for nid in nodes.keys()}
    for nid, node in nodes.items():
        pid = node.get("parentId")
        if pid and pid in children:
            children[pid].append(nid)
    for nid in children:
        children[nid].sort(key=lambda cid: (int(nodes.get(cid, {}).get("order") or 0), str(cid)))
    return children


def descendants(root_id: str, children: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    stack = [root_id]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def ancestor_chain(node_id: str, nodes: dict[str, Any]) -> list[str]:
    chain: list[str] = []
    cur = node_id
    seen = set()
    while True:
        if cur in seen:
            break
        seen.add(cur)
        chain.append(cur)
        pid = nodes.get(cur, {}).get("parentId")
        if not pid or pid not in nodes:
            break
        cur = pid
    return chain


def macro_and_mid(
    leaf_id: str,
    *,
    root_id: str,
    nodes: dict[str, Any],
) -> tuple[str, str]:
    chain = ancestor_chain(leaf_id, nodes)
    # chain = [leaf, parent, ..., root?]
    macro_id = leaf_id
    for cur in chain:
        pid = nodes.get(cur, {}).get("parentId")
        if pid == root_id:
            macro_id = cur
            break
    mid_id = leaf_id
    # find the first node whose parent is macro_id
    for cur in chain:
        pid = nodes.get(cur, {}).get("parentId")
        if pid == macro_id:
            mid_id = cur
            break
    return macro_id, mid_id


def name_of(node_id: str, nodes: dict[str, Any]) -> str:
    n = nodes.get(node_id, {})
    name = n.get("name") or node_id
    if not isinstance(name, str) or not name.strip():
        return node_id
    return name.strip()


def order_of(node_id: str, nodes: dict[str, Any]) -> int:
    n = nodes.get(node_id, {})
    try:
        return int(n.get("order") or 0)
    except Exception:
        return 0


def parse_leaf_domains(base: dict[str, Any]) -> list[LeafDomain]:
    nodes: dict[str, Any] = base.get("nodes") or {}
    root_id = base.get("rootId")
    if not isinstance(root_id, str) or root_id not in nodes:
        raise RuntimeError("Invalid base.json: missing rootId")

    children = build_children(nodes)

    excluded: set[str] = set()
    if "methods" in nodes:
        excluded = descendants("methods", children)

    leaves: list[LeafDomain] = []
    for nid in nodes.keys():
        if nid == root_id:
            continue
        if nid in excluded:
            continue
        if children.get(nid):
            continue

        macro_id, mid_id = macro_and_mid(nid, root_id=root_id, nodes=nodes)
        macro_name = name_of(macro_id, nodes)
        mid_name = name_of(mid_id, nodes)
        leaf_name = name_of(nid, nodes)

        # Build a stable ordering key: macro order → mid order → leaf order.
        ok = (order_of(macro_id, nodes), order_of(mid_id, nodes), order_of(nid, nodes))
        path = [macro_name]
        if mid_id != macro_id and mid_name:
            path.append(mid_name)
        if leaf_name and leaf_name not in path:
            path.append(leaf_name)

        leaves.append(
            LeafDomain(
                id=nid,
                name=leaf_name,
                macro_id=macro_id,
                macro_name=macro_name,
                mid_id=mid_id,
                mid_name=mid_name,
                path=path,
                order_key=tuple(int(x) for x in ok),
            )
        )

    leaves.sort(key=lambda d: (d.order_key, d.macro_name, d.mid_name, d.name, d.id))
    return leaves


def query_total_papers(con: sqlite3.Connection, *, since_year: int) -> int:
    row = con.execute(
        """
        SELECT COUNT(DISTINCT p.openalex_id) AS c
        FROM papers p
        JOIN paper_tags t ON t.openalex_id = p.openalex_id AND t.tag_type = 'method'
        WHERE p.publication_year >= ?
          AND EXISTS (SELECT 1 FROM paper_domains d WHERE d.openalex_id = p.openalex_id);
        """,
        (since_year,),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def query_methods(con: sqlite3.Connection, *, since_year: int) -> list[Method]:
    rows = con.execute(
        """
        SELECT
          t.tag AS tag,
          COALESCE(def.label, t.tag) AS label,
          COALESCE(def.description, '') AS description,
          COUNT(DISTINCT p.openalex_id) AS c
        FROM papers p
        JOIN paper_tags t ON t.openalex_id = p.openalex_id AND t.tag_type = 'method'
        LEFT JOIN tag_defs def ON def.tag_type = 'method' AND def.tag = t.tag
        WHERE p.publication_year >= ?
          AND EXISTS (SELECT 1 FROM paper_domains d WHERE d.openalex_id = p.openalex_id)
        GROUP BY t.tag
        ORDER BY c DESC, t.tag ASC;
        """,
        (since_year,),
    ).fetchall()
    out: list[Method] = []
    for r in rows:
        tag = str(r[0] or "").strip()
        if not tag:
            continue
        label = str(r[1] or tag).strip() or tag
        desc = str(r[2] or "").strip()
        try:
            c = int(r[3] or 0)
        except Exception:
            c = 0
        if c <= 0:
            continue
        out.append(Method(tag=tag, label=label, description=desc, count=c))
    return out


def query_domain_totals(
    con: sqlite3.Connection,
    *,
    since_year: int,
    domain_ids: list[str],
) -> dict[str, int]:
    if not domain_ids:
        return {}
    placeholders = ",".join(["?"] * len(domain_ids))
    rows = con.execute(
        f"""
        SELECT
          d.domain_id,
          COUNT(DISTINCT p.openalex_id) AS c
        FROM papers p
        JOIN paper_domains d ON d.openalex_id = p.openalex_id
        JOIN paper_tags t ON t.openalex_id = p.openalex_id AND t.tag_type = 'method'
        WHERE p.publication_year >= ?
          AND d.domain_id IN ({placeholders})
        GROUP BY d.domain_id;
        """,
        (since_year, *domain_ids),
    ).fetchall()
    out: dict[str, int] = {}
    for r in rows:
        did = str(r[0] or "").strip()
        if not did:
            continue
        try:
            out[did] = int(r[1] or 0)
        except Exception:
            out[did] = 0
    return out


def query_cells(
    con: sqlite3.Connection,
    *,
    since_year: int,
    domain_ids: list[str],
) -> dict[tuple[str, str], int]:
    if not domain_ids:
        return {}
    placeholders = ",".join(["?"] * len(domain_ids))
    rows = con.execute(
        f"""
        SELECT
          d.domain_id,
          t.tag,
          COUNT(DISTINCT p.openalex_id) AS c
        FROM papers p
        JOIN paper_domains d ON d.openalex_id = p.openalex_id
        JOIN paper_tags t ON t.openalex_id = p.openalex_id AND t.tag_type = 'method'
        WHERE p.publication_year >= ?
          AND d.domain_id IN ({placeholders})
        GROUP BY d.domain_id, t.tag;
        """,
        (since_year, *domain_ids),
    ).fetchall()
    out: dict[tuple[str, str], int] = {}
    for r in rows:
        did = str(r[0] or "").strip()
        tag = str(r[1] or "").strip()
        if not did or not tag:
            continue
        try:
            c = int(r[2] or 0)
        except Exception:
            c = 0
        out[(did, tag)] = c
    return out


def build_markdown(data: dict[str, Any]) -> str:
    window = data.get("window") or {}
    since_year = window.get("sinceYear")
    years = window.get("years")
    total_papers = (data.get("totals") or {}).get("papers")

    lines: list[str] = []
    lines.append("# Problem ↔ Method Map")
    lines.append("")
    lines.append(f"- Generated: {data.get('generatedAt')}")
    lines.append(f"- Window: last {years} years (since {since_year})")
    lines.append(f"- Papers (with method tags): {total_papers}")
    lines.append("")

    methods = data.get("methods") or []
    if methods:
        lines.append("## Methods (counts)")
        lines.append("")
        for m in methods:
            lines.append(f"- {m.get('label')} ({m.get('tag')}): {m.get('count')}")
        lines.append("")

    domains = data.get("domains") or []
    if domains:
        lines.append("## Domains (counts)")
        lines.append("")
        top = sorted(domains, key=lambda d: int(d.get("totalPapers") or 0), reverse=True)[:20]
        for d in top:
            path = " / ".join(d.get("path") or [])
            lines.append(f"- {path} ({d.get('id')}): {d.get('totalPapers')}")
        lines.append("")

    pairs = data.get("topPairs") or []
    if pairs:
        lines.append("## Top Intersections (domain × method)")
        lines.append("")
        for it in pairs:
            lines.append(
                f"- {it.get('domainPath')} × {it.get('methodLabel')}: {it.get('count')}"
            )
        lines.append("")

    blanks = data.get("blankSpots") or []
    if blanks:
        lines.append("## Blank Spots (high expected, low observed)")
        lines.append("")
        for it in blanks:
            lines.append(
                f"- {it.get('domainPath')} × {it.get('methodLabel')}: observed={it.get('count')}, expected≈{it.get('expected')}, ratio≈{it.get('opportunity')}"
            )
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- “Problem space” is approximated by the site taxonomy’s leaf subfields (domains).")
    lines.append("- “Method space” uses heuristic method tags (CNN/GNN/Transformer/LLM/…).")
    lines.append("- Blank spots are ranked by an independence-based expectation: expected = domain_total × method_total / total_papers, then ratio = (expected+1)/(observed+1).")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a Problem↔Method overview (leaf domain × AI method tags) + blank-spot hints."
    )
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--base", type=Path, default=BASE_JSON, help="Taxonomy base.json path (default: web/data/base.json)")
    ap.add_argument("--out-json", type=Path, default=OUT_JSON, help="Output JSON path (default: web/data/problem_method_map.json)")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown path (default: web/data/problem_method_map.md)")
    ap.add_argument("--years", type=int, default=3, help="Time window in years (default: 3)")
    ap.add_argument("--since-year", type=int, default=0, help="Override start year (inclusive). If set, overrides --years.")
    ap.add_argument("--min-expected", type=float, default=3.0, help="Minimum expected count to consider a blank spot (default: 3.0)")
    ap.add_argument("--top-blank", type=int, default=24, help="How many blank spots to export (default: 24)")
    ap.add_argument("--top-pairs", type=int, default=24, help="How many top (domain×method) pairs to export (default: 24)")
    args = ap.parse_args()

    base = load_json(args.base)
    leaves = parse_leaf_domains(base)
    domain_ids = [d.id for d in leaves]

    now_year = datetime.now(tz=UTC).year
    years = int(args.years or 3)
    since_year = int(args.since_year or 0) or (now_year - max(1, years) + 1)

    con = connect(args.db)
    total_papers = query_total_papers(con, since_year=since_year)
    methods = query_methods(con, since_year=since_year)

    domain_totals = query_domain_totals(con, since_year=since_year, domain_ids=domain_ids)
    cell_counts = query_cells(con, since_year=since_year, domain_ids=domain_ids)
    con.close()

    method_by_tag = {m.tag: m for m in methods}
    tags = [m.tag for m in methods]

    domains_out: list[dict[str, Any]] = []
    for d in leaves:
        domains_out.append(
            {
                "id": d.id,
                "name": d.name,
                "macroId": d.macro_id,
                "macroName": d.macro_name,
                "midId": d.mid_id,
                "midName": d.mid_name,
                "path": d.path,
                "totalPapers": int(domain_totals.get(d.id, 0)),
            }
        )

    methods_out: list[dict[str, Any]] = []
    method_totals = {m.tag: int(m.count) for m in methods}
    for m in methods:
        methods_out.append(
            {
                "tag": m.tag,
                "label": m.label,
                "description": m.description,
                "count": int(m.count),
            }
        )

    # Full matrix cells (including zeros) for easy visualization.
    cells_out: list[list[int]] = []
    for yi, d in enumerate(leaves):
        for xi, tag in enumerate(tags):
            c = int(cell_counts.get((d.id, tag), 0))
            cells_out.append([xi, yi, c])

    # Top intersections by observed count.
    top_pairs: list[dict[str, Any]] = []
    for (did, tag), c in sorted(cell_counts.items(), key=lambda kv: (-int(kv[1]), kv[0][0], kv[0][1]))[: int(args.top_pairs)]:
        domain = next((x for x in domains_out if x["id"] == did), None)
        method = method_by_tag.get(tag)
        if not domain or not method:
            continue
        top_pairs.append(
            {
                "domainId": did,
                "domainPath": " / ".join(domain.get("path") or [domain.get("name") or did]),
                "methodTag": tag,
                "methodLabel": method.label,
                "count": int(c),
            }
        )

    # Blank spots: high expected, low observed.
    blanks: list[dict[str, Any]] = []
    min_expected = float(args.min_expected)

    denom = max(1, int(total_papers))
    for di, d in enumerate(domains_out):
        dt = int(d.get("totalPapers") or 0)
        if dt <= 0:
            continue
        for mi, m in enumerate(methods_out):
            tag = str(m.get("tag") or "").strip()
            mt = int(method_totals.get(tag, 0))
            if mt <= 0:
                continue
            observed = int(cell_counts.get((d["id"], tag), 0))
            expected = (dt * mt) / denom
            if expected < min_expected:
                continue
            # Ratio > 1 means "under-explored" relative to expectation.
            ratio = (expected + 1.0) / (observed + 1.0)
            if ratio <= 1.25:
                continue
            blanks.append(
                {
                    "domainId": d["id"],
                    "domainPath": " / ".join(d.get("path") or [d.get("name") or d["id"]]),
                    "methodTag": tag,
                    "methodLabel": str(m.get("label") or tag),
                    "count": observed,
                    "expected": round(expected, 2),
                    "opportunity": round(ratio, 2),
                }
            )

    blanks.sort(key=lambda it: (float(it.get("opportunity") or 0.0), float(it.get("expected") or 0.0)), reverse=True)
    blanks = blanks[: int(args.top_blank)]

    out: dict[str, Any] = {
        "version": "0.1",
        "generatedAt": iso_now(),
        "window": {"sinceYear": since_year, "years": years},
        "totals": {"papers": int(total_papers)},
        "domains": domains_out,
        "methods": methods_out,
        "cells": cells_out,
        "topPairs": top_pairs,
        "blankSpots": blanks,
        "notes": {
            "problemSpace": "Leaf domains in the site taxonomy (excluding the 'methods' branch).",
            "methodSpace": "Heuristic method tags stored in paper_tags(tag_type='method').",
            "blankSpotFormula": "expected = domain_total * method_total / total_papers; opportunity = (expected+1)/(observed+1).",
        },
    }

    save_json(args.out_json, out)
    save_text(args.out_md, build_markdown(out))

    max_cell = 0
    for _, _, c in cells_out:
        max_cell = max(max_cell, int(c))
    print(
        "[ok] wrote",
        args.out_json,
        "cells=",
        len(cells_out),
        "domains=",
        len(domains_out),
        "methods=",
        len(methods_out),
        "max_cell=",
        max_cell,
        "total_papers=",
        total_papers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

