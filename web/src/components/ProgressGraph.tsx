"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ECharts } from "@/components/ECharts";
import { scoreToMaturity } from "@/lib/progress/compute";
import type { MaturityLevel } from "@/lib/progress/types";
import { maturityColor } from "@/lib/ui/colors";

type GraphNode = {
  id: string;
  name: string;
  depth: number;
  score: number;
  maturity?: MaturityLevel;
  macroId?: string;
  macroName?: string;
  metrics?: Record<string, number>;
};

type GraphLink = { source: string; target: string };

export function ProgressGraph({
  nodes,
  links,
  metricKey,
  metricLabels,
  macroColors,
  labelDepth = 1,
  height = 520,
}: {
  nodes: GraphNode[];
  links: GraphLink[];
  metricKey?: string;
  metricLabels?: Record<string, string>;
  macroColors?: Record<string, string>;
  labelDepth?: number;
  height?: number;
}) {
  const router = useRouter();

  const option: EChartsOption = useMemo(() => {
    const key = metricKey?.trim() || "";
    const maxScore = Math.max(
      1,
      ...nodes.map((n) => {
        if (key && n.metrics && typeof n.metrics[key] === "number") return n.metrics[key];
        return n.score;
      }),
    );
    const chartNodes = nodes.map((n) => {
      const score = (() => {
        if (key && n.metrics && typeof n.metrics[key] === "number") return n.metrics[key];
        return n.score;
      })();
      const maturity = n.maturity ?? scoreToMaturity(score);
      const size = 14 + 34 * Math.sqrt(Math.max(0, score) / maxScore);
      const color = maturityColor(maturity);
      const macroBorder = n.macroId ? macroColors?.[n.macroId] : undefined;
      return {
        id: n.id,
        name: n.name,
        value: score,
        category: n.depth,
        macroId: n.macroId,
        macroName: n.macroName,
        metrics: n.metrics,
        symbolSize: size,
        itemStyle: {
          color,
          shadowBlur: 24,
          shadowColor: color,
          borderColor: macroBorder ?? "rgba(255,255,255,0.10)",
          borderWidth: macroBorder ? 2 : 1,
        },
        label: {
          show: n.depth <= labelDepth,
          color: "rgba(255,255,255,0.85)",
          fontSize: 12,
        },
        emphasis: { label: { show: true } },
      };
    });

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { dataType?: string; value?: unknown; name?: unknown; data?: unknown };
          if (p?.dataType !== "node") return "";
          const name = typeof p.name === "string" ? p.name : "Node";
          const data = p.data && typeof p.data === "object" ? (p.data as Record<string, unknown>) : {};
          const score = typeof p.value === "number" ? p.value : Number(p.value ?? 0);
          const macroName = typeof data.macroName === "string" ? data.macroName : "";
          const metricsRaw = data.metrics;
          const metrics: Record<string, number> =
            metricsRaw && typeof metricsRaw === "object" ? (metricsRaw as Record<string, number>) : {};
          const label = (k: string) => metricLabels?.[k] ?? k;
          const fmt = (v: unknown) => (typeof v === "number" ? v.toFixed(1) : "-");

          const selectedKey = key || "score";
          const selectedLabel = key ? label(key) : "Score";
          const selectedValue = fmt(score);

          const rows: string[] = [];
          const addRow = (k: string) => {
            const v = metrics?.[k];
            if (typeof v !== "number") return;
            const isSelected = k === selectedKey;
            rows.push(
              `<div style="display:flex;justify-content:space-between;gap:12px;${isSelected ? "font-weight:700" : "opacity:.85"}"><span>${label(
                k,
              )}</span><span style="font-variant-numeric:tabular-nums">${fmt(v)}</span></div>`,
            );
          };

          // Show a compact profile.
          addRow("overall");
          addRow("data");
          addRow("model");
          addRow("predict");
          addRow("experiment");
          addRow("explain");
          addRow("tooling");
          addRow("autonomy");

          const macroLine = macroName
            ? `<div style="opacity:.65;margin-top:2px">${macroName}</div>`
            : "";

          const selectedLine = `<div style="opacity:.85;margin-top:6px"><span style="font-weight:700">${selectedLabel}</span>: ${selectedValue}</div>`;
          const table = rows.length
            ? `<div style="margin-top:6px;line-height:1.45">${rows.join("")}</div>`
            : "";

          return `<div style="font-weight:700">${name}</div>${macroLine}${selectedLine}${table}<div style="opacity:.6;margin-top:6px">Click to open</div>`;
        },
      },
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          data: chartNodes,
          links: links.map((l) => ({
            ...l,
            lineStyle: { color: "rgba(255,255,255,0.16)", width: 1, curveness: 0 },
          })),
          force: {
            repulsion: 120,
            gravity: 0.08,
            edgeLength: [60, 140],
            friction: 0.2,
          },
          emphasis: { focus: "adjacency" },
          labelLayout: { hideOverlap: true },
        },
      ],
    } satisfies EChartsOption;
  }, [labelDepth, links, macroColors, metricKey, metricLabels, nodes]);

  return (
    <ECharts
      option={option}
      style={{ height }}
      onEvents={{
        click: (params: unknown) => {
          const p = params as { dataType?: string; data?: { id?: unknown } };
          if (p?.dataType !== "node") return;
          const id = p?.data?.id;
          if (typeof id !== "string") return;
          router.push(`/domain/${encodeURIComponent(id)}`);
        },
      }}
    />
  );
}
