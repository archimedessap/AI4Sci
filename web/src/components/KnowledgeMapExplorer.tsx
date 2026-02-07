"use client";

import { useMemo, useState } from "react";

import { ProgressGraph } from "@/components/ProgressGraph";
import { ProgressTree } from "@/components/ProgressTree";

export type KnowledgeMapMetricKey =
  | "overall"
  | "data"
  | "model"
  | "predict"
  | "experiment"
  | "explain"
  | "tooling"
  | "autonomy";

export type KnowledgeMapNode = {
  id: string;
  name: string;
  depth: number;
  parentId: string | null;
  macroId: string;
  macroName: string;
  metrics: Record<KnowledgeMapMetricKey, number>;
};

export type KnowledgeMapLink = { source: string; target: string };

const METRICS: Array<{ key: KnowledgeMapMetricKey; label: string }> = [
  { key: "overall", label: "Overall" },
  { key: "data", label: "Data" },
  { key: "model", label: "Modeling" },
  { key: "predict", label: "Prediction & Control" },
  { key: "experiment", label: "Experiment & Design" },
  { key: "explain", label: "Explanation" },
  { key: "tooling", label: "Tooling" },
  { key: "autonomy", label: "Autonomy" },
];

const MACRO_PALETTE = ["#22d3ee", "#a78bfa", "#4ade80", "#fb7185", "#fbbf24", "#60a5fa"];

function clampScore(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

export function KnowledgeMapExplorer({
  rootId,
  nodes,
  links,
  initialScope = "macro",
  initialMetric = "overall",
  initialIncludeMethods = false,
  initialLayout = "tree",
  height = 560,
}: {
  rootId: string;
  nodes: KnowledgeMapNode[];
  links: KnowledgeMapLink[];
  initialScope?: "macro" | "sub" | "full";
  initialMetric?: KnowledgeMapMetricKey;
  initialIncludeMethods?: boolean;
  initialLayout?: "tree" | "graph";
  height?: number;
}) {
  const [layout, setLayout] = useState<"tree" | "graph">(initialLayout);
  const [scope, setScope] = useState<"macro" | "sub" | "full">(initialScope);
  const [metric, setMetric] = useState<KnowledgeMapMetricKey>(initialMetric);
  const [includeMethods, setIncludeMethods] = useState<boolean>(initialIncludeMethods);

  const macroInfo = useMemo(() => {
    const macros = nodes
      .filter((n) => n.parentId === rootId)
      .map((m) => ({ id: m.id, name: m.name }))
      .filter(Boolean);
    const colorByMacro = new Map<string, string>();
    macros.forEach((m, i) => colorByMacro.set(m.id, MACRO_PALETTE[i % MACRO_PALETTE.length]));
    return { macros, colorByMacro };
  }, [nodes, rootId]);

  const metricLabels = useMemo(() => {
    const out: Record<string, string> = {};
    for (const m of METRICS) out[m.key] = m.label;
    return out;
  }, []);

  const { visibleNodes, visibleLinks, labelDepth } = useMemo(() => {
    const include = (n: KnowledgeMapNode) => {
      if (!includeMethods && n.macroId === "methods") return false;
      if (scope === "macro") return n.id === rootId || n.depth <= 1;
      if (scope === "sub") return n.id === rootId || n.depth <= 2;
      return true;
    };

    const vn = nodes.filter(include);
    const ids = new Set(vn.map((n) => n.id));
    const vl = links.filter((l) => ids.has(l.source) && ids.has(l.target));
    return {
      visibleNodes: vn,
      visibleLinks: vl,
      labelDepth: scope === "macro" ? 1 : 2,
    };
  }, [includeMethods, links, nodes, rootId, scope]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-white/60">
          <span className="font-semibold text-white/80">Layout</span>
          <button
            type="button"
            onClick={() => setLayout("tree")}
            className={`rounded-full border px-3 py-1 font-semibold ${
              layout === "tree"
                ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"
            }`}
          >
            Tree (A)
          </button>
          <button
            type="button"
            onClick={() => setLayout("graph")}
            className={`rounded-full border px-3 py-1 font-semibold ${
              layout === "graph"
                ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"
            }`}
          >
            Graph
          </button>

          <span className="font-semibold text-white/80">Scope</span>
          <button
            type="button"
            onClick={() => setScope("macro")}
            className={`rounded-full border px-3 py-1 font-semibold ${
              scope === "macro"
                ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"
            }`}
          >
            Macro
          </button>
          <button
            type="button"
            onClick={() => setScope("sub")}
            className={`rounded-full border px-3 py-1 font-semibold ${
              scope === "sub"
                ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"
            }`}
          >
            Subfields
          </button>
          <button
            type="button"
            onClick={() => setScope("full")}
            className={`rounded-full border px-3 py-1 font-semibold ${
              scope === "full"
                ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"
            }`}
          >
            Full
          </button>

          <span className="ml-2 font-semibold text-white/80">Metric</span>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as KnowledgeMapMetricKey)}
            className="rounded-xl border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-white/85 outline-none focus:border-cyan-400/60"
          >
            {METRICS.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>

          <label className="ml-2 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-white/70 hover:bg-white/[0.05]">
            <input
              type="checkbox"
              checked={includeMethods}
              onChange={(e) => setIncludeMethods(e.target.checked)}
              className="h-3.5 w-3.5 accent-cyan-400"
            />
            Include Methods
          </label>
        </div>
        <div className="text-xs text-white/45">
          Node color = maturity, size = {METRICS.find((m) => m.key === metric)?.label ?? metric}. Border = macro group.
        </div>
      </div>

      {layout === "tree" ? (
        <ProgressTree
          rootId={rootId}
          nodes={visibleNodes.map((n) => ({
            id: n.id,
            name: n.name,
            depth: n.depth,
            parentId: n.parentId,
            macroId: n.macroId,
            macroName: n.macroName,
            metrics: n.metrics,
          }))}
          height={height}
          metricKey={metric}
          metricLabels={metricLabels}
          labelDepth={labelDepth}
          collapseDepth={scope === "full" ? 2 : 99}
          macroColors={Object.fromEntries(macroInfo.colorByMacro.entries())}
        />
      ) : (
        <ProgressGraph
          nodes={visibleNodes.map((n) => ({
            id: n.id,
            name: n.name,
            depth: n.depth,
            score: clampScore(n.metrics[metric]),
            macroId: n.macroId,
            macroName: n.macroName,
            metrics: n.metrics,
          }))}
          links={visibleLinks}
          height={height}
          metricKey={metric}
          metricLabels={metricLabels}
          labelDepth={labelDepth}
          macroColors={Object.fromEntries(macroInfo.colorByMacro.entries())}
        />
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-white/50">
        <span className="mr-1 font-semibold text-white/65">Macro</span>
        {macroInfo.macros
          .filter((m) => includeMethods || m.id !== "methods")
          .map((m) => (
            <span
              key={m.id}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.02] px-2.5 py-1"
            >
              <span
                className="h-2 w-2 rounded-sm"
                style={{
                  background: macroInfo.colorByMacro.get(m.id) ?? "rgba(255,255,255,0.4)",
                  boxShadow: `0 0 12px ${macroInfo.colorByMacro.get(m.id) ?? "rgba(255,255,255,0.25)"}`,
                }}
              />
              <span>{m.name}</span>
            </span>
          ))}
      </div>
    </div>
  );
}
