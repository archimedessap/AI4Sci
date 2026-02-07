"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { ECharts } from "@/components/ECharts";
import type { NarrativeStageKey } from "@/lib/progress/narrative";
import { narrativeStageColor, narrativeStageLabel } from "@/lib/progress/narrative";

export type TrendsLeaf = {
  id: string;
  name: string;
  macroName?: string | null;
};

export type TrendsMover = {
  id: string;
  name: string;
  macroName?: string | null;
  score: number;
  delta: number;
};

export type NarrativeCriterionRow = {
  key: string;
  label: string;
  metric?: string;
  current: number | null;
  threshold: number;
  passed: boolean;
  etaDays: number | null;
};

export type TrendsNarrative = {
  currentStageKey: NarrativeStageKey | "none";
  nextStageKey: NarrativeStageKey | null;
  etaDays: number | null;
  etaDate: string | null;
  pointsUsed: number;
  nextCriteria: NarrativeCriterionRow[];
};

function fmtDelta(delta: number) {
  const d = Math.round(delta * 100) / 100;
  return d >= 0 ? `+${d.toFixed(2)}` : d.toFixed(2);
}

function fmtMetric(metric: string | undefined, v: number | null) {
  if (typeof v !== "number") return "—";
  if (metric === "confidence") return v.toFixed(2);
  if (metric === "aiRecent") return Math.round(v).toLocaleString();
  if (metric === "theory" || metric === "principles") return v.toFixed(2);
  if (metric === "signalRatioExplain" || metric === "signalRatioExperiment") return v.toFixed(3);
  return v.toFixed(1);
}

export function TrendsClient({
  leaves,
  selectedId,
  dates,
  scores,
  narrative,
  movers,
  updatedAt,
}: {
  leaves: TrendsLeaf[];
  selectedId: string;
  dates: string[];
  scores: Array<number | null>;
  narrative: TrendsNarrative | null;
  movers: TrendsMover[];
  updatedAt: string;
}) {
  const router = useRouter();

  const option: EChartsOption = useMemo(() => {
    const lineData = scores.map((v, idx) => [dates[idx] ?? "", v] as [string, number | null]);
    const threshLines = [
      { yAxis: 10, lineStyle: { color: "rgba(255,255,255,0.18)" } },
      { yAxis: 30, lineStyle: { color: "rgba(255,255,255,0.18)" } },
      { yAxis: 55, lineStyle: { color: "rgba(255,255,255,0.18)" } },
      { yAxis: 75, lineStyle: { color: "rgba(255,255,255,0.18)" } },
    ];

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const items = Array.isArray(params) ? (params as Array<{ data?: unknown }>) : [];
          const first = items[0]?.data;
          const tuple = Array.isArray(first) ? first : [];
          const [d, v] = tuple as [string, number | null];
          const vv = typeof v === "number" ? v.toFixed(2) : "—";
          return `<div style="font-weight:600">${d}</div><div style="opacity:.85">Overall: ${vv}</div>`;
        },
      },
      grid: { left: 46, right: 18, top: 18, bottom: 44 },
      xAxis: {
        type: "category",
        data: dates,
        axisLabel: { color: "rgba(255,255,255,0.65)", fontSize: 10 },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.14)" } },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { color: "rgba(255,255,255,0.65)", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
      },
      series: [
        {
          name: "Overall",
          type: "line",
          showSymbol: false,
          smooth: 0.2,
          data: lineData,
          lineStyle: { color: "#22d3ee", width: 2 },
          areaStyle: { color: "rgba(34,211,238,0.10)" },
          markLine: {
            symbol: "none",
            label: { color: "rgba(255,255,255,0.55)", fontSize: 10 },
            data: threshLines,
          },
        },
      ],
    } satisfies EChartsOption;
  }, [dates, scores]);

  const selected = leaves.find((l) => l.id === selectedId);
  const lastScore = (() => {
    for (let i = scores.length - 1; i >= 0; i -= 1) {
      const v = scores[i];
      if (typeof v === "number") return v;
    }
    return null;
  })();

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
      <div className="lg:col-span-7">
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs text-white/45">
            History updated: {new Date(updatedAt).toLocaleString()}
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-white/60">Domain</label>
            <select
              value={selectedId}
              onChange={(e) => {
                const next = e.target.value;
                router.push(`/trends?id=${encodeURIComponent(next)}`);
              }}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-white/80 outline-none hover:bg-white/[0.05]"
            >
              {leaves.map((l) => (
                <option key={l.id} value={l.id}>
                  {(l.macroName ? `${l.macroName} / ` : "") + l.name}
                </option>
              ))}
            </select>
            <Link
              href={`/domain/${encodeURIComponent(selectedId)}`}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-semibold text-white/75 hover:bg-white/[0.06]"
            >
              Open
            </Link>
          </div>
        </div>

        <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-white/90">
                {selected?.name ?? selectedId}
              </div>
              <div className="mt-1 text-xs text-white/50">
                {(selected?.macroName ?? "").trim() ? `Macro: ${selected?.macroName}` : null}
              </div>
            </div>
            {narrative ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-white/70">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: narrativeStageColor(narrative.currentStageKey) }}
                  />
                  <span className="font-semibold text-white/80">
                    {narrativeStageLabel(narrative.currentStageKey)}
                  </span>
                  <span className="text-white/50">•</span>
                  <span>score={typeof lastScore === "number" ? lastScore.toFixed(2) : "—"}</span>
                </div>
                <div className="mt-1 text-white/55">
                  {narrative.nextStageKey == null ? (
                    <span>Next milestone: —</span>
                  ) : narrative.etaDate ? (
                    <span>
                      Next milestone ({narrativeStageLabel(narrative.nextStageKey)}) ETA:{" "}
                      <span className="font-semibold text-cyan-200">{narrative.etaDate}</span>{" "}
                      <span className="text-white/45">(last {narrative.pointsUsed} pts)</span>
                    </span>
                  ) : (
                    <span>
                      Next milestone ({narrativeStageLabel(narrative.nextStageKey)}): need more history (or no upward trend)
                    </span>
                  )}
                </div>
                {narrative.nextCriteria.length ? (
                  <div className="mt-2 space-y-1 text-[11px] text-white/55">
                    {narrative.nextCriteria.slice(0, 5).map((c) => (
                      <div key={c.key} className="flex items-start justify-between gap-3">
                        <div className="min-w-0 truncate">
                          <span
                            className="mr-1"
                            style={{
                              color: c.passed ? "rgba(74,222,128,0.95)" : "rgba(148,163,184,0.8)",
                            }}
                          >
                            {c.passed ? "✓" : "•"}
                          </span>
                          {c.label}
                        </div>
                        <div className="shrink-0 text-right text-white/45">
                          {fmtMetric(c.metric, c.current)}/{fmtMetric(c.metric, c.threshold)}
                          {typeof c.etaDays === "number" ? ` • ${Math.ceil(c.etaDays)}d` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="mt-4">
            <ECharts option={option} style={{ height: 340 }} />
          </div>
        </div>
      </div>

      <div className="lg:col-span-5">
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <div className="text-sm font-semibold text-white/90">Top Movers (Δ latest)</div>
          <div className="mt-1 text-xs text-white/50">
            Latest snapshot vs previous snapshot. Click to view trend.
          </div>
          <div className="mt-4 space-y-2">
            {movers.map((m) => (
              <button
                key={m.id}
                onClick={() => router.push(`/trends?id=${encodeURIComponent(m.id)}`)}
                className="w-full rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2 text-left hover:bg-white/[0.05]"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-xs font-semibold text-white/85">
                      {m.name}
                    </div>
                    <div className="truncate text-[11px] text-white/45">
                      {m.macroName ?? ""}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-xs text-white/70">{m.score.toFixed(1)}</div>
                    <div
                      className="text-[11px]"
                      style={{ color: m.delta >= 0 ? "rgba(74,222,128,0.9)" : "rgba(251,113,133,0.9)" }}
                    >
                      {fmtDelta(m.delta)}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
          <div className="mt-4 text-xs text-white/45">
            Share tip: open a domain, then share the URL.
          </div>
        </div>
      </div>
    </div>
  );
}
