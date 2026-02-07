#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "data"

BASE_PATH = DATA_DIR / "base.json"
AUTO_OVERRIDES_PATH = DATA_DIR / "auto_overrides.json"
OVERRIDES_PATH = DATA_DIR / "overrides.json"
DOMAIN_EXTRA_METRICS_PATH = DATA_DIR / "domain_extra_metrics.json"
OUT_PATH = DATA_DIR / "progress_history.json"

DIM_KEYS = ["data", "model", "predict", "experiment", "explain"]
DEFAULT_CONFIDENCE = 0.25


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _clamp_score(x: float) -> float:
    return max(0.0, min(100.0, x))


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default


def _safe_float(v: Any) -> float | None:
    try:
        n = float(v)
    except Exception:
        return None
    if not math.isfinite(n):
        return None
    return n


def merge_dimension(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    next_dim: dict[str, Any] = {"score": 0.0}
    if base:
        score = _safe_float(base.get("score"))
        if score is not None:
            next_dim["score"] = score
        next_dim.update(base)
    if override:
        score = _safe_float(override.get("score"))
        if score is not None:
            next_dim["score"] = score
        next_dim.update(override)
    if _safe_float(next_dim.get("score")) is None:
        next_dim["score"] = 0.0
    return next_dim


def merge_node(base_node: dict[str, Any], override_node: dict[str, Any]) -> dict[str, Any]:
    next_node: dict[str, Any] = {**base_node}

    if "name" in override_node:
        next_node["name"] = override_node["name"]
    if "description" in override_node:
        next_node["description"] = override_node["description"]
    if "order" in override_node:
        next_node["order"] = override_node["order"]

    if isinstance(override_node.get("overall"), dict):
        base_overall = base_node.get("overall")
        next_node["overall"] = {
            **(base_overall if isinstance(base_overall, dict) else {}),
            **override_node["overall"],
        }

    if isinstance(override_node.get("dimensions"), dict):
        base_dims = base_node.get("dimensions")
        next_dims: dict[str, Any] = {**(base_dims if isinstance(base_dims, dict) else {})}

        for dim_key, override_dim in override_node["dimensions"].items():
            if dim_key not in DIM_KEYS:
                continue
            if not isinstance(override_dim, dict):
                continue
            base_dim = next_dims.get(dim_key)
            next_dims[dim_key] = merge_dimension(base_dim if isinstance(base_dim, dict) else None, override_dim)

        next_node["dimensions"] = next_dims

    return next_node


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


def score_to_maturity(score: float) -> int:
    s = _clamp_score(score)
    if s < 10:
        return 0
    if s < 30:
        return 1
    if s < 55:
        return 2
    if s < 75:
        return 3
    return 4


@dataclass(frozen=True)
class LeafInfo:
    id: str
    name: str
    macro_id: str
    macro_name: str


def infer_date(ts: str | None) -> str:
    if isinstance(ts, str) and len(ts) >= 10:
        return ts[:10]
    return datetime.now(tz=UTC).date().isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description="Append a snapshot to web/data/progress_history.json.")
    ap.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help="Output path for progress_history.json (default: web/data/progress_history.json).",
    )
    ap.add_argument(
        "--no-replace-same-date",
        action="store_true",
        help="Do not replace existing snapshot with the same YYYY-MM-DD (default: replace).",
    )
    ap.add_argument(
        "--keep-days",
        type=int,
        default=0,
        help="Keep only last N days of snapshots (0 = keep all).",
    )
    args = ap.parse_args()

    if not BASE_PATH.exists():
        raise SystemExit(f"Base file not found: {BASE_PATH}")

    base = _read_json(BASE_PATH, default={})
    if not isinstance(base, dict):
        raise SystemExit(f"Invalid base.json structure: {BASE_PATH}")

    auto_overrides = _read_json(
        AUTO_OVERRIDES_PATH,
        default={"version": "0.1", "updatedAt": datetime.fromtimestamp(0, tz=UTC).isoformat(), "nodes": {}},
    )
    overrides = _read_json(
        OVERRIDES_PATH,
        default={"version": "0.1", "updatedAt": datetime.fromtimestamp(0, tz=UTC).isoformat(), "nodes": {}},
    )
    extra_metrics = _read_json(DOMAIN_EXTRA_METRICS_PATH, default={})
    extra_nodes = extra_metrics.get("nodes") if isinstance(extra_metrics, dict) else None
    extra_nodes = extra_nodes if isinstance(extra_nodes, dict) else {}

    merged = apply_overrides(apply_overrides(base, auto_overrides), overrides)
    nodes = merged.get("nodes")
    if not isinstance(nodes, dict):
        raise SystemExit("Invalid base.json: expected `nodes` to be an object.")

    root_id = merged.get("rootId") if isinstance(merged.get("rootId"), str) else "ai4sci"
    generated_at = merged.get("generatedAt") if isinstance(merged.get("generatedAt"), str) else None
    snapshot_date = infer_date(generated_at)

    children = build_children(nodes)

    # Leaf nodes in the "problem space": exclude root + methods branch.
    leaves: list[LeafInfo] = []
    for node_id, node in nodes.items():
        if node_id == root_id:
            continue
        if children.get(node_id):
            continue
        if not isinstance(node, dict):
            continue

        macro_id = macro_of(node_id, nodes=nodes, root_id=root_id)
        if macro_id == "methods":
            continue

        name = node.get("name")
        macro_node = nodes.get(macro_id)
        macro_name = macro_node.get("name") if isinstance(macro_node, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(macro_name, str) or not macro_name.strip():
            macro_name = macro_id

        leaves.append(
            LeafInfo(
                id=node_id,
                name=name.strip(),
                macro_id=macro_id,
                macro_name=str(macro_name).strip(),
            )
        )

    # Load existing history (if any) and append/replace snapshot.
    history = _read_json(args.out, default={})
    if not isinstance(history, dict):
        history = {}

    hist_leaves_raw = history.get("leaves")
    hist_leaves: list[dict[str, Any]] = list(hist_leaves_raw) if isinstance(hist_leaves_raw, list) else []
    hist_leaf_index: dict[str, int] = {}
    for idx, it in enumerate(hist_leaves):
        if isinstance(it, dict) and isinstance(it.get("id"), str):
            hist_leaf_index[it["id"]] = idx

    if not hist_leaves:
        for li in sorted(leaves, key=lambda x: x.id):
            hist_leaf_index[li.id] = len(hist_leaves)
            hist_leaves.append(
                {"id": li.id, "name": li.name, "macroId": li.macro_id, "macroName": li.macro_name}
            )
    else:
        for li in sorted(leaves, key=lambda x: x.id):
            if li.id in hist_leaf_index:
                idx = hist_leaf_index[li.id]
                # Keep ids stable; update name/macro for display.
                hist_leaves[idx] = {
                    **(hist_leaves[idx] if isinstance(hist_leaves[idx], dict) else {}),
                    "id": li.id,
                    "name": li.name,
                    "macroId": li.macro_id,
                    "macroName": li.macro_name,
                }
            else:
                hist_leaf_index[li.id] = len(hist_leaves)
                hist_leaves.append(
                    {"id": li.id, "name": li.name, "macroId": li.macro_id, "macroName": li.macro_name}
                )

    n = len(hist_leaves)

    def mk_arr() -> list[float | None]:
        return [None] * n

    overall = mk_arr()
    data_s = mk_arr()
    model_s = mk_arr()
    predict_s = mk_arr()
    experiment_s = mk_arr()
    explain_s = mk_arr()
    conf = mk_arr()
    ai_recent = mk_arr()
    penetration = mk_arr()
    growth_norm = mk_arr()
    tooling = mk_arr()
    autonomy = mk_arr()

    for li in leaves:
        idx = hist_leaf_index.get(li.id)
        if idx is None:
            continue
        node = nodes.get(li.id)
        if not isinstance(node, dict):
            continue
        dims = node.get("dimensions")
        dims = dims if isinstance(dims, dict) else {}

        dim_scores: dict[str, float] = {}
        dim_confs: dict[str, float] = {}
        for k in DIM_KEYS:
            dim = dims.get(k)
            if not isinstance(dim, dict):
                dim = {}
            score = _safe_float(dim.get("score")) or 0.0
            dim_scores[k] = _clamp_score(score)
            c = _safe_float(dim.get("confidence"))
            dim_confs[k] = _clamp01(c if c is not None else DEFAULT_CONFIDENCE)

        overall_score = None
        overall_obj = node.get("overall")
        if isinstance(overall_obj, dict):
            overall_score = _safe_float(overall_obj.get("score"))
        if overall_score is None:
            overall_score = sum(dim_scores.values()) / float(len(DIM_KEYS))
        overall_score = _clamp_score(float(overall_score))

        overall_conf = None
        if isinstance(overall_obj, dict):
            overall_conf = _safe_float(overall_obj.get("confidence"))
        if overall_conf is None:
            overall_conf = sum(dim_confs.values()) / float(len(DIM_KEYS))
        overall_conf = _clamp01(float(overall_conf))

        overall[idx] = round(overall_score, 2)
        data_s[idx] = round(dim_scores["data"], 2)
        model_s[idx] = round(dim_scores["model"], 2)
        predict_s[idx] = round(dim_scores["predict"], 2)
        experiment_s[idx] = round(dim_scores["experiment"], 2)
        explain_s[idx] = round(dim_scores["explain"], 2)
        conf[idx] = round(overall_conf, 4)

        model = dims.get("model") if isinstance(dims.get("model"), dict) else {}
        signals = model.get("signals") if isinstance(model.get("signals"), dict) else {}
        if isinstance(signals, dict):
            v = _safe_float(signals.get("ai_recent"))
            if v is not None:
                ai_recent[idx] = float(v)
            v = _safe_float(signals.get("penetration"))
            if v is not None:
                penetration[idx] = float(v)
            v = _safe_float(signals.get("growth_norm"))
            if v is not None:
                growth_norm[idx] = float(v)

        extra_entry = extra_nodes.get(li.id) if isinstance(extra_nodes, dict) else None
        if isinstance(extra_entry, dict):
            t = _safe_float(extra_entry.get("tooling"))
            if t is not None:
                tooling[idx] = round(_clamp_score(100.0 * _clamp01(t)), 2)
            a = _safe_float(extra_entry.get("autonomy"))
            if a is not None:
                autonomy[idx] = round(_clamp_score(100.0 * _clamp01(a)), 2)

    # Grow existing snapshots arrays if new leaves were added.
    snapshots_raw = history.get("snapshots")
    snapshots: list[dict[str, Any]] = list(snapshots_raw) if isinstance(snapshots_raw, list) else []

    def ensure_len(arr: Any, target: int) -> list[Any]:
        out = list(arr) if isinstance(arr, list) else []
        if len(out) < target:
            out.extend([None] * (target - len(out)))
        return out

    for s in snapshots:
        if not isinstance(s, dict):
            continue
        for key in [
            "overall",
            "data",
            "model",
            "predict",
            "experiment",
            "explain",
            "confidence",
            "aiRecent",
            "penetration",
            "growthNorm",
            "tooling",
            "autonomy",
        ]:
            s[key] = ensure_len(s.get(key), n)

    snapshot = {
        "date": snapshot_date,
        "ts": generated_at or datetime.now(tz=UTC).isoformat(),
        "generatedAt": generated_at or datetime.now(tz=UTC).isoformat(),
        "autoUpdatedAt": auto_overrides.get("updatedAt") if isinstance(auto_overrides, dict) else None,
        "manualUpdatedAt": overrides.get("updatedAt") if isinstance(overrides, dict) else None,
        "overall": overall,
        "data": data_s,
        "model": model_s,
        "predict": predict_s,
        "experiment": experiment_s,
        "explain": explain_s,
        "confidence": conf,
        "aiRecent": ai_recent,
        "penetration": penetration,
        "growthNorm": growth_norm,
        "tooling": tooling,
        "autonomy": autonomy,
    }

    replaced = False
    should_replace_same_date = not bool(args.no_replace_same_date)
    if should_replace_same_date:
        for i, s in enumerate(snapshots):
            if isinstance(s, dict) and s.get("date") == snapshot_date:
                snapshots[i] = snapshot
                replaced = True
                break

    if not replaced:
        snapshots.append(snapshot)

    # Sort snapshots by date then ts.
    def key_of(s: dict[str, Any]) -> tuple[str, str]:
        d = s.get("date")
        t = s.get("ts")
        return (str(d or ""), str(t or ""))

    snapshots = [s for s in snapshots if isinstance(s, dict) and isinstance(s.get("date"), str)]
    snapshots.sort(key=key_of)

    if int(args.keep_days or 0) > 0 and snapshots:
        cutoff = datetime.fromisoformat(snapshots[-1]["date"]).date()
        keep_from = cutoff.toordinal() - int(args.keep_days) + 1
        kept: list[dict[str, Any]] = []
        for s in snapshots:
            try:
                d = date.fromisoformat(str(s.get("date")))
            except Exception:
                continue
            if d.toordinal() >= keep_from:
                kept.append(s)
        snapshots = kept

    out = {
        "version": history.get("version") if isinstance(history.get("version"), str) else "0.1",
        "updatedAt": datetime.now(tz=UTC).isoformat(),
        "rootId": root_id,
        "leaves": hist_leaves,
        "snapshots": snapshots,
        "stats": {"leaves": n, "snapshots": len(snapshots)},
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"[done] wrote {args.out} (snapshots={len(snapshots)} leaves={n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
