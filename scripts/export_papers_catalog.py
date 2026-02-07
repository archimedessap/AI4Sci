#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"

DEFAULT_OUT_JSON = ROOT / "web" / "data" / "papers_catalog.json"
DEFAULT_OUT_MD = ROOT / "web" / "data" / "papers_catalog.md"


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


def norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    t = norm_space(text)
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


@dataclass(frozen=True)
class DomainInfo:
    id: str
    name: str


def domain_names_from_base(base: dict[str, Any]) -> dict[str, str]:
    nodes: dict[str, Any] = base.get("nodes") or {}
    out: dict[str, str] = {}
    for nid, node in nodes.items():
        name = node.get("name")
        if isinstance(name, str) and name.strip():
            out[nid] = name.strip()
    return out


def leaf_domain_ids_from_base(base: dict[str, Any]) -> list[str]:
    nodes: dict[str, Any] = base.get("nodes") or {}
    root_id = str(base.get("rootId") or "ai4sci")

    children: dict[str, list[str]] = {nid: [] for nid in nodes.keys()}
    for nid, node in nodes.items():
        pid = node.get("parentId")
        if isinstance(pid, str) and pid in children:
            children[pid].append(nid)
    for pid in children:
        children[pid].sort(key=lambda cid: (int((nodes.get(cid) or {}).get("order") or 0), str(cid)))

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

    leaves: list[str] = []
    for nid in nodes.keys():
        if nid == root_id:
            continue
        if nid in excluded:
            continue
        if children.get(nid):
            continue
        leaves.append(nid)

    leaves.sort(key=lambda nid: (int((nodes.get(nid) or {}).get("order") or 0), str(nid)))
    return leaves


def read_papers(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = con.execute(
        """
        SELECT
          openalex_id,
          doi,
          arxiv_id,
          title,
          abstract,
          publication_date,
          publication_year,
          cited_by_count,
          primary_url,
          source
        FROM papers;
        """
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out[str(r["openalex_id"])] = {
            "id": str(r["openalex_id"]),
            "doi": r["doi"],
            "arxivId": r["arxiv_id"],
            "title": r["title"],
            "abstract": r["abstract"],
            "publicationDate": r["publication_date"],
            "publicationYear": r["publication_year"],
            "citedBy": r["cited_by_count"],
            "url": r["primary_url"] or r["openalex_id"],
            "source": r["source"],
            "domains": [],
        }
    return out


def read_links(con: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = con.execute("SELECT openalex_id, domain_id FROM paper_domains;").fetchall()
    out: list[tuple[str, str]] = []
    for r in rows:
        out.append((str(r["openalex_id"]), str(r["domain_id"])))
    return out


def read_tag_defs(con: sqlite3.Connection, *, tag_type: str) -> dict[str, dict[str, Any]]:
    try:
        rows = con.execute(
            """
            SELECT tag, label, description
            FROM tag_defs
            WHERE tag_type = ?;
            """,
            (tag_type,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        tag = str(r["tag"])
        out[tag] = {
            "tag": tag,
            "label": r["label"],
            "description": r["description"],
        }
    return out


def read_paper_tags(con: sqlite3.Connection, *, tag_type: str) -> dict[str, list[dict[str, Any]]]:
    try:
        rows = con.execute(
            """
            SELECT openalex_id, tag, confidence
            FROM paper_tags
            WHERE tag_type = ?
            ORDER BY COALESCE(confidence, 0) DESC;
            """,
            (tag_type,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        oid = str(r["openalex_id"])
        tag = str(r["tag"])
        conf = r["confidence"]
        try:
            conf_f = float(conf) if conf is not None else None
        except Exception:
            conf_f = None
        out.setdefault(oid, []).append({"tag": tag, "confidence": conf_f})
    return out


def sort_key(p: dict[str, Any]) -> tuple[int, int, str]:
    cited = p.get("citedBy")
    year = p.get("publicationYear")
    date = p.get("publicationDate")
    try:
        cited_i = int(cited) if cited is not None else 0
    except Exception:
        cited_i = 0
    try:
        year_i = int(year) if year is not None else 0
    except Exception:
        year_i = 0
    date_s = str(date) if isinstance(date, str) else ""
    return (cited_i, year_i, date_s)


def export_catalog(
    *,
    db_path: Path,
    base_json_path: Path,
    out_json: Path,
    out_md: Path | None,
    max_total: int,
    max_per_domain_json: int,
    max_per_domain: int,
    abstract_chars_json: int,
    abstract_chars_md: int,
) -> dict[str, Any]:
    base = load_json(base_json_path)
    name_by_domain = domain_names_from_base(base)
    leaf_domains = leaf_domain_ids_from_base(base)

    con = connect(db_path)
    papers = read_papers(con)
    links = read_links(con)
    method_defs = read_tag_defs(con, tag_type="method")
    method_tags = read_paper_tags(con, tag_type="method")
    con.close()

    # Attach domains to paper records.
    domain_counts: dict[str, int] = {}
    for openalex_id, domain_id in links:
        p = papers.get(openalex_id)
        if not p:
            continue
        p["domains"].append(domain_id)
        domain_counts[domain_id] = domain_counts.get(domain_id, 0) + 1

    # Attach method tags (tag ids only, sorted by confidence desc).
    for openalex_id, tags in method_tags.items():
        p = papers.get(openalex_id)
        if not p:
            continue
        tag_ids = [t.get("tag") for t in tags if isinstance(t, dict) and isinstance(t.get("tag"), str)]
        tag_ids = [t for t in tag_ids if t]
        if tag_ids:
            p["methodTags"] = tag_ids

    # Select exported papers: ensure domain coverage by selecting top-k per domain.
    domain_ids = sorted(domain_counts.keys(), key=lambda d: (-domain_counts.get(d, 0), d))
    k = int(max_per_domain_json)
    if k <= 0 and max_total > 0 and domain_ids:
        k = max(1, int(max_total) // max(1, len(domain_ids)))

    if k > 0 and domain_ids:
        ids_by_domain: dict[str, list[str]] = {}
        for openalex_id, domain_id in links:
            if domain_id not in domain_counts:
                continue
            ids_by_domain.setdefault(domain_id, []).append(openalex_id)

        keep_ids: set[str] = set()
        for did in domain_ids:
            ids = ids_by_domain.get(did) or []
            items = [papers.get(oid) for oid in ids]
            items = [p for p in items if p]
            items.sort(key=sort_key, reverse=True)
            keep_ids.update({p["id"] for p in items[:k]})

        all_papers = [p for p in papers.values() if p.get("id") in keep_ids]
        all_papers.sort(key=sort_key, reverse=True)
        if max_total > 0 and len(all_papers) > max_total:
            # Safety cap (may reduce some domain coverage if max_total is too low).
            all_papers = all_papers[: max_total]
    else:
        all_papers = list(papers.values())
        all_papers.sort(key=sort_key, reverse=True)
        if max_total > 0:
            all_papers = all_papers[:max_total]

    # Trim abstracts for JSON to keep payload manageable.
    for p in all_papers:
        if abstract_chars_json > 0:
            p["abstract"] = truncate(p.get("abstract"), abstract_chars_json) or None
        else:
            if not p.get("abstract"):
                p["abstract"] = None

    # Domain summaries.
    domains_out: list[dict[str, Any]] = []
    all_domain_ids = sorted(set(domain_counts.keys()) | set(leaf_domains))
    for domain_id in all_domain_ids:
        count = int(domain_counts.get(domain_id, 0))
        domains_out.append(
            {
                "id": domain_id,
                "name": name_by_domain.get(domain_id, domain_id),
                "count": count,
            }
        )
    domains_out.sort(key=lambda d: (-int(d.get("count") or 0), str(d.get("name") or d.get("id") or "")))

    # Method summaries (count within exported papers).
    method_counts: dict[str, int] = {}
    for p in all_papers:
        for t in p.get("methodTags") or []:
            if not isinstance(t, str) or not t:
                continue
            method_counts[t] = method_counts.get(t, 0) + 1

    methods_out: list[dict[str, Any]] = []
    for tag, count in sorted(method_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        d = method_defs.get(tag) or {}
        methods_out.append(
            {
                "tag": tag,
                "label": d.get("label") or tag,
                "description": d.get("description") or None,
                "count": int(count),
            }
        )

    catalog: dict[str, Any] = {
        "version": "0.1",
        "generatedAt": iso_now(),
        "db": {
            "path": str(db_path),
            "papers": int(len(papers)),
            "links": int(len(links)),
        },
        "domains": domains_out,
        "methods": methods_out,
        "papers": all_papers,
    }

    save_json(out_json, catalog)

    if out_md:
        md = build_markdown(
            catalog,
            max_per_domain=max_per_domain,
            abstract_chars=abstract_chars_md,
            name_by_domain=name_by_domain,
        )
        save_text(out_md, md)

    return catalog


def build_markdown(
    catalog: dict[str, Any],
    *,
    max_per_domain: int,
    abstract_chars: int,
    name_by_domain: dict[str, str],
) -> str:
    papers: list[dict[str, Any]] = list(catalog.get("papers") or [])
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for p in papers:
        for d in p.get("domains") or []:
            by_domain.setdefault(str(d), []).append(p)
    for d in by_domain:
        by_domain[d].sort(key=sort_key, reverse=True)

    lines: list[str] = []
    lines.append("# AI4Sci Paper Catalog")
    lines.append("")
    lines.append(f"- Generated: {catalog.get('generatedAt')}")
    db = catalog.get("db") or {}
    lines.append(f"- DB: `{db.get('path')}` (papers={db.get('papers')}, links={db.get('links')})")
    lines.append("")
    lines.append("说明：这是从 SQLite 论文库导出的可读目录（title + 抽象截断 + 链接）。")
    lines.append("")

    domains: list[dict[str, Any]] = list(catalog.get("domains") or [])
    for dom in domains:
        did = str(dom.get("id") or "")
        if not did:
            continue
        name = name_by_domain.get(did, did)
        count = dom.get("count") or 0
        lines.append(f"## {name} ({did}) — {count} papers")
        lines.append("")
        items = by_domain.get(did, [])
        if max_per_domain > 0:
            items = items[:max_per_domain]
        if not items:
            lines.append("_No papers yet._")
            lines.append("")
            continue
        for i, p in enumerate(items, start=1):
            title = norm_space(str(p.get("title") or "")).strip() or "(untitled)"
            url = str(p.get("url") or p.get("id") or "").strip()
            year = p.get("publicationYear") or ""
            cited = p.get("citedBy")
            meta_bits: list[str] = []
            if year:
                meta_bits.append(str(year))
            if isinstance(cited, int) or (isinstance(cited, str) and cited.isdigit()):
                meta_bits.append(f"cited_by={cited}")
            meta = f" ({', '.join(meta_bits)})" if meta_bits else ""
            if url:
                lines.append(f"{i}. [{title}]({url}){meta}")
            else:
                lines.append(f"{i}. {title}{meta}")
            abs_ = truncate(p.get("abstract"), abstract_chars) if abstract_chars > 0 else ""
            if abs_:
                lines.append(f"   - Abstract: {abs_}")
            methods = p.get("methodTags") or []
            if isinstance(methods, list):
                method_ids = [str(m) for m in methods if isinstance(m, str) and m.strip()]
                if method_ids:
                    lines.append(f"   - Methods: {', '.join(method_ids[:4])}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Export a human-browsable paper catalog from the SQLite library.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--base", type=Path, default=BASE_JSON, help="Base progress JSON (for domain names).")
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON, help="Output JSON path.")
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD, help="Output Markdown path (set to '' to disable).")
    ap.add_argument("--max-total", type=int, default=8000, help="Max papers in JSON (0 = no limit).")
    ap.add_argument(
        "--max-per-domain-json",
        type=int,
        default=0,
        help="Max papers per domain in JSON (0 = auto from max-total / #domains).",
    )
    ap.add_argument("--max-per-domain", type=int, default=200, help="Max papers per domain in Markdown (0 = no limit).")
    ap.add_argument("--abstract-json", type=int, default=900, help="Abstract chars in JSON (0 = keep full).")
    ap.add_argument("--abstract-md", type=int, default=320, help="Abstract chars in Markdown (0 = omit).")
    args = ap.parse_args()

    out_md: Path | None = args.out_md
    if isinstance(args.out_md, Path) and str(args.out_md) == "":
        out_md = None

    export_catalog(
        db_path=args.db,
        base_json_path=args.base,
        out_json=args.out_json,
        out_md=out_md,
        max_total=int(args.max_total),
        max_per_domain_json=int(args.max_per_domain_json),
        max_per_domain=int(args.max_per_domain),
        abstract_chars_json=int(args.abstract_json),
        abstract_chars_md=int(args.abstract_md),
    )

    print(f"[done] wrote {args.out_json}" + (f" and {out_md}" if out_md else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
