import { NextResponse } from "next/server";
import { z } from "zod";

import { DIMENSION_KEYS, type DimensionKey, type NodeOverride } from "@/lib/progress/types";
import { readOverridesData, writeOverridesData } from "@/lib/progress/storage.server";

export const dynamic = "force-dynamic";

function isAuthorized(req: Request) {
  const configured = process.env.ADMIN_TOKEN;
  if (!configured) return process.env.NODE_ENV !== "production";
  const auth = req.headers.get("authorization") ?? "";
  if (auth.startsWith("Bearer ")) return auth.slice("Bearer ".length) === configured;
  const alt = req.headers.get("x-admin-token");
  return alt === configured;
}

const DimensionKeySchema = z.enum(
  [...DIMENSION_KEYS] as unknown as [DimensionKey, ...DimensionKey[]],
);

const MaturitySchema = z.union([
  z.literal(0),
  z.literal(1),
  z.literal(2),
  z.literal(3),
  z.literal(4),
]);

const PatchSchema = z
  .object({
    name: z.string().optional(),
    description: z.string().optional(),
    order: z.number().int().optional(),
    overall: z
      .object({
        score: z.number().min(0).max(100).optional(),
        maturity: MaturitySchema.optional(),
        confidence: z.number().min(0).max(1).optional(),
        note: z.string().optional(),
      })
      .optional(),
    dimensions: z
      .record(
        DimensionKeySchema,
        z
          .object({
            score: z.number().min(0).max(100).optional(),
            maturity: MaturitySchema.optional(),
            confidence: z.number().min(0).max(1).optional(),
            note: z.string().optional(),
          })
          .partial(),
      )
      .optional(),
  })
  .partial();

const UpdateSchema = z.object({
  nodeId: z.string().min(1),
  patch: PatchSchema.optional(),
  clearNode: z.boolean().optional(),
  clearDimension: DimensionKeySchema.optional(),
});

export function GET(req: Request) {
  if (!isAuthorized(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  return NextResponse.json(readOverridesData());
}

export async function POST(req: Request) {
  if (!isAuthorized(req)) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => null);
  const parsed = UpdateSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_request", details: parsed.error.flatten() }, { status: 400 });
  }

  const { nodeId, patch, clearNode, clearDimension } = parsed.data;
  const overrides = readOverridesData();

  if (clearNode) {
    delete overrides.nodes[nodeId];
  } else if (clearDimension) {
    const node = overrides.nodes[nodeId];
    if (node?.dimensions) {
      delete node.dimensions[clearDimension];
      if (Object.keys(node.dimensions).length === 0) delete node.dimensions;
    }
    if (node && Object.keys(node).length === 0) delete overrides.nodes[nodeId];
  } else if (patch) {
    const existing: NodeOverride = overrides.nodes[nodeId] ?? {};
    const next: NodeOverride = { ...existing };
    if (patch.name !== undefined) next.name = patch.name;
    if (patch.description !== undefined) next.description = patch.description;
    if (patch.order !== undefined) next.order = patch.order;
    if (patch.overall) next.overall = { ...(existing.overall ?? {}), ...patch.overall };
    if (patch.dimensions) {
      next.dimensions = { ...(existing.dimensions ?? {}) };
      for (const dimKey of Object.keys(patch.dimensions) as DimensionKey[]) {
        const dimPatch = patch.dimensions[dimKey];
        if (!dimPatch) continue;
        next.dimensions[dimKey] = { ...(existing.dimensions?.[dimKey] ?? {}), ...dimPatch };
      }
    }
    overrides.nodes[nodeId] = next;
  } else {
    return NextResponse.json({ error: "no_change" }, { status: 400 });
  }

  overrides.updatedAt = new Date().toISOString();
  writeOverridesData(overrides);
  return NextResponse.json({ ok: true, updatedAt: overrides.updatedAt });
}
