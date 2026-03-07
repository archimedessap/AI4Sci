"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ECharts } from "@/components/ECharts";
import type {
  FirstPrinciplesAxisKey,
  FirstPrinciplesDomain,
} from "@/lib/first-principles/types";

const MACRO_PALETTE = [
  "#22d3ee",
  "#a78bfa",
  "#4ade80",
  "#fb7185",
  "#fbbf24",
  "#60a5fa",
  "#f97316",
  "#2dd4bf",
];

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function safeNum(v: unknown) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function FirstPrinciplesScatterChart({
  domains,
  xKey,
  yKey,
  xLabel,
  yLabel,
  height = 420,
}: {
  domains: FirstPrinciplesDomain[];
  xKey: FirstPrinciplesAxisKey;
  yKey: FirstPrinciplesAxisKey;
  xLabel: string;
  yLabel: string;
  height?: number;
}) {
  const router = useRouter();

  const option: EChartsOption = useMemo(() => {
    const macros = Array.from(
      new Map(domains.map((d) => [d.macroId, d.macroName] as const)).entries(),
    ).map(([id, name]) => ({ id, name }));
    const macroColor = new Map<string, string>();
    macros.forEach((m, i) => macroColor.set(m.id, MACRO_PALETTE[i % MACRO_PALETTE.length]));

    const maxAi = Math.max(1, ...domains.map((d) => Math.max(0, d.signals.aiRecent || 0)));
    const topByClosure = new Set(
      domains
        .slice()
        .sort((a, b) => b.closureReadiness - a.closureReadiness)
        .slice(0, 12)
        .map((d) => d.id),
    );

    const seriesData = domains.map((domain) => {
      const ai = Math.max(0, safeNum(domain.signals.aiRecent));
      const size = 8 + 18 * Math.sqrt(ai / maxAi);
      const color = macroColor.get(domain.macroId) ?? "rgba(255,255,255,0.7)";
      return {
        id: domain.id,
        name: domain.name,
        macroName: domain.macroName,
        profileLabel: domain.profile.label,
        summary: domain.profile.summary,
        value: [
          clamp(domain.axes[xKey] ?? 0, 0, 100),
          clamp(domain.axes[yKey] ?? 0, 0, 100),
          ai,
        ],
        symbolSize: size,
        itemStyle: { color, opacity: 0.86, shadowBlur: 18, shadowColor: `${color}77` },
        label: {
          show: topByClosure.has(domain.id) || domain.closureReadiness >= 50,
          formatter: domain.name,
          color: "rgba(255,255,255,0.75)",
          fontSize: 10,
          position: "right" as const,
        },
        closureReadiness: domain.closureReadiness,
        instrumentalismGap: domain.gaps.instrumentalism,
        theoryActionGap: domain.gaps.theoryAction,
        momentum7d: domain.signals.momentum7d,
        newPapers7d: domain.signals.newPapers7d,
      };
    });

    return {
      backgroundColor: "transparent",
      grid: { left: 60, right: 20, top: 16, bottom: 50 },
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { data?: unknown };
          const d = p?.data;
          if (!d || typeof d !== "object") return "";
          const dd = d as Record<string, unknown>;
          return [
            `<div style="font-weight:700">${String(dd.name || "")}</div>`,
            `<div style="opacity:.65;margin-top:2px">${String(dd.macroName || "")}</div>`,
            `<div style="margin-top:8px;display:flex;justify-content:space-between;gap:12px"><span style="opacity:.8">${xLabel}</span><span style="font-weight:700">${safeNum(
              (dd.value as unknown[] | undefined)?.[0],
            ).toFixed(1)}</span></div>`,
            `<div style="display:flex;justify-content:space-between;gap:12px"><span style="opacity:.8">${yLabel}</span><span style="font-weight:700">${safeNum(
              (dd.value as unknown[] | undefined)?.[1],
            ).toFixed(1)}</span></div>`,
            `<div style="display:flex;justify-content:space-between;gap:12px"><span style="opacity:.8">Closure</span><span style="font-weight:700">${safeNum(
              dd.closureReadiness,
            ).toFixed(1)}</span></div>`,
            `<div style="margin-top:6px;opacity:.88">${String(dd.profileLabel || "")}</div>`,
            `<div style="opacity:.75;margin-top:4px">${String(dd.summary || "")}</div>`,
            `<div style="margin-top:8px;opacity:.85">Gap(instr.) ${safeNum(dd.instrumentalismGap).toFixed(
              1,
            )} · Gap(theory-action) ${safeNum(dd.theoryActionGap).toFixed(1)}</div>`,
            `<div style="opacity:.8">7d momentum ${safeNum(dd.momentum7d).toFixed(
              1,
            )} · new papers ${Math.round(safeNum(dd.newPapers7d))}</div>`,
            `<div style="opacity:.65;margin-top:6px">Click to open</div>`,
          ].join("");
        },
      },
      xAxis: {
        type: "value",
        min: 0,
        max: 100,
        name: xLabel,
        nameTextStyle: { color: "rgba(255,255,255,0.55)", fontSize: 11, padding: [0, 0, 0, 0] },
        axisLabel: { color: "rgba(255,255,255,0.65)" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        name: yLabel,
        nameTextStyle: { color: "rgba(255,255,255,0.55)", fontSize: 11, padding: [0, 0, 0, 0] },
        axisLabel: { color: "rgba(255,255,255,0.65)" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
      },
      series: [
        {
          type: "scatter",
          data: seriesData,
          symbolSize: (value: unknown, params: unknown) => {
            const p = params as { data?: { symbolSize?: unknown } };
            const size = Number(p?.data?.symbolSize);
            return Number.isFinite(size) ? size : 10;
          },
          emphasis: {
            focus: "self",
            itemStyle: { opacity: 0.95, shadowBlur: 26, shadowColor: "rgba(255,255,255,0.22)" },
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "rgba(255,255,255,0.16)", type: "dashed" },
            data: [{ xAxis: 50 }, { yAxis: 50 }],
          },
        },
      ],
    } satisfies EChartsOption;
  }, [domains, xKey, xLabel, yKey, yLabel]);

  return (
    <ECharts
      option={option}
      style={{ height }}
      onEvents={{
        click: (params: unknown) => {
          const p = params as { data?: { id?: unknown } };
          if (typeof p?.data?.id !== "string") return;
          router.push(`/domain/${encodeURIComponent(p.data.id)}`);
        },
      }}
    />
  );
}
