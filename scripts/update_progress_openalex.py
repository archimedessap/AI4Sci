#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "web" / "data" / "base.json"
CACHE_DIR = ROOT / ".cache"
CONCEPT_CACHE_PATH = CACHE_DIR / "openalex_concepts.json"

USER_AGENT = "AI4SciProgressAtlas/0.1 (OpenAlex; +https://openalex.org/)"
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except Exception:
        return default


OPENALEX_EMAIL = (os.environ.get("OPENALEX_EMAIL") or "").strip()
DEFAULT_REQUEST_SLEEP = max(0.0, env_float("OPENALEX_REQUEST_SLEEP", 0.3))
OPENALEX_MIN_DELAY = max(0.0, env_float("OPENALEX_MIN_DELAY", 0.0))


def retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    raw = exc.headers.get("Retry-After") if exc.headers else None
    if not raw:
        return None
    try:
        return max(1.0, float(raw))
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = (dt.astimezone(UTC) - datetime.now(tz=UTC)).total_seconds()
    return max(1.0, delta)


def retry_delay_seconds(attempt: int, exc: Exception) -> float:
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = retry_after_seconds(exc)
        if retry_after is not None:
            return min(retry_after + 1.0, 600.0)
        if exc.code == 429:
            return min(15.0 * (2**attempt), 300.0)
        if exc.code in TRANSIENT_HTTP_CODES:
            return min(5.0 * (2**attempt), 120.0)
    return min(2.0**attempt, 8.0)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _clamp_score(x: float) -> float:
    return max(0.0, min(100.0, x))


def _log10p(x: float) -> float:
    return math.log10(max(1e-9, x + 1.0))


def _log2(x: float) -> float:
    return math.log(max(1e-9, x), 2.0)


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _iso(d: date) -> str:
    return d.isoformat()


def http_get_json(url: str, *, retries: int = 5, timeout: int = 30) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            if OPENALEX_MIN_DELAY > 0:
                time.sleep(OPENALEX_MIN_DELAY)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in TRANSIENT_HTTP_CODES:
                raise
            time.sleep(retry_delay_seconds(attempt, e))
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(retry_delay_seconds(attempt, e))
        except Exception as e:  # noqa: BLE001
            last_err = e
            sleep_s = retry_delay_seconds(attempt, e)
            time.sleep(sleep_s)
    raise RuntimeError(f"GET failed after {retries} retries: {url}") from last_err


def openalex_url(path: str, params: dict[str, str]) -> str:
    q = dict(params)
    if OPENALEX_EMAIL:
        q.setdefault("mailto", OPENALEX_EMAIL)
    qs = urllib.parse.urlencode(q)
    return f"https://api.openalex.org{path}?{qs}"


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
    # https://openalex.org/C123 -> C123
    return openalex_id.rstrip("/").split("/")[-1]


CONCEPT_ID_RE = re.compile(r"^C\d+$", re.I)


def normalize_concept_id(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    if v.startswith("https://openalex.org/"):
        v = concept_id_from_url(v)
    if CONCEPT_ID_RE.fullmatch(v):
        return v.upper()
    return None


def fetch_concept_by_id(concept_id: str, cache: dict[str, dict[str, str]]) -> tuple[str, str]:
    cid = normalize_concept_id(concept_id)
    if not cid:
        raise RuntimeError(f"Invalid OpenAlex concept id: {concept_id}")

    cache_key = f"id:{cid}"
    cached = cache.get(cache_key)
    if cached and cached.get("id") == cid and cached.get("name"):
        return cached["id"], cached["name"]

    data = http_get_json(f"https://api.openalex.org/concepts/{urllib.parse.quote(cid)}")
    name = data.get("display_name") or cid
    cache[cache_key] = {"id": cid, "name": str(name)}
    return cid, str(name)


def find_concept(term: str, cache: dict[str, dict[str, str]]) -> tuple[str, str]:
    cached = cache.get(term)
    if cached and "id" in cached and "name" in cached:
        return cached["id"], cached["name"]

    data = http_get_json(
        openalex_url(
            "/concepts",
            {
                "search": term,
                "per-page": "5",
            },
        )
    )
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


def resolve_concept(concept: dict[str, Any], cache: dict[str, dict[str, str]]) -> tuple[str, str]:
    raw_id = concept.get("id")
    cid = normalize_concept_id(raw_id) if isinstance(raw_id, str) else None
    if cid:
        return fetch_concept_by_id(cid, cache)

    raw_name = concept.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        return find_concept(raw_name.strip(), cache)

    raise RuntimeError("Concept must include either openalex.concept.id (C123...) or openalex.concept.name")


def works_count(*, filter_str: str, search: str | None = None) -> int:
    params = {"filter": filter_str, "per-page": "1"}
    if search:
        params["search"] = search
    data = http_get_json(openalex_url("/works", params))
    return int((data.get("meta") or {}).get("count") or 0)


def works_top(*, filter_str: str, per_page: int = 10) -> list[dict[str, Any]]:
    params = {
        "filter": filter_str,
        "per-page": str(per_page),
        "sort": "cited_by_count:desc",
        "select": ",".join(
            [
                "id",
                "display_name",
                "publication_year",
                "cited_by_count",
                "primary_location",
                "ids",
            ]
        ),
    }
    data = http_get_json(openalex_url("/works", params))
    return list(data.get("results") or [])


@dataclass
class DomainSignals:
    total_recent: int
    ai_recent: int
    ai_last_year: int
    ai_prev_year: int
    term_counts: dict[str, int]
    top_works: list[dict[str, Any]]


def compute_growth(ai_last_year: int, ai_prev_year: int) -> float:
    ratio = (ai_last_year + 1.0) / (ai_prev_year + 1.0)
    # Map ratio to [0,1]: 1->0.5, 2->0.75, 4->1.0, 0.5->0.25
    score = 0.5 + 0.25 * _log2(ratio)
    return _clamp01(score)


def compute_dimension_scores(
    *,
    penetration: float,
    volume_norm: float,
    growth_norm: float,
    signal_ratio: float,
    kind: str,
) -> float:
    p = math.sqrt(_clamp01(penetration))
    v = _clamp01(volume_norm)
    g = _clamp01(growth_norm)
    s = _clamp01(signal_ratio)

    if kind == "model":
        return 100.0 * (0.45 * p + 0.35 * v + 0.20 * g)
    if kind == "data":
        return 100.0 * (0.40 * p + 0.40 * s + 0.20 * g)
    if kind == "predict":
        return 100.0 * (0.35 * p + 0.45 * s + 0.20 * g)
    if kind == "experiment":
        return 100.0 * (0.25 * p + 0.55 * s + 0.20 * g)
    if kind == "explain":
        return 100.0 * (0.35 * p + 0.45 * s + 0.20 * g)
    return 0.0


DIM_TERM_QUERIES: dict[str, list[str]] = {
    "data": ["dataset", "benchmark"],
    "predict": ["forecast", "control", "reinforcement learning"],
    "experiment": ["closed loop", "autonomous", "robotic"],
    "explain": ["causal", "interpretability", "symbolic"],
}


def build_filter(*parts: str) -> str:
    return ",".join([p for p in parts if p])


def main() -> int:
    ap = argparse.ArgumentParser(description="Update web/data/base.json progress signals via OpenAlex.")
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="Comma-separated node ids to update (repeatable). If set, updates only these ids.",
    )
    ap.add_argument(
        "--include",
        action="append",
        default=[],
        help="Comma-separated node ids to include (repeatable), even when using --only-missing.",
    )
    ap.add_argument(
        "--only-missing",
        action="store_true",
        help="Update only nodes missing any of the 5 dimension scores.",
    )
    ap.add_argument(
        "--max-domains",
        type=int,
        default=0,
        help="Stop after updating N domains (0 = all).",
    )
    ap.add_argument(
        "--request-sleep",
        type=float,
        default=DEFAULT_REQUEST_SLEEP,
        help="Sleep seconds between OpenAlex requests (default: env OPENALEX_REQUEST_SLEEP or 0.3).",
    )
    args = ap.parse_args()

    if not BASE_PATH.exists():
        raise SystemExit(f"Base file not found: {BASE_PATH}")

    base = json.loads(BASE_PATH.read_text("utf-8"))
    nodes: dict[str, dict[str, Any]] = base.get("nodes") or {}
    root_id = base.get("rootId") or "ai4sci"

    cache = load_concept_cache()

    ai_concept_id, ai_concept_name = find_concept("Machine learning", cache)

    today = _today()
    window_years = 5
    window_start = date(today.year - (window_years - 1), 1, 1)
    last_year_start = today - timedelta(days=365)
    prev_year_start = today - timedelta(days=730)

    leaf_ids: list[str] = []
    for nid, node in nodes.items():
        if nid == root_id:
            continue
        concept = ((node.get("openalex") or {}).get("concept") or {})
        cid = normalize_concept_id(concept.get("id")) if isinstance(concept, dict) else None
        name = concept.get("name") if isinstance(concept, dict) else None
        if cid or (isinstance(name, str) and name.strip()):
            leaf_ids.append(nid)

    def parse_id_list(values: list[str]) -> set[str]:
        out: set[str] = set()
        for raw in values:
            for part in str(raw).split(","):
                s = part.strip()
                if s:
                    out.add(s)
        return out

    only_ids = parse_id_list(list(args.only or []))
    include_ids = parse_id_list(list(args.include or []))

    leaf_set = set(leaf_ids)

    if only_ids:
        leaf_ids = [nid for nid in leaf_ids if nid in only_ids]
    elif args.only_missing:

        def missing_any_dim(nid: str) -> bool:
            node = nodes.get(nid) or {}
            dims = node.get("dimensions") or {}
            if not isinstance(dims, dict):
                return True
            need = {"data", "model", "predict", "experiment", "explain"}
            return not need.issubset(set(dims.keys()))

        leaf_ids = [nid for nid in leaf_ids if missing_any_dim(nid) or nid in include_ids]

    # Ensure explicit include ids are present if they exist and have OpenAlex concepts.
    for nid in sorted(include_ids):
        if nid in leaf_set and nid not in leaf_ids:
            leaf_ids.append(nid)

    leaf_ids = sorted(set(leaf_ids), key=lambda s: (s not in include_ids, s))

    if int(args.max_domains or 0) > 0:
        leaf_ids = leaf_ids[: int(args.max_domains)]

    print(f"[info] domains_to_update={len(leaf_ids)} only={len(only_ids)} only_missing={bool(args.only_missing)}")

    domain_signals: dict[str, DomainSignals] = {}
    request_sleep = max(0.0, float(args.request_sleep))
    query_warnings: list[dict[str, str]] = []
    updated_domains = 0

    for idx, nid in enumerate(leaf_ids, start=1):
        node = nodes[nid]
        concept = node.setdefault("openalex", {}).setdefault("concept", {})

        print(f"[domain] {idx}/{len(leaf_ids)} {nid}")

        try:
            concept_id, concept_display = resolve_concept(concept, cache)
        except Exception as e:  # noqa: BLE001
            concept_name = concept.get("name")
            label = concept_name if isinstance(concept_name, str) and concept_name.strip() else "-"
            print(f"[warn] concept lookup failed for {nid} ({label}): {e}")
            continue

        node["openalex"]["concept"]["id"] = concept_id
        node["openalex"]["concept"]["name"] = concept_display

        base_filter = build_filter(
            f"concept.id:{concept_id}",
            f"from_publication_date:{_iso(window_start)}",
        )
        ai_filter = build_filter(
            f"concept.id:{concept_id}",
            f"concept.id:{ai_concept_id}",
            f"from_publication_date:{_iso(window_start)}",
        )
        ai_last_year_filter = build_filter(
            f"concept.id:{concept_id}",
            f"concept.id:{ai_concept_id}",
            f"from_publication_date:{_iso(last_year_start)}",
        )
        ai_prev_year_filter = build_filter(
            f"concept.id:{concept_id}",
            f"concept.id:{ai_concept_id}",
            f"from_publication_date:{_iso(prev_year_start)}",
            f"to_publication_date:{_iso(last_year_start)}",
        )

        try:
            time.sleep(request_sleep)
            total_recent = works_count(filter_str=base_filter)
            time.sleep(request_sleep)
            ai_recent = works_count(filter_str=ai_filter)
            time.sleep(request_sleep)
            ai_last_year = works_count(filter_str=ai_last_year_filter)
            time.sleep(request_sleep)
            ai_prev_year = works_count(filter_str=ai_prev_year_filter)

            term_counts: dict[str, int] = {}
            for dim, terms in DIM_TERM_QUERIES.items():
                for t in terms:
                    key = f"{dim}:{t}"
                    time.sleep(request_sleep)
                    term_counts[key] = works_count(filter_str=ai_filter, search=t)

            time.sleep(request_sleep)
            top_works = works_top(filter_str=ai_filter, per_page=12)
        except Exception as e:  # noqa: BLE001
            query_warnings.append({"domain": nid, "error": str(e)})
            print(f"[warn] query failed for {nid} ({concept_display}): {e}")
            continue

        domain_signals[nid] = DomainSignals(
            total_recent=total_recent,
            ai_recent=ai_recent,
            ai_last_year=ai_last_year,
            ai_prev_year=ai_prev_year,
            term_counts=term_counts,
            top_works=top_works,
        )
        updated_domains += 1

        if idx % 5 == 0 or idx == len(leaf_ids):
            print(f"[ok] {idx}/{len(leaf_ids)} updated: {nid} ({concept_display})")

    if not domain_signals:
        raise SystemExit("OpenAlex progress update failed: no domains updated successfully.")

    max_log_volume = max((_log10p(s.ai_recent) for s in domain_signals.values()), default=1.0)
    max_log_volume = max(max_log_volume, 1e-6)

    for nid, signals in domain_signals.items():
        node = nodes[nid]
        total_recent = signals.total_recent
        ai_recent = signals.ai_recent
        penetration = (ai_recent / total_recent) if total_recent > 0 else 0.0
        growth_norm = compute_growth(signals.ai_last_year, signals.ai_prev_year)
        volume_norm = _clamp01(_log10p(ai_recent) / max_log_volume)
        confidence = _clamp01(0.15 + 0.85 * volume_norm)

        def dim_signal_ratio(dim_key: str) -> float:
            if ai_recent <= 0:
                return 0.0
            terms = DIM_TERM_QUERIES.get(dim_key, [])
            summed = 0
            for t in terms:
                summed += signals.term_counts.get(f"{dim_key}:{t}", 0)
            return min(ai_recent, summed) / max(1.0, float(ai_recent))

        def evidence_items() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for w in signals.top_works:
                title = w.get("display_name") or ""
                url = w.get("id") or ""
                year = w.get("publication_year")
                cited = w.get("cited_by_count")
                venue: str | None = None
                pl = w.get("primary_location") or {}
                src = (pl.get("source") or {}).get("display_name")
                if isinstance(src, str) and src.strip():
                    venue = src.strip()
                if not (isinstance(title, str) and title.strip() and isinstance(url, str) and url.strip()):
                    continue
                item: dict[str, Any] = {
                    "title": title.strip(),
                    "url": url.strip(),
                    "source": "OpenAlex",
                }
                if isinstance(year, int):
                    item["year"] = int(year)
                if isinstance(cited, int):
                    item["citedBy"] = int(cited)
                if isinstance(venue, str) and venue.strip():
                    item["venue"] = venue.strip()
                out.append(item)
            return out

        node["dimensions"] = node.get("dimensions") or {}
        for dim_key in ["data", "model", "predict", "experiment", "explain"]:
            sratio = 1.0 if dim_key == "model" else dim_signal_ratio(dim_key)
            score = compute_dimension_scores(
                penetration=penetration,
                volume_norm=volume_norm,
                growth_norm=growth_norm,
                signal_ratio=sratio,
                kind=dim_key,
            )
            score = _clamp_score(score)
            metrics: dict[str, Any] = {
                "score": round(score, 2),
                "confidence": round(confidence, 3),
                "signals": {
                    "total_recent": total_recent,
                    "ai_recent": ai_recent,
                    "penetration": round(penetration, 6),
                    "growth_norm": round(growth_norm, 4),
                    "volume_norm": round(volume_norm, 4),
                    "signal_ratio": round(sratio, 4),
                },
            }
            for t in DIM_TERM_QUERIES.get(dim_key, []):
                metrics["signals"][f"term:{t}"] = signals.term_counts.get(f"{dim_key}:{t}", 0)

            if dim_key == "model":
                metrics["evidence"] = evidence_items()

            node["dimensions"][dim_key] = metrics

    base["generatedAt"] = datetime.now(tz=UTC).isoformat()
    base["meta"] = {
        "source": "openalex",
        "windowYears": window_years,
        "fromPublicationDate": _iso(window_start),
        "aiConcept": ai_concept_name,
        "aiConceptId": ai_concept_id,
        "termQueries": DIM_TERM_QUERIES,
        "updatedDomains": updated_domains,
        "warningCount": len(query_warnings),
        "warnings": query_warnings[:20],
    }

    save_concept_cache(cache)
    BASE_PATH.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", "utf-8")
    if query_warnings:
        print(f"[warn] completed with {len(query_warnings)} domain-level query warnings")
    print(f"[done] wrote {BASE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
