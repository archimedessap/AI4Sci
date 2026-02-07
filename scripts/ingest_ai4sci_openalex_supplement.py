#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from export_papers_catalog import export_catalog
from ingest_ai4sci_openalex import (
    BASE_JSON,
    DEFAULT_DB,
    ROOT,
    concept_id_from_url,
    extract_arxiv_id,
    find_concept,
    http_get_json,
    inverted_index_to_text,
    iso_now,
    load_concept_cache,
    openalex_url,
    parse_leaf_domains,
    parse_work_concepts,
    save_concept_cache,
)
from paper_db import (
    add_paper_domain,
    connect,
    init_db,
    replace_paper_concepts,
    upsert_concept,
    upsert_paper,
)

SOURCE_CACHE_PATH = ROOT / ".cache" / "openalex_sources.json"
SOURCE_ID_RE = re.compile(r"^S\d+$", re.I)
ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")
DEFAULT_AI_KEYWORDS = [
    "machine learning",
    "deep learning",
    "neural network",
    "transformer",
    "graph neural network",
    "reinforcement learning",
    "physics-informed",
    "surrogate model",
]


@dataclass(frozen=True)
class SourceRef:
    raw: str
    source_id: str | None
    display_name: str | None
    issn: str | None


def parse_csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def load_list_file(path: Path | None) -> list[str]:
    if not path:
        return []
    if not path.exists():
        raise SystemExit(f"List file not found: {path}")
    items: list[str] = []
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def merge_lists(*lists: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for lst in lists:
        for item in lst:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def source_id_from_url(openalex_id: str) -> str:
    return openalex_id.rstrip("/").split("/")[-1]


def load_source_cache() -> dict[str, dict[str, str]]:
    if not SOURCE_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(SOURCE_CACHE_PATH.read_text("utf-8"))
    except Exception:
        return {}


def save_source_cache(cache: dict[str, dict[str, str]]) -> None:
    SOURCE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", "utf-8")


def resolve_source(term: str, cache: dict[str, dict[str, str]]) -> SourceRef:
    raw = term.strip()
    if not raw:
        raise RuntimeError("Empty source term")

    if raw.lower().startswith("issn:"):
        issn = raw.split(":", 1)[1].strip()
        if issn:
            return SourceRef(raw=raw, source_id=None, display_name=None, issn=issn.upper())

    if raw.startswith("https://openalex.org/"):
        sid = source_id_from_url(raw)
        if SOURCE_ID_RE.fullmatch(sid):
            return SourceRef(raw=raw, source_id=sid.upper(), display_name=None, issn=None)

    if SOURCE_ID_RE.fullmatch(raw):
        return SourceRef(raw=raw, source_id=raw.upper(), display_name=None, issn=None)

    if ISSN_RE.fullmatch(raw):
        return SourceRef(raw=raw, source_id=None, display_name=None, issn=raw.upper())

    cached = cache.get(raw)
    if cached and (cached.get("id") or cached.get("issn")):
        return SourceRef(
            raw=raw,
            source_id=cached.get("id"),
            display_name=cached.get("name"),
            issn=cached.get("issn"),
        )

    data = http_get_json(openalex_url("/sources", {"search": raw, "per-page": "5"}))
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"OpenAlex source not found for term: {raw}")

    term_norm = raw.casefold()
    top = None
    for r in results:
        dn = (r.get("display_name") or "").strip().casefold()
        if dn and dn == term_norm:
            top = r
            break
    if top is None:
        top = results[0]

    sid = source_id_from_url(top["id"])
    name = top.get("display_name") or raw
    issn = None
    issns = top.get("issn")
    if isinstance(issns, list) and issns:
        issn = str(issns[0])

    cache[raw] = {"id": sid, "name": name, "issn": issn or ""}
    return SourceRef(raw=raw, source_id=sid, display_name=name, issn=issn)


def extract_concept_ids(work: dict[str, Any]) -> list[str]:
    concepts = work.get("concepts") or []
    if not isinstance(concepts, list):
        return []
    ids: list[str] = []
    for c in concepts:
        if not isinstance(c, dict):
            continue
        cid_url = c.get("id")
        if isinstance(cid_url, str) and cid_url.strip():
            ids.append(concept_id_from_url(cid_url))
    return ids


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Supplement OpenAlex ingestion using keyword/journal search to improve AI4Sci recall."
    )
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite path (default: data/papers.sqlite)")
    ap.add_argument(
        "--from-date",
        type=str,
        default=None,
        help="Filter works from publication date (YYYY-MM-DD). If omitted, defaults to 5 years window.",
    )
    ap.add_argument("--years", type=int, default=5, help="Window years when --from-date is omitted.")
    ap.add_argument(
        "--keywords",
        type=str,
        default=None,
        help="Comma-separated search keywords (for global OpenAlex search).",
    )
    ap.add_argument("--keywords-file", type=Path, default=None, help="File with one keyword per line.")
    ap.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated journal names, ISSNs, or OpenAlex source ids.",
    )
    ap.add_argument("--sources-file", type=Path, default=None, help="File with one journal/source per line.")
    ap.add_argument(
        "--ai-keywords",
        type=str,
        default=None,
        help="Comma-separated AI keywords used when querying sources (defaults to --keywords or a small preset).",
    )
    ap.add_argument("--ai-keywords-file", type=Path, default=None, help="File with one AI keyword per line.")
    ap.add_argument(
        "--domains",
        type=str,
        default=None,
        help="Comma-separated leaf domain ids to attach (optional). If omitted, allow all leaf domains.",
    )
    ap.add_argument(
        "--include-methods",
        action="store_true",
        help="Include 'methods' subtree domains (ml/causal/robotics...). Default: excluded.",
    )
    ap.add_argument(
        "--max-works-per-query",
        type=int,
        default=800,
        help="Max works per search query (default: 800, 0 = no limit).",
    )
    ap.add_argument("--max-works", type=int, default=0, help="Stop after N works total (0 = no limit).")
    ap.add_argument("--sleep", type=float, default=0.15, help="Sleep seconds between API calls (default 0.15).")
    ap.add_argument(
        "--allow-no-domain",
        action="store_true",
        help="Ingest works even if no leaf domain concept match is found.",
    )
    ap.add_argument("--no-export", action="store_true", help="Skip exporting web paper catalog files.")
    ap.add_argument(
        "--export-json",
        type=Path,
        default=ROOT / "web" / "data" / "papers_catalog.json",
        help="Export JSON path (default: web/data/papers_catalog.json)",
    )
    ap.add_argument(
        "--export-md",
        type=Path,
        default=ROOT / "web" / "data" / "papers_catalog.md",
        help="Export Markdown path (default: web/data/papers_catalog.md)",
    )
    ap.add_argument("--export-max-total", type=int, default=8000, help="Max papers in exported JSON (0 = no limit).")
    ap.add_argument(
        "--export-max-per-domain",
        type=int,
        default=200,
        help="Max papers per domain in exported Markdown (0 = no limit).",
    )
    args = ap.parse_args()

    keywords = merge_lists(parse_csv_list(args.keywords), load_list_file(args.keywords_file))
    sources_raw = merge_lists(parse_csv_list(args.sources), load_list_file(args.sources_file))
    ai_keywords = merge_lists(parse_csv_list(args.ai_keywords), load_list_file(args.ai_keywords_file))

    if sources_raw and not ai_keywords:
        ai_keywords = keywords or list(DEFAULT_AI_KEYWORDS)
        print(f"[info] source queries use ai keywords: {', '.join(ai_keywords)}")

    if not keywords and not sources_raw:
        raise SystemExit("Provide --keywords and/or --sources for supplementary ingestion.")

    if args.from_date:
        from_date = date.fromisoformat(args.from_date)
    else:
        today = datetime.now(tz=UTC).date()
        from_date = date(today.year - (args.years - 1), 1, 1)

    if not BASE_JSON.exists():
        raise SystemExit(f"Base data not found: {BASE_JSON}")

    cache = load_concept_cache()
    base = json.loads(BASE_JSON.read_text("utf-8"))
    nodes: dict[str, Any] = base.get("nodes") or {}

    # Ensure leaf nodes have concept ids. (The progress updater writes them.)
    for nid, node in nodes.items():
        concept = ((node.get("openalex") or {}).get("concept") or {})
        if not concept.get("id") and concept.get("name"):
            try:
                cid, name = find_concept(concept["name"], cache)
                node.setdefault("openalex", {}).setdefault("concept", {})
                node["openalex"]["concept"]["id"] = cid
                node["openalex"]["concept"]["name"] = name
            except Exception:
                continue

    domains = parse_leaf_domains(base, include_methods=bool(args.include_methods))
    if args.domains:
        allow = {d.strip() for d in args.domains.split(",") if d.strip()}
        domains = [d for d in domains if d.id in allow]
    if not domains:
        raise SystemExit("No leaf domains with OpenAlex concept ids found.")

    domain_by_concept: dict[str, list[Any]] = {}
    for d in domains:
        domain_by_concept.setdefault(d.concept_id, []).append(d)

    source_cache = load_source_cache()
    sources: list[SourceRef] = []
    for raw in sources_raw:
        try:
            src = resolve_source(raw, source_cache)
            sources.append(src)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] source resolve failed for {raw!r}: {e}")
    if sources_raw and not sources:
        raise SystemExit("No sources resolved; aborting.")

    con = connect(args.db)
    init_db(con)

    started_at = iso_now()
    added = 0
    updated = 0
    errors = 0
    skipped_no_domain = 0
    skipped_seen = 0
    total_seen = 0

    params_json = json.dumps(
        {
            "from_date": from_date.isoformat(),
            "keywords": keywords,
            "sources": [s.raw for s in sources],
            "ai_keywords": ai_keywords,
            "allow_no_domain": bool(args.allow_no_domain),
        },
        ensure_ascii=False,
    )
    run_id = con.execute(
        "INSERT INTO sync_runs(started_at, source, params_json) VALUES(?, ?, ?)",
        (started_at, "openalex_supplement", params_json),
    ).lastrowid
    con.commit()

    select_fields = ",".join(
        [
            "id",
            "display_name",
            "publication_year",
            "publication_date",
            "cited_by_count",
            "abstract_inverted_index",
            "concepts",
            "ids",
            "doi",
            "primary_location",
        ]
    )

    seen_openalex_ids: set[str] = set()

    def ingest_work(work: dict[str, Any], *, now: str) -> None:
        nonlocal added, updated, errors, skipped_no_domain, skipped_seen

        openalex_id = work.get("id")
        title = work.get("display_name") or ""
        if not (
            isinstance(openalex_id, str)
            and openalex_id
            and isinstance(title, str)
            and title.strip()
        ):
            errors += 1
            return

        if openalex_id in seen_openalex_ids:
            skipped_seen += 1
            return
        seen_openalex_ids.add(openalex_id)

        concept_ids = extract_concept_ids(work)
        matched_domains: list[Any] = []
        for cid in concept_ids:
            matched_domains.extend(domain_by_concept.get(cid, []))

        dedup_domains: list[Any] = []
        domain_ids_seen: set[str] = set()
        for d in matched_domains:
            if d.id in domain_ids_seen:
                continue
            domain_ids_seen.add(d.id)
            dedup_domains.append(d)

        if not dedup_domains and not args.allow_no_domain:
            skipped_no_domain += 1
            return

        ids = work.get("ids") or {}
        doi_url = work.get("doi") or ids.get("doi")
        pl = work.get("primary_location") or {}
        landing = pl.get("landing_page_url") or pl.get("pdf_url") or ids.get("openalex")
        source = ((pl.get("source") or {}).get("display_name")) if isinstance(pl, dict) else None
        abstract = inverted_index_to_text(work.get("abstract_inverted_index"))
        arxiv_id = extract_arxiv_id(doi_url, landing)

        row = {
            "openalex_id": openalex_id,
            "doi": doi_url if isinstance(doi_url, str) else None,
            "arxiv_id": arxiv_id,
            "title": title.strip(),
            "abstract": abstract,
            "publication_date": work.get("publication_date")
            if isinstance(work.get("publication_date"), str)
            else None,
            "publication_year": work.get("publication_year") if isinstance(work.get("publication_year"), int) else None,
            "cited_by_count": work.get("cited_by_count") if isinstance(work.get("cited_by_count"), int) else None,
            "primary_url": landing if isinstance(landing, str) else None,
            "source": source if isinstance(source, str) else None,
            "created_at": now,
            "updated_at": now,
        }

        status = upsert_paper(con, row)
        if status == "inserted":
            added += 1
        else:
            updated += 1

        try:
            c_rows, link_rows = parse_work_concepts(work, now=now)
            for cr in c_rows:
                upsert_concept(con, cr)
            replace_paper_concepts(con, openalex_id=openalex_id, concepts=link_rows)
        except Exception:
            pass

        for d in dedup_domains:
            add_paper_domain(
                con,
                openalex_id=openalex_id,
                domain_id=d.id,
                domain_concept_id=d.concept_id,
            )

    def run_query(*, label: str, filter_str: str, search: str | None) -> None:
        nonlocal total_seen
        cursor = "*"
        query_seen = 0
        while cursor:
            if args.max_works and total_seen >= args.max_works:
                break
            if args.max_works_per_query and query_seen >= args.max_works_per_query:
                break

            params = {
                "filter": filter_str,
                "cursor": cursor,
                "per-page": "200",
                "select": select_fields,
            }
            if search:
                params["search"] = search

            time.sleep(max(0.0, args.sleep))
            data = http_get_json(openalex_url("/works", params))
            results = data.get("results") or []
            if not results:
                break

            now = iso_now()
            stop_due_to_limit = False
            for w in results:
                if args.max_works and total_seen >= args.max_works:
                    stop_due_to_limit = True
                    break
                if args.max_works_per_query and query_seen >= args.max_works_per_query:
                    stop_due_to_limit = True
                    break
                total_seen += 1
                query_seen += 1
                ingest_work(w, now=now)

            cursor = None if stop_due_to_limit else (data.get("meta") or {}).get("next_cursor")
            con.commit()

        print(f"[ok] {label}: seen={query_seen} total_seen={total_seen}")

    base_filter = f"from_publication_date:{from_date.isoformat()}"
    for kw in keywords:
        run_query(label=f"keyword:{kw}", filter_str=base_filter, search=kw)

    if sources:
        for src in sources:
            src_label = src.display_name or src.source_id or src.issn or src.raw
            if src.source_id:
                src_filter = f"primary_location.source.id:{src.source_id}"
            elif src.issn:
                src_filter = f"primary_location.source.issn:{src.issn}"
            else:
                print(f"[warn] source missing id/issn, skipping: {src.raw}")
                continue

            if not ai_keywords:
                raise SystemExit("No AI keywords available for source queries; set --ai-keywords.")

            for kw in ai_keywords:
                filter_str = ",".join([src_filter, base_filter])
                run_query(label=f"source:{src_label} + {kw}", filter_str=filter_str, search=kw)

    finished_at = iso_now()
    con.execute(
        "UPDATE sync_runs SET finished_at = ?, added = ?, updated = ?, errors = ? WHERE id = ?",
        (finished_at, added, updated, errors, run_id),
    )
    con.commit()
    con.close()

    save_concept_cache(cache)
    save_source_cache(source_cache)

    print(
        "[done] supplement ingest",
        f"added={added}",
        f"updated={updated}",
        f"errors={errors}",
        f"skipped_no_domain={skipped_no_domain}",
        f"skipped_seen={skipped_seen}",
    )

    if not args.no_export:
        try:
            export_catalog(
                db_path=args.db,
                base_json_path=BASE_JSON,
                out_json=args.export_json,
                out_md=args.export_md,
                max_total=int(args.export_max_total),
                max_per_domain_json=0,
                max_per_domain=int(args.export_max_per_domain),
                abstract_chars_json=900,
                abstract_chars_md=320,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[warn] export catalog failed: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
