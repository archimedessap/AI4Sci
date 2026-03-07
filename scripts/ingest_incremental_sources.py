#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from export_papers_catalog import export_catalog
from ingest_ai4sci_openalex import BASE_JSON, DEFAULT_DB, ROOT, extract_arxiv_id, parse_leaf_domains
from paper_db import add_paper_domain, connect, init_db, upsert_paper

CACHE_DIR = ROOT / ".cache"
STATE_PATH = CACHE_DIR / "incremental_sources_state.json"
DEFAULT_CONFIG = ROOT / "scripts" / "ai4sci_incremental_sources.json"
DEFAULT_AI_KEYWORDS_FILE = ROOT / "scripts" / "ai4sci_incremental_ai_keywords.txt"
DEFAULT_DOMAIN_ALIASES = ROOT / "scripts" / "ai4sci_incremental_domain_aliases.json"

OUT_JSON = ROOT / "web" / "data" / "incremental_sources.json"
OUT_MD = ROOT / "web" / "data" / "incremental_sources.md"

DEFAULT_OUT_CATALOG_JSON = ROOT / "web" / "data" / "papers_catalog.json"
DEFAULT_OUT_CATALOG_MD = ROOT / "web" / "data" / "papers_catalog.md"

USER_AGENT = "AI4SciProgressAtlas/0.3 (incremental sources; +https://openalex.org/)"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
ARXIV_ID_RE = re.compile(r"(?P<id>\d{4}\.\d{4,5})(v\d+)?", re.I)


def iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def save_json(path: Path, data: dict[str, Any]) -> None:
    save_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_list_file(path: Path) -> list[str]:
    items: list[str] = []
    for line in path.read_text("utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append(s)
    return items


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    raw = html.unescape(text)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</p>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return norm_space(raw)


def truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    t = norm_space(text)
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def parse_datetime_any(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        dt = None
    if dt is None:
        try:
            dt = parsedate_to_datetime(raw.strip())
        except Exception:
            dt = None
    if dt is None:
        try:
            d = date.fromisoformat(raw.strip()[:10])
            dt = datetime(d.year, d.month, d.day, tzinfo=UTC)
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def normalize_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    s = html.unescape(raw).strip()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    m = DOI_RE.search(s)
    if not m:
        return None
    doi = m.group(0).rstrip(").,;]")
    return doi.lower()


def doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    return f"https://doi.org/{doi}"


def normalize_url(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith("/"):
        s = s[:-1]
    return s


def normalize_arxiv_id(raw: str | None) -> str | None:
    if not raw:
        return None
    m = ARXIV_ID_RE.search(raw)
    if not m:
        return None
    return m.group("id")


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    t = text.casefold()
    hits: list[str] = []
    for kw in keywords:
        k = kw.casefold()
        if k and k in t:
            hits.append(kw)
    return hits


def match_text_key(text: str) -> str:
    t = html.unescape(text).casefold()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return f" {t} " if t else " "


@dataclass(frozen=True)
class SourceConfig:
    id: str
    type: str
    name: str
    source_name: str
    assume_scientific_context: bool
    require_domain_match: bool
    domain_hints: list[str]
    max_items: int
    url: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class FeedItem:
    source_id: str
    source_type: str
    source_name: str
    title: str
    summary: str
    link: str | None
    guid: str | None
    published_at: str | None
    updated_at: str | None
    doi: str | None
    arxiv_id: str | None
    authors: list[str]
    categories: list[str]


def load_source_configs(path: Path) -> list[SourceConfig]:
    raw = read_json(path, {})
    out: list[SourceConfig] = []
    for source_type in ("rss", "arxiv"):
        items = raw.get(source_type)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id") or "").strip()
            name = str(item.get("name") or sid).strip()
            source_name = str(item.get("sourceName") or name).strip()
            if not sid or not name or not source_name:
                continue
            out.append(
                SourceConfig(
                    id=sid,
                    type=source_type,
                    name=name,
                    source_name=source_name,
                    assume_scientific_context=bool(item.get("assumeScientificContext", False)),
                    require_domain_match=bool(item.get("requireDomainMatch", False)),
                    domain_hints=[str(v).strip() for v in item.get("domainHints") or [] if str(v).strip()],
                    max_items=max(1, int(item.get("maxItems") or 25)),
                    url=str(item.get("url")).strip() if item.get("url") else None,
                    query=str(item.get("query")).strip() if item.get("query") else None,
                )
            )
    return out


def http_get_text(url: str, *, retries: int = 4, timeout: int = 30) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(min(2.0**attempt, 8.0))
    raise RuntimeError(f"GET failed after {retries} retries: {url}") from last_err


def first_child_text(node: ET.Element, names: list[str]) -> str | None:
    name_set = set(names)
    for child in node:
        if local_name(child.tag) in name_set:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return None


def child_texts(node: ET.Element, names: list[str]) -> list[str]:
    name_set = set(names)
    out: list[str] = []
    for child in node:
        if local_name(child.tag) in name_set:
            text = "".join(child.itertext()).strip()
            if text:
                out.append(text)
    return out


def parse_rss_feed(xml_text: str, *, source: SourceConfig) -> list[FeedItem]:
    root = ET.fromstring(xml_text)
    items = [el for el in root.iter() if local_name(el.tag) == "item"]
    out: list[FeedItem] = []
    for item in items:
        title = strip_html(first_child_text(item, ["title"]))
        if not title:
            continue
        link = first_child_text(item, ["link"])
        guid = first_child_text(item, ["guid", "identifier"])
        description = first_child_text(item, ["description", "encoded", "summary"])
        summary = strip_html(description)
        published = first_child_text(item, ["pubDate", "date", "published", "publicationDate", "coverDate"])
        updated = first_child_text(item, ["updated", "modified", "date"])
        categories = child_texts(item, ["category", "subject"])
        authors = child_texts(item, ["creator", "author"])
        doi = normalize_doi(first_child_text(item, ["doi", "identifier"]))
        if doi is None:
            doi = normalize_doi(summary) or normalize_doi(link)
        arxiv_id = normalize_arxiv_id(extract_arxiv_id(doi_url(doi), link))
        out.append(
            FeedItem(
                source_id=source.id,
                source_type=source.type,
                source_name=source.source_name,
                title=title,
                summary=summary,
                link=normalize_url(link),
                guid=guid,
                published_at=(parse_datetime_any(published) or parse_datetime_any(updated)).isoformat()
                if (parse_datetime_any(published) or parse_datetime_any(updated))
                else None,
                updated_at=parse_datetime_any(updated).isoformat() if parse_datetime_any(updated) else None,
                doi=doi,
                arxiv_id=arxiv_id,
                authors=authors,
                categories=categories,
            )
        )
    return out


def parse_arxiv_feed(xml_text: str, *, source: SourceConfig) -> list[FeedItem]:
    root = ET.fromstring(xml_text)
    out: list[FeedItem] = []
    for entry in root.iter():
        if local_name(entry.tag) != "entry":
            continue
        title = strip_html(first_child_text(entry, ["title"]))
        if not title:
            continue
        summary = strip_html(first_child_text(entry, ["summary"]))
        published = first_child_text(entry, ["published"])
        updated = first_child_text(entry, ["updated"])
        guid = first_child_text(entry, ["id"])
        link = None
        for child in entry:
            if local_name(child.tag) != "link":
                continue
            rel = child.attrib.get("rel")
            href = child.attrib.get("href")
            if rel in {None, "alternate"} and href:
                link = href.strip()
                break
        doi = normalize_doi(first_child_text(entry, ["doi"]))
        arxiv_id = normalize_arxiv_id(guid) or normalize_arxiv_id(link)
        authors = child_texts(entry, ["name"])
        categories: list[str] = []
        for child in entry:
            if local_name(child.tag) == "category":
                term = child.attrib.get("term")
                if term:
                    categories.append(term.strip())
        out.append(
            FeedItem(
                source_id=source.id,
                source_type=source.type,
                source_name=source.source_name,
                title=title,
                summary=summary,
                link=normalize_url(link),
                guid=guid,
                published_at=parse_datetime_any(published).isoformat() if parse_datetime_any(published) else None,
                updated_at=parse_datetime_any(updated).isoformat() if parse_datetime_any(updated) else None,
                doi=doi,
                arxiv_id=arxiv_id,
                authors=authors,
                categories=categories,
            )
        )
    return out


def arxiv_api_url(query: str, *, max_results: int) -> str:
    params = {
        "search_query": query,
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    return f"https://export.arxiv.org/api/query?{urllib.parse.urlencode(params)}"


def load_domain_aliases(path: Path) -> dict[str, list[str]]:
    raw = read_json(path, {})
    out: dict[str, list[str]] = {}
    for domain_id, aliases in raw.items():
        if not isinstance(aliases, list):
            continue
        vals = [str(v).strip() for v in aliases if str(v).strip()]
        if vals:
            out[str(domain_id)] = vals
    return out


def build_domain_matchers() -> tuple[dict[str, str], dict[str, list[str]]]:
    base = read_json(BASE_JSON, {})
    name_by_domain: dict[str, str] = {}
    domains = parse_leaf_domains(base, include_methods=False)
    for domain in domains:
        name_by_domain[domain.id] = domain.name
    alias_map = load_domain_aliases(DEFAULT_DOMAIN_ALIASES)
    for domain_id, name in name_by_domain.items():
        alias_map.setdefault(domain_id, [])
        if name not in alias_map[domain_id]:
            alias_map[domain_id].append(name)
    return name_by_domain, alias_map


def match_domains(text: str, *, alias_map: dict[str, list[str]], source: SourceConfig) -> list[str]:
    key = match_text_key(text)
    matched: set[str] = set()
    for domain_id, aliases in alias_map.items():
        for alias in aliases:
            alias_key = match_text_key(alias).strip()
            if alias_key and f" {alias_key} " in key:
                matched.add(domain_id)
                break
    if not matched and len(source.domain_hints) == 1 and source.assume_scientific_context:
        matched.add(source.domain_hints[0])
    return sorted(matched)


def item_unique_key(item: FeedItem) -> str:
    doi = normalize_doi(item.doi)
    if doi:
        return f"doi:{doi}"
    arxiv_id = normalize_arxiv_id(item.arxiv_id)
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    if item.guid:
        return f"guid:{hashlib.sha1(item.guid.encode('utf-8', errors='ignore')).hexdigest()}"
    if item.link:
        return f"url:{hashlib.sha1(item.link.encode('utf-8', errors='ignore')).hexdigest()}"
    basis = f"{item.source_id}|{item.title}|{item.published_at or ''}"
    return f"text:{hashlib.sha1(basis.encode('utf-8', errors='ignore')).hexdigest()}"


def load_existing_identity_maps(con: sqlite3.Connection) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    doi_map: dict[str, str] = {}
    arxiv_map: dict[str, str] = {}
    url_map: dict[str, str] = {}
    rows = con.execute("SELECT openalex_id, doi, arxiv_id, primary_url FROM papers;").fetchall()
    for row in rows:
        paper_id = str(row["openalex_id"])
        doi = normalize_doi(row["doi"])
        arxiv_id = normalize_arxiv_id(row["arxiv_id"])
        url = normalize_url(row["primary_url"])
        if doi and doi not in doi_map:
            doi_map[doi] = paper_id
        if arxiv_id and arxiv_id not in arxiv_map:
            arxiv_map[arxiv_id] = paper_id
        if url and url not in url_map:
            url_map[url] = paper_id
    return doi_map, arxiv_map, url_map


def select_paper_id(
    *,
    item: FeedItem,
    doi_map: dict[str, str],
    arxiv_map: dict[str, str],
    url_map: dict[str, str],
) -> tuple[str, bool]:
    doi = normalize_doi(item.doi)
    arxiv_id = normalize_arxiv_id(item.arxiv_id)
    url = normalize_url(item.link)
    existing = None
    if doi and doi in doi_map:
        existing = doi_map[doi]
    elif arxiv_id and arxiv_id in arxiv_map:
        existing = arxiv_map[arxiv_id]
    elif url and url in url_map:
        existing = url_map[url]
    if existing:
        return existing, True
    unique = item_unique_key(item).replace(":", "_")
    return f"incremental:{item.source_type}:{item.source_id}:{unique}", False


def update_identity_maps(
    *,
    paper_id: str,
    item: FeedItem,
    doi_map: dict[str, str],
    arxiv_map: dict[str, str],
    url_map: dict[str, str],
) -> None:
    doi = normalize_doi(item.doi)
    arxiv_id = normalize_arxiv_id(item.arxiv_id)
    url = normalize_url(item.link)
    if doi:
        doi_map[doi] = paper_id
    if arxiv_id:
        arxiv_map[arxiv_id] = paper_id
    if url:
        url_map[url] = paper_id


def build_paper_row(item: FeedItem, *, paper_id: str, now: str) -> dict[str, Any]:
    published_dt = parse_datetime_any(item.published_at)
    doi = normalize_doi(item.doi)
    primary_url = item.link or doi_url(doi) or item.guid or paper_id
    return {
        "openalex_id": paper_id,
        "doi": doi_url(doi) if doi else None,
        "arxiv_id": normalize_arxiv_id(item.arxiv_id),
        "title": item.title,
        "abstract": item.summary or None,
        "publication_date": published_dt.date().isoformat() if published_dt else None,
        "publication_year": int(published_dt.year) if published_dt else None,
        "cited_by_count": 0,
        "primary_url": primary_url,
        "source": item.source_name,
        "created_at": now,
        "updated_at": now,
    }


def should_include_item(
    *,
    item: FeedItem,
    source: SourceConfig,
    ai_keywords: list[str],
    alias_map: dict[str, list[str]],
) -> tuple[bool, list[str], list[str], str | None]:
    text = f"{item.title}\n{item.summary}\n{' '.join(item.categories)}"
    matched_ai = match_keywords(text, ai_keywords)
    if not matched_ai:
        return False, [], [], "no_ai_keyword"

    matched_domains = match_domains(text, alias_map=alias_map, source=source)
    if source.require_domain_match and not matched_domains:
        return False, matched_ai, matched_domains, "no_domain_match"

    if not source.assume_scientific_context and not matched_domains:
        return False, matched_ai, matched_domains, "insufficient_science_context"

    return True, matched_ai, matched_domains, None


def render_md(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Incremental Sources\n")
    lines.append(f"- UpdatedAt: {data.get('updatedAt')}\n")
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    lines.append(
        f"- Total new={stats.get('newItems')} inserted={stats.get('inserted')} updated={stats.get('updated')} included={stats.get('includedItems')}\n"
    )
    lines.append("\n## Sources\n")
    for source in data.get("sources") or []:
        if not isinstance(source, dict):
            continue
        lines.append(
            f"- {source.get('name')} [{source.get('type')}]: status={source.get('status')} fetched={source.get('fetchedItems')} included={source.get('includedItems')} new={source.get('newItems')}\n"
        )
    lines.append("\n## Recent Items\n")
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('publishedAt') or 'unknown'} | {item.get('sourceName')} | {item.get('title')}\n"
        )
    return "".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch incremental arXiv + RSS sources, upsert recent AI4Sci papers, and write freshness artifacts."
    )
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path.")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Incremental sources config JSON.")
    ap.add_argument("--state", type=Path, default=STATE_PATH, help="Persistent state JSON.")
    ap.add_argument(
        "--ai-keywords-file",
        type=Path,
        action="append",
        default=None,
        help="AI keywords file (one phrase per line). Can be passed multiple times.",
    )
    ap.add_argument("--domain-aliases", type=Path, default=DEFAULT_DOMAIN_ALIASES, help="Domain alias JSON.")
    ap.add_argument("--lookback-hours", type=int, default=336, help="Ignore items older than this window unless unseen.")
    ap.add_argument("--max-items-per-source", type=int, default=30, help="Cap fetched items per source.")
    ap.add_argument("--max-out-items", type=int, default=200, help="Max recent items stored in output JSON.")
    ap.add_argument("--sleep", type=float, default=0.2, help="Sleep seconds between network requests.")
    ap.add_argument("--force", action="store_true", help="Treat all fetched items as new (ignore state).")
    ap.add_argument("--no-export", action="store_true", help="Skip exporting papers_catalog after ingestion.")
    ap.add_argument("--out-json", type=Path, default=OUT_JSON, help="Output JSON path.")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown path.")
    ap.add_argument("--export-json", type=Path, default=DEFAULT_OUT_CATALOG_JSON, help="papers_catalog.json path.")
    ap.add_argument("--export-md", type=Path, default=DEFAULT_OUT_CATALOG_MD, help="papers_catalog.md path.")
    ap.add_argument("--export-max-total", type=int, default=8000, help="Max papers in exported JSON.")
    ap.add_argument("--export-max-per-domain", type=int, default=200, help="Max papers per domain in exported Markdown.")
    args = ap.parse_args()

    configs = load_source_configs(args.config)
    if not configs:
        raise SystemExit(f"No incremental sources loaded from {args.config}")

    ai_keyword_files = args.ai_keywords_file or [DEFAULT_AI_KEYWORDS_FILE]
    ai_keywords = []
    for path in ai_keyword_files:
        ai_keywords.extend(load_list_file(path))
    ai_keywords = list(dict.fromkeys([kw for kw in ai_keywords if kw]))
    if not ai_keywords:
        raise SystemExit("No AI keywords configured for incremental ingestion.")

    name_by_domain, alias_map = build_domain_matchers()
    alias_map.update(load_domain_aliases(args.domain_aliases))
    for domain_id, name in name_by_domain.items():
        alias_map.setdefault(domain_id, [])
        if name not in alias_map[domain_id]:
            alias_map[domain_id].append(name)

    state = read_json(args.state, {"version": "1", "sources": {}})
    state_sources = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    state["sources"] = state_sources

    con = connect(args.db)
    init_db(con)
    doi_map, arxiv_map, url_map = load_existing_identity_maps(con)

    now = iso_now()
    sync_params = {
        "config": str(args.config),
        "lookbackHours": int(args.lookback_hours),
        "maxItemsPerSource": int(args.max_items_per_source),
        "sources": [cfg.id for cfg in configs],
    }
    sync_run_id = con.execute(
        "INSERT INTO sync_runs(started_at, source, params_json) VALUES(?, ?, ?)",
        (now, "incremental_sources", json.dumps(sync_params, ensure_ascii=False)),
    ).lastrowid
    con.commit()

    lookback_cutoff = datetime.now(tz=UTC) - timedelta(hours=max(1, int(args.lookback_hours)))
    total_fetched = 0
    total_included = 0
    total_new = 0
    total_inserted = 0
    total_updated = 0
    total_errors = 0
    recent_items: list[dict[str, Any]] = []
    source_reports: list[dict[str, Any]] = []

    for cfg in configs:
        source_state = state_sources.get(cfg.id)
        if not isinstance(source_state, dict):
            source_state = {}
            state_sources[cfg.id] = source_state
        seen_keys = source_state.get("seenKeys")
        seen_list = [str(v) for v in seen_keys if str(v)] if isinstance(seen_keys, list) else []
        seen_set = set(seen_list)

        fetched_items = 0
        included_items = 0
        new_items = 0
        inserted = 0
        updated = 0
        skipped = {"too_old": 0, "no_ai_keyword": 0, "no_domain_match": 0, "insufficient_science_context": 0}
        status = "ok"
        error = None
        last_published_at = None

        try:
            if cfg.type == "rss":
                if not cfg.url:
                    raise RuntimeError(f"RSS source {cfg.id} missing URL")
                xml_text = http_get_text(cfg.url)
                items = parse_rss_feed(xml_text, source=cfg)
            elif cfg.type == "arxiv":
                if not cfg.query:
                    raise RuntimeError(f"arXiv source {cfg.id} missing query")
                xml_text = http_get_text(
                    arxiv_api_url(
                        cfg.query,
                        max_results=min(max(1, int(args.max_items_per_source)), max(1, int(cfg.max_items))),
                    )
                )
                items = parse_arxiv_feed(xml_text, source=cfg)
            else:
                raise RuntimeError(f"Unsupported source type: {cfg.type}")
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = str(exc)
            total_errors += 1
            source_state["lastError"] = error
            source_state["lastCheckedAt"] = iso_now()
            source_reports.append(
                {
                    "id": cfg.id,
                    "type": cfg.type,
                    "name": cfg.name,
                    "sourceName": cfg.source_name,
                    "status": status,
                    "error": error,
                    "checkedAt": source_state["lastCheckedAt"],
                    "fetchedItems": 0,
                    "includedItems": 0,
                    "newItems": 0,
                    "inserted": 0,
                    "updated": 0,
                    "lastPublishedAt": None,
                    "url": cfg.url,
                    "query": cfg.query,
                }
            )
            time.sleep(max(0.0, float(args.sleep)))
            continue

        fetched_items = len(items)
        total_fetched += fetched_items

        for item in items:
            unique_key = item_unique_key(item)
            published_dt = parse_datetime_any(item.published_at)
            is_new = args.force or unique_key not in seen_set
            if published_dt is not None and published_dt < lookback_cutoff and not is_new:
                skipped["too_old"] += 1
                continue

            include, matched_ai, matched_domains, skip_reason = should_include_item(
                item=item,
                source=cfg,
                ai_keywords=ai_keywords,
                alias_map=alias_map,
            )
            if not include:
                if skip_reason:
                    skipped[skip_reason] = skipped.get(skip_reason, 0) + 1
                continue

            paper_id, reused = select_paper_id(item=item, doi_map=doi_map, arxiv_map=arxiv_map, url_map=url_map)
            paper = build_paper_row(item, paper_id=paper_id, now=now)
            action = upsert_paper(con, paper)
            update_identity_maps(paper_id=paper_id, item=item, doi_map=doi_map, arxiv_map=arxiv_map, url_map=url_map)
            if action == "inserted":
                inserted += 1
                total_inserted += 1
            else:
                updated += 1
                total_updated += 1

            for domain_id in matched_domains:
                add_paper_domain(con, openalex_id=paper_id, domain_id=domain_id, domain_concept_id=None)

            included_items += 1
            total_included += 1
            if is_new:
                new_items += 1
                total_new += 1

            if published_dt and (last_published_at is None or published_dt > parse_datetime_any(last_published_at)):
                last_published_at = published_dt.isoformat()

            source_seen_key = unique_key
            if source_seen_key not in seen_set:
                seen_set.add(source_seen_key)
                seen_list.append(source_seen_key)

            recent_items.append(
                {
                    "id": paper_id,
                    "sourceId": cfg.id,
                    "sourceType": cfg.type,
                    "sourceName": cfg.source_name,
                    "title": item.title,
                    "summary": truncate(item.summary, 320),
                    "publishedAt": published_dt.isoformat() if published_dt else item.published_at,
                    "updatedAt": item.updated_at,
                    "url": item.link,
                    "doi": normalize_doi(item.doi),
                    "arxivId": normalize_arxiv_id(item.arxiv_id),
                    "matchedAiKeywords": matched_ai[:8],
                    "domains": matched_domains,
                    "domainNames": [name_by_domain.get(did, did) for did in matched_domains],
                    "isNew": bool(is_new),
                    "dbAction": action,
                    "reusedExistingPaper": reused,
                }
            )

        source_state["seenKeys"] = seen_list[-1000:]
        source_state["lastCheckedAt"] = iso_now()
        source_state["lastSuccessAt"] = source_state["lastCheckedAt"]
        source_state["lastError"] = None
        source_state["lastPublishedAt"] = last_published_at
        source_reports.append(
            {
                "id": cfg.id,
                "type": cfg.type,
                "name": cfg.name,
                "sourceName": cfg.source_name,
                "status": status,
                "error": error,
                "checkedAt": source_state["lastCheckedAt"],
                "fetchedItems": fetched_items,
                "includedItems": included_items,
                "newItems": new_items,
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "lastPublishedAt": last_published_at,
                "url": cfg.url,
                "query": cfg.query,
            }
        )
        time.sleep(max(0.0, float(args.sleep)))

    con.commit()

    recent_items.sort(
        key=lambda item: (
            parse_datetime_any(item.get("publishedAt") or item.get("updatedAt")) or datetime.fromtimestamp(0, tz=UTC),
            item.get("sourceName") or "",
            item.get("title") or "",
        ),
        reverse=True,
    )
    if args.max_out_items > 0:
        recent_items = recent_items[: int(args.max_out_items)]

    now_dt = datetime.now(tz=UTC)
    direct_counts = {"last6h": 0, "last24h": 0, "last72h": 0}
    for item in recent_items:
        published_dt = parse_datetime_any(item.get("publishedAt") or item.get("updatedAt"))
        if published_dt is None:
            continue
        age_h = (now_dt - published_dt).total_seconds() / 3600.0
        if age_h <= 6:
            direct_counts["last6h"] += 1
        if age_h <= 24:
            direct_counts["last24h"] += 1
        if age_h <= 72:
            direct_counts["last72h"] += 1

    out = {
        "version": "1",
        "updatedAt": iso_now(),
        "window": {
            "lookbackHours": int(args.lookback_hours),
            "maxItemsPerSource": int(args.max_items_per_source),
        },
        "stats": {
            "fetchedItems": total_fetched,
            "includedItems": total_included,
            "newItems": total_new,
            "inserted": total_inserted,
            "updated": total_updated,
            "errors": total_errors,
            "directCounts": direct_counts,
        },
        "sources": source_reports,
        "items": recent_items,
    }

    save_json(args.state, state)
    save_json(args.out_json, out)
    save_text(args.out_md, render_md(out))

    if not args.no_export:
        export_catalog(
            db_path=args.db,
            base_json_path=BASE_JSON,
            out_json=args.export_json,
            out_md=args.export_md,
            max_total=int(args.export_max_total),
            max_per_domain_json=0,
            max_per_domain=int(args.export_max_per_domain),
            abstract_chars_json=1800,
            abstract_chars_md=400,
        )

    finished_at = iso_now()
    con.execute(
        """
        UPDATE sync_runs
        SET finished_at = ?, added = ?, updated = ?, errors = ?
        WHERE id = ?
        """,
        (finished_at, total_inserted, total_updated, total_errors, int(sync_run_id)),
    )
    con.commit()
    con.close()

    print(f"[done] wrote {args.out_json} and {args.out_md}")
    if not args.no_export:
        print(f"[done] exported {args.export_json} and {args.export_md}")
    print(
        f"[done] incremental sources fetched={total_fetched} included={total_included} new={total_new} inserted={total_inserted} updated={total_updated} errors={total_errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
