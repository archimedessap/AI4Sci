"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ECharts } from "@/components/ECharts";

export type DepthAgencyPoint = {
  id: string;
  name: string;
  macroId: string;
  macroName: string;
  agency: number; // 0..100
  depth: number; // 0..100
  aiRecent: number;
  autonomy: number; // 0..100
  tooling: number; // 0..100
  experiment: number; // 0..100
  layers: { phenomena: number; empirical: number; theory: number; principles: number }; // 0..100
};

const MACRO_PALETTE = ["#22d3ee", "#a78bfa", "#4ade80", "#fb7185", "#fbbf24", "#60a5fa"];

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function safeNum(v: unknown) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function DepthAgencyChart({
  points,
  height = 520,
}: {
  points: DepthAgencyPoint[];
  height?: number;
}) {
  const router = useRouter();

  const option: EChartsOption = useMemo(() => {
    const macros = Array.from(
      new Map(points.map((p) => [p.macroId, p.macroName] as const)).entries(),
    ).map(([id, name]) => ({ id, name }));
    const macroColor = new Map<string, string>();
    macros.forEach((m, i) => macroColor.set(m.id, MACRO_PALETTE[i % MACRO_PALETTE.length]));

    const maxAi = Math.max(1, ...points.map((p) => Math.max(0, p.aiRecent || 0)));
    const topByAi = new Set(
      points
        .slice()
        .sort((a, b) => (b.aiRecent ?? 0) - (a.aiRecent ?? 0))
        .slice(0, 14)
        .map((p) => p.id),
    );

    const seriesData = points.map((p) => {
      const ai = Math.max(0, safeNum(p.aiRecent));
      const sz = 6 + 18 * Math.sqrt(ai / maxAi);
      const color = macroColor.get(p.macroId) ?? "rgba(255,255,255,0.65)";
      return {
        name: p.name,
        value: [clamp(p.agency, 0, 100), clamp(p.depth, 0, 100), ai],
        id: p.id,
        macroId: p.macroId,
        macroName: p.macroName,
        agency: p.agency,
        depth: p.depth,
        aiRecent: p.aiRecent,
        autonomy: p.autonomy,
        tooling: p.tooling,
        experiment: p.experiment,
        layers: p.layers,
        symbolSize: sz,
        itemStyle: { color, opacity: 0.85, shadowBlur: 18, shadowColor: `${color}77` },
        label: {
          show: topByAi.has(p.id) || p.depth >= 55,
          formatter: p.name,
          color: "rgba(255,255,255,0.75)",
          fontSize: 10,
          position: "right" as const,
        },
      };
    });

    return {
      backgroundColor: "transparent",
      grid: { left: 62, right: 22, top: 22, bottom: 54 },
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { data?: unknown };
          const d = p?.data;
          if (!d || typeof d !== "object") return "";
          const dd = d as Record<string, unknown>;
          const layersRaw = dd.layers;
          const layers =
            layersRaw && typeof layersRaw === "object"
              ? (layersRaw as Record<string, unknown>)
              : {};
          const rows = [
            `<div style="font-weight:700">${String(dd.name || "")}</div>`,
            `<div style="opacity:.65;margin-top:2px">${String(dd.macroName || "")}</div>`,
            `<div style="margin-top:8px;display:flex;justify-content:space-between;gap:12px"><span style="opacity:.8">Agency</span><span style="font-weight:700">${safeNum(
              dd.agency,
            ).toFixed(1)}</span></div>`,
            `<div style="display:flex;justify-content:space-between;gap:12px"><span style="opacity:.8">Depth</span><span style="font-weight:700">${safeNum(
              dd.depth,
            ).toFixed(1)}</span></div>`,
            `<div style="margin-top:8px;opacity:.9">Autonomy ${safeNum(dd.autonomy).toFixed(
              0,
            )}% · Tooling ${safeNum(dd.tooling).toFixed(0)}% · Experiment ${safeNum(
              dd.experiment,
              ).toFixed(0)}%</div>`,
            `<div style="margin-top:6px;opacity:.85">Phen ${safeNum(layers.phenomena).toFixed(
              0,
            )}% · Emp ${safeNum(layers.empirical).toFixed(0)}% · Theory ${safeNum(
              layers.theory,
            ).toFixed(0)}% · Prin ${safeNum(layers.principles).toFixed(0)}%</div>`,
            `<div style="margin-top:6px;opacity:.65">AI×Domain (5y) papers: ${Math.trunc(
              safeNum(dd.aiRecent),
            )}</div>`,
            `<div style="opacity:.6;margin-top:6px">Click to open</div>`,
          ];
          return rows.join("");
        },
      },
      xAxis: {
        type: "value",
        min: 0,
        max: 100,
        name: "Agency (Assistant → Collaborator → Autonomous)",
        nameTextStyle: { color: "rgba(255,255,255,0.55)", fontSize: 11, padding: [0, 0, 0, 0] },
        axisLabel: { color: "rgba(255,255,255,0.65)" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        name: "Epistemic Depth (Phenomena → Principles)",
        nameTextStyle: { color: "rgba(255,255,255,0.55)", fontSize: 11, padding: [0, 0, 0, 0] },
        axisLabel: { color: "rgba(255,255,255,0.65)" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
      },
      series: [
        {
          type: "scatter",
          data: seriesData,
          symbolSize: (val: unknown, params: unknown) => {
            const p = params as { data?: { symbolSize?: unknown } };
            const sz = Number(p?.data?.symbolSize);
            return Number.isFinite(sz) ? sz : 10;
          },
          emphasis: {
            focus: "self",
            itemStyle: { opacity: 0.95, shadowBlur: 28, shadowColor: "rgba(255,255,255,0.25)" },
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "rgba(255,255,255,0.18)", type: "dashed" },
            data: [{ xAxis: 33 }, { xAxis: 66 }],
          },
          markArea: {
            silent: true,
            itemStyle: { color: "rgba(255,255,255,0.03)" },
            data: [
              [
                { name: "Assistant", xAxis: 0, yAxis: 0 },
                { xAxis: 33, yAxis: 100 },
              ],
              [
                { name: "Collaborator", xAxis: 33, yAxis: 0 },
                { xAxis: 66, yAxis: 100 },
              ],
              [
                { name: "Autonomous", xAxis: 66, yAxis: 0 },
                { xAxis: 100, yAxis: 100 },
              ],
            ],
            label: { color: "rgba(255,255,255,0.35)", fontSize: 10 },
          },
        },
      ],
    } satisfies EChartsOption;
  }, [points]);

  return (
    <ECharts
      option={option}
      style={{ height }}
      onEvents={{
        click: (params: unknown) => {
          const p = params as { data?: { id?: unknown } };
          const id = p?.data?.id;
          if (typeof id !== "string") return;
          router.push(`/domain/${encodeURIComponent(id)}`);
        },
      }}
    />
  );
}
