"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ECharts } from "@/components/ECharts";
import type { DimensionKey, MaturityLevel } from "@/lib/progress/types";
import { maturityColor } from "@/lib/ui/colors";

type Row = {
  id: string;
  name: string;
  maturity: MaturityLevel;
  values: Record<DimensionKey, number>;
};

export function ProgressHeatmap({
  dimensions,
  rows,
  height = 520,
}: {
  dimensions: Array<{ key: DimensionKey; label: string }>;
  rows: Row[];
  height?: number;
}) {
  const router = useRouter();

  const option: EChartsOption = useMemo(() => {
    const xLabels = dimensions.map((d) => d.label);
    const yLabels = rows.map((r) => r.name);
    const data: Array<[number, number, number, string]> = [];

    for (let yi = 0; yi < rows.length; yi += 1) {
      const row = rows[yi];
      for (let xi = 0; xi < dimensions.length; xi += 1) {
        const dim = dimensions[xi];
        const v = row.values[dim.key] ?? 0;
        data.push([xi, yi, v, row.id]);
      }
    }

    return {
      backgroundColor: "transparent",
      tooltip: {
        position: "top",
        formatter: (params: unknown) => {
          const p = params as { data?: unknown };
          const tuple = Array.isArray(p?.data) ? p.data : [];
          const [xi, yi, v] = tuple as [number, number, number];
          const dim = dimensions[xi]?.label ?? "";
          const row = rows[yi]?.name ?? "";
          return `<div style="font-weight:600">${row}</div><div style="opacity:.85">${dim}: ${Number(v).toFixed(
            1,
          )}</div><div style="opacity:.6">Click to open</div>`;
        },
      },
      grid: { left: 140, right: 20, top: 24, bottom: 46 },
      xAxis: {
        type: "category",
        data: xLabels,
        axisLabel: { color: "rgba(255,255,255,0.7)", fontSize: 11 },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
      },
      yAxis: {
        type: "category",
        data: yLabels,
        axisLabel: {
          color: (_value?: string | number, index?: number) =>
            maturityColor(rows[index ?? 0]?.maturity ?? 0),
          fontSize: 11,
        },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
      },
      visualMap: {
        min: 0,
        max: 100,
        calculable: false,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        text: ["High", "Low"],
        textStyle: { color: "rgba(255,255,255,0.6)", fontSize: 10 },
        inRange: { color: ["#0b1220", "#22d3ee", "#a78bfa", "#fb7185"] },
      },
      series: [
        {
          name: "Score",
          type: "heatmap",
          data: data.map(([x, y, v, id]) => ({
            value: [x, y, v],
            id,
            itemStyle: { borderColor: "rgba(255,255,255,0.06)" },
          })),
          emphasis: {
            itemStyle: { shadowBlur: 16, shadowColor: "rgba(255,255,255,0.25)" },
          },
        },
      ],
    } satisfies EChartsOption;
  }, [dimensions, rows]);

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
