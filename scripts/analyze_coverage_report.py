#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
LAYERS_JSON = ROOT / "web" / "data" / "discovery_layers.json"
FORMAL_LAYERS_JSON = ROOT / "web" / "data" / "formal_layers.json"
OUT_JSON = ROOT / "web" / "data" / "coverage_report.json"
OUT_MD = ROOT / "web" / "data" / "coverage_report.md"


@dataclass(frozen=True)
class DomainRow:
    id: str
    name: str
    macro_id: str
    macro_name: str
    concept_id: str
    concept_name: str
    db_total: int
    db_y0: int
    db_y1: int
    has_discovery_layers: bool
    has_formal_layers: bool
    llm_sampled: int
    llm_discovery: int
    llm_confidence: float
    llm_scheme: str | None
    scores: dict[str, float]


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


def clamp_score(v: Any) -> float:
    try:
        f = float(v)
    except Exception:
        return 0.0
    if f != f or f == float("inf") or f == float("-inf"):
        return 0.0
    return max(0.0, min(100.0, f))


def parse_leaf_domains(base: dict[str, Any], *, include_methods: bool = False) -> list[str]:
    nodes: dict[str, Any] = base.get("nodes") or {}
    root_id = base.get("rootId")

    children_by_id: dict[str, list[str]] = {nid: [] for nid in nodes.keys()}
    for nid, node in nodes.items():
        pid = node.get("parentId")
        if pid and pid in children_by_id:
            children_by_id[pid].append(nid)

    def descendants(root: str) -> set[str]:
        out: set[str] = set()
        stack = [root]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            stack.extend(children_by_id.get(cur, []))
        return out

    excluded: set[str] = set()
    if not include_methods and "methods" in nodes:
        excluded = descendants("methods")

    leaves: list[str] = []
    for nid in nodes.keys():
        if nid == root_id:
            continue
        if nid in excluded:
            continue
        if children_by_id.get(nid):
            continue
        leaves.append(nid)
    leaves.sort()
    return leaves


def macro_of(domain_id: str, base: dict[str, Any]) -> str:
    nodes: dict[str, Any] = base.get("nodes") or {}
    root_id = base.get("rootId")
    cur = domain_id
    visited: set[str] = set()
    while True:
        if cur in visited:
            return domain_id
        visited.add(cur)
        node = nodes.get(cur) or {}
        pid = node.get("parentId")
        if not isinstance(pid, str) or not pid:
            return domain_id
        if pid == root_id:
            return cur
        cur = pid


def avg_overall(scores: dict[str, float]) -> float:
    dims = [scores.get(k, 0.0) for k in ("data", "model", "predict", "experiment", "explain")]
    if not dims:
        return 0.0
    return sum(dims) / len(dims)


def query_domain_counts(con: sqlite3.Connection) -> dict[str, dict[str, int]]:
    cur_year = datetime.now(tz=UTC).year
    rows = con.execute(
        """
        SELECT
          d.domain_id AS domain_id,
          COUNT(*) AS total,
          SUM(CASE WHEN p.publication_year = ? THEN 1 ELSE 0 END) AS y0,
          SUM(CASE WHEN p.publication_year = ? THEN 1 ELSE 0 END) AS y1
        FROM paper_domains d
        JOIN papers p ON p.openalex_id = d.openalex_id
        GROUP BY d.domain_id;
        """,
        (cur_year, cur_year - 1),
    ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        did = r["domain_id"]
        out[str(did)] = {
            "total": int(r["total"] or 0),
            "y0": int(r["y0"] or 0),
            "y1": int(r["y1"] or 0),
        }
    return out


def build_markdown(
    *,
    data: dict[str, Any],
    rows: list[DomainRow],
    macro_rows: list[dict[str, Any]],
) -> str:
    cur_year = datetime.now(tz=UTC).year
    lines: list[str] = []
    lines.append("# Coverage Report")
    lines.append("")
    lines.append(f"- Generated: {data.get('generatedAt')}")
    lines.append(f"- Leaf domains: {data.get('summary', {}).get('leafDomains')}")
    lines.append(f"- DB covered domains: {data.get('summary', {}).get('domainsWithDb')}")
    lines.append(f"- DB papers: {data.get('db', {}).get('papers')}")
    lines.append("")

    lines.append("## By Macro")
    lines.append("")
    for m in macro_rows:
        lines.append(
            f"- {m.get('name')} ({m.get('id')}): leaf={m.get('leafDomains')} • with_db={m.get('withDb')} • papers={m.get('dbPapers')}"
        )
    lines.append("")

    missing = [r for r in rows if r.db_total <= 0]
    if missing:
        lines.append("## Missing DB Coverage (0 papers)")
        lines.append("")
        for r in missing:
            lines.append(f"- {r.macro_name} / {r.name} ({r.id})")
        lines.append("")

    lines.append("## Domain Table")
    lines.append("")
    lines.append(
        f"| Macro | Domain | DB papers | {cur_year} | {cur_year - 1} | LLM layers | LLM sample | OA overall |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        layers = ""
        if r.has_discovery_layers:
            layers = "D"
        if r.has_formal_layers:
            layers = f"{layers}+F" if layers else "F"
        oa_overall = avg_overall(r.scores)
        lines.append(
            f"| {r.macro_name} | {r.name} (`{r.id}`) | {r.db_total} | {r.db_y0} | {r.db_y1} | {layers} | {r.llm_sampled or ''} | {oa_overall:.1f} |"
        )
    lines.append("")
    lines.append(
        "注：OA overall=五维平均（便于快速扫一眼，不等同于网站内的 computeProgress 聚合逻辑）。"
    )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit taxonomy coverage vs local paper DB.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--out", type=Path, default=OUT_JSON, help="Output JSON (default: web/data/coverage_report.json)")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown (default: web/data/coverage_report.md)")
    args = ap.parse_args()

    if not BASE_JSON.exists():
        raise SystemExit(f"Base not found: {BASE_JSON}")

    base = load_json(BASE_JSON)
    nodes: dict[str, Any] = base.get("nodes") or {}
    leaf_ids = parse_leaf_domains(base, include_methods=False)

    discovery_layers = load_json(LAYERS_JSON)
    discovery_nodes = discovery_layers.get("nodes") or {}
    has_discovery = {str(k) for k in discovery_nodes.keys()} if isinstance(discovery_nodes, dict) else set()

    formal_layers = load_json(FORMAL_LAYERS_JSON)
    formal_nodes = formal_layers.get("nodes") or {}
    has_formal = {str(k) for k in formal_nodes.keys()} if isinstance(formal_nodes, dict) else set()

    con = connect(args.db)
    counts = query_domain_counts(con)
    total_papers = int(con.execute("SELECT COUNT(*) AS c FROM papers;").fetchone()["c"] or 0)
    total_links = int(con.execute("SELECT COUNT(*) AS c FROM paper_domains;").fetchone()["c"] or 0)

    macro_ids = [n["id"] for n in nodes.values() if n.get("parentId") == base.get("rootId")]
    macro_name_by_id = {m: (nodes.get(m) or {}).get("name") or m for m in macro_ids}

    rows: list[DomainRow] = []
    for did in leaf_ids:
        n = nodes.get(did) or {}
        name = (n.get("name") or did) if isinstance(n.get("name"), str) else did
        mid = macro_of(did, base)
        mname = macro_name_by_id.get(mid) or (nodes.get(mid) or {}).get("name") or mid
        concept = ((n.get("openalex") or {}).get("concept") or {})
        cid = str(concept.get("id") or "").strip()
        cname = str(concept.get("name") or "").strip()
        c = counts.get(did) or {"total": 0, "y0": 0, "y1": 0}
        dims = (n.get("dimensions") or {}) if isinstance(n.get("dimensions"), dict) else {}
        scores = {k: clamp_score((dims.get(k) or {}).get("score")) for k in ("data", "model", "predict", "experiment", "explain")}
        scores["overall"] = avg_overall(scores)

        d_entry = (discovery_nodes.get(did) or {}) if isinstance(discovery_nodes, dict) else {}
        f_entry = (formal_nodes.get(did) or {}) if isinstance(formal_nodes, dict) else {}
        llm_scheme = None
        chosen: dict[str, Any] | None = None
        if did in has_formal:
            llm_scheme = "formal"
            chosen = f_entry if isinstance(f_entry, dict) else None
        elif did in has_discovery:
            llm_scheme = "discovery"
            chosen = d_entry if isinstance(d_entry, dict) else None

        stats = (chosen.get("stats") or {}) if isinstance(chosen, dict) else {}
        llm_sampled = int(stats.get("sampledPapers") or 0) if llm_scheme else 0
        llm_discovery = int(stats.get("discoveryPapers") or 0) if llm_scheme else 0
        llm_conf = float(chosen.get("confidence") or 0.0) if llm_scheme else 0.0
        rows.append(
            DomainRow(
                id=did,
                name=name,
                macro_id=mid,
                macro_name=str(mname),
                concept_id=cid,
                concept_name=cname,
                db_total=int(c.get("total") or 0),
                db_y0=int(c.get("y0") or 0),
                db_y1=int(c.get("y1") or 0),
                has_discovery_layers=did in has_discovery,
                has_formal_layers=did in has_formal,
                llm_sampled=llm_sampled,
                llm_discovery=llm_discovery,
                llm_confidence=llm_conf,
                llm_scheme=llm_scheme,
                scores=scores,
            )
        )

    rows.sort(key=lambda r: (r.macro_id, r.name.lower()))

    macro_summary: dict[str, dict[str, Any]] = {}
    for r in rows:
        m = macro_summary.setdefault(
            r.macro_id,
            {"id": r.macro_id, "name": r.macro_name, "leafDomains": 0, "withDb": 0, "dbPapers": 0},
        )
        m["leafDomains"] += 1
        if r.db_total > 0:
            m["withDb"] += 1
        m["dbPapers"] += r.db_total

    macro_rows = sorted(macro_summary.values(), key=lambda m: str(m.get("id")))

    out = {
        "version": "0.1",
        "generatedAt": iso_now(),
        "db": {
            "path": str(args.db),
            "papers": total_papers,
            "domainLinks": total_links,
        },
        "summary": {
            "leafDomains": len(rows),
            "domainsWithDb": sum(1 for r in rows if r.db_total > 0),
            "domainsMissingDb": sum(1 for r in rows if r.db_total <= 0),
            "domainsWithLayers": sum(1 for r in rows if r.has_discovery_layers or r.has_formal_layers),
        },
        "macros": macro_rows,
        "domains": [
            {
                "id": r.id,
                "name": r.name,
                "macroId": r.macro_id,
                "macroName": r.macro_name,
                "openalex": {"concept": {"id": r.concept_id, "name": r.concept_name}},
                "db": {"total": r.db_total, "y0": r.db_y0, "y1": r.db_y1},
                "hasDiscoveryLayers": r.has_discovery_layers,
                "hasFormalLayers": r.has_formal_layers,
                "llm": {
                    "scheme": r.llm_scheme,
                    "sampledPapers": r.llm_sampled or None,
                    "discoveryPapers": r.llm_discovery or None,
                    "confidence": round(float(r.llm_confidence or 0.0), 4) if r.llm_scheme else None,
                },
                "scores": r.scores,
            }
            for r in rows
        ],
    }

    save_json(args.out, out)
    md = build_markdown(data=out, rows=rows, macro_rows=macro_rows)
    save_text(args.out_md, md)
    print(f"[done] wrote {args.out} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
