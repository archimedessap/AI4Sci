"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";
import type { CSSProperties } from "react";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function ECharts({
  option,
  className,
  style,
  onEvents,
}: {
  option: EChartsOption;
  className?: string;
  style?: CSSProperties;
  onEvents?: Record<string, (params: unknown) => void>;
}) {
  return (
    <ReactECharts
      option={option}
      className={className}
      style={style}
      notMerge
      lazyUpdate
      onEvents={onEvents}
      opts={{ renderer: "canvas" }}
    />
  );
}
