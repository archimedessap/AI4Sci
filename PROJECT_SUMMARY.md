# AI4Sci Project Summary

## Purpose
- Build an "AI4Sci Progress Atlas" that tracks progress signals per scientific subdomain.
- Combine OpenAlex data, a local SQLite paper library, and optional LLM analysis.
- Provide a Next.js web UI for exploration, evidence, and admin overrides.

## Architecture
- Python pipeline writes data files under `web/data/` and maintains a local DB `data/papers.sqlite`.
- Next.js app (in `web/`) reads `web/data/*.json` on the server and renders pages dynamically.
- Optional LLM steps (DeepSeek default) for classification and layered "discovery depth."

## Data Sources
- OpenAlex API (includes arXiv) for domain-level metrics and paper ingestion.
- Manual daily updates: `updates/YYYY-MM-DD*.md`.
- LLM outputs (optional) generated from the local paper library.

## Key Data Flow
1) `scripts/update_progress_openalex.py` -> `web/data/base.json`
2) `scripts/ingest_ai4sci_openalex.py` -> `data/papers.sqlite`
3) `scripts/ingest_ai4sci_openalex_supplement.py` -> supplement keyword/journal ingestion into SQLite
4) `scripts/tag_ai_methods.py` -> method tags in SQLite
5) `scripts/export_papers_catalog.py` -> `web/data/papers_catalog.json` (+ `.md`)
6) `scripts/analyze_*` -> `web/data/problem_method_map.json`, `coverage_report.json`, `top_papers_last_year.json`, `domain_extra_metrics.json`
7) `scripts/update_daily_updates.py` -> `web/data/daily_updates.json` (+ `.md`)
8) `scripts/judge_*_llm.py` -> optional LLM-derived layers and auto overrides
9) Admin overrides -> `web/data/overrides.json` via `/admin`

## Repository Layout
- `scripts/`: Python pipelines and analysis tools.
- `data/`: Local SQLite DB (`papers.sqlite`), ignored by git.
- `web/`: Next.js app (SSR).
- `web/data/`: JSON/MD datasets used by the UI.
- `updates/`: Daily updates input Markdown files.
- `.cache/`: OpenAlex concept cache (ignored by git).

## Core Scripts
- `scripts/update_all.py`: one-command pipeline; includes OpenAlex progress, DB ingest, tags, exports, analyses, daily updates.
- `scripts/update_progress_openalex.py`: updates `web/data/base.json` from OpenAlex concepts.
- `scripts/ingest_ai4sci_openalex.py`: ingests papers to SQLite.
- `scripts/ingest_ai4sci_openalex_supplement.py`: keyword/journal supplement ingest to improve recall.
- `scripts/tag_ai_methods.py`: heuristic method tags (CNN/GNN/Transformer/LLM/etc).
- `scripts/export_papers_catalog.py`: exports `web/data/papers_catalog.json`.
- `scripts/analyze_problem_method_map.py`: generates `web/data/problem_method_map.json`.
- `scripts/analyze_coverage_report.py`: generates `web/data/coverage_report.json`.
- `scripts/analyze_domain_extra_metrics.py`: generates `web/data/domain_extra_metrics.json`.
- `scripts/analyze_top_papers_last_year.py`: generates `web/data/top_papers_last_year.json`.
- `scripts/update_daily_updates.py`: classifies `updates/*.md` into `web/data/daily_updates.json`.
- `scripts/update_progress_history.py`: appends progress snapshots -> `web/data/progress_history.json`.
- `scripts/judge_progress_llm.py`: LLM auto overrides -> `web/data/auto_overrides.json`.
- `scripts/judge_discovery_layers_llm.py`: LLM discovery layers -> `web/data/discovery_layers.json`.
- `scripts/judge_formal_layers_llm.py`: LLM formal layers -> `web/data/formal_layers.json`.

## Web App Routes
- `/` home (map + charts)
- `/domain/[id]` subdomain detail (radar, evidence, paper list)
- `/papers` full paper catalog (filters + sorting)
- `/updates` daily updates
- `/problem-method` problem-method heatmap
- `/coverage` coverage table
- `/trends` milestones & trends (snapshot time series)
- `/top` top papers (last-year window)
- `/methodology` methodology notes
- `/admin` admin overrides (requires `ADMIN_TOKEN`)
- `/api/progress` data API

## Paper Sorting Options
- Domain page and `/papers` support: Most cited, Citation rate (citations/year), Most recent.

## LLM Providers
- Provider selection in `scripts/llm_clients.py`.
- Priority when `LLM_PROVIDER` not set: DeepSeek -> OpenAI -> Gemini -> Grok.
- DeepSeek is OpenAI-compatible (`https://api.deepseek.com` by default).

## Environment Variables (Key)
- `.env` (repo root) for Python scripts:
  - `LLM_PROVIDER` (openai|gemini|deepseek|grok)
  - `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `GROK_API_KEY`
  - Optional knobs: `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT_S`, `LLM_RETRIES`
- `web/.env.local` for admin UI:
  - `ADMIN_TOKEN`

## Important Data Files
- `web/data/base.json`: OpenAlex progress snapshot
- `web/data/overrides.json`: manual overrides from `/admin`
- `web/data/auto_overrides.json`: LLM auto overrides (optional)
- `web/data/papers_catalog.json`: paper list (exported from SQLite)
- `web/data/problem_method_map.json`: problem-method heatmap data
- `web/data/domain_extra_metrics.json`: tooling/autonomy metrics
- `web/data/coverage_report.json`: coverage table data
- `web/data/top_papers_last_year.json`: last-year top papers
- `web/data/daily_updates.json`: daily updates classified
- `web/data/progress_history.json`: progress snapshots (time series)
- `web/data/discovery_layers.json`, `web/data/formal_layers.json`: LLM layer outputs

## Running Locally
- Update pipeline:
  - `python3 scripts/update_all.py --daily-updates`
  - `python3 scripts/update_all.py --daily-updates --daily-updates-no-llm`
- Web dev:
  - `cd web && npm run dev`
- Web prod:
  - `cd web && npm run build && npm start`

## Scheduling Updates
- Recommended: daily schedule to run `scripts/update_all.py`.
- Local Mac example uses `launchd` (not tracked in repo).
- `/.github/workflows/daily-update.yml` exists for GitHub Actions (optional).
