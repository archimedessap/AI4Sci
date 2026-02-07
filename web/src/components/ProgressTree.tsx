"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ECharts } from "@/components/ECharts";
import { scoreToMaturity } from "@/lib/progress/compute";
import { maturityColor } from "@/lib/ui/colors";

type TreeNode = {
  id: string;
  name: string;
  depth: number;
  parentId: string | null;
  macroId?: string;
  macroName?: string;
  metrics?: Record<string, number>;
};

type TreeDatum = {
  id: string;
  name: string;
  value: number;
  depth: number;
  macroId?: string;
  macroName?: string;
  metrics?: Record<string, number>;
  children?: TreeDatum[];
  collapsed?: boolean;
  symbolSize?: number;
  itemStyle?: Record<string, unknown>;
  label?: Record<string, unknown>;
  lineStyle?: Record<string, unknown>;
};

type TooltipMetric = { k: string; v: number };

function clampScore(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function buildTreeData({
  rootId,
  nodes,
  metricKey,
  macroColors,
  labelDepth,
  collapseDepth,
}: {
  rootId: string;
  nodes: TreeNode[];
  metricKey: string;
  macroColors?: Record<string, string>;
  labelDepth: number;
  collapseDepth: number;
}): TreeDatum | null {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const childrenById = new Map<string, string[]>();
  for (const n of nodes) childrenById.set(n.id, []);
  for (const n of nodes) {
    if (!n.parentId) continue;
    if (!childrenById.has(n.parentId)) continue;
    childrenById.get(n.parentId)!.push(n.id);
  }
  for (const list of childrenById.values()) list.sort((a, b) => a.localeCompare(b));

  const root = byId.get(rootId);
  if (!root) return null;

  const make = (id: string): TreeDatum => {
    const n = byId.get(id)!;
    const score = clampScore(n.metrics?.[metricKey] ?? 0);
    const maturity = scoreToMaturity(score);
    const color = maturityColor(maturity);
    const macroBorder = n.macroId ? macroColors?.[n.macroId] : undefined;
    const size = id === rootId ? 34 : 10 + 18 * Math.sqrt(score / 100);

    const metrics = n.metrics ?? {};
    const tooltipMetrics: TooltipMetric[] = [
      "overall",
      "data",
      "model",
      "predict",
      "experiment",
      "explain",
      "tooling",
      "autonomy",
    ]
      .filter((k) => typeof metrics[k] === "number")
      .map((k) => ({ k, v: metrics[k] }));

    const children = (childrenById.get(id) ?? []).map(make);
    return {
      id: n.id,
      name: n.name,
      value: score,
      depth: n.depth,
      macroId: n.macroId,
      macroName: n.macroName,
      metrics: n.metrics,
      children: children.length ? children : undefined,
      collapsed: n.depth >= collapseDepth,
      symbolSize: size,
      itemStyle: {
        color,
        borderColor: macroBorder ?? "rgba(255,255,255,0.12)",
        borderWidth: macroBorder ? 2 : 1,
        shadowBlur: 18,
        shadowColor: color,
      },
      lineStyle: {
        color: macroBorder ? `${macroBorder}55` : "rgba(255,255,255,0.14)",
        width: macroBorder ? 1.2 : 1,
      },
      label: {
        show: n.depth <= labelDepth,
        color: "rgba(255,255,255,0.84)",
        fontSize: n.depth <= 1 ? 13 : 12,
        backgroundColor: "rgba(0,0,0,0.0)",
        formatter: () => `${n.name}`,
      },
      // Attach a compact tooltip profile as meta.
      // ECharts will expose it at params.data.tooltipMetrics.
      ...(tooltipMetrics.length ? { tooltipMetrics } : {}),
    } as TreeDatum & { tooltipMetrics?: TooltipMetric[] };
  };

  return make(rootId);
}

export function ProgressTree({
  rootId,
  nodes,
  metricKey,
  metricLabels,
  macroColors,
  labelDepth = 2,
  collapseDepth = 4,
  height = 560,
}: {
  rootId: string;
  nodes: TreeNode[];
  metricKey: string;
  metricLabels?: Record<string, string>;
  macroColors?: Record<string, string>;
  labelDepth?: number;
  collapseDepth?: number;
  height?: number;
}) {
  const router = useRouter();

  const option: EChartsOption = useMemo(() => {
    const tree = buildTreeData({
      rootId,
      nodes,
      metricKey,
      macroColors,
      labelDepth,
      collapseDepth,
    });
    if (!tree) {
      return { series: [] } satisfies EChartsOption;
    }

    const key = metricKey?.trim() || "";
    const label = (k: string) => metricLabels?.[k] ?? k;
    const fmt = (v: unknown) => (typeof v === "number" ? v.toFixed(1) : "-");

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        triggerOn: "mousemove",
        formatter: (params: unknown) => {
          const p = params as { dataType?: string; name?: unknown; value?: unknown; data?: unknown };
          if (p?.dataType !== "node") return "";
          const name = typeof p.name === "string" ? p.name : "Node";
          const data =
            p.data && typeof p.data === "object" ? (p.data as Record<string, unknown>) : {};
          const score = typeof p.value === "number" ? p.value : Number(p.value ?? 0);
          const macroName = typeof data.macroName === "string" ? data.macroName : "";

          const selectedLine = key
            ? `<div style=\"opacity:.85;margin-top:6px\"><span style=\"font-weight:700\">${label(
                key,
              )}</span>: ${fmt(score)}</div>`
            : `<div style=\"opacity:.85;margin-top:6px\"><span style=\"font-weight:700\">Score</span>: ${fmt(
                score,
              )}</div>`;

          const tmRaw = data.tooltipMetrics;
          const tm: TooltipMetric[] = Array.isArray(tmRaw)
            ? (tmRaw as TooltipMetric[])
            : [];
          const rows = tm
            .map((r) => {
              const k2 = String(r.k ?? "");
              const v2 = r.v;
              const isSelected = k2 === key;
              return `<div style=\"display:flex;justify-content:space-between;gap:12px;${
                isSelected ? "font-weight:700" : "opacity:.85"
              }\"><span>${label(k2)}</span><span style=\"font-variant-numeric:tabular-nums\">${fmt(
                v2,
              )}</span></div>`;
            })
            .join("");

          const macroLine = macroName
            ? `<div style=\"opacity:.65;margin-top:2px\">${macroName}</div>`
            : "";

          return `<div style=\"font-weight:700\">${name}</div>${macroLine}${selectedLine}${
            rows ? `<div style=\"margin-top:6px;line-height:1.45\">${rows}</div>` : ""
          }<div style=\"opacity:.6;margin-top:6px\">Click to open</div>`;
        },
      },
      series: [
        {
          type: "tree",
          data: [tree],
          top: "2%",
          left: "2%",
          bottom: "2%",
          right: "16%",
          roam: true,
          orient: "LR",
          layout: "orthogonal",
          symbol: "circle",
          expandAndCollapse: true,
          initialTreeDepth: -1,
          lineStyle: {
            curveness: 0,
          },
          label: {
            position: "right",
            verticalAlign: "middle",
            align: "left",
          },
          leaves: {
            label: {
              position: "right",
              verticalAlign: "middle",
              align: "left",
            },
          },
          emphasis: { focus: "descendant" },
          animationDuration: 300,
          animationDurationUpdate: 300,
        },
      ],
    } satisfies EChartsOption;
  }, [collapseDepth, labelDepth, macroColors, metricKey, metricLabels, nodes, rootId]);

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
