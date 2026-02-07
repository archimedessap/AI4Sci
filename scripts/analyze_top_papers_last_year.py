#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
OUT_JSON = ROOT / "web" / "data" / "top_papers_last_year.json"
OUT_MD = ROOT / "web" / "data" / "top_papers_last_year.md"


@dataclass(frozen=True)
class Domain:
    id: str
    name: str


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


def parse_leaf_domains(base: dict[str, Any], *, include_methods: bool = False) -> list[Domain]:
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

    leaves: list[Domain] = []
    for nid, node in nodes.items():
        if nid == root_id:
            continue
        if nid in excluded:
            continue
        if children_by_id.get(nid):
            continue
        name = node.get("name") or nid
        if not isinstance(name, str) or not name.strip():
            name = nid
        leaves.append(Domain(id=nid, name=name.strip()))
    leaves.sort(key=lambda d: d.id)
    return leaves


def parse_pub_date(pub_date: str | None, pub_year: int | None) -> date | None:
    if isinstance(pub_date, str) and pub_date:
        try:
            return date.fromisoformat(pub_date)
        except Exception:
            pass
    if isinstance(pub_year, int) and pub_year > 0:
        # fallback: mid-year
        try:
            return date(pub_year, 7, 1)
        except Exception:
            return None
    return None


def query_domain_papers(con: sqlite3.Connection, domain_id: str) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT
          p.openalex_id,
          p.title,
          p.abstract,
          p.publication_date,
          p.publication_year,
          p.cited_by_count,
          p.primary_url,
          p.source
        FROM paper_domains d
        JOIN papers p ON p.openalex_id = d.openalex_id
        WHERE d.domain_id = ?;
        """,
        (domain_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["openalex_id"],
                "title": r["title"],
                "abstract": r["abstract"],
                "publicationDate": r["publication_date"],
                "publicationYear": r["publication_year"],
                "citedBy": r["cited_by_count"] if r["cited_by_count"] is not None else 0,
                "url": r["primary_url"] or r["openalex_id"],
                "source": r["source"],
            }
        )
    return out


def query_all_papers_with_domains(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT
          p.openalex_id,
          p.title,
          p.abstract,
          p.publication_date,
          p.publication_year,
          p.cited_by_count,
          p.primary_url,
          p.source,
          GROUP_CONCAT(d.domain_id) AS domain_ids
        FROM papers p
        JOIN paper_domains d ON d.openalex_id = p.openalex_id
        GROUP BY p.openalex_id;
        """
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        domain_ids_raw = r["domain_ids"] or ""
        domain_ids = [s for s in str(domain_ids_raw).split(",") if s]
        domain_ids = sorted(set(domain_ids))
        out.append(
            {
                "id": r["openalex_id"],
                "title": r["title"],
                "abstract": r["abstract"],
                "publicationDate": r["publication_date"],
                "publicationYear": r["publication_year"],
                "citedBy": r["cited_by_count"] if r["cited_by_count"] is not None else 0,
                "url": r["primary_url"] or r["openalex_id"],
                "source": r["source"],
                "domainIds": domain_ids,
            }
        )
    return out


def composite_rank(
    papers: list[dict[str, Any]],
    *,
    today: date,
    since: date,
    top_k: int,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    for p in papers:
        pd = parse_pub_date(p.get("publicationDate"), p.get("publicationYear"))
        if not pd:
            continue
        # OpenAlex may contain future/placeholder dates; ignore for "last year" analysis.
        if pd > today:
            continue
        if pd < since:
            continue
        cited = int(p.get("citedBy") or 0)
        cited = max(0, cited)
        log_c = math.log1p(cited)
        age_days = max(0, (today - pd).days)
        recency = max(0.0, 1.0 - (age_days / 365.0))
        items.append({**p, "_pubDate": pd.isoformat(), "_logCited": log_c, "_recency": recency})

    if not items:
        return [], 0

    max_log = max((it["_logCited"] for it in items), default=1.0)
    max_log = max(max_log, 1e-9)

    for it in items:
        c_norm = float(it["_logCited"]) / max_log
        r_norm = float(it["_recency"])
        score = 0.7 * c_norm + 0.3 * r_norm
        it["_score"] = score

    items.sort(key=lambda it: (it.get("_score", 0.0), it.get("_logCited", 0.0), it.get("_pubDate", "")), reverse=True)
    total = len(items)
    top = items[:top_k] if top_k > 0 else items

    cleaned: list[dict[str, Any]] = []
    for it in top:
        obj: dict[str, Any] = {
            "id": it["id"],
            "title": it["title"],
            "url": it.get("url") or it["id"],
            "publicationDate": it.get("publicationDate") or it.get("_pubDate"),
            "publicationYear": it.get("publicationYear"),
            "citedBy": int(it.get("citedBy") or 0),
            "source": it.get("source"),
            "score": round(float(it.get("_score", 0.0)), 4),
        }
        domain_ids = it.get("domainIds")
        if isinstance(domain_ids, list) and domain_ids:
            obj["domainIds"] = sorted({str(d) for d in domain_ids if str(d).strip()})
        cleaned.append(obj)
    return cleaned, total


def build_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Top AI4Sci Papers (Last Year)")
    lines.append("")
    lines.append(f"- Generated: {data.get('generatedAt')}")
    lines.append(f"- Since: {data.get('since')}")
    lines.append("")

    global_top = data.get("globalTop") or []
    if global_top:
        lines.append("## Global Top")
        lines.append("")
        for i, it in enumerate(global_top, start=1):
            title = str(it.get("title") or "").strip()
            url = str(it.get("url") or "").strip()
            score = it.get("score")
            cited = it.get("citedBy")
            pub = it.get("publicationDate") or it.get("publicationYear") or ""
            dom = it.get("domainName") or it.get("domainId") or ""
            if not dom:
                doms = it.get("domainNames") or it.get("domainIds") or []
                if isinstance(doms, list) and doms:
                    dom = ",".join(str(x) for x in doms[:3])
            meta = []
            if dom:
                meta.append(str(dom))
            if pub:
                meta.append(str(pub))
            if cited is not None:
                meta.append(f"cited_by={cited}")
            if score is not None:
                meta.append(f"score={score}")
            m = f" ({', '.join(meta)})" if meta else ""
            lines.append(f"{i}. [{title}]({url}){m}")
        lines.append("")

    by_domain = data.get("byDomain") or []
    for dom in by_domain:
        name = dom.get("domainName") or dom.get("domainId")
        did = dom.get("domainId")
        total = dom.get("totalInLastYear")
        lines.append(f"## {name} ({did}) — {total} papers in last year")
        lines.append("")
        top = dom.get("top") or []
        if not top:
            lines.append("_No papers found in last year window._")
            lines.append("")
            continue
        for i, it in enumerate(top, start=1):
            title = str(it.get("title") or "").strip()
            url = str(it.get("url") or "").strip()
            score = it.get("score")
            cited = it.get("citedBy")
            pub = it.get("publicationDate") or it.get("publicationYear") or ""
            meta = []
            if pub:
                meta.append(str(pub))
            if cited is not None:
                meta.append(f"cited_by={cited}")
            if score is not None:
                meta.append(f"score={score}")
            m = f" ({', '.join(meta)})" if meta else ""
            lines.append(f"{i}. [{title}]({url}){m}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze top AI4Sci papers in the last year (composite rank).")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--out", type=Path, default=OUT_JSON, help="Output JSON path (default: web/data/top_papers_last_year.json)")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown path (default: web/data/top_papers_last_year.md)")
    ap.add_argument("--include-methods", action="store_true", help="Include methods domains in analysis.")
    ap.add_argument("--domains", type=str, default=None, help="Comma-separated domain ids to analyze (optional).")
    ap.add_argument("--top", type=int, default=10, help="Top K per domain (default: 10).")
    ap.add_argument("--global-top", type=int, default=20, help="Global top K (default: 20).")
    args = ap.parse_args()

    if not BASE_JSON.exists():
        raise SystemExit(f"Base data not found: {BASE_JSON}")
    base = load_json(BASE_JSON)
    domains = parse_leaf_domains(base, include_methods=bool(args.include_methods))
    if args.domains:
        allow = {d.strip() for d in args.domains.split(",") if d.strip()}
        domains = [d for d in domains if d.id in allow]
    if not domains:
        raise SystemExit("No domains selected.")

    con = connect(args.db)
    today = datetime.now(tz=UTC).date()
    since = today - timedelta(days=365)

    by_domain_out: list[dict[str, Any]] = []
    domain_name_by_id = {d.id: d.name for d in domains}

    for d in domains:
        papers = query_domain_papers(con, d.id)
        top, total_last_year = composite_rank(papers, today=today, since=since, top_k=int(args.top))
        by_domain_out.append(
            {
                "domainId": d.id,
                "domainName": d.name,
                "totalInDb": len(papers),
                "totalInLastYear": int(total_last_year),
                "top": top,
            }
        )

    # Global top across all papers in DB (not limited to per-domain top).
    all_papers = query_all_papers_with_domains(con)
    global_top, global_total_last_year = composite_rank(
        all_papers, today=today, since=since, top_k=int(args.global_top)
    )
    for it in global_top:
        dom_ids = it.get("domainIds") or []
        if isinstance(dom_ids, list):
            it["domainNames"] = [domain_name_by_id.get(did, did) for did in dom_ids]

    con.close()

    out: dict[str, Any] = {
        "version": "0.1",
        "generatedAt": iso_now(),
        "since": since.isoformat(),
        "byDomain": by_domain_out,
        "globalTotalInLastYear": int(global_total_last_year),
        "globalTop": global_top,
    }
    save_json(args.out, out)
    if args.out_md:
        save_text(args.out_md, build_markdown(out))
    print(f"[done] wrote {args.out}" + (f" and {args.out_md}" if args.out_md else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
