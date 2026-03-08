#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    printable = " ".join(shlex.quote(c) for c in cmd)
    print(f"[run] {printable}")
    subprocess.run(cmd, check=True)  # noqa: S603


def main() -> int:
    ap = argparse.ArgumentParser(
        description="One-command update pipeline: OpenAlex progress + paper DB + derived visualizations."
    )
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "papers.sqlite", help="SQLite DB path.")
    ap.add_argument("--years", type=int, default=3, help="Ingest window years (default: 3).")
    ap.add_argument(
        "--max-works-per-domain",
        type=int,
        default=2000,
        help="Max works per domain per sort pass (default: 2000).",
    )
    ap.add_argument(
        "--domains",
        type=str,
        default=None,
        help="Comma-separated leaf domain ids to ingest (optional). If omitted, ingest all leaf domains.",
    )
    ap.add_argument(
        "--openalex-full",
        action="store_true",
        help="Run OpenAlex progress updater in full mode (default: --only-missing for speed).",
    )
    ap.add_argument(
        "--skip-openalex",
        action="store_true",
        help="Skip OpenAlex progress update.",
    )
    ap.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip OpenAlex paper ingestion into local DB.",
    )
    ap.add_argument(
        "--skip-supplement",
        action="store_true",
        help="Skip supplementary OpenAlex ingestion (keywords/journals).",
    )
    ap.add_argument(
        "--skip-incremental",
        action="store_true",
        help="Skip direct-source incremental ingestion (arXiv + RSS/TOC).",
    )
    ap.add_argument(
        "--supplement-sources-file",
        type=Path,
        default=ROOT / "scripts" / "ai4sci_sources.txt",
        help="Primary sources list for supplementary ingestion.",
    )
    ap.add_argument(
        "--supplement-top-journals-file",
        type=Path,
        default=ROOT / "scripts" / "ai4sci_top_journals.txt",
        help="Top-journal sources list for supplementary ingestion.",
    )
    ap.add_argument(
        "--supplement-ai-keywords-file",
        type=Path,
        default=ROOT / "scripts" / "ai4sci_ai_keywords.txt",
        help="AI keyword list for supplementary ingestion.",
    )
    ap.add_argument(
        "--supplement-keywords-file",
        type=Path,
        default=ROOT / "scripts" / "ai4sci_conference_keywords.txt",
        help="Conference/global keyword list for supplementary ingestion.",
    )
    ap.add_argument(
        "--incremental-config",
        type=Path,
        default=ROOT / "scripts" / "ai4sci_incremental_sources.json",
        help="Config JSON for direct incremental sources.",
    )
    ap.add_argument(
        "--incremental-ai-keywords-file",
        type=Path,
        default=ROOT / "scripts" / "ai4sci_incremental_ai_keywords.txt",
        help="AI keywords file for direct incremental sources.",
    )
    ap.add_argument(
        "--incremental-lookback-hours",
        type=int,
        default=336,
        help="Lookback window for direct incremental sources (default: 336h / 14d).",
    )
    ap.add_argument(
        "--skip-tags",
        action="store_true",
        help="Skip method tagging step.",
    )
    ap.add_argument(
        "--tag-updated-since-hours",
        type=int,
        default=336,
        help="Only retag papers updated within the last N hours (default: 336, 0 = entire DB).",
    )
    ap.add_argument(
        "--skip-exports",
        action="store_true",
        help="Skip exporting / analyzing web data files (papers catalog, maps, etc).",
    )
    ap.add_argument(
        "--skip-history",
        action="store_true",
        help="Skip writing web/data/progress_history.json snapshot.",
    )
    ap.add_argument(
        "--skip-first-principles",
        action="store_true",
        help="Skip generating the first-principles lens and daily monitor artifacts.",
    )
    ap.add_argument(
        "--daily-updates",
        action="store_true",
        help="Also classify updates/*.md into web/data/daily_updates.json (+ .md).",
    )
    ap.add_argument(
        "--daily-updates-no-llm",
        action="store_true",
        help="Run daily updates classifier in heuristic mode (no LLM calls).",
    )
    ap.add_argument(
        "--daily-updates-no-catalog",
        action="store_true",
        help="Disable auto-generated daily entries from papers_catalog.json.",
    )
    args = ap.parse_args()

    py = sys.executable or "python3"

    if not args.skip_openalex:
        cmd = [py, str(ROOT / "scripts" / "update_progress_openalex.py")]
        if not args.openalex_full:
            cmd.append("--only-missing")
        run(cmd)

    if not args.skip_ingest:
        cmd = [
            py,
            str(ROOT / "scripts" / "ingest_ai4sci_openalex.py"),
            "--db",
            str(args.db),
            "--years",
            str(int(args.years)),
            "--max-works-per-domain",
            str(int(args.max_works_per_domain)),
            "--sort-strategy",
            "both",
            "--no-export",
        ]
        if args.domains:
            cmd.extend(["--domains", args.domains])
        run(cmd)

    if not args.skip_supplement:
        cmd = [
            py,
            str(ROOT / "scripts" / "ingest_ai4sci_openalex_supplement.py"),
            "--db",
            str(args.db),
            "--years",
            str(int(args.years)),
            "--sources-file",
            str(args.supplement_sources_file),
            "--sources-file",
            str(args.supplement_top_journals_file),
            "--ai-keywords-file",
            str(args.supplement_ai_keywords_file),
            "--keywords-file",
            str(args.supplement_keywords_file),
            "--no-export",
        ]
        if args.domains:
            cmd.extend(["--domains", args.domains])
        run(cmd)

    if not args.skip_incremental:
        cmd = [
            py,
            str(ROOT / "scripts" / "ingest_incremental_sources.py"),
            "--db",
            str(args.db),
            "--config",
            str(args.incremental_config),
            "--ai-keywords-file",
            str(args.incremental_ai_keywords_file),
            "--lookback-hours",
            str(int(args.incremental_lookback_hours)),
            "--no-export",
        ]
        run(cmd)

    if not args.skip_tags:
        cmd = [py, str(ROOT / "scripts" / "tag_ai_methods.py"), "--db", str(args.db), "--only-missing"]
        if int(args.tag_updated_since_hours) > 0:
            cmd.extend(["--updated-since-hours", str(int(args.tag_updated_since_hours))])
        run(cmd)

    if not args.skip_exports:
        run([py, str(ROOT / "scripts" / "export_papers_catalog.py"), "--db", str(args.db)])
        run([py, str(ROOT / "scripts" / "analyze_domain_extra_metrics.py"), "--db", str(args.db)])
        run([py, str(ROOT / "scripts" / "analyze_problem_method_map.py"), "--db", str(args.db)])
        run([py, str(ROOT / "scripts" / "analyze_top_papers_last_year.py"), "--db", str(args.db)])
        run([py, str(ROOT / "scripts" / "analyze_coverage_report.py"), "--db", str(args.db)])

    if args.daily_updates:
        cmd = [py, str(ROOT / "scripts" / "update_daily_updates.py")]
        if not args.daily_updates_no_catalog:
            cmd.append("--auto-from-catalog")
        if args.daily_updates_no_llm:
            cmd.append("--no-llm")
        run(cmd)

    if not args.skip_history:
        run([py, str(ROOT / "scripts" / "update_progress_history.py")])

    if not args.skip_first_principles:
        run([py, str(ROOT / "scripts" / "analyze_first_principles_lens.py")])

    print("[done] update pipeline finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
