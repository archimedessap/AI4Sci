#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from llm_clients import LLMError, load_llm_from_env
from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
OUT_JSON = ROOT / "web" / "data" / "discovery_layers.json"
OUT_MD = ROOT / "web" / "data" / "discovery_layers.md"
CACHE_DIR = ROOT / ".cache"

PROMPT_VERSION = "discovery_layers.v1"

LayerKey = Literal["phenomena", "empirical", "theory", "principles"]
LAYER_KEYS: list[LayerKey] = ["phenomena", "empirical", "theory", "principles"]


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    macro_id: str
    ai_recent: float


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
    return json.loads(path.read_text("utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def clamp01(v: Any) -> float:
    try:
        f = float(v)
    except Exception:
        return 0.0
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return max(0.0, min(1.0, f))


def norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    t = norm_space(text)
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def parse_leaf_domains(base: dict[str, Any]) -> list[Domain]:
    nodes: dict[str, Any] = base.get("nodes") or {}
    root_id = base.get("rootId")
    children_by_id: dict[str, list[str]] = {nid: [] for nid in nodes.keys()}
    for nid, node in nodes.items():
        pid = node.get("parentId")
        if pid and pid in children_by_id:
            children_by_id[pid].append(nid)

    def macro_of(did: str) -> str:
        cur = did
        visited: set[str] = set()
        while True:
            if cur in visited:
                return did
            visited.add(cur)
            n = nodes.get(cur) or {}
            pid = n.get("parentId")
            if not isinstance(pid, str) or not pid:
                return did
            if pid == root_id:
                return cur
            cur = pid

    leaves: list[Domain] = []
    for nid, node in nodes.items():
        if nid == root_id:
            continue
        if children_by_id.get(nid):
            continue
        name = node.get("name") or nid
        if not isinstance(name, str) or not name.strip():
            name = nid
        ai_recent = 0.0
        dims = node.get("dimensions")
        if isinstance(dims, dict):
            model = dims.get("model")
            if isinstance(model, dict):
                signals = model.get("signals")
                if isinstance(signals, dict):
                    try:
                        ai_recent = float(signals.get("ai_recent") or 0.0)
                    except Exception:
                        ai_recent = 0.0
        leaves.append(Domain(id=nid, name=name.strip(), macro_id=macro_of(nid), ai_recent=ai_recent))
    leaves.sort(key=lambda d: d.id)
    return leaves


def query_domain_total(con: sqlite3.Connection, domain_id: str) -> int:
    row = con.execute(
        """
        SELECT COUNT(*) AS total
        FROM paper_domains d
        WHERE d.domain_id = ?;
        """,
        (domain_id,),
    ).fetchone()
    return int(row["total"] or 0) if row else 0


def query_top_papers(
    con: sqlite3.Connection,
    *,
    domain_id: str,
    limit: int,
    order_by: str,
    since: date | None = None,
) -> list[dict[str, Any]]:
    allowed = {
        "cited": "COALESCE(p.cited_by_count, 0) DESC, COALESCE(p.publication_year, 0) DESC",
        "recent": "COALESCE(p.publication_date, '') DESC, COALESCE(p.publication_year, 0) DESC",
    }
    clause = allowed.get(order_by)
    if not clause:
        raise ValueError(f"Unsupported order_by: {order_by}")

    cur_year = datetime.now(tz=UTC).year
    since_date = since.isoformat() if since else None
    since_year = since.year if since else None

    where_extra = ""
    params: list[Any] = [domain_id]
    if since_date and since_year is not None:
        where_extra = """
          AND (
            (p.publication_date IS NOT NULL AND p.publication_date >= ?)
            OR (p.publication_date IS NULL AND p.publication_year IS NOT NULL AND p.publication_year >= ?)
          )
        """
        params.extend([since_date, since_year])
    # Avoid OpenAlex future placeholders when publication_date is missing.
    where_extra += " AND (p.publication_year IS NULL OR p.publication_year <= ?)"
    params.append(cur_year)
    params.append(limit)

    rows = con.execute(
        f"""
        SELECT
          p.openalex_id, p.title, p.abstract, p.publication_year, p.publication_date,
          p.cited_by_count, p.primary_url, p.source
        FROM paper_domains d
        JOIN papers p ON p.openalex_id = d.openalex_id
        WHERE d.domain_id = ?
          AND (p.publication_date IS NULL OR p.publication_date <= date('now'))
          {where_extra}
        ORDER BY {clause}
        LIMIT ?;
        """,
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "openalex_id": r["openalex_id"],
                "title": r["title"],
                "abstract": r["abstract"],
                "publication_year": r["publication_year"],
                "publication_date": r["publication_date"],
                "cited_by_count": r["cited_by_count"],
                "primary_url": r["primary_url"] or r["openalex_id"],
                "source": r["source"],
            }
        )
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


def paper_weight(p: dict[str, Any], now_year: int) -> float:
    cited = p.get("cited_by_count")
    year = p.get("publication_year")
    try:
        cited_i = int(cited) if cited is not None else 0
    except Exception:
        cited_i = 0
    try:
        year_i = int(year) if year is not None else 0
    except Exception:
        year_i = 0

    cite_w = 1.0 + math.log1p(max(0, cited_i))
    if year_i >= now_year - 1:
        recency = 1.0
    elif year_i >= now_year - 3:
        recency = 0.85
    elif year_i >= now_year - 6:
        recency = 0.7
    else:
        recency = 0.55
    return max(0.1, cite_w * recency)


def build_prompt(domain: Domain, *, total_in_db: int, papers: list[dict[str, Any]]) -> str:
    paper_lines: list[str] = []
    for i, p in enumerate(papers, start=1):
        openalex_id = str(p.get("openalex_id") or "").strip()
        title = truncate(str(p.get("title") or ""), 180)
        abs_ = truncate(p.get("abstract"), 900)
        year = p.get("publication_year") or p.get("publication_date") or ""
        cited = p.get("cited_by_count")
        suffix = []
        if year:
            suffix.append(str(year))
        if isinstance(cited, int):
            suffix.append(f"cited_by={cited}")
        paper_lines.append(
            f"{i}. id={openalex_id} | {title} ({', '.join(suffix)})\n   abstract: {abs_}"
        )

    return f"""你是一个“AI4Sci 科学发现分层评估器”。给定一个领域里若干 AI×领域（AI4Sci）论文的标题+摘要，请判断它们是否属于“AI 帮助产生科学发现”的工作，并把发现深度映射到四层（可同时贡献多个层级，0..1）。

领域：{domain.name} (id={domain.id})
本地库中该领域论文总数（AI4Sci）：{total_in_db}

四层定义（外→内）：
1) phenomena（新现象）：AI 帮助发现新的现象/模式/异常/结构/分类或新的可重复观测结果，但不一定形成稳定规律或机制解释。
2) empirical（新经验定律）：AI 帮助提出可复用的经验关系/经验公式/统计规律/通用关联（跨样本、跨条件仍成立），但缺少明确机理或理论统一。
3) theory（新理论）：AI 帮助提出可检验的机制模型/理论框架/方程结构，能够解释并预测（不仅拟合），并有可证伪的预测或推论。
4) principles（新原理）：AI 帮助发现更基础/更统一的原理（例如对多现象的统一解释、对理论的压缩与公理化、揭示更根本约束/对称性/守恒/第一性原理层面的结构）。

评分规则：
- layerScores 每项 0..1，表示该论文对该层“发现”的贡献强度；不要求单调、不要求和为 1。
- 如果论文主要是工程/工具/模型性能/数据集/benchmark，而没有“新的科学发现”，则 isDiscovery=false 且 layerScores 全 0。
- 只能根据 title+abstract 给出判断，不要臆测。

输入论文（可能摘要不完整）：
{chr(10).join(paper_lines) if paper_lines else "(none)"}

输出要求：只输出严格 JSON（不要额外文字）：
{{
  "confidence": 0-1,
  "note": "一句话总结（<=120字，概括该领域在四层上的总体倾向）",
  "papers": [
    {{
      "id": "openalex_id (必须与输入中的 id 完全一致)",
      "isDiscovery": true/false,
      "layerScores": {{
        "phenomena": 0-1,
        "empirical": 0-1,
        "theory": 0-1,
        "principles": 0-1
      }},
      "summary": "可选：若 isDiscovery=true，则用<=60字描述发现点；否则可省略",
      "confidence": 0-1
    }}
  ]
}}
"""

def repair_json(client: Any, bad_text: str) -> dict[str, Any]:
    prompt = f"""下面是一段模型输出，但不是合法 JSON。请在不改变语义的前提下修复为严格 JSON（UTF-8，双引号，true/false/null），只输出 JSON，不要 Markdown：

{bad_text}
"""
    fixed = client.generate_text(
        prompt=prompt,
        system="你是 JSON 修复器。只输出严格 JSON。",
    )
    return extract_json(fixed)


def aggregate_layers(
    papers: list[dict[str, Any]],
    judged: list[dict[str, Any]],
) -> tuple[dict[LayerKey, float], dict[LayerKey, list[dict[str, Any]]], float]:
    by_id = {str(p["openalex_id"]): p for p in papers if p.get("openalex_id")}
    now_year = datetime.now(tz=UTC).year

    sum_w = 0.0
    sum_conf_w = 0.0
    sum_conf = 0.0
    layer_sums: dict[LayerKey, float] = {k: 0.0 for k in LAYER_KEYS}

    contribs: dict[LayerKey, list[tuple[float, dict[str, Any]]]] = {k: [] for k in LAYER_KEYS}

    for item in judged:
        pid = item.get("id")
        if not isinstance(pid, str) or pid not in by_id:
            continue
        paper = by_id[pid]
        is_discovery = bool(item.get("isDiscovery"))
        scores = item.get("layerScores") or {}
        summary = item.get("summary")
        summary_str = truncate(summary, 120) if isinstance(summary, str) else ""
        pconf = clamp01(item.get("confidence"))
        if not is_discovery:
            continue
        w = paper_weight(paper, now_year) * (0.5 + 0.5 * pconf)
        sum_w += w
        sum_conf_w += w
        sum_conf += w * pconf

        for k in LAYER_KEYS:
            v = clamp01(scores.get(k) if isinstance(scores, dict) else 0.0)
            layer_sums[k] += w * v
            contrib = w * v
            if contrib > 0:
                contribs[k].append(
                    (
                        contrib,
                        {
                            "id": pid,
                            "title": paper.get("title"),
                            "url": paper.get("primary_url") or paper.get("openalex_id"),
                            "year": paper.get("publication_year"),
                            "citedBy": paper.get("cited_by_count"),
                            "score": round(v, 3),
                            "summary": summary_str or None,
                        },
                    )
                )

    layers: dict[LayerKey, float] = {}
    for k in LAYER_KEYS:
        layers[k] = (layer_sums[k] / sum_w) if sum_w > 0 else 0.0
        layers[k] = max(0.0, min(1.0, layers[k]))

    evidence: dict[LayerKey, list[dict[str, Any]]] = {}
    for k in LAYER_KEYS:
        items = sorted(contribs[k], key=lambda t: t[0], reverse=True)[:5]
        evidence[k] = [{kk: vv for kk, vv in it.items() if vv is not None} for _, it in items]

    overall_conf = (sum_conf / sum_conf_w) if sum_conf_w > 0 else 0.0
    overall_conf = max(0.0, min(1.0, overall_conf))
    return layers, evidence, overall_conf


def build_markdown(data: dict[str, Any], base: dict[str, Any]) -> str:
    nodes = data.get("nodes") or {}
    domains = (base.get("nodes") or {})

    def domain_name(did: str) -> str:
        n = domains.get(did) or {}
        name = n.get("name")
        return name if isinstance(name, str) and name.strip() else did

    lines: list[str] = []
    lines.append("# AI4Sci Discovery Layers (LLM)")
    lines.append("")
    lines.append(f"- Generated: {data.get('generatedAt')}")
    lines.append(f"- Provider: {data.get('provider')} / {data.get('model')}")
    lines.append(f"- Prompt: {data.get('promptVersion')}")
    lines.append("")

    for did, entry in sorted(nodes.items(), key=lambda kv: kv[0]):
        layers = (entry.get("layers") or {}) if isinstance(entry, dict) else {}
        conf = entry.get("confidence")
        total_db = ((entry.get("stats") or {}).get("dbTotalPapers")) if isinstance(entry, dict) else None
        lines.append(f"## {domain_name(did)} ({did})")
        lines.append("")
        lines.append(f"- Confidence: {conf}")
        if total_db is not None:
            lines.append(f"- DB papers: {total_db}")
        lines.append(
            f"- Layers: phenomena={round(clamp01(layers.get('phenomena'))*100)}% | empirical={round(clamp01(layers.get('empirical'))*100)}% | theory={round(clamp01(layers.get('theory'))*100)}% | principles={round(clamp01(layers.get('principles'))*100)}%"
        )
        note = entry.get("note")
        if isinstance(note, str) and note.strip():
            lines.append(f"- Note: {note.strip()}")
        lines.append("")

        evidence = entry.get("evidence") or {}
        for k in LAYER_KEYS:
            items = evidence.get(k) if isinstance(evidence, dict) else None
            if not items:
                continue
            k_label = {
                "phenomena": "Phenomena 新现象",
                "empirical": "Empirical 新经验定律",
                "theory": "Theory 新理论",
                "principles": "Principles 新原理",
            }[k]
            lines.append(f"### {k_label}")
            for i, it in enumerate(items[:5], start=1):
                title = norm_space(str(it.get("title") or "")).strip()
                url = str(it.get("url") or "").strip()
                score = it.get("score")
                year = it.get("year")
                cited = it.get("citedBy")
                meta: list[str] = []
                if year:
                    meta.append(str(year))
                if cited is not None:
                    meta.append(f"cited_by={cited}")
                if score is not None:
                    meta.append(f"layer_score={score}")
                m = f" ({', '.join(meta)})" if meta else ""
                if title and url:
                    lines.append(f"{i}. [{title}]({url}){m}")
                elif title:
                    lines.append(f"{i}. {title}{m}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Judge AI4Sci discovery layers (phenomena/empirical/theory/principles) via LLM.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--out", type=Path, default=OUT_JSON, help="Output JSON path (default: web/data/discovery_layers.json)")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown path (default: web/data/discovery_layers.md)")
    ap.add_argument(
        "--provider",
        type=str,
        default="deepseek",
        choices=["openai", "gemini", "deepseek", "grok"],
        help="LLM provider (default: deepseek).",
    )
    ap.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override provider model (e.g. gemini-3-flash). If set, writes to the corresponding *_MODEL env var for this run.",
    )
    ap.add_argument("--domains", type=str, default=None, help="Comma-separated leaf domain ids (optional).")
    ap.add_argument(
        "--since-days",
        type=int,
        default=0,
        help="Only sample papers within the last N days (based on publication_date/year). 0 = no window filter.",
    )
    ap.add_argument(
        "--exclude-macros",
        type=str,
        default="methods,formal",
        help="Exclude top-level macro ids (comma-separated). Default: methods,formal.",
    )
    ap.add_argument(
        "--include-macros",
        type=str,
        default=None,
        help="Only include these top-level macro ids (comma-separated). Overrides --exclude-macros.",
    )
    ap.add_argument("--papers", type=int, default=12, help="Max papers per domain in prompt (default: 12).")
    ap.add_argument(
        "--order-by",
        type=str,
        default="ai_recent",
        choices=["ai_recent", "id"],
        help="Domain processing order (default: ai_recent).",
    )
    ap.add_argument(
        "--max-domains",
        type=int,
        default=0,
        help="Process at most N domains (after filtering). 0 = all.",
    )
    ap.add_argument(
        "--only-missing",
        action="store_true",
        help="Only judge domains not yet present in output (or missing layers).",
    )
    ap.add_argument(
        "--flush-each",
        action="store_true",
        help="Write output JSON after each domain so you can interrupt safely.",
    )
    ap.add_argument("--sleep", type=float, default=0.8, help="Sleep seconds between LLM calls (default: 0.8).")
    ap.add_argument("--dry-run", action="store_true", help="Do not write output; print parsed JSON per domain.")
    args = ap.parse_args()

    if not BASE_JSON.exists():
        raise SystemExit(f"Base data not found: {BASE_JSON}")
    base = load_json(BASE_JSON)

    load_dotenv_file(ROOT / ".env")
    load_dotenv_file(ROOT / ".env.local")

    # Optional model override for this run.
    if args.model:
        if args.provider == "gemini":
            os.environ["GEMINI_MODEL"] = args.model
        elif args.provider == "openai":
            os.environ["OPENAI_MODEL"] = args.model
        elif args.provider == "deepseek":
            os.environ["DEEPSEEK_MODEL"] = args.model
        elif args.provider == "grok":
            os.environ["GROK_MODEL"] = args.model

    # This task needs enough output budget for per-paper JSON; ensure a sane minimum.
    try:
        cur_max = int(os.getenv("LLM_MAX_OUTPUT_TOKENS") or "0")
    except Exception:
        cur_max = 0
    if cur_max < 4000:
        os.environ["LLM_MAX_OUTPUT_TOKENS"] = "4000"

    cfg, client = load_llm_from_env(provider=args.provider)
    con = connect(args.db)

    domains = parse_leaf_domains(base)

    include_macros = None
    if args.include_macros:
        include_macros = {s.strip() for s in args.include_macros.split(",") if s.strip()}
    exclude_macros = {s.strip() for s in (args.exclude_macros or "").split(",") if s.strip()}
    if include_macros is not None:
        domains = [d for d in domains if d.macro_id in include_macros]
    elif exclude_macros:
        domains = [d for d in domains if d.macro_id not in exclude_macros]

    if args.domains:
        allow = {d.strip() for d in args.domains.split(",") if d.strip()}
        domains = [d for d in domains if d.id in allow]
    if not domains:
        raise SystemExit("No domains selected.")

    existing = load_json(args.out) if args.out.exists() else {}
    next_data: dict[str, Any] = {
        "version": existing.get("version") or "0.1",
        "generatedAt": iso_now(),
        "updatedAt": iso_now(),
        "provider": cfg.provider,
        "model": cfg.model,
        "promptVersion": PROMPT_VERSION,
        "window": {
            "sinceDays": int(args.since_days or 0),
            "sinceDate": (date.today() - timedelta(days=int(args.since_days))).isoformat()
            if int(args.since_days or 0) > 0
            else None,
        },
        "nodes": dict(existing.get("nodes") or {}),
    }

    since = date.today() - timedelta(days=int(args.since_days)) if int(args.since_days or 0) > 0 else None

    # Ordering/selection helpers.
    if args.only_missing:
        prev_nodes = next_data.get("nodes") or {}
        domains = [
            d
            for d in domains
            if not (
                isinstance(prev_nodes.get(d.id), dict)
                and isinstance((prev_nodes.get(d.id) or {}).get("layers"), dict)
                and (prev_nodes.get(d.id) or {}).get("layers")
            )
        ]

    if args.order_by == "ai_recent":
        domains = sorted(domains, key=lambda d: (-d.ai_recent, d.id))
    else:
        domains = sorted(domains, key=lambda d: d.id)

    if int(args.max_domains or 0) > 0:
        domains = domains[: int(args.max_domains)]

    for i, domain in enumerate(domains, start=1):
        total_in_db = query_domain_total(con, domain.id)
        if total_in_db <= 0:
            print(f"[skip] {domain.id} has no papers in DB")
            continue

        top_cited = query_top_papers(
            con,
            domain_id=domain.id,
            limit=max(4, args.papers // 2),
            order_by="cited",
            since=since,
        )
        recent = query_top_papers(
            con,
            domain_id=domain.id,
            limit=max(4, args.papers // 2),
            order_by="recent",
            since=since,
        )

        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for p in top_cited + recent:
            pid = p.get("openalex_id")
            if not isinstance(pid, str) or not pid:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            merged.append(p)
            if len(merged) >= args.papers:
                break

        prompt = build_prompt(domain, total_in_db=total_in_db, papers=merged)
        try:
            text = client.generate_text(
                prompt=prompt,
                system="你是严谨的科学计量分析助手。输出必须是严格 JSON。",
            )
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            (CACHE_DIR / f"discovery_layers_last_{domain.id}.txt").write_text(text, "utf-8")
            try:
                parsed = extract_json(text)
            except Exception:
                parsed = repair_json(client, text)
            conf = clamp01(parsed.get("confidence"))
            note = parsed.get("note")
            note_str = note.strip() if isinstance(note, str) else ""
            judged = parsed.get("papers") or []
            if not isinstance(judged, list):
                judged = []

            sample_ids = {str(p.get("openalex_id")) for p in merged if p.get("openalex_id")}
            discovery_used = 0
            for it in judged:
                if not isinstance(it, dict):
                    continue
                pid = it.get("id")
                if isinstance(pid, str) and pid in sample_ids and bool(it.get("isDiscovery")):
                    discovery_used += 1

            layers, evidence, agg_conf = aggregate_layers(merged, judged)
            node_obj: dict[str, Any] = {
                "layers": {k: round(layers[k], 4) for k in LAYER_KEYS},
                "confidence": round(max(conf, agg_conf), 4),
                "llm": {
                    "provider": cfg.provider,
                    "model": cfg.model,
                    "promptVersion": PROMPT_VERSION,
                },
                "note": note_str or None,
                "stats": {
                    "dbTotalPapers": int(total_in_db),
                    "sampledPapers": int(len(merged)),
                    "discoveryPapers": int(discovery_used),
                },
                "evidence": evidence,
                "updatedAt": iso_now(),
            }
            # Avoid writing null note if absent (keep file cleaner)
            if not node_obj.get("note"):
                node_obj.pop("note", None)

            next_data["nodes"][domain.id] = node_obj

            if args.dry_run:
                print(json.dumps({domain.id: node_obj}, ensure_ascii=False, indent=2))
            else:
                print(f"[ok] {i}/{len(domains)} {domain.id} ({domain.name}) layers updated")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {domain.id} LLM failed: {e}. Keeping existing/empty.")

        if args.flush_each and not args.dry_run:
            next_data["updatedAt"] = iso_now()
            save_json(args.out, next_data)

        time.sleep(max(0.0, float(args.sleep)))

    con.close()

    if not args.dry_run:
        save_json(args.out, next_data)
        if args.out_md:
            save_text(args.out_md, build_markdown(next_data, base))
        print(f"[done] wrote {args.out}" + (f" and {args.out_md}" if args.out_md else ""))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
