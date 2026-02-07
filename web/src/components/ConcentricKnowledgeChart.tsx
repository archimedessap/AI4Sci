"use client";

import type { EChartsOption } from "echarts";
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ECharts } from "@/components/ECharts";

type DomainLevels = {
  id: string;
  name: string;
  levels: {
    phenomena: number; // 0..1
    empirical: number; // 0..1
    theory: number; // 0..1
    principles: number; // 0..1
  };
};

const LEVELS = [
  { key: "phenomena", label: "新现象 Phenomena", color: "#22d3ee" },
  { key: "empirical", label: "新经验定律 Empirical", color: "#4ade80" },
  { key: "theory", label: "新理论 Theory", color: "#a78bfa" },
  { key: "principles", label: "新原理 Principles", color: "#fb7185" },
] as const;

type LevelKey = (typeof LEVELS)[number]["key"];

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

export function ConcentricKnowledgeChart({
  domains,
  height = 520,
}: {
  domains: DomainLevels[];
  height?: number;
}) {
  const router = useRouter();

  const option: EChartsOption = useMemo(() => {
    const names = domains.map((d) => d.name);
    // Draw from outside -> inside: invert the radius axis, then stack series
    // from outermost -> innermost.
    const ringKeysOuterToInner: LevelKey[] = [
      "phenomena",
      "empirical",
      "theory",
      "principles",
    ];

    return {
      backgroundColor: "transparent",
      angleAxis: {
        type: "category",
        data: names,
        startAngle: 90,
        axisLabel: {
          color: "rgba(255,255,255,0.75)",
          fontSize: 11,
          rotate: 20,
        },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.12)" } },
      },
      radiusAxis: {
        min: 0,
        max: 4,
        interval: 1,
        inverse: true,
        axisLabel: {
          color: "rgba(255,255,255,0.45)",
          fontSize: 10,
          formatter: (v: number) => {
            // Direction: outside -> inside (outermost ring = Phenomena).
            if (v === 1) return "现象";
            if (v === 2) return "经验";
            if (v === 3) return "理论";
            if (v === 4) return "原理";
            return "";
          },
        },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.10)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
      },
      polar: { radius: "82%" },
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { dataIndex?: unknown };
          const idx = typeof p.dataIndex === "number" ? p.dataIndex : -1;
          const domain = idx >= 0 ? domains[idx] : undefined;
          if (!domain) return "";
          const lines = [
            `<div style="font-weight:600">${domain.name}</div>`,
            ...LEVELS.map((l) => {
              const v = domain.levels[l.key as LevelKey] ?? 0;
              return `<div style="opacity:.85"><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${l.color};margin-right:8px;box-shadow:0 0 12px ${l.color}55"></span>${l.label}: ${(Number(v) * 100).toFixed(0)}%</div>`;
            }),
            `<div style="opacity:.6;margin-top:6px">Click to open</div>`,
          ];
          return lines.join("");
        },
      },
      legend: {
        show: true,
        bottom: 0,
        textStyle: { color: "rgba(255,255,255,0.65)", fontSize: 11 },
        itemWidth: 10,
        itemHeight: 10,
        data: LEVELS.map((l) => l.label),
      },
      series: ringKeysOuterToInner.map((k) => {
        const meta = LEVELS.find((l) => l.key === k)!;
        return {
          name: meta.label,
          type: "bar",
          coordinateSystem: "polar",
          stack: "depth",
          roundCap: true,
          barWidth: 18,
          itemStyle: {
            color: meta.color,
            shadowBlur: 18,
            shadowColor: `${meta.color}55`,
            opacity: 0.92,
          },
          emphasis: {
            itemStyle: { shadowBlur: 28, shadowColor: `${meta.color}77` },
          },
          data: domains.map((d) => ({
            value: clamp01(d.levels[k] ?? 0),
            id: d.id,
          })),
        };
      }),
      graphic: [
        {
          type: "group",
          left: "center",
          top: "center",
          children: [
            {
              type: "text",
              style: {
                text: "知识\n深度",
                fill: "rgba(255,255,255,0.75)",
                font: "600 14px ui-sans-serif, system-ui",
                align: "center",
                verticalAlign: "middle",
              },
            },
          ],
        },
      ],
      animationDuration: 700,
    } satisfies EChartsOption;
  }, [domains]);

  return (
    <ECharts
      option={option}
      style={{ height }}
      onEvents={{
        click: (params: unknown) => {
          const p = params as { dataIndex?: unknown; data?: { id?: unknown } };
          const id = p?.data?.id;
          if (typeof id === "string") {
            router.push(`/domain/${encodeURIComponent(id)}`);
            return;
          }
          const idx = typeof p.dataIndex === "number" ? p.dataIndex : -1;
          const domain = idx >= 0 ? domains[idx] : undefined;
          if (domain) router.push(`/domain/${encodeURIComponent(domain.id)}`);
        },
      }}
    />
  );
}
