"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { ECharts } from "@/components/ECharts";
import type { DimensionKey } from "@/lib/progress/types";

export function RadarChart({
  title,
  dimensions,
  values,
  height = 320,
}: {
  title?: string;
  dimensions: Array<{ key: DimensionKey; label: string }>;
  values: Record<DimensionKey, number>;
  height?: number;
}) {
  const option: EChartsOption = useMemo(() => {
    const indicator = dimensions.map((d) => ({
      name: d.label,
      max: 100,
    }));
    const data = dimensions.map((d) => values[d.key] ?? 0);

    return {
      backgroundColor: "transparent",
      title: title
        ? {
            text: title,
            left: "center",
            top: 0,
            textStyle: {
              color: "rgba(255,255,255,0.85)",
              fontSize: 12,
              fontWeight: 600,
            },
          }
        : undefined,
      radar: {
        indicator,
        radius: "62%",
        splitNumber: 5,
        axisName: { color: "rgba(255,255,255,0.7)", fontSize: 11 },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.10)" } },
        splitArea: { areaStyle: { color: ["rgba(255,255,255,0.02)"] } },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.12)" } },
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: data,
              areaStyle: { color: "rgba(34,211,238,0.18)" },
              lineStyle: { color: "rgba(34,211,238,0.9)" },
              itemStyle: { color: "rgba(167,139,250,0.95)" },
            },
          ],
        },
      ],
    } satisfies EChartsOption;
  }, [dimensions, title, values]);

  return <ECharts option={option} style={{ height }} />;
}

