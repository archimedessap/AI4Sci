#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from llm_clients import LLMError, load_llm_from_env
from paper_db import connect

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "papers.sqlite"
BASE_JSON = ROOT / "web" / "data" / "base.json"
AUTO_OVERRIDES_JSON = ROOT / "web" / "data" / "auto_overrides.json"


DimensionKey = Literal["data", "model", "predict", "experiment", "explain"]
DIM_KEYS: list[DimensionKey] = ["data", "model", "predict", "experiment", "explain"]


@dataclass(frozen=True)
class Domain:
    id: str
    name: str


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


def parse_leaf_domains(base: dict[str, Any]) -> list[Domain]:
    nodes: dict[str, Any] = base.get("nodes") or {}
    root_id = base.get("rootId")
    children_by_id: dict[str, list[str]] = {nid: [] for nid in nodes.keys()}
    for nid, node in nodes.items():
        pid = node.get("parentId")
        if pid and pid in children_by_id:
            children_by_id[pid].append(nid)

    leaves: list[Domain] = []
    for nid, node in nodes.items():
        if nid == root_id:
            continue
        if children_by_id.get(nid):
            continue
        name = node.get("name") or nid
        if not isinstance(name, str) or not name.strip():
            name = nid
        leaves.append(Domain(id=nid, name=name.strip()))
    leaves.sort(key=lambda d: d.id)
    return leaves


def get_baseline_scores(base: dict[str, Any], domain_id: str) -> dict[DimensionKey, float]:
    node = (base.get("nodes") or {}).get(domain_id) or {}
    dims = node.get("dimensions") or {}
    out: dict[DimensionKey, float] = {}
    for k in DIM_KEYS:
        v = ((dims.get(k) or {}).get("score")) if isinstance(dims, dict) else None
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        out[k] = max(0.0, min(100.0, fv))
    return out


def query_domain_stats(con: sqlite3.Connection, domain_id: str) -> dict[str, int]:
    cur_year = datetime.now(tz=UTC).year
    row = con.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN p.publication_year = ? THEN 1 ELSE 0 END) AS y0,
          SUM(CASE WHEN p.publication_year = ? THEN 1 ELSE 0 END) AS y1
        FROM paper_domains d
        JOIN papers p ON p.openalex_id = d.openalex_id
        WHERE d.domain_id = ?;
        """,
        (cur_year, cur_year - 1, domain_id),
    ).fetchone()
    if not row:
        return {"total": 0, "y0": 0, "y1": 0}
    return {"total": int(row["total"] or 0), "y0": int(row["y0"] or 0), "y1": int(row["y1"] or 0)}


def query_top_papers(
    con: sqlite3.Connection,
    *,
    domain_id: str,
    limit: int,
    order_by: str,
) -> list[dict[str, Any]]:
    allowed = {
        "cited": "COALESCE(p.cited_by_count, 0) DESC, COALESCE(p.publication_year, 0) DESC",
        "recent": "COALESCE(p.publication_date, '') DESC, COALESCE(p.publication_year, 0) DESC",
    }
    clause = allowed.get(order_by)
    if not clause:
        raise ValueError(f"Unsupported order_by: {order_by}")
    rows = con.execute(
        f"""
        SELECT
          p.openalex_id, p.title, p.abstract, p.publication_year, p.publication_date,
          p.cited_by_count, p.primary_url, p.source
        FROM paper_domains d
        JOIN papers p ON p.openalex_id = d.openalex_id
        WHERE d.domain_id = ?
        ORDER BY {clause}
        LIMIT ?;
        """,
        (domain_id, limit),
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
                "primary_url": r["primary_url"],
                "source": r["source"],
            }
        )
    return out


def truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str) -> dict[str, Any]:
    m = JSON_BLOCK_RE.search(text)
    if m:
        text = m.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        # best-effort: find first {...} block
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def clamp_score(v: Any) -> float:
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


def build_prompt(
    *,
    domain: Domain,
    baseline: dict[DimensionKey, float],
    stats: dict[str, int],
    papers: list[dict[str, Any]],
) -> str:
    paper_lines: list[str] = []
    for i, p in enumerate(papers, start=1):
        title = truncate(str(p.get("title") or ""), 180)
        abs_ = truncate(p.get("abstract"), 700)
        year = p.get("publication_year") or p.get("publication_date") or ""
        cited = p.get("cited_by_count")
        suffix = []
        if year:
            suffix.append(str(year))
        if isinstance(cited, int):
            suffix.append(f"cited_by={cited}")
        paper_lines.append(f"{i}. {title} ({', '.join(suffix)})\n   abstract: {abs_}")

    baseline_lines = "\n".join([f"- {k}: {baseline[k]:.1f}" for k in DIM_KEYS])
    return f"""你是一个“AI for Science 进展评估器”。请基于给定的证据，给出该领域在五个维度的 0-100 分数（尽量接近 baseline，除非证据强烈支持调整）。

领域：{domain.name} (id={domain.id})

五维定义（你要打分的对象是“AI 在该领域中承担该角色的成熟度/渗透度”）：
1) data：数据/基准/测量自动化、数据可用性与可复用性
2) model：AI 作为建模/仿真替代或补充（surrogate、PINN、neural operator 等）
3) predict：预测与控制（forecast/control/RL、跨分布泛化）
4) experiment：实验/合成的闭环自动化（robotic lab、self-driving lab）
5) explain：解释/因果/符号/可检验理论生成（mechanism/causality/theory）

四层“发现深度”（用于你在 note 中解释倾向，但最终输出仍是五维分数）：
外→内：现象(Phenomena) → 经验定律(Empirical laws) → 理论(Theory) → 原理(Principles)。

结构化统计：
- AI4Sci 论文总数（库中）：{stats.get('total', 0)}
- 今年发表数：{stats.get('y0', 0)}
- 去年发表数：{stats.get('y1', 0)}

当前 baseline（来自 OpenAlex 自动信号）：
{baseline_lines}

代表性论文（title + abstract 摘要，可能不完整）：
{chr(10).join(paper_lines) if paper_lines else "(none)"}

输出要求（只输出 JSON，不要额外文字）：
{{
  "dimensions": {{
    "data": 0-100,
    "model": 0-100,
    "predict": 0-100,
    "experiment": 0-100,
    "explain": 0-100
  }},
  "confidence": 0-1,
  "note": "一句话理由（<=200字，说明你为何相对 baseline 调整/不调整，以及与四层发现深度的关系）"
}}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Use an LLM to propose AI4Sci progress scores from the paper library.")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB path (default: data/papers.sqlite)")
    ap.add_argument("--out", type=Path, default=AUTO_OVERRIDES_JSON, help="Write auto overrides JSON (default: web/data/auto_overrides.json)")
    ap.add_argument(
        "--provider",
        type=str,
        default="deepseek",
        choices=["openai", "gemini", "deepseek", "grok"],
        help="LLM provider (default: deepseek).",
    )
    ap.add_argument("--domains", type=str, default=None, help="Comma-separated leaf domain ids (optional).")
    ap.add_argument("--papers", type=int, default=12, help="Max papers per domain in prompt (default: 12).")
    ap.add_argument("--sleep", type=float, default=0.8, help="Sleep seconds between LLM calls (default: 0.8).")
    ap.add_argument("--dry-run", action="store_true", help="Do not write output; print parsed JSON per domain.")
    args = ap.parse_args()

    if not BASE_JSON.exists():
        raise SystemExit(f"Base data not found: {BASE_JSON}")
    base = load_json(BASE_JSON)

    # Optional: load repo-level env files for API keys (do not override existing env).
    load_dotenv_file(ROOT / ".env")
    load_dotenv_file(ROOT / ".env.local")

    domains = parse_leaf_domains(base)
    if args.domains:
        allow = {d.strip() for d in args.domains.split(",") if d.strip()}
        domains = [d for d in domains if d.id in allow]
    if not domains:
        raise SystemExit("No domains selected.")

    cfg, client = load_llm_from_env(provider=args.provider)
    con = connect(args.db)

    existing = load_json(args.out) if args.out.exists() else {}
    next_data: dict[str, Any] = {
        "version": existing.get("version") or "0.1",
        "updatedAt": iso_now(),
        "generatedAt": iso_now(),
        "provider": cfg.provider,
        "model": cfg.model,
        "nodes": dict(existing.get("nodes") or {}),
    }

    for i, domain in enumerate(domains, start=1):
        baseline = get_baseline_scores(base, domain.id)
        stats = query_domain_stats(con, domain.id)
        top_cited = query_top_papers(con, domain_id=domain.id, limit=max(4, args.papers // 2), order_by="cited")
        recent = query_top_papers(con, domain_id=domain.id, limit=max(4, args.papers // 2), order_by="recent")

        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for p in top_cited + recent:
            oid = p.get("openalex_id")
            if not isinstance(oid, str) or not oid:
                continue
            if oid in seen:
                continue
            seen.add(oid)
            merged.append(p)
            if len(merged) >= args.papers:
                break

        prompt = build_prompt(domain=domain, baseline=baseline, stats=stats, papers=merged)
        try:
            text = client.generate_text(
                prompt=prompt,
                system="你是严谨的科学计量分析助手。输出必须是严格 JSON。",
            )
            parsed = extract_json(text)
            dims = parsed.get("dimensions") or {}
            out_dims: dict[DimensionKey, dict[str, Any]] = {}
            conf = clamp01(parsed.get("confidence"))
            note = parsed.get("note")
            note_str = note.strip() if isinstance(note, str) else ""

            for k in DIM_KEYS:
                payload: dict[str, Any] = {
                    "score": clamp_score(dims.get(k, baseline[k])),
                    "confidence": conf,
                }
                if note_str:
                    payload["note"] = note_str
                out_dims[k] = payload

            next_data["nodes"][domain.id] = {
                "dimensions": out_dims,
            }

            if args.dry_run:
                print(json.dumps({domain.id: next_data["nodes"][domain.id]}, ensure_ascii=False, indent=2))
            else:
                print(f"[ok] {i}/{len(domains)} {domain.id} ({domain.name}) updated")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {domain.id} LLM failed: {e}. Keeping existing/empty.")
        time.sleep(max(0.0, float(args.sleep)))

    con.close()

    if not args.dry_run:
        save_json(args.out, next_data)
        print(f"[done] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
