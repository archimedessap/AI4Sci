import "server-only";

import fs from "node:fs";
import path from "node:path";

import { z } from "zod";

const LeafSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    macroId: z.string().optional(),
    macroName: z.string().optional(),
  })
  .passthrough();

const NumOrNullArray = z.array(z.union([z.number(), z.null()]));

const SnapshotSchema = z
  .object({
    date: z.string(),
    ts: z.string(),
    generatedAt: z.string().optional(),
    autoUpdatedAt: z.string().optional(),
    manualUpdatedAt: z.string().optional(),
    overall: NumOrNullArray,
    data: NumOrNullArray,
    model: NumOrNullArray,
    predict: NumOrNullArray,
    experiment: NumOrNullArray,
    explain: NumOrNullArray,
    confidence: NumOrNullArray.optional(),
    aiRecent: NumOrNullArray.optional(),
    penetration: NumOrNullArray.optional(),
    growthNorm: NumOrNullArray.optional(),
    tooling: NumOrNullArray.optional(),
    autonomy: NumOrNullArray.optional(),
  })
  .passthrough();

const ProgressHistorySchema = z
  .object({
    version: z.string(),
    updatedAt: z.string(),
    rootId: z.string(),
    leaves: z.array(LeafSchema),
    snapshots: z.array(SnapshotSchema),
    stats: z
      .object({
        leaves: z.number().int().optional(),
        snapshots: z.number().int().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

export type ProgressHistory = z.infer<typeof ProgressHistorySchema>;

let cached: ProgressHistory | null = null;
let cachedMtimeMs = 0;

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

export function readProgressHistory(): ProgressHistory | null {
  const p = dataPath("progress_history.json");
  if (!fs.existsSync(p)) return null;
  try {
    const stat = fs.statSync(p);
    const mtimeMs = stat.mtimeMs || 0;
    if (cached && cachedMtimeMs === mtimeMs) return cached;
    const raw = fs.readFileSync(p, "utf8");
    cached = ProgressHistorySchema.parse(JSON.parse(raw));
    cachedMtimeMs = mtimeMs;
    return cached;
  } catch {
    return null;
  }
}
