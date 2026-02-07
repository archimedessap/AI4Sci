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

from llm_clients import load_llm_from_env
from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
OUT_JSON = ROOT / "web" / "data" / "formal_layers.json"
OUT_MD = ROOT / "web" / "data" / "formal_layers.md"
CACHE_DIR = ROOT / ".cache"

PROMPT_VERSION = "formal_layers.v1"

LayerKey = Literal["instances", "conjectures", "proofs", "foundations"]
LAYER_KEYS: list[LayerKey] = ["instances", "conjectures", "proofs", "foundations"]


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    macro_id: str


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
        leaves.append(Domain(id=nid, name=name.strip(), macro_id=macro_of(nid)))
    leaves.sort(key=lambda d: d.id)
    return leaves


def query_domain_total(con: sqlite3.Connection, domain_id: str) -> int:
    row = con.execute(
        "SELECT COUNT(*) AS total FROM paper_domains d WHERE d.domain_id = ?;",
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
        abs_ = truncate(p.get("abstract"), 650)
        year = p.get("publication_year") or p.get("publication_date") or ""
        cited = p.get("cited_by_count")
        suffix = []
        if year:
            suffix.append(str(year))
        if isinstance(cited, int):
            suffix.append(f"cited_by={cited}")
        paper_lines.append(f"{i}. id={openalex_id} | {title} ({', '.join(suffix)})\n   abstract: {abs_}")

    return f"""你是一个“Formal Sciences 进展分层评估器”。给定一个形式科学领域里若干 AI×领域（AI4Sci）论文的标题+摘要，请判断它们是否对形式知识/形式推理产生实质贡献，并把贡献深度映射到四层（可同时贡献多个层级，0..1）。

领域：{domain.name} (id={domain.id})
本地库中该领域论文总数（AI4Sci）：{total_in_db}

四层定义（外→内）：
1) instances（实例求解）：AI 主要用于求解/计算/搜索/构造反例/生成样本，解决具体实例或具体定理的特定情形，但不一定产生可复用的命题或证明方法。
2) conjectures（猜想/命题）：AI 帮助发现新的猜想、模式、命题、经验规律（数学意义上的模式），或提出可复用的启发式策略/推理模板，但未给出完整严谨证明。
3) proofs（证明/验证）：AI 帮助生成证明（或证明草图）、形式化证明、自动定理证明成功、或用形式系统完成可核验的验证（不仅是“答案正确”，而是“证明可检查”）。
4) foundations（理论/基础）：AI 帮助提出新的理论框架/形式系统/统一多个结果的结构、元定理/公理化/可迁移证明策略等更“基础”的贡献。

评分规则：
- layerScores 每项 0..1，表示该论文对该层贡献强度；不要求单调、不要求和为 1。
- 如果论文主要只是“应用数学/统计/优化作为工具”或“模型工程/性能”，但没有对形式知识或形式推理能力的实质贡献，则 isDiscovery=false 且 layerScores 全 0。
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
        "instances": 0-1,
        "conjectures": 0-1,
        "proofs": 0-1,
        "foundations": 0-1
      }},
      "confidence": 0-1
    }}
  ]
}}
"""


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


def repair_json(client: Any, bad_text: str) -> dict[str, Any]:
    prompt = f"""下面是一段模型输出，但不是合法 JSON。请在不改变语义的前提下修复为严格 JSON（UTF-8，双引号，true/false/null），只输出 JSON，不要 Markdown：

{bad_text}
"""
    fixed = client.generate_text(prompt=prompt, system="你是 JSON 修复器。只输出严格 JSON。")
    return extract_json(fixed)


def aggregate_layers(
    papers: list[dict[str, Any]],
    judged: list[dict[str, Any]],
) -> tuple[dict[LayerKey, float], dict[LayerKey, list[dict[str, Any]]], float, int]:
    by_id = {str(p["openalex_id"]): p for p in papers if p.get("openalex_id")}
    now_year = datetime.now(tz=UTC).year

    sum_w = 0.0
    sum_conf_w = 0.0
    sum_conf = 0.0
    layer_sums: dict[LayerKey, float] = {k: 0.0 for k in LAYER_KEYS}
    contribs: dict[LayerKey, list[tuple[float, dict[str, Any]]]] = {k: [] for k in LAYER_KEYS}
    discovery_count = 0

    for item in judged:
        pid = item.get("id")
        if not isinstance(pid, str) or pid not in by_id:
            continue
        paper = by_id[pid]
        is_discovery = bool(item.get("isDiscovery"))
        scores = item.get("layerScores") or {}
        pconf = clamp01(item.get("confidence"))
        if not is_discovery:
            continue
        discovery_count += 1
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
        evidence[k] = [it for _, it in items]

    overall_conf = (sum_conf / sum_conf_w) if sum_conf_w > 0 else 0.0
    overall_conf = max(0.0, min(1.0, overall_conf))
    return layers, evidence, overall_conf, discovery_count


def build_markdown(data: dict[str, Any], base: dict[str, Any]) -> str:
    nodes = data.get("nodes") or {}
    domains = (base.get("nodes") or {})

    def domain_name(did: str) -> str:
        n = domains.get(did) or {}
        name = n.get("name")
        return name if isinstance(name, str) and name.strip() else did

    lines: list[str] = []
    lines.append("# Formal Sciences Layers (LLM)")
    lines.append("")
    lines.append(f"- Generated: {data.get('generatedAt')}")
    lines.append(f"- Provider: {data.get('provider')} / {data.get('model')}")
    lines.append(f"- Prompt: {data.get('promptVersion')}")
    win = data.get("window") or {}
    if win.get("sinceDays"):
        lines.append(f"- Window: last {win.get('sinceDays')} days (since {win.get('sinceDate')})")
    lines.append("")

    label = {
        "instances": "Instances 实例求解",
        "conjectures": "Conjectures 猜想/命题",
        "proofs": "Proofs 证明/验证",
        "foundations": "Foundations 理论/基础",
    }

    for did, entry in sorted(nodes.items(), key=lambda kv: kv[0]):
        layers = (entry.get("layers") or {}) if isinstance(entry, dict) else {}
        conf = entry.get("confidence")
        stats = entry.get("stats") or {}
        lines.append(f"## {domain_name(did)} ({did})")
        lines.append("")
        lines.append(f"- Confidence: {conf}")
        if stats.get("dbTotalPapers") is not None:
            lines.append(f"- DB papers: {stats.get('dbTotalPapers')}")
        if stats.get("sampledPapers") is not None:
            lines.append(f"- Sampled papers: {stats.get('sampledPapers')} (discoveries={stats.get('discoveryPapers')})")
        lines.append(
            "- Layers: "
            + " | ".join(
                f"{k}={round(clamp01(layers.get(k)) * 100)}%" for k in LAYER_KEYS
            )
        )
        note = entry.get("note")
        if isinstance(note, str) and note.strip():
            lines.append(f"- Note: {note.strip()}")
        lines.append("")

        ev = entry.get("evidence") or {}
        for k in LAYER_KEYS:
            items = ev.get(k) or []
            if not items:
                continue
            lines.append(f"### {label[k]}")
            for i, it in enumerate(items[:5], start=1):
                title = norm_space(str(it.get("title") or "")).strip()
                url = str(it.get("url") or "").strip()
                meta: list[str] = []
                if it.get("year"):
                    meta.append(str(it.get("year")))
                if it.get("citedBy") is not None:
                    meta.append(f"cited_by={it.get('citedBy')}")
                if it.get("score") is not None:
                    meta.append(f"layer_score={it.get('score')}")
                m = f" ({', '.join(meta)})" if meta else ""
                if title and url:
                    lines.append(f"{i}. [{title}]({url}){m}")
                elif title:
                    lines.append(f"{i}. {title}{m}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Judge formal-science layers (instances/conjectures/proofs/foundations) via LLM.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--out", type=Path, default=OUT_JSON, help="Output JSON path (default: web/data/formal_layers.json)")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown path (default: web/data/formal_layers.md)")
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
    ap.add_argument("--since-days", type=int, default=0, help="Only sample papers within the last N days (0 = no window).")
    ap.add_argument("--papers", type=int, default=16, help="Max papers per domain in prompt (default: 16).")
    ap.add_argument("--sleep", type=float, default=0.8, help="Sleep seconds between LLM calls (default: 0.8).")
    ap.add_argument("--dry-run", action="store_true", help="Do not write output; print parsed JSON per domain.")
    args = ap.parse_args()

    if not BASE_JSON.exists():
        raise SystemExit(f"Base data not found: {BASE_JSON}")
    base = load_json(BASE_JSON)

    load_dotenv_file(ROOT / ".env")
    load_dotenv_file(ROOT / ".env.local")

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

    domains = [d for d in parse_leaf_domains(base) if d.macro_id == "formal"]
    if args.domains:
        allow = {d.strip() for d in args.domains.split(",") if d.strip()}
        domains = [d for d in domains if d.id in allow]
    if not domains:
        raise SystemExit("No formal domains selected.")

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
            "sinceDate": (datetime.now(tz=UTC).date() - timedelta(days=int(args.since_days))).isoformat()
            if int(args.since_days or 0) > 0
            else None,
        },
        "nodes": dict(existing.get("nodes") or {}),
    }

    since = datetime.now(tz=UTC).date() - timedelta(days=int(args.since_days)) if int(args.since_days or 0) > 0 else None

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
            (CACHE_DIR / f"formal_layers_last_{domain.id}.txt").write_text(text, "utf-8")
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

            layers, evidence, overall_conf, discovery_count = aggregate_layers(merged, judged)

            next_data["nodes"][domain.id] = {
                "layers": layers,
                "confidence": round(overall_conf, 4),
                "llm": {
                    "provider": cfg.provider,
                    "model": cfg.model,
                    "promptVersion": PROMPT_VERSION,
                },
                "note": note_str,
                "stats": {
                    "dbTotalPapers": total_in_db,
                    "sampledPapers": len(merged),
                    "discoveryPapers": discovery_count,
                },
                "evidence": evidence,
                "updatedAt": iso_now(),
            }

            if args.dry_run:
                print(json.dumps({domain.id: next_data["nodes"][domain.id]}, ensure_ascii=False, indent=2))
            else:
                print(f"[ok] {i}/{len(domains)} {domain.id} ({domain.name}) layers updated")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {domain.id} LLM failed: {e}. Keeping existing/empty.")
        time.sleep(max(0.0, float(args.sleep)))

    con.close()

    if not args.dry_run:
        save_json(args.out, next_data)
        md = build_markdown(next_data, base)
        save_text(args.out_md, md)
        print(f"[done] wrote {args.out} and {args.out_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
