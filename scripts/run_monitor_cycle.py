#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "data"

STATUS_JSON = DATA_DIR / "monitor_status.json"
STATUS_MD = DATA_DIR / "monitor_status.md"
FIRST_PRINCIPLES_PATH = DATA_DIR / "first_principles_lens.json"
DAILY_UPDATES_PATH = DATA_DIR / "daily_updates.json"
PROGRESS_HISTORY_PATH = DATA_DIR / "progress_history.json"
BASE_PATH = DATA_DIR / "base.json"
PAPERS_CATALOG_PATH = DATA_DIR / "papers_catalog.json"
INCREMENTAL_SOURCES_PATH = DATA_DIR / "incremental_sources.json"


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


def parse_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def age_hours(now: datetime, ts: datetime | None) -> float | None:
    if ts is None:
        return None
    return round((now - ts).total_seconds() / 3600.0, 2)


def printable_cmd(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


@dataclass(frozen=True)
class Alert:
    severity: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message}


def command_specs(mode: str, *, py: str, no_llm: bool, catalog_days: int, db: Path) -> list[tuple[str, list[str]]]:
    if mode == "fast":
        fast_incremental = [py, str(ROOT / "scripts" / "ingest_incremental_sources.py"), "--db", str(db), "--lookback-hours", "336"]
        fast_tags = [
            py,
            str(ROOT / "scripts" / "tag_ai_methods.py"),
            "--db",
            str(db),
            "--only-missing",
            "--updated-since-hours",
            "72",
        ]
        fast_updates = [py, str(ROOT / "scripts" / "update_daily_updates.py"), "--auto-from-catalog", "--catalog-days", str(int(catalog_days))]
        if no_llm:
            fast_updates.append("--no-llm")
        return [
            ("incremental-sources", fast_incremental),
            ("tag-methods", fast_tags),
            ("daily-updates", fast_updates),
            ("progress-history", [py, str(ROOT / "scripts" / "update_progress_history.py")]),
            ("first-principles", [py, str(ROOT / "scripts" / "analyze_first_principles_lens.py")]),
        ]
    if mode == "daily-full":
        cmd = [
            py,
            str(ROOT / "scripts" / "update_all.py"),
            "--db",
            str(db),
            "--openalex-full",
            "--daily-updates",
        ]
        if no_llm:
            cmd.append("--daily-updates-no-llm")
        return [("update-all", cmd)]
    if mode == "analyze-only":
        return [
            ("progress-history", [py, str(ROOT / "scripts" / "update_progress_history.py")]),
            ("first-principles", [py, str(ROOT / "scripts" / "analyze_first_principles_lens.py")]),
        ]
    raise ValueError(f"Unsupported mode: {mode}")


def render_md(status: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Monitor Status\n")
    lines.append(f"- UpdatedAt: {status.get('updatedAt')}\n")
    run = status.get("run") if isinstance(status.get("run"), dict) else {}
    lines.append(f"- Mode: {run.get('mode')}\n")
    lines.append(f"- Success: {run.get('success')}\n")
    lines.append(f"- DurationSeconds: {run.get('durationSeconds')}\n")

    lines.append("\n## Commands\n")
    for cmd in run.get("commands", []):
        if not isinstance(cmd, dict):
            continue
        lines.append(
            f"- {cmd.get('label')}: ok={cmd.get('ok')} duration={cmd.get('durationSeconds')}s cmd=`{cmd.get('cmd')}`\n"
        )

    alerts = status.get("alerts") if isinstance(status.get("alerts"), list) else []
    lines.append("\n## Alerts\n")
    if alerts:
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            lines.append(f"- [{alert.get('severity')}] {alert.get('message')}\n")
    else:
        lines.append("- none\n")

    freshness = status.get("freshness") if isinstance(status.get("freshness"), list) else []
    lines.append("\n## Freshness\n")
    for item in freshness:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('name')}: status={item.get('status')} ageHours={item.get('ageHours')} path={item.get('path')}\n"
        )

    pipeline = status.get("pipeline") if isinstance(status.get("pipeline"), dict) else {}
    direct_sources = pipeline.get("directSources") if isinstance(pipeline.get("directSources"), dict) else {}
    direct_counts = direct_sources.get("counts") if isinstance(direct_sources.get("counts"), dict) else {}

    lines.append("\n## Direct Sources\n")
    if direct_counts:
        lines.append(
            f"- last6h={direct_counts.get('last6h')} last24h={direct_counts.get('last24h')} last72h={direct_counts.get('last72h')} errors={direct_sources.get('errors')}\n"
        )

    lines.append("\n## Diagnoses\n")
    for diag in pipeline.get("diagnoses", []):
        lines.append(f"- {diag}\n")

    lines.append("\n## Watchlist\n")
    for item in pipeline.get("watchlist", []):
        if not isinstance(item, dict):
            continue
        reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
        lines.append(f"- {item.get('name')} ({item.get('macroName')}): {'; '.join(str(r) for r in reasons)}\n")

    return "".join(lines).rstrip() + "\n"


def evaluate_freshness(now: datetime, *, first_principles: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Alert]]:
    files = [
        ("base", BASE_PATH, parse_datetime(read_json(BASE_PATH, {}).get("generatedAt")), 48.0),
        ("papersCatalog", PAPERS_CATALOG_PATH, parse_datetime(read_json(PAPERS_CATALOG_PATH, {}).get("generatedAt")), 36.0),
        ("incrementalSources", INCREMENTAL_SOURCES_PATH, parse_datetime(read_json(INCREMENTAL_SOURCES_PATH, {}).get("updatedAt")), 24.0),
        ("dailyUpdates", DAILY_UPDATES_PATH, parse_datetime(read_json(DAILY_UPDATES_PATH, {}).get("updatedAt")), 36.0),
        ("progressHistory", PROGRESS_HISTORY_PATH, parse_datetime(read_json(PROGRESS_HISTORY_PATH, {}).get("updatedAt")), 36.0),
        ("firstPrinciples", FIRST_PRINCIPLES_PATH, parse_datetime(first_principles.get("updatedAt")), 24.0),
    ]
    out: list[dict[str, Any]] = []
    alerts: list[Alert] = []
    for name, path, timestamp, threshold in files:
        if timestamp is None and path.exists():
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        item_age = age_hours(now, timestamp)
        if not path.exists():
            status = "missing"
            alerts.append(Alert("critical", f"{name}_missing", f"{name} 缺失：{path.relative_to(ROOT)}"))
        elif item_age is None:
            status = "unknown"
            alerts.append(Alert("warn", f"{name}_unknown_time", f"{name} 存在，但无法解析时间戳。"))
        elif item_age > threshold * 2:
            status = "critical"
            alerts.append(Alert("critical", f"{name}_very_stale", f"{name} 已超过 {item_age:.1f} 小时未刷新。"))
        elif item_age > threshold:
            status = "stale"
            alerts.append(Alert("warn", f"{name}_stale", f"{name} 已超过 {item_age:.1f} 小时未刷新。"))
        else:
            status = "fresh"
        out.append(
            {
                "name": name,
                "path": str(path.relative_to(ROOT)),
                "timestamp": timestamp.isoformat() if timestamp else None,
                "ageHours": item_age,
                "thresholdHours": threshold,
                "status": status,
            }
        )
    return out, alerts


def build_status(
    *,
    mode: str,
    started_at: str,
    finished_at: str,
    commands: list[dict[str, Any]],
    success: bool,
) -> dict[str, Any]:
    now = parse_datetime(finished_at) or datetime.now(tz=UTC)
    first_principles = read_json(FIRST_PRINCIPLES_PATH, {})
    monitor = first_principles.get("monitor") if isinstance(first_principles.get("monitor"), dict) else {}

    freshness, alerts = evaluate_freshness(now, first_principles=first_principles)

    recent_papers = monitor.get("recentPapers") if isinstance(monitor.get("recentPapers"), dict) else {}
    if int(recent_papers.get("last7d") or 0) <= 0:
        alerts.append(Alert("warn", "no_recent_papers_7d", "近 7 天未检测到新论文，可能是数据源延迟或抓取链路停滞。"))

    latest_updates = monitor.get("latestUpdates") if isinstance(monitor.get("latestUpdates"), list) else []
    if not latest_updates:
        alerts.append(Alert("warn", "no_recent_updates", "daily_updates.json 中没有最近更新条目。"))

    direct_sources = monitor.get("directSources") if isinstance(monitor.get("directSources"), dict) else {}
    direct_counts = direct_sources.get("counts") if isinstance(direct_sources.get("counts"), dict) else {}
    if int(direct_counts.get("last24h") or 0) <= 0:
        alerts.append(Alert("warn", "no_direct_hits_24h", "近 24 小时没有来自 arXiv/RSS 的增量命中。"))

    incremental = read_json(INCREMENTAL_SOURCES_PATH, {})
    for source in incremental.get("sources") or []:
        if not isinstance(source, dict):
            continue
        if str(source.get("status") or "").lower() == "error":
            alerts.append(
                Alert(
                    "warn",
                    f"incremental_source_error_{source.get('id')}",
                    f"直连源 {source.get('name')} 抓取失败：{source.get('error') or 'unknown error'}",
                )
            )

    watchlist = monitor.get("watchlist") if isinstance(monitor.get("watchlist"), list) else []
    if watchlist:
        first_item = watchlist[0]
        if isinstance(first_item, dict):
            alerts.append(
                Alert(
                    "info",
                    "watchlist_focus",
                    f"当前最高优先级跟踪领域：{first_item.get('name')}（{first_item.get('profileLabel')}）。",
                )
            )

    critical_count = sum(1 for item in alerts if item.severity == "critical")
    warn_count = sum(1 for item in alerts if item.severity == "warn")
    info_count = sum(1 for item in alerts if item.severity == "info")

    started_dt = parse_datetime(started_at)
    finished_dt = parse_datetime(finished_at)
    duration_seconds = None
    if started_dt and finished_dt:
        duration_seconds = round((finished_dt - started_dt).total_seconds(), 2)

    return {
        "version": "1",
        "updatedAt": finished_at,
        "run": {
            "mode": mode,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "durationSeconds": duration_seconds,
            "success": success,
            "commands": commands,
        },
        "freshness": freshness,
        "alerts": [item.as_dict() for item in alerts],
        "summary": {
            "critical": critical_count,
            "warn": warn_count,
            "info": info_count,
        },
        "pipeline": {
            "recentPapers": recent_papers,
            "dimensionMix": monitor.get("dimensionMix"),
            "directSources": direct_sources,
            "diagnoses": monitor.get("diagnoses") if isinstance(monitor.get("diagnoses"), list) else [],
            "watchlist": watchlist,
            "topMovers": monitor.get("topMovers") if isinstance(monitor.get("topMovers"), list) else [],
            "latestUpdates": latest_updates,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a fast or full monitoring cycle and write monitor status artifacts.")
    ap.add_argument(
        "--mode",
        choices=["fast", "daily-full", "analyze-only"],
        default="fast",
        help="fast=hourly lightweight refresh; daily-full=full pipeline; analyze-only=derive status from existing data.",
    )
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "papers.sqlite", help="SQLite DB path.")
    ap.add_argument(
        "--catalog-days",
        type=int,
        default=7,
        help="How many recent days of papers to include when running fast daily updates.",
    )
    ap.add_argument("--no-llm", action="store_true", help="Disable LLM use during update steps when supported.")
    ap.add_argument("--out-json", type=Path, default=STATUS_JSON, help="Output JSON status path.")
    ap.add_argument("--out-md", type=Path, default=STATUS_MD, help="Output Markdown status path.")
    ap.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit non-zero if any critical alerts remain after the cycle.",
    )
    args = ap.parse_args()

    py = sys.executable or "python3"
    started_at = iso_now()
    run_started = time.monotonic()
    commands_out: list[dict[str, Any]] = []
    success = True

    try:
        for label, cmd in command_specs(args.mode, py=py, no_llm=bool(args.no_llm), catalog_days=int(args.catalog_days), db=args.db):
            cmd_started = time.monotonic()
            printable = printable_cmd(cmd)
            print(f"[run] {label}: {printable}")
            try:
                subprocess.run(cmd, check=True)  # noqa: S603
                ok = True
                return_code = 0
                error = None
            except subprocess.CalledProcessError as exc:
                ok = False
                return_code = exc.returncode
                error = str(exc)
                success = False
                commands_out.append(
                    {
                        "label": label,
                        "cmd": printable,
                        "ok": ok,
                        "returnCode": return_code,
                        "durationSeconds": round(time.monotonic() - cmd_started, 2),
                        "error": error,
                    }
                )
                raise
            commands_out.append(
                {
                    "label": label,
                    "cmd": printable,
                    "ok": ok,
                    "returnCode": return_code,
                    "durationSeconds": round(time.monotonic() - cmd_started, 2),
                    "error": error,
                }
            )
    except subprocess.CalledProcessError:
        pass

    finished_at = iso_now()
    status = build_status(
        mode=args.mode,
        started_at=started_at,
        finished_at=finished_at,
        commands=commands_out,
        success=success,
    )
    if status.get("run") and isinstance(status["run"], dict):
        status["run"]["wallClockSeconds"] = round(time.monotonic() - run_started, 2)

    save_json(args.out_json, status)
    save_text(args.out_md, render_md(status))
    print(f"[done] wrote {args.out_json} and {args.out_md}")

    critical_count = int((status.get("summary") or {}).get("critical") or 0)
    if not success:
        return 1
    if args.fail_on_critical and critical_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
