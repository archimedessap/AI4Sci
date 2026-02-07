#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from paper_db import (
    add_paper_domain,
    connect,
    init_db,
    replace_paper_concepts,
    upsert_concept,
    upsert_paper,
)
from export_papers_catalog import export_catalog

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
CACHE_DIR = ROOT / ".cache"
CONCEPT_CACHE_PATH = CACHE_DIR / "openalex_concepts.json"

USER_AGENT = "AI4SciProgressAtlas/0.2 (OpenAlex; +https://openalex.org/)"


def http_get_json(url: str, *, retries: int = 5, timeout: int = 40) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(min(2.0**attempt, 8.0))
    raise RuntimeError(f"GET failed after {retries} retries: {url}") from last_err


def openalex_url(path: str, params: dict[str, str]) -> str:
    return f"https://api.openalex.org{path}?{urllib.parse.urlencode(params)}"


def load_concept_cache() -> dict[str, dict[str, str]]:
    if not CONCEPT_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CONCEPT_CACHE_PATH.read_text("utf-8"))
    except Exception:
        return {}


def save_concept_cache(cache: dict[str, dict[str, str]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CONCEPT_CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", "utf-8")


def concept_id_from_url(openalex_id: str) -> str:
    return openalex_id.rstrip("/").split("/")[-1]


def find_concept(term: str, cache: dict[str, dict[str, str]]) -> tuple[str, str]:
    cached = cache.get(term)
    if cached and cached.get("id") and cached.get("name"):
        return cached["id"], cached["name"]

    data = http_get_json(openalex_url("/concepts", {"search": term, "per-page": "5"}))
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"OpenAlex concept not found for term: {term}")

    term_norm = term.strip().casefold()
    top = None
    for r in results:
        dn = (r.get("display_name") or "").strip().casefold()
        if dn and dn == term_norm:
            top = r
            break
    if top is None:
        top = results[0]

    cid = concept_id_from_url(top["id"])
    name = top.get("display_name") or term
    cache[term] = {"id": cid, "name": name}
    return cid, name


def inverted_index_to_text(inv: dict[str, list[int]] | None) -> str | None:
    if not inv:
        return None
    max_pos = -1
    for positions in inv.values():
        if not positions:
            continue
        mp = max(positions)
        if mp > max_pos:
            max_pos = mp
    if max_pos < 0:
        return None
    words = [""] * (max_pos + 1)
    for token, positions in inv.items():
        for p in positions or []:
            if 0 <= p <= max_pos:
                words[p] = token
    text = " ".join(w for w in words if w)
    # basic cleanup
    text = re.sub(r"\s+([,.;:!?])", r"\\1", text)
    return text.strip() or None


ARXIV_ABS_RE = re.compile(r"arxiv\\.org/(abs|pdf)/(?P<id>[0-9]{4}\\.[0-9]{4,5})(v\\d+)?")
ARXIV_DOI_RE = re.compile(r"10\\.48550/arxiv\\.(?P<id>[0-9]{4}\\.[0-9]{4,5})(v\\d+)?", re.I)


def extract_arxiv_id(doi_url: str | None, landing_url: str | None) -> str | None:
    if isinstance(landing_url, str):
        m = ARXIV_ABS_RE.search(landing_url)
        if m:
            return m.group("id")
    if isinstance(doi_url, str):
        m = ARXIV_DOI_RE.search(doi_url)
        if m:
            return m.group("id")
    return None


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    concept_id: str


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
        concept = ((node.get("openalex") or {}).get("concept") or {})
        cid = concept.get("id")
        if not isinstance(cid, str) or not cid.strip():
            continue
        leaves.append(Domain(id=nid, name=node.get("name") or nid, concept_id=cid.strip()))

    leaves.sort(key=lambda d: d.id)
    return leaves


def parse_ai_concepts(raw: str, cache: dict[str, dict[str, str]]) -> list[str]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    ids: list[str] = []
    for p in parts:
        if p.startswith("https://openalex.org/C"):
            ids.append(concept_id_from_url(p))
        elif re.fullmatch(r"C\\d+", p):
            ids.append(p)
        else:
            cid, _ = find_concept(p, cache)
            ids.append(cid)
    # stable unique
    seen = set()
    out: list[str] = []
    for cid in ids:
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def parse_work_concepts(w: dict[str, Any], *, now: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns:
      - concepts rows for `concepts` table
      - link rows for `paper_concepts` table (must include openalex_id)
    """
    out_concepts: list[dict[str, Any]] = []
    out_links: list[dict[str, Any]] = []
    concepts = w.get("concepts") or []
    if not isinstance(concepts, list):
        return out_concepts, out_links

    work_id = w.get("id")
    if not isinstance(work_id, str) or not work_id:
        return out_concepts, out_links

    for c in concepts:
        if not isinstance(c, dict):
            continue
        cid_url = c.get("id")
        name = c.get("display_name")
        if not (isinstance(cid_url, str) and cid_url.strip() and isinstance(name, str) and name.strip()):
            continue
        cid = concept_id_from_url(cid_url)
        level = c.get("level")
        wikidata = c.get("wikidata")
        score = c.get("score")
        try:
            level_i = int(level) if level is not None else None
        except Exception:
            level_i = None
        try:
            score_f = float(score) if score is not None else None
        except Exception:
            score_f = None

        out_concepts.append(
            {
                "concept_id": cid,
                "display_name": name.strip(),
                "level": level_i,
                "wikidata": wikidata if isinstance(wikidata, str) and wikidata.strip() else None,
                "updated_at": now,
            }
        )
        out_links.append(
            {
                "openalex_id": work_id,
                "concept_id": cid,
                "score": score_f,
            }
        )

    return out_concepts, out_links


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest AI4Sci (AI×domain) papers from OpenAlex into SQLite.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite path (default: data/papers.sqlite)")
    ap.add_argument(
        "--from-date",
        type=str,
        default=None,
        help="Filter works from publication date (YYYY-MM-DD). If omitted, defaults to 5 years window.",
    )
    ap.add_argument("--years", type=int, default=5, help="Window years when --from-date is omitted.")
    ap.add_argument(
        "--ai-concepts",
        type=str,
        default="Machine learning,Artificial intelligence,Deep learning",
        help="Comma-separated OpenAlex concept ids or names treated as AI (default: ML, AI, Deep learning).",
    )
    ap.add_argument("--domains", type=str, default=None, help="Comma-separated domain node ids to ingest (optional).")
    ap.add_argument(
        "--include-methods",
        action="store_true",
        help="Include 'methods' subtree domains (ml/causal/robotics...). Default: excluded to keep AI4Sci focused on science domains.",
    )
    ap.add_argument(
        "--sort-strategy",
        type=str,
        default="both",
        choices=["both", "cited", "recent"],
        help="Ingestion strategy per domain: cited_by_count desc, publication_date desc, or both (default).",
    )
    ap.add_argument(
        "--max-works-per-domain",
        type=int,
        default=2000,
        help="Max works per domain per sort pass (default: 2000, 0 = no limit).",
    )
    ap.add_argument("--max-works", type=int, default=0, help="Stop after N works total (0 = no limit).")
    ap.add_argument("--sleep", type=float, default=0.15, help="Sleep seconds between API calls (default 0.15).")
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

    if not BASE_JSON.exists():
        raise SystemExit(f"Base data not found: {BASE_JSON}")

    cache = load_concept_cache()
    ai_concepts = parse_ai_concepts(args.ai_concepts, cache)

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

    if args.from_date:
        from_date = date.fromisoformat(args.from_date)
    else:
        today = datetime.now(tz=UTC).date()
        from_date = date(today.year - (args.years - 1), 1, 1)

    con = connect(args.db)
    init_db(con)

    started_at = iso_now()
    added = 0
    updated = 0
    errors = 0
    total_seen = 0

    params_json = json.dumps(
        {
            "from_date": from_date.isoformat(),
            "ai_concepts": ai_concepts,
            "domains": [d.id for d in domains],
        },
        ensure_ascii=False,
    )
    run_id = con.execute(
        "INSERT INTO sync_runs(started_at, source, params_json) VALUES(?, ?, ?)",
        (started_at, "openalex", params_json),
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

    ai_filter = "|".join(ai_concepts)
    sort_clauses: list[str] = []
    if args.sort_strategy in {"both", "cited"}:
        sort_clauses.append("cited_by_count:desc")
    if args.sort_strategy in {"both", "recent"}:
        sort_clauses.append("publication_date:desc")

    try:
        for i, d in enumerate(domains, start=1):
            domain_count = 0
            for sort_clause in sort_clauses:
                cursor = "*"
                pass_count = 0
                while cursor:
                    if args.max_works and total_seen >= args.max_works:
                        cursor = None
                        break
                    if args.max_works_per_domain and pass_count >= args.max_works_per_domain:
                        cursor = None
                        break

                    filter_str = ",".join(
                        [
                            f"concept.id:{d.concept_id}",
                            f"concept.id:{ai_filter}",
                            f"from_publication_date:{from_date.isoformat()}",
                        ]
                    )
                    url = openalex_url(
                        "/works",
                        {
                            "filter": filter_str,
                            "cursor": cursor,
                            "per-page": "200",
                            "sort": sort_clause,
                            "select": select_fields,
                        },
                    )

                    time.sleep(max(0.0, args.sleep))
                    data = http_get_json(url)
                    results = data.get("results") or []
                    if not results:
                        break

                    now = iso_now()
                    stop_due_to_limit = False
                    for w in results:
                        if args.max_works and total_seen >= args.max_works:
                            stop_due_to_limit = True
                            break
                        if args.max_works_per_domain and pass_count >= args.max_works_per_domain:
                            stop_due_to_limit = True
                            break
                        total_seen += 1
                        pass_count += 1
                        domain_count += 1

                        openalex_id = w.get("id")
                        title = w.get("display_name") or ""
                        if not (
                            isinstance(openalex_id, str)
                            and openalex_id
                            and isinstance(title, str)
                            and title.strip()
                        ):
                            continue

                        ids = w.get("ids") or {}
                        doi_url = w.get("doi") or ids.get("doi")
                        pl = w.get("primary_location") or {}
                        landing = pl.get("landing_page_url") or pl.get("pdf_url") or ids.get("openalex")
                        source = ((pl.get("source") or {}).get("display_name")) if isinstance(pl, dict) else None
                        abstract = inverted_index_to_text(w.get("abstract_inverted_index"))
                        arxiv_id = extract_arxiv_id(doi_url, landing)

                        row = {
                            "openalex_id": openalex_id,
                            "doi": doi_url if isinstance(doi_url, str) else None,
                            "arxiv_id": arxiv_id,
                            "title": title.strip(),
                            "abstract": abstract,
                            "publication_date": w.get("publication_date")
                            if isinstance(w.get("publication_date"), str)
                            else None,
                            "publication_year": w.get("publication_year")
                            if isinstance(w.get("publication_year"), int)
                            else None,
                            "cited_by_count": w.get("cited_by_count")
                            if isinstance(w.get("cited_by_count"), int)
                            else None,
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

                        # Store OpenAlex concept tags for later subfield/method analysis.
                        try:
                            c_rows, link_rows = parse_work_concepts(w, now=now)
                            for cr in c_rows:
                                upsert_concept(con, cr)
                            replace_paper_concepts(con, openalex_id=openalex_id, concepts=link_rows)
                        except Exception:
                            # Don't fail ingestion if concept parsing fails.
                            pass
                        add_paper_domain(
                            con,
                            openalex_id=openalex_id,
                            domain_id=d.id,
                            domain_concept_id=d.concept_id,
                        )

                    cursor = None if stop_due_to_limit else (data.get("meta") or {}).get("next_cursor")
                    con.commit()

                    if stop_due_to_limit:
                        cursor = None
                        break

            print(f"[ok] {i}/{len(domains)} {d.id} ({d.name}) +{domain_count} works")

    except Exception as e:  # noqa: BLE001
        errors += 1
        print(f"[error] ingest failed: {e}")
        raise
    finally:
        finished_at = iso_now()
        con.execute(
            "UPDATE sync_runs SET finished_at=?, added=?, updated=?, errors=? WHERE id=?",
            (finished_at, added, updated, errors, run_id),
        )
        con.commit()
        con.close()
        save_concept_cache(cache)

    if not args.no_export:
        try:
            export_catalog(
                db_path=args.db,
                base_json_path=BASE_JSON,
                out_json=args.export_json,
                out_md=args.export_md,
                max_total=int(args.export_max_total),
                max_per_domain=int(args.export_max_per_domain),
                abstract_chars_json=900,
                abstract_chars_md=320,
            )
            print(f"[ok] exported catalog: {args.export_json} (+ {args.export_md})")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] export catalog failed: {e}")

    print(f"[done] db={args.db} added={added} updated={updated} total_seen={total_seen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
