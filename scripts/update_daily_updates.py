#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from llm_clients import LLMClient, LLMError, load_llm_from_env

ROOT = Path(__file__).resolve().parents[1]
UPDATES_DIR = ROOT / "updates"
OUT_JSON = ROOT / "web" / "data" / "daily_updates.json"
OUT_MD = ROOT / "web" / "data" / "daily_updates.md"

DimensionKey = Literal["data", "model", "predict", "experiment", "explain"]
DIM_KEYS: list[DimensionKey] = ["data", "model", "predict", "experiment", "explain"]


def iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        raw = path.read_text("utf-8")
    except Exception:
        return
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("export "):
            s = s[7:].strip()
        if "=" not in s:
            continue
        key, value = s.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        v = value.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        os.environ[key] = v


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def save_json(path: Path, data: dict[str, Any]) -> None:
    save_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def sha256_text(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8", errors="ignore"))
    return f"sha256:{h.hexdigest()}"


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class UpdateSource:
    date: str
    rel_path: str
    raw: str
    content_hash: str
    source_type: Literal["manual", "catalog"] = "manual"


def read_update_sources(updates_dir: Path) -> list[UpdateSource]:
    if not updates_dir.exists():
        return []

    sources: list[UpdateSource] = []
    for p in sorted(updates_dir.rglob("*.md")):
        rel = str(p.relative_to(ROOT))
        m = DATE_RE.search(p.name)
        if not m:
            continue
        date = m.group(1)
        try:
            raw = p.read_text("utf-8").strip()
        except Exception:
            continue
        if not raw:
            continue
        sources.append(
            UpdateSource(
                date=date,
                rel_path=rel,
                raw=raw,
                content_hash=sha256_text(raw),
                source_type="manual",
            )
        )

    sources.sort(key=lambda s: (s.date, s.rel_path))
    return sources


def parse_date_ymd(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def safe_int(raw: Any) -> int | None:
    try:
        return int(raw)
    except Exception:
        return None


def _top_domains_text(
    papers: list[dict[str, Any]],
    *,
    domain_name_by_id: dict[str, str],
    max_items: int = 8,
) -> str:
    counts: dict[str, int] = {}
    for p in papers:
        domains = p.get("domains")
        if not isinstance(domains, list):
            continue
        for d in domains:
            if not isinstance(d, str) or not d.strip():
                continue
            did = d.strip()
            counts[did] = counts.get(did, 0) + 1

    if not counts:
        return ""
    items = sorted(counts.items(), key=lambda it: (-it[1], it[0]))[:max_items]
    out: list[str] = []
    for did, c in items:
        out.append(f"{domain_name_by_id.get(did, did)}({c})")
    return ", ".join(out)


def build_catalog_daily_raw(
    *,
    date_ymd: str,
    papers: list[dict[str, Any]],
    total_count: int,
    domain_name_by_id: dict[str, str],
) -> str:
    lines: list[str] = []
    lines.append(f"# Auto Daily Research Update ({date_ymd})")
    lines.append("")
    lines.append(f"- Source: papers_catalog.json")
    lines.append(f"- New papers tracked today: {total_count}")

    top_domains = _top_domains_text(papers, domain_name_by_id=domain_name_by_id, max_items=8)
    if top_domains:
        lines.append(f"- Top domains: {top_domains}")

    lines.append("")
    lines.append("## Highlights")
    for p in papers:
        title = str(p.get("title") or "").strip()
        if not title:
            continue
        cited = safe_int(p.get("citedBy"))
        source = str(p.get("source") or "").strip()
        abstract = str(p.get("abstract") or "").strip()

        domains = p.get("domains")
        dnames: list[str] = []
        if isinstance(domains, list):
            for d in domains:
                if not isinstance(d, str) or not d.strip():
                    continue
                dnames.append(domain_name_by_id.get(d.strip(), d.strip()))
        dnames = list(dict.fromkeys(dnames))[:4]

        tail_parts: list[str] = []
        if dnames:
            tail_parts.append("/".join(dnames))
        if source:
            tail_parts.append(source)
        if cited is not None:
            tail_parts.append(f"citedBy={cited}")
        tail = f" ({' | '.join(tail_parts)})" if tail_parts else ""
        lines.append(f"- {title}{tail}")
        if abstract:
            lines.append(f"  - {truncate(abstract, 280)}")

    return "\n".join(lines).strip() + "\n"


def read_catalog_update_sources(
    *,
    catalog_json: Path,
    days: int,
    max_papers_per_day: int,
    min_papers_per_day: int,
) -> list[UpdateSource]:
    if days <= 0 or max_papers_per_day <= 0:
        return []

    catalog = load_json(catalog_json)
    papers_raw = catalog.get("papers")
    if not isinstance(papers_raw, list):
        return []

    domain_name_by_id: dict[str, str] = {}
    domains_raw = catalog.get("domains")
    if isinstance(domains_raw, list):
        for d in domains_raw:
            if not isinstance(d, dict):
                continue
            did = d.get("id")
            name = d.get("name")
            if isinstance(did, str) and did.strip() and isinstance(name, str) and name.strip():
                domain_name_by_id[did.strip()] = name.strip()

    today = datetime.now(tz=UTC).date()
    from_day = today - timedelta(days=max(0, days - 1))

    grouped_all: dict[date, list[dict[str, Any]]] = {}
    for raw in papers_raw:
        if not isinstance(raw, dict):
            continue
        d = parse_date_ymd(raw.get("publicationDate"))
        if d is None:
            continue
        if d > today:
            continue
        grouped_all.setdefault(d, []).append(raw)

    if not grouped_all:
        return []

    chosen_days = sorted([k for k in grouped_all.keys() if k >= from_day], reverse=True)
    if not chosen_days:
        # Fallback: if recent calendar window has no publications, keep the latest available days.
        chosen_days = sorted(grouped_all.keys(), reverse=True)[: max(1, days)]

    grouped: dict[date, list[dict[str, Any]]] = {k: grouped_all[k] for k in chosen_days}

    out: list[UpdateSource] = []
    for day in sorted(grouped.keys()):
        rows = grouped.get(day) or []
        if len(rows) < max(1, min_papers_per_day):
            continue

        def rank_key(p: dict[str, Any]) -> tuple[int, str]:
            cited = safe_int(p.get("citedBy"))
            return (cited if cited is not None else -1, str(p.get("title") or ""))

        rows_sorted = sorted(
            rows,
            key=rank_key,
            reverse=True,
        )
        picked = rows_sorted[:max_papers_per_day]
        raw_text = build_catalog_daily_raw(
            date_ymd=day.isoformat(),
            papers=picked,
            total_count=len(rows),
            domain_name_by_id=domain_name_by_id,
        )
        day_str = day.isoformat()
        out.append(
            UpdateSource(
                date=day_str,
                rel_path=f"auto:papers_catalog:{day_str}",
                raw=raw_text,
                content_hash=sha256_text(raw_text),
                source_type="catalog",
            )
        )

    out.sort(key=lambda s: (s.date, s.rel_path))
    return out


JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str) -> dict[str, Any]:
    m = JSON_BLOCK_RE.search(text)
    if m:
        text = m.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def clamp100(v: Any) -> float:
    try:
        f = float(v)
    except Exception:
        return 0.0
    return max(0.0, min(100.0, f))


def clamp01(v: Any) -> float:
    try:
        f = float(v)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, f))


def normalize_dims(raw: Any) -> dict[DimensionKey, float]:
    dims: dict[DimensionKey, float] = {k: 0.0 for k in DIM_KEYS}
    if isinstance(raw, dict):
        for k in DIM_KEYS:
            if k in raw:
                dims[k] = clamp100(raw.get(k))
    total = sum(dims.values())
    if total <= 0:
        each = 100.0 / len(DIM_KEYS)
        return {k: each for k in DIM_KEYS}
    scale = 100.0 / total
    return {k: round(dims[k] * scale, 2) for k in DIM_KEYS}


def clean_str_list(v: Any, *, max_items: int) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for it in v:
        if not isinstance(it, str):
            continue
        s = re.sub(r"\s+", " ", it).strip()
        if not s:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def heuristic_dims(text: str) -> dict[DimensionKey, float]:
    t = text.lower()
    scores: dict[DimensionKey, float] = {k: 0.0 for k in DIM_KEYS}
    rules: list[tuple[DimensionKey, list[str], float]] = [
        ("data", ["data", "dataset", "ingest", "crawl", "etl", "openalex", "sqlite", "索引", "抓取", "数据", "标注"], 1.0),
        ("model", ["model", "train", "finetune", "prompt", "llm", "embed", "transformer", "模型", "训练", "推理"], 1.0),
        ("predict", ["predict", "forecast", "control", "planning", "optimiz", "policy", "预测", "控制", "规划", "优化"], 1.0),
        ("experiment", ["experiment", "lab", "robot", "closed-loop", "automation", "实验", "自动化", "闭环"], 1.0),
        ("explain", ["explain", "causal", "theory", "interpret", "visual", "doc", "解释", "因果", "理论", "可视化", "文档"], 1.0),
    ]
    for dim, kws, w in rules:
        for kw in kws:
            if kw in t:
                scores[dim] += w
    return normalize_dims(scores)


def build_prompt(raw: str) -> tuple[str, str]:
    system = (
        "你是一个“每日更新/日报”的结构化标注器。"
        "你必须只输出 JSON（不要 Markdown、不要解释、不要代码块外的文字）。"
    )
    prompt = f"""请把下面的“每日更新”文本结构化为 JSON，用于网站可视化：

五维分类（请按“投入/影响”分配权重，0-100，五个维度加总=100）：
- data：数据、数据集、爬取/ETL、索引、存储、质量、基准构建
- model：模型、架构、训练/推理、提示词、评测方法、LLM 应用
- predict：预测/控制/规划/优化/决策、仿真与推演
- experiment：实验设计、实验自动化、机器人、闭环实验
- explain：解释/因果/理论、归纳总结、方法论、文档与可视化

输出 JSON schema（严格遵守字段名）：
{{
  "summary": "一句话概括（<=40字）",
  "highlights": ["3-6条要点，每条<=60字"],
  "dimensions": {{"data": 0, "model": 0, "predict": 0, "experiment": 0, "explain": 0}},
  "tags": ["可选：3-8个短标签"],
  "confidence": 0.0
}}

注意：
- dimensions 必须是数字，且加总=100（允许小数，但建议整数）。
- confidence 是 0-1 的小数，表示你对分类的把握。

每日更新原文：
\"\"\"{raw.strip()}\"\"\""""
    return system, prompt


def truncate(text: str, max_chars: int) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def fallback_summary(raw: str) -> str:
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^[#*\-\d.]+\s*", "", s).strip()
        if not s:
            continue
        return truncate(s, 40)
    return ""


def fallback_highlights(raw: str, *, max_items: int = 6) -> list[str]:
    out: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(("-", "*", "•")):
            s = re.sub(r"^[-*•]+\s*", "", s).strip()
        else:
            continue
        if not s:
            continue
        out.append(truncate(s, 60))
        if len(out) >= max_items:
            break
    return out


def classify_update(*, client: LLMClient | None, raw: str) -> dict[str, Any]:
    if client is None:
        dims = heuristic_dims(raw)
        return {
            "summary": fallback_summary(raw),
            "highlights": fallback_highlights(raw),
            "dimensions": dims,
            "tags": [],
            "confidence": 0.2,
            "_mode": "heuristic",
        }

    system, prompt = build_prompt(raw)
    text = client.generate_text(prompt=prompt, system=system)
    data = extract_json(text)

    summary = data.get("summary")
    if not isinstance(summary, str):
        summary = ""
    summary = re.sub(r"\s+", " ", summary).strip() or fallback_summary(raw)

    highlights = clean_str_list(data.get("highlights"), max_items=6) or fallback_highlights(raw)
    tags = clean_str_list(data.get("tags"), max_items=10)
    tags = list(dict.fromkeys(tags))[:8]

    dims = normalize_dims(data.get("dimensions"))
    confidence = clamp01(data.get("confidence"))

    return {
        "summary": summary,
        "highlights": highlights,
        "dimensions": dims,
        "tags": tags,
        "confidence": confidence,
        "_mode": "llm",
    }


def render_md(entries: list[dict[str, Any]], *, updated_at: str) -> str:
    lines: list[str] = []
    lines.append("# Daily Updates\n")
    lines.append(f"- UpdatedAt: {updated_at}\n")
    for e in sorted(entries, key=lambda it: it.get("date") or "", reverse=True):
        date = e.get("date") or ""
        summary = e.get("summary") or ""
        lines.append(f"\n## {date}\n")
        if summary:
            lines.append(f"{summary}\n")
        source_type = str(e.get("sourceType") or "manual")
        source_path = str(e.get("sourcePath") or "")
        lines.append(f"- Source: {source_type} ({source_path})\n")
        dims = e.get("dimensions") or {}
        if isinstance(dims, dict):
            dim_line = " • ".join([f"{k}={float(dims.get(k) or 0):.0f}" for k in DIM_KEYS])
            lines.append(f"- Dimensions: {dim_line}\n")
        tags = e.get("tags") or []
        if isinstance(tags, list) and tags:
            lines.append(f"- Tags: {', '.join(str(t) for t in tags if t)}\n")
        hl = e.get("highlights") or []
        if isinstance(hl, list) and hl:
            lines.append("- Highlights:\n")
            for it in hl:
                if isinstance(it, str) and it.strip():
                    lines.append(f"  - {it.strip()}\n")
    return "".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Classify daily updates with an LLM and export web/data/daily_updates.json (+ .md)."
    )
    ap.add_argument("--updates-dir", type=Path, default=UPDATES_DIR, help="Input folder with YYYY-MM-DD*.md files.")
    ap.add_argument("--out-json", type=Path, default=OUT_JSON, help="Output JSON path.")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown path.")
    ap.add_argument("--force", action="store_true", help="Reclassify all files (ignore cached hashes).")
    ap.add_argument("--max-files", type=int, default=0, help="Limit processed files (0=all).")
    ap.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Force provider: openai|gemini|deepseek|grok (optional).",
    )
    ap.add_argument("--no-llm", action="store_true", help="Skip LLM and use heuristic classifier.")
    ap.add_argument("--include-raw", action="store_true", help="Include raw update text in exported JSON.")
    ap.add_argument(
        "--auto-from-catalog",
        action="store_true",
        help="Auto-generate daily update entries from web/data/papers_catalog.json.",
    )
    ap.add_argument(
        "--catalog-json",
        type=Path,
        default=ROOT / "web" / "data" / "papers_catalog.json",
        help="papers_catalog.json path for auto updates.",
    )
    ap.add_argument(
        "--catalog-days",
        type=int,
        default=7,
        help="How many recent days to include from papers catalog when --auto-from-catalog is enabled.",
    )
    ap.add_argument(
        "--catalog-max-papers-per-day",
        type=int,
        default=25,
        help="Max paper highlights per day for auto catalog updates.",
    )
    ap.add_argument(
        "--catalog-min-papers-per-day",
        type=int,
        default=3,
        help="Skip auto day entries with fewer papers than this threshold.",
    )
    args = ap.parse_args()

    load_dotenv_file(ROOT / ".env")

    client: LLMClient | None = None
    provider = None
    if args.provider:
        p = args.provider.strip().lower()
        if p not in {"openai", "gemini", "deepseek", "grok"}:
            raise SystemExit(f"Invalid --provider: {args.provider}")
        provider = cast(Literal["openai", "gemini", "deepseek", "grok"], p)

    if not args.no_llm:
        try:
            _, client = load_llm_from_env(provider=provider)
        except LLMError as e:
            print(f"[warn] LLM not configured ({e}); fallback to heuristic mode")
            client = None

    prev = load_json(args.out_json)
    prev_entries: list[dict[str, Any]] = prev.get("entries") if isinstance(prev.get("entries"), list) else []
    prev_by_source: dict[str, dict[str, Any]] = {}
    for it in prev_entries:
        if isinstance(it, dict):
            sp = it.get("sourcePath")
            if isinstance(sp, str) and sp:
                prev_by_source[sp] = it

    sources = read_update_sources(args.updates_dir)
    if args.auto_from_catalog:
        auto_sources = read_catalog_update_sources(
            catalog_json=args.catalog_json,
            days=int(args.catalog_days),
            max_papers_per_day=int(args.catalog_max_papers_per_day),
            min_papers_per_day=int(args.catalog_min_papers_per_day),
        )
        if auto_sources:
            print(f"[info] loaded {len(auto_sources)} auto daily entries from {args.catalog_json}")
        sources.extend(auto_sources)

    sources.sort(key=lambda s: (s.date, s.rel_path))
    if args.max_files and args.max_files > 0:
        # Keep the most recent N sources to speed up debugging.
        sources = sorted(sources, key=lambda s: (s.date, s.rel_path), reverse=True)[: int(args.max_files)]
        sources.sort(key=lambda s: (s.date, s.rel_path))

    if not sources and not args.force and prev_entries:
        updated_at = iso_now()
        source_type_counts: dict[str, int] = {}
        for it in prev_entries:
            if not isinstance(it, dict):
                continue
            st = str(it.get("sourceType") or "manual").strip().lower() or "manual"
            source_type_counts[st] = source_type_counts.get(st, 0) + 1
        out = {
            "version": "1",
            "updatedAt": updated_at,
            "entries": prev_entries,
            "stats": {
                "total": len(prev_entries),
                "changed": 0,
                "skipped": len(prev_entries),
                "sourceTypes": source_type_counts,
                "reusedPrevious": True,
            },
        }
        save_json(args.out_json, out)
        save_text(args.out_md, render_md(prev_entries, updated_at=updated_at))
        print("[info] no update sources found; reused previous daily updates")
        print(f"[done] wrote {args.out_json} and {args.out_md}")
        return 0

    next_entries: list[dict[str, Any]] = []
    changed = 0
    skipped = 0
    for src in sources:
        prev_item = prev_by_source.get(src.rel_path)
        if not args.force and prev_item and prev_item.get("sourceHash") == src.content_hash:
            next_entries.append(prev_item)
            skipped += 1
            continue

        meta = classify_update(client=client, raw=src.raw)
        next_entries.append(
            {
                "id": f"{src.date}:{src.rel_path}",
                "date": src.date,
                "sourcePath": src.rel_path,
                "sourceHash": src.content_hash,
                "sourceType": src.source_type,
                "summary": meta.get("summary") or "",
                "highlights": meta.get("highlights") or [],
                "dimensions": meta.get("dimensions") or {k: 0 for k in DIM_KEYS},
                "tags": meta.get("tags") or [],
                "confidence": meta.get("confidence") or 0.0,
                "mode": meta.get("_mode") or ("heuristic" if client is None else "llm"),
                "classifiedAt": iso_now(),
            }
        )
        if args.include_raw:
            next_entries[-1]["raw"] = src.raw
        changed += 1
        print(f"[ok] {src.date} {src.rel_path} classified")

    next_entries.sort(key=lambda it: (it.get("date") or "", it.get("sourcePath") or ""))
    updated_at = iso_now()
    source_type_counts: dict[str, int] = {}
    for it in next_entries:
        st = str(it.get("sourceType") or "manual").strip().lower() or "manual"
        source_type_counts[st] = source_type_counts.get(st, 0) + 1
    out = {
        "version": "1",
        "updatedAt": updated_at,
        "entries": next_entries,
        "stats": {
            "total": len(next_entries),
            "changed": changed,
            "skipped": skipped,
            "sourceTypes": source_type_counts,
        },
    }
    save_json(args.out_json, out)
    save_text(args.out_md, render_md(next_entries, updated_at=updated_at))
    print(f"[done] wrote {args.out_json} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
