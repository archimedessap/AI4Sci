import type { DimensionKey } from "@/lib/progress/types";

export type DailyUpdateEntry = {
  id: string;
  date: string; // YYYY-MM-DD
  sourcePath: string;
  sourceHash: string;
  sourceType?: "manual" | "catalog";
  summary: string;
  highlights: string[];
  dimensions: Record<DimensionKey, number>; // sum ~= 100
  tags: string[];
  confidence: number; // 0..1
  mode: "llm" | "heuristic";
  classifiedAt: string; // ISO
  raw?: string; // optional, only when generated with --include-raw
};

export type DailyUpdatesData = {
  version: string;
  updatedAt: string;
  entries: DailyUpdateEntry[];
  stats?: {
    total?: number;
    changed?: number;
    skipped?: number;
    sourceTypes?: Record<string, number>;
  };
};
