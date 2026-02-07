import "server-only";

import { computeProgress } from "./compute";
import type {
  DimensionKey,
  DimensionMetrics,
  OverridesData,
  ProgressDataBase,
  ProgressDataComputed,
  ProgressNodeBase,
} from "./types";
import { readAutoOverridesData, readBaseData, readOverridesData } from "./storage.server";

function mergeDimension(
  base: DimensionMetrics | undefined,
  override: Partial<DimensionMetrics> | undefined,
): DimensionMetrics {
  const next: DimensionMetrics = { score: base?.score ?? override?.score ?? 0 };
  if (base) Object.assign(next, base);
  if (override) Object.assign(next, override);
  return next;
}

function mergeNode(
  baseNode: ProgressNodeBase,
  overrideNode: OverridesData["nodes"][string],
): ProgressNodeBase {
  const next: ProgressNodeBase = { ...baseNode };

  if (overrideNode.name !== undefined) next.name = overrideNode.name;
  if (overrideNode.description !== undefined) next.description = overrideNode.description;
  if (overrideNode.order !== undefined) next.order = overrideNode.order;

  if (overrideNode.overall) {
    next.overall = { ...(baseNode.overall ?? {}), ...(overrideNode.overall ?? {}) };
  }

  if (overrideNode.dimensions) {
    next.dimensions = { ...(baseNode.dimensions ?? {}) };
    for (const dimKey of Object.keys(overrideNode.dimensions)) {
      const dk = dimKey as DimensionKey;
      next.dimensions[dk] = mergeDimension(
        baseNode.dimensions?.[dk],
        overrideNode.dimensions[dk],
      );
    }
  }

  return next;
}

function applyOverrides(base: ProgressDataBase, overrides: OverridesData): ProgressDataBase {
  const nextNodes: Record<string, ProgressNodeBase> = { ...base.nodes };
  for (const [id, overrideNode] of Object.entries(overrides.nodes ?? {})) {
    if (!nextNodes[id]) continue;
    nextNodes[id] = mergeNode(nextNodes[id], overrideNode);
  }

  return { ...base, nodes: nextNodes };
}

export function getProgressData(): ProgressDataComputed {
  const base = readBaseData();
  const autoOverrides = readAutoOverridesData();
  const overrides = readOverridesData();
  const mergedAuto = applyOverrides(base, autoOverrides);
  const mergedManual = applyOverrides(mergedAuto, overrides);
  return computeProgress(mergedManual);
}
