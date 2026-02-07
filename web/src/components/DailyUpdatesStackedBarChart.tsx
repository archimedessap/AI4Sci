"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { ECharts } from "@/components/ECharts";
import type { DimensionKey } from "@/lib/progress/types";
import type { DailyUpdateEntry } from "@/lib/updates/types";

const DIM_COLORS: Record<DimensionKey, string> = {
  data: "#22d3ee",
  model: "#a78bfa",
  predict: "#4ade80",
  experiment: "#fb7185",
  explain: "#fbbf24",
};

export function DailyUpdatesStackedBarChart({
  entries,
  dimensions,
  height = 360,
}: {
  entries: DailyUpdateEntry[];
  dimensions: Array<{ key: DimensionKey; label: string }>;
  height?: number;
}) {
  const option: EChartsOption = useMemo(() => {
    const rows = [...entries].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    const dates = rows.map((e) => e.date);

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
      },
      legend: {
        top: 0,
        textStyle: { color: "rgba(255,255,255,0.65)", fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
      },
      grid: { left: 44, right: 18, top: 42, bottom: 34, containLabel: true },
      xAxis: {
        type: "category",
        data: dates,
        axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 11 },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.18)" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        max: 100,
        axisLabel: { color: "rgba(255,255,255,0.55)", fontSize: 11 },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.10)" } },
      },
      series: dimensions.map((d) => ({
        name: d.label,
        type: "bar",
        stack: "total",
        barMaxWidth: 34,
        emphasis: { focus: "series" },
        itemStyle: { color: DIM_COLORS[d.key] },
        data: rows.map((e) => Number(e.dimensions?.[d.key] ?? 0)),
      })),
    } satisfies EChartsOption;
  }, [dimensions, entries]);

  return <ECharts option={option} style={{ height }} />;
}

