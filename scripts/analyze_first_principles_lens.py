#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "data"

BASE_PATH = DATA_DIR / "base.json"
AUTO_OVERRIDES_PATH = DATA_DIR / "auto_overrides.json"
OVERRIDES_PATH = DATA_DIR / "overrides.json"
DISCOVERY_LAYERS_PATH = DATA_DIR / "discovery_layers.json"
FORMAL_LAYERS_PATH = DATA_DIR / "formal_layers.json"
EXTRA_METRICS_PATH = DATA_DIR / "domain_extra_metrics.json"
PAPERS_CATALOG_PATH = DATA_DIR / "papers_catalog.json"
PROGRESS_HISTORY_PATH = DATA_DIR / "progress_history.json"
DAILY_UPDATES_PATH = DATA_DIR / "daily_updates.json"
INCREMENTAL_SOURCES_PATH = DATA_DIR / "incremental_sources.json"

OUT_JSON = DATA_DIR / "first_principles_lens.json"
OUT_MD = DATA_DIR / "first_principles_lens.md"

DIM_KEYS = ["data", "model", "predict", "experiment", "explain"]
AXIS_KEYS = ["observability", "compressibility", "causalGrasp", "intervention", "autonomyReadiness"]

AXIS_DEFINITIONS = {
    "observability": "科学对象是否被稳定观测、结构化记录并沉淀为可计算证据。",
    "compressibility": "AI 是否已经学会把领域现象压缩成稳定、可泛化的表征与预测器。",
    "causalGrasp": "系统是否从相关性推进到机制、理论与统一解释。",
    "intervention": "是否具备反事实与可操作的干预/控制能力，而不只是被动拟合。",
    "autonomyReadiness": "是否接近把观测、建模、实验与更新理论串成可复用闭环。",
}


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


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except Exception:
        return default
    if not math.isfinite(num):
        return default
    return num


def clamp01(value: Any) -> float:
    return max(0.0, min(1.0, safe_float(value)))


def clamp100(value: Any) -> float:
    return max(0.0, min(100.0, safe_float(value)))


def parse_date_ymd(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def merge_dimension(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"score": 0.0}
    if isinstance(base, dict):
        out.update(base)
    if isinstance(override, dict):
        out.update(override)
    if "score" not in out or not math.isfinite(safe_float(out.get("score"), math.nan)):
        out["score"] = 0.0
    else:
        out["score"] = safe_float(out.get("score"))
    return out


def merge_node(base_node: dict[str, Any], override_node: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {**base_node}
    for key in ("name", "description", "order"):
        if key in override_node:
            out[key] = override_node[key]

    if isinstance(override_node.get("overall"), dict):
        base_overall = base_node.get("overall")
        out["overall"] = {**(base_overall if isinstance(base_overall, dict) else {}), **override_node["overall"]}

    if isinstance(override_node.get("dimensions"), dict):
        base_dims = base_node.get("dimensions")
        next_dims: dict[str, Any] = {**(base_dims if isinstance(base_dims, dict) else {})}
        for dim_key, override_dim in override_node["dimensions"].items():
            if dim_key not in DIM_KEYS or not isinstance(override_dim, dict):
                continue
            base_dim = next_dims.get(dim_key)
            next_dims[dim_key] = merge_dimension(base_dim if isinstance(base_dim, dict) else None, override_dim)
        out["dimensions"] = next_dims

    return out


def apply_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    base_nodes = base.get("nodes")
    override_nodes = overrides.get("nodes")
    if not isinstance(base_nodes, dict) or not isinstance(override_nodes, dict):
        return base

    next_nodes: dict[str, Any] = {**base_nodes}
    for node_id, override_node in override_nodes.items():
        if node_id not in next_nodes:
            continue
        base_node = next_nodes.get(node_id)
        if not isinstance(base_node, dict) or not isinstance(override_node, dict):
            continue
        next_nodes[node_id] = merge_node(base_node, override_node)

    return {**base, "nodes": next_nodes}


def build_children(nodes: dict[str, Any]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {node_id: [] for node_id in nodes.keys()}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        parent_id = node.get("parentId")
        if isinstance(parent_id, str) and parent_id in children:
            children[parent_id].append(node_id)
    return children


def macro_of(node_id: str, *, nodes: dict[str, Any], root_id: str) -> str:
    visited: set[str] = set()
    cur = node_id
    while True:
        if cur in visited:
            return node_id
        visited.add(cur)
        node = nodes.get(cur)
        if not isinstance(node, dict):
            return node_id
        parent_id = node.get("parentId")
        if not isinstance(parent_id, str) or not parent_id:
            return node_id
        if parent_id == root_id:
            return cur
        cur = parent_id


def score_from_layers(node_id: str, *, discovery_nodes: dict[str, Any], formal_nodes: dict[str, Any]) -> dict[str, float]:
    formal = formal_nodes.get(node_id)
    if isinstance(formal, dict):
        layers = formal.get("layers")
        if isinstance(layers, dict):
            return {
                "phenomena": 100.0 * clamp01(layers.get("instances")),
                "empirical": 100.0 * clamp01(layers.get("conjectures")),
                "theory": 100.0 * clamp01(layers.get("proofs")),
                "principles": 100.0 * clamp01(layers.get("foundations")),
            }

    science = discovery_nodes.get(node_id)
    if isinstance(science, dict):
        layers = science.get("layers")
        if isinstance(layers, dict):
            return {
                "phenomena": 100.0 * clamp01(layers.get("phenomena")),
                "empirical": 100.0 * clamp01(layers.get("empirical")),
                "theory": 100.0 * clamp01(layers.get("theory")),
                "principles": 100.0 * clamp01(layers.get("principles")),
            }

    return {"phenomena": 0.0, "empirical": 0.0, "theory": 0.0, "principles": 0.0}


def adoption_score(ai_recent: float, max_ai_recent: float) -> float:
    if max_ai_recent <= 0:
        return 0.0
    return 100.0 * (math.log1p(max(0.0, ai_recent)) / math.log1p(max_ai_recent))


def closure_readiness_from_axes(values: list[float]) -> float:
    if not values:
        return 0.0
    low = min(values)
    avg = sum(values) / len(values)
    return clamp100(0.7 * low + 0.3 * avg)


def choose_profile(axes: dict[str, float], gaps: dict[str, float], *, momentum_7d: float, new_papers_7d: int) -> dict[str, str]:
    closure = axes["closureReadiness"]
    instrumentalism = gaps["instrumentalism"]
    theory_action = gaps["theoryAction"]
    observation_gap = gaps["observationCompression"]

    if closure >= 50 and axes["intervention"] >= 45 and axes["autonomyReadiness"] >= 45:
        return {
            "key": "closure_frontier",
            "label": "闭环前沿",
            "summary": "观测、解释、干预与自治已经开始耦合，接近可复用的科学闭环。",
        }
    if instrumentalism >= 12 and axes["compressibility"] >= 40:
        return {
            "key": "instrumentalist_surge",
            "label": "工具主义跃迁",
            "summary": "预测/压缩能力增长快于机制理解，当前更像高效仪器而不是成熟理论。",
        }
    if observation_gap >= 14 and axes["observability"] >= 40:
        return {
            "key": "observation_heavy",
            "label": "观测富集",
            "summary": "数据与工具基础在变强，但尚未充分压缩成稳定可迁移的模型结构。",
        }
    if theory_action >= 10 and axes["causalGrasp"] >= 35:
        return {
            "key": "theory_seeking",
            "label": "理论先行",
            "summary": "解释/理论已有积累，但转化为干预与自治流程仍偏慢。",
        }
    if momentum_7d >= 1.0 or new_papers_7d >= 4:
        return {
            "key": "active_frontier",
            "label": "活跃边界",
            "summary": "近期内容更新密集，值得高频跟踪其是否从工程推进跨入机制突破。",
        }
    return {
        "key": "balanced_exploration",
        "label": "平衡探索",
        "summary": "目前进展较均衡，但尚未形成决定性的理论压缩或闭环优势。",
    }


def ranking_entry(domain: dict[str, Any], field: str, label: str, value: float) -> dict[str, Any]:
    return {
        "id": domain["id"],
        "name": domain["name"],
        "macroId": domain["macroId"],
        "macroName": domain["macroName"],
        "profileLabel": domain["profile"]["label"],
        "field": field,
        "label": label,
        "value": round(value, 2),
        "closureReadiness": round(safe_float(domain.get("closureReadiness")), 2),
        "momentum7d": round(safe_float(domain.get("signals", {}).get("momentum7d")), 2),
        "newPapers7d": int(safe_float(domain.get("signals", {}).get("newPapers7d"), 0)),
    }


def dataset_freshness(name: str, path: Path, *, timestamp: datetime | None, now: datetime) -> dict[str, Any]:
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) if path.exists() else None
    ts = timestamp or mtime
    age_hours = (now - ts).total_seconds() / 3600 if ts is not None else None
    return {
        "name": name,
        "path": str(path.relative_to(ROOT)),
        "timestamp": ts.isoformat() if ts else None,
        "ageHours": round(age_hours, 2) if age_hours is not None else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a first-principles AI4Sci lens and daily monitoring summary from existing data artifacts."
    )
    ap.add_argument("--out-json", type=Path, default=OUT_JSON, help="Output JSON path.")
    ap.add_argument("--out-md", type=Path, default=OUT_MD, help="Output Markdown path.")
    ap.add_argument(
        "--paper-window-days",
        type=int,
        default=7,
        help="Recent papers window used for watchboard signals (default: 7).",
    )
    ap.add_argument(
        "--update-window-days",
        type=int,
        default=7,
        help="Recent daily updates window used for trend synthesis (default: 7).",
    )
    ap.add_argument(
        "--history-window-days",
        type=int,
        default=7,
        help="Snapshot delta window for momentum estimates (default: 7).",
    )
    ap.add_argument("--top-k", type=int, default=8, help="Number of entries to keep in each ranking.")
    args = ap.parse_args()

    now = datetime.now(tz=UTC)
    today = now.date()

    base = read_json(BASE_PATH, {})
    if not isinstance(base, dict) or not isinstance(base.get("nodes"), dict):
        raise SystemExit(f"Invalid or missing base.json: {BASE_PATH}")

    auto_overrides = read_json(
        AUTO_OVERRIDES_PATH,
        {"version": "0.1", "updatedAt": datetime.fromtimestamp(0, tz=UTC).isoformat(), "nodes": {}},
    )
    overrides = read_json(
        OVERRIDES_PATH,
        {"version": "0.1", "updatedAt": datetime.fromtimestamp(0, tz=UTC).isoformat(), "nodes": {}},
    )
    discovery_layers = read_json(DISCOVERY_LAYERS_PATH, {})
    formal_layers = read_json(FORMAL_LAYERS_PATH, {})
    extra_metrics = read_json(EXTRA_METRICS_PATH, {})
    papers_catalog = read_json(PAPERS_CATALOG_PATH, {})
    progress_history = read_json(PROGRESS_HISTORY_PATH, {})
    daily_updates = read_json(DAILY_UPDATES_PATH, {})
    incremental_sources = read_json(INCREMENTAL_SOURCES_PATH, {})

    merged = apply_overrides(apply_overrides(base, auto_overrides), overrides)
    nodes = merged.get("nodes")
    if not isinstance(nodes, dict):
        raise SystemExit("Invalid merged data: expected nodes object.")

    root_id = merged.get("rootId") if isinstance(merged.get("rootId"), str) else "ai4sci"
    children = build_children(nodes)
    discovery_nodes = discovery_layers.get("nodes") if isinstance(discovery_layers.get("nodes"), dict) else {}
    formal_nodes = formal_layers.get("nodes") if isinstance(formal_layers.get("nodes"), dict) else {}
    extra_nodes = extra_metrics.get("nodes") if isinstance(extra_metrics.get("nodes"), dict) else {}

    leaf_ids: list[str] = []
    for node_id, node in nodes.items():
        if node_id == root_id or children.get(node_id):
            continue
        if not isinstance(node, dict):
            continue
        if macro_of(node_id, nodes=nodes, root_id=root_id) == "methods":
            continue
        leaf_ids.append(node_id)

    leaf_ids.sort()

    ai_recent_values: list[float] = []
    for node_id in leaf_ids:
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        dims = node.get("dimensions")
        model_dim = dims.get("model") if isinstance(dims, dict) else None
        signals = model_dim.get("signals") if isinstance(model_dim, dict) else None
        ai_recent_values.append(max(0.0, safe_float(signals.get("ai_recent") if isinstance(signals, dict) else 0)))
    max_ai_recent = max(ai_recent_values) if ai_recent_values else 0.0

    papers = papers_catalog.get("papers") if isinstance(papers_catalog.get("papers"), list) else []
    domain_paper_counts_7d: dict[str, int] = {}
    recent_counts = {"last1d": 0, "last3d": 0, "last7d": 0}
    paper_window_start = today - timedelta(days=max(0, int(args.paper_window_days) - 1))
    latest_publication_date: date | None = None
    for raw in papers:
        if not isinstance(raw, dict):
            continue
        pub_date = parse_date_ymd(raw.get("publicationDate"))
        if pub_date is None or pub_date > today:
            continue
        if latest_publication_date is None or pub_date > latest_publication_date:
            latest_publication_date = pub_date
        delta_days = (today - pub_date).days
        if delta_days <= 0:
            recent_counts["last1d"] += 1
        if delta_days <= 2:
            recent_counts["last3d"] += 1
        if delta_days <= 6:
            recent_counts["last7d"] += 1
        if pub_date < paper_window_start:
            continue
        domains = raw.get("domains")
        if not isinstance(domains, list):
            continue
        for domain_id in domains:
            if not isinstance(domain_id, str) or not domain_id.strip():
                continue
            domain_paper_counts_7d[domain_id.strip()] = domain_paper_counts_7d.get(domain_id.strip(), 0) + 1

    history_leaves = progress_history.get("leaves") if isinstance(progress_history.get("leaves"), list) else []
    history_snapshots = progress_history.get("snapshots") if isinstance(progress_history.get("snapshots"), list) else []
    history_index_by_id: dict[str, int] = {}
    for idx, leaf in enumerate(history_leaves):
        if isinstance(leaf, dict):
            leaf_id = leaf.get("id")
            if isinstance(leaf_id, str) and leaf_id.strip():
                history_index_by_id[leaf_id.strip()] = idx

    latest_snapshot = history_snapshots[-1] if history_snapshots else None
    baseline_snapshot = None
    if history_snapshots:
        latest_date = parse_date_ymd(latest_snapshot.get("date") if isinstance(latest_snapshot, dict) else None)
        if latest_date is not None:
            cutoff = latest_date - timedelta(days=max(0, int(args.history_window_days)))
            for snap in reversed(history_snapshots):
                snap_date = parse_date_ymd(snap.get("date") if isinstance(snap, dict) else None)
                if snap_date is None:
                    continue
                if snap_date <= cutoff:
                    baseline_snapshot = snap
                    break
        if baseline_snapshot is None:
            baseline_snapshot = history_snapshots[0]

    update_entries = daily_updates.get("entries") if isinstance(daily_updates.get("entries"), list) else []
    update_window_start = today - timedelta(days=max(0, int(args.update_window_days) - 1))
    update_mix_raw = {dim: 0.0 for dim in DIM_KEYS}
    update_mix_count = 0
    latest_updates: list[dict[str, Any]] = []
    for entry in sorted(update_entries, key=lambda it: str(it.get("date") or ""), reverse=True):
        if not isinstance(entry, dict):
            continue
        entry_date = parse_date_ymd(entry.get("date"))
        if entry_date is not None and entry_date >= update_window_start:
            dims = entry.get("dimensions")
            if isinstance(dims, dict):
                for dim in DIM_KEYS:
                    update_mix_raw[dim] += clamp100(dims.get(dim))
                update_mix_count += 1
        if len(latest_updates) < 5:
            latest_updates.append(
                {
                    "date": entry.get("date"),
                    "summary": entry.get("summary"),
                    "sourceType": entry.get("sourceType") or "manual",
                    "confidence": round(clamp01(entry.get("confidence")), 2),
                }
            )

    if update_mix_count > 0:
        update_mix = {dim: round(update_mix_raw[dim] / update_mix_count, 2) for dim in DIM_KEYS}
    else:
        each = round(100.0 / len(DIM_KEYS), 2)
        update_mix = {dim: each for dim in DIM_KEYS}

    incremental_items = incremental_sources.get("items") if isinstance(incremental_sources.get("items"), list) else []
    incremental_reports = incremental_sources.get("sources") if isinstance(incremental_sources.get("sources"), list) else []
    direct_counts = {"last6h": 0, "last24h": 0, "last72h": 0}
    recent_direct_items: list[dict[str, Any]] = []
    direct_source_errors = 0
    direct_source_summaries: list[dict[str, Any]] = []

    for report in incremental_reports:
        if not isinstance(report, dict):
            continue
        if str(report.get("status") or "").lower() == "error":
            direct_source_errors += 1
        direct_source_summaries.append(
            {
                "id": report.get("id"),
                "name": report.get("name"),
                "type": report.get("type"),
                "status": report.get("status"),
                "newItems": int(safe_float(report.get("newItems"), 0)),
                "includedItems": int(safe_float(report.get("includedItems"), 0)),
                "lastPublishedAt": report.get("lastPublishedAt"),
            }
        )

    for item in incremental_items:
        if not isinstance(item, dict):
            continue
        published_dt = parse_datetime(item.get("publishedAt") or item.get("updatedAt"))
        if published_dt is not None:
            age_h = (now - published_dt).total_seconds() / 3600.0
            if age_h <= 6:
                direct_counts["last6h"] += 1
            if age_h <= 24:
                direct_counts["last24h"] += 1
            if age_h <= 72:
                direct_counts["last72h"] += 1
        if len(recent_direct_items) < 8:
            recent_direct_items.append(
                {
                    "sourceName": item.get("sourceName"),
                    "title": item.get("title"),
                    "publishedAt": item.get("publishedAt"),
                    "isNew": bool(item.get("isNew")),
                    "domains": item.get("domainNames") or [],
                    "url": item.get("url"),
                }
            )

    top_direct_sources = sorted(
        direct_source_summaries,
        key=lambda item: (-int(item.get("newItems") or 0), -int(item.get("includedItems") or 0), str(item.get("name") or "")),
    )[:6]

    domains_out: list[dict[str, Any]] = []
    for node_id in leaf_ids:
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        dims = node.get("dimensions")
        if not isinstance(dims, dict):
            continue
        dim_scores = {dim: clamp100((dims.get(dim) or {}).get("score")) for dim in DIM_KEYS}
        model_dim = dims.get("model") if isinstance(dims.get("model"), dict) else {}
        model_signals = model_dim.get("signals") if isinstance(model_dim.get("signals"), dict) else {}
        ai_recent = max(0.0, safe_float(model_signals.get("ai_recent")))
        confidence = clamp01((node.get("overall") or {}).get("confidence"))
        tooling = 100.0 * clamp01((extra_nodes.get(node_id) or {}).get("tooling"))
        autonomy = 100.0 * clamp01((extra_nodes.get(node_id) or {}).get("autonomy"))
        layers = score_from_layers(node_id, discovery_nodes=discovery_nodes, formal_nodes=formal_nodes)
        adoption = adoption_score(ai_recent, max_ai_recent)

        observability = clamp100(0.55 * dim_scores["data"] + 0.30 * tooling + 0.15 * adoption)
        compressibility = clamp100(0.55 * dim_scores["model"] + 0.25 * dim_scores["predict"] + 0.20 * layers["empirical"])
        causal_grasp = clamp100(0.40 * dim_scores["explain"] + 0.30 * layers["theory"] + 0.30 * layers["principles"])
        intervention = clamp100(0.45 * dim_scores["predict"] + 0.35 * dim_scores["experiment"] + 0.20 * autonomy)
        autonomy_readiness = clamp100(0.45 * dim_scores["experiment"] + 0.35 * autonomy + 0.20 * tooling)

        axes = {
            "observability": round(observability, 2),
            "compressibility": round(compressibility, 2),
            "causalGrasp": round(causal_grasp, 2),
            "intervention": round(intervention, 2),
            "autonomyReadiness": round(autonomy_readiness, 2),
        }
        closure = closure_readiness_from_axes(list(axes.values()))
        axes["closureReadiness"] = round(closure, 2)

        gaps = {
            "instrumentalism": round(compressibility - causal_grasp, 2),
            "theoryAction": round(causal_grasp - intervention, 2),
            "observationCompression": round(observability - compressibility, 2),
        }

        momentum_7d = 0.0
        history_idx = history_index_by_id.get(node_id)
        if history_idx is not None and isinstance(latest_snapshot, dict) and isinstance(baseline_snapshot, dict):
            latest_overall = latest_snapshot.get("overall")
            base_overall = baseline_snapshot.get("overall")
            if isinstance(latest_overall, list) and isinstance(base_overall, list):
                if history_idx < len(latest_overall) and history_idx < len(base_overall):
                    momentum_7d = round(safe_float(latest_overall[history_idx]) - safe_float(base_overall[history_idx]), 2)

        macro_id = macro_of(node_id, nodes=nodes, root_id=root_id)
        macro_node = nodes.get(macro_id)
        macro_name = macro_node.get("name") if isinstance(macro_node, dict) else macro_id
        new_papers_7d = int(domain_paper_counts_7d.get(node_id, 0))

        profile = choose_profile(axes, gaps, momentum_7d=momentum_7d, new_papers_7d=new_papers_7d)

        domains_out.append(
            {
                "id": node_id,
                "name": node.get("name") or node_id,
                "macroId": macro_id,
                "macroName": macro_name if isinstance(macro_name, str) else macro_id,
                "axes": axes,
                "scores": {
                    **{dim: round(dim_scores[dim], 2) for dim in DIM_KEYS},
                    "tooling": round(tooling, 2),
                    "autonomy": round(autonomy, 2),
                    "adoption": round(adoption, 2),
                    "confidence": round(100.0 * confidence, 2),
                },
                "layers": {key: round(value, 2) for key, value in layers.items()},
                "gaps": gaps,
                "closureReadiness": round(closure, 2),
                "profile": profile,
                "signals": {
                    "aiRecent": int(round(ai_recent)),
                    "momentum7d": momentum_7d,
                    "newPapers7d": new_papers_7d,
                },
            }
        )

    domains_out.sort(key=lambda item: (-safe_float(item.get("closureReadiness")), item.get("name", "")))

    top_k = max(1, int(args.top_k))
    rankings = {
        "instrumentalistFrontiers": [
            ranking_entry(d, "instrumentalism", "工具主义差值", safe_float(d["gaps"]["instrumentalism"]))
            for d in sorted(domains_out, key=lambda item: safe_float(item["gaps"]["instrumentalism"]), reverse=True)[:top_k]
        ],
        "closureLeaders": [
            ranking_entry(d, "closureReadiness", "闭环就绪度", safe_float(d["closureReadiness"]))
            for d in sorted(domains_out, key=lambda item: safe_float(item["closureReadiness"]), reverse=True)[:top_k]
        ],
        "mechanismLeaders": [
            ranking_entry(d, "causalGrasp", "机制掌握度", safe_float(d["axes"]["causalGrasp"]))
            for d in sorted(domains_out, key=lambda item: safe_float(item["axes"]["causalGrasp"]), reverse=True)[:top_k]
        ],
        "fastMovers": [
            ranking_entry(d, "momentum7d", "7天动量", safe_float(d["signals"]["momentum7d"]))
            for d in sorted(domains_out, key=lambda item: safe_float(item["signals"]["momentum7d"]), reverse=True)[:top_k]
        ],
        "observationHeavy": [
            ranking_entry(d, "observationCompression", "观测-压缩差值", safe_float(d["gaps"]["observationCompression"]))
            for d in sorted(domains_out, key=lambda item: safe_float(item["gaps"]["observationCompression"]), reverse=True)[:top_k]
        ],
    }

    watchlist: list[dict[str, Any]] = []
    for domain in sorted(
        domains_out,
        key=lambda item: (
            safe_float(item["signals"]["newPapers7d"]) * 3
            + max(0.0, safe_float(item["signals"]["momentum7d"])) * 5
            + max(0.0, safe_float(item["gaps"]["instrumentalism"]))
        ),
        reverse=True,
    ):
        reasons: list[str] = []
        if safe_float(domain["signals"]["newPapers7d"]) >= 4:
            reasons.append(f"近{args.paper_window_days}天新增论文 {int(domain['signals']['newPapers7d'])} 篇")
        if safe_float(domain["signals"]["momentum7d"]) >= 1.0:
            reasons.append(f"整体分数 7 天提升 {safe_float(domain['signals']['momentum7d']):.1f}")
        if safe_float(domain["gaps"]["instrumentalism"]) >= 12:
            reasons.append("预测/压缩增速快于机制理解")
        if safe_float(domain["gaps"]["theoryAction"]) >= 10:
            reasons.append("解释层走在干预层前面")
        if safe_float(domain["axes"]["closureReadiness"]) >= 48:
            reasons.append("已接近闭环前沿")
        if not reasons:
            continue
        watchlist.append(
            {
                "id": domain["id"],
                "name": domain["name"],
                "macroName": domain["macroName"],
                "profileLabel": domain["profile"]["label"],
                "reasons": reasons[:3],
            }
        )
        if len(watchlist) >= top_k:
            break

    closure_leader_macros: dict[str, int] = {}
    for item in rankings["closureLeaders"][: min(5, len(rankings["closureLeaders"]))]:
        macro = str(item.get("macroName") or "")
        if macro:
            closure_leader_macros[macro] = closure_leader_macros.get(macro, 0) + 1
    dominant_macro = ""
    dominant_macro_count = 0
    for macro, count in closure_leader_macros.items():
        if count > dominant_macro_count:
            dominant_macro = macro
            dominant_macro_count = count

    model_data_share = update_mix["data"] + update_mix["model"]
    explain_experiment_share = update_mix["explain"] + update_mix["experiment"]
    diagnoses: list[str] = []
    if model_data_share >= explain_experiment_share + 12:
        diagnoses.append(
            f"近{args.update_window_days}天更新以“观测/压缩”层为主（data+model={model_data_share:.1f}），说明前沿更偏工具与表征扩张，而非机制/闭环跃迁。"
        )
    elif explain_experiment_share >= model_data_share + 12:
        diagnoses.append(
            f"近{args.update_window_days}天更新明显转向“解释/实验”层（explain+experiment={explain_experiment_share:.1f}），表明部分领域正在从会做走向理解与干预。"
        )
    else:
        diagnoses.append(
            f"近{args.update_window_days}天五维更新较均衡（data+model={model_data_share:.1f}，explain+experiment={explain_experiment_share:.1f}），说明工程推进与认识论推进同时存在。"
        )

    fast_movers = rankings["fastMovers"][: min(5, len(rankings["fastMovers"]))]
    if fast_movers:
        fast_gap_mean = sum(
            safe_float(
                next(
                    (
                        d["gaps"]["instrumentalism"]
                        for d in domains_out
                        if d["id"] == item["id"]
                    ),
                    0.0,
                )
            )
            for item in fast_movers
        ) / max(1, len(fast_movers))
        if fast_gap_mean >= 8:
            diagnoses.append("最近动量最高的领域，平均仍存在较明显的“工具主义差值”，说明 AI4Sci 的快进展常先体现在预测/压缩，而不是机制统一。")
        else:
            diagnoses.append("最近动量最高的领域，其解释层并未明显落后于模型层，说明部分前沿正在摆脱纯黑箱增长。")

    if dominant_macro and dominant_macro_count >= 2:
        diagnoses.append(f"闭环就绪度靠前的领域主要集中在 {dominant_macro}，这通常意味着该宏观领域已经同时具备可计算表征、实验反馈和自治工作流。")

    if direct_counts["last24h"] > 0:
        diagnoses.append(
            f"直连增量源在近 24 小时命中 {direct_counts['last24h']} 条 AI4Sci 内容，说明上游刷新已不再完全受 OpenAlex 延迟支配。"
        )
    else:
        diagnoses.append("直连增量源在近 24 小时没有命中新的 AI4Sci 内容，需区分是前沿平静、过滤过严，还是上游 feed 失效。")

    if direct_source_errors > 0:
        diagnoses.append(f"当前有 {direct_source_errors} 个直连源抓取失败，应优先修复这些 feed，否则小时级监控会出现盲区。")

    freshness = [
        dataset_freshness("base", BASE_PATH, timestamp=parse_datetime(base.get("generatedAt")), now=now),
        dataset_freshness("papersCatalog", PAPERS_CATALOG_PATH, timestamp=parse_datetime(papers_catalog.get("generatedAt")), now=now),
        dataset_freshness("incrementalSources", INCREMENTAL_SOURCES_PATH, timestamp=parse_datetime(incremental_sources.get("updatedAt")), now=now),
        dataset_freshness("dailyUpdates", DAILY_UPDATES_PATH, timestamp=parse_datetime(daily_updates.get("updatedAt")), now=now),
        dataset_freshness("progressHistory", PROGRESS_HISTORY_PATH, timestamp=parse_datetime(progress_history.get("updatedAt")), now=now),
        dataset_freshness("discoveryLayers", DISCOVERY_LAYERS_PATH, timestamp=None, now=now),
        dataset_freshness("domainExtraMetrics", EXTRA_METRICS_PATH, timestamp=parse_datetime(extra_metrics.get("generatedAt")), now=now),
    ]

    top_new_papers = []
    for domain in sorted(domains_out, key=lambda item: safe_float(item["signals"]["newPapers7d"]), reverse=True)[:top_k]:
        count = int(safe_float(domain["signals"]["newPapers7d"]))
        if count <= 0:
            continue
        top_new_papers.append(
            {
                "id": domain["id"],
                "name": domain["name"],
                "macroName": domain["macroName"],
                "count": count,
            }
        )

    out = {
        "version": "1",
        "updatedAt": iso_now(),
        "sourceFiles": {
            "base": str(BASE_PATH.relative_to(ROOT)),
            "autoOverrides": str(AUTO_OVERRIDES_PATH.relative_to(ROOT)),
            "overrides": str(OVERRIDES_PATH.relative_to(ROOT)),
            "discoveryLayers": str(DISCOVERY_LAYERS_PATH.relative_to(ROOT)),
            "formalLayers": str(FORMAL_LAYERS_PATH.relative_to(ROOT)),
            "domainExtraMetrics": str(EXTRA_METRICS_PATH.relative_to(ROOT)),
            "papersCatalog": str(PAPERS_CATALOG_PATH.relative_to(ROOT)),
            "progressHistory": str(PROGRESS_HISTORY_PATH.relative_to(ROOT)),
            "dailyUpdates": str(DAILY_UPDATES_PATH.relative_to(ROOT)),
            "incrementalSources": str(INCREMENTAL_SOURCES_PATH.relative_to(ROOT)),
        },
        "definitions": AXIS_DEFINITIONS,
        "window": {
            "paperDays": int(args.paper_window_days),
            "updateDays": int(args.update_window_days),
            "historyDays": int(args.history_window_days),
        },
        "monitor": {
            "freshness": freshness,
            "recentPapers": {
                **recent_counts,
                "windowDays": int(args.paper_window_days),
                "latestPublicationDate": latest_publication_date.isoformat() if latest_publication_date else None,
            },
            "dimensionMix": update_mix,
            "directSources": {
                "updatedAt": incremental_sources.get("updatedAt"),
                "counts": direct_counts,
                "errors": direct_source_errors,
                "topSources": top_direct_sources,
                "recentItems": recent_direct_items,
            },
            "latestUpdates": latest_updates,
            "topMovers": rankings["fastMovers"],
            "topNewPaperDomains": top_new_papers,
            "watchlist": watchlist,
            "diagnoses": diagnoses,
        },
        "rankings": rankings,
        "domains": domains_out,
    }

    md_lines: list[str] = []
    md_lines.append("# First Principles Lens\n")
    md_lines.append(f"- UpdatedAt: {out['updatedAt']}\n")
    md_lines.append(
        f"- Monitor window: papers={args.paper_window_days}d, updates={args.update_window_days}d, history={args.history_window_days}d\n"
    )
    md_lines.append("\n## Axes\n")
    for key in AXIS_KEYS:
        md_lines.append(f"- **{key}**: {AXIS_DEFINITIONS[key]}\n")

    md_lines.append("\n## Daily Diagnoses\n")
    for item in diagnoses:
        md_lines.append(f"- {item}\n")

    md_lines.append("\n## Watchlist\n")
    for item in watchlist:
        md_lines.append(f"- **{item['name']}** ({item['macroName']} / {item['profileLabel']}): {'; '.join(item['reasons'])}\n")

    md_lines.append("\n## Top Closure Leaders\n")
    for item in rankings["closureLeaders"]:
        md_lines.append(f"- {item['name']} ({item['macroName']}): closure={item['value']:.2f}\n")

    md_lines.append("\n## Top Instrumentalist Frontiers\n")
    for item in rankings["instrumentalistFrontiers"]:
        md_lines.append(f"- {item['name']} ({item['macroName']}): gap={item['value']:.2f}\n")

    md_lines.append("\n## Recent Updates\n")
    for item in latest_updates:
        md_lines.append(f"- {item.get('date')}: {item.get('summary')}\n")

    save_json(args.out_json, out)
    save_text(args.out_md, "".join(md_lines).rstrip() + "\n")
    print(f"[done] wrote {args.out_json} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
