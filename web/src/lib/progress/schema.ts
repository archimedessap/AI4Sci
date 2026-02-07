import { z } from "zod";
import { DIMENSION_KEYS, type DimensionKey } from "./types";

const DimensionKeyValues = [...DIMENSION_KEYS] as unknown as [
  DimensionKey,
  ...DimensionKey[],
];
export const DimensionKeySchema = z.enum(DimensionKeyValues);

export const EvidenceItemSchema = z
  .object({
    title: z.string(),
    url: z.string(),
    year: z.number().int().optional(),
    citedBy: z.number().int().nonnegative().optional(),
    venue: z.string().optional(),
    source: z.string().optional(),
  })
  .passthrough();

const MaturityLevelSchema = z.union([
  z.literal(0),
  z.literal(1),
  z.literal(2),
  z.literal(3),
  z.literal(4),
]);

export const DimensionMetricsSchema = z
  .object({
    score: z.number(),
    maturity: MaturityLevelSchema.optional(),
    confidence: z.number().min(0).max(1).optional(),
    signals: z.record(z.string(), z.number()).optional(),
    evidence: z.array(EvidenceItemSchema).optional(),
    note: z.string().optional(),
  })
  .passthrough();

export const OverallMetricsSchema = z
  .object({
    score: z.number().optional(),
    maturity: MaturityLevelSchema.optional(),
    confidence: z.number().min(0).max(1).optional(),
    note: z.string().optional(),
  })
  .passthrough();

export const ProgressNodeSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    description: z.string().optional(),
    parentId: z.string().nullable().optional(),
    order: z.number().int().optional(),
    openalex: z
      .object({
        concept: z
          .object({
            id: z.string().optional(),
            name: z.string().optional(),
          })
          .optional(),
      })
      .optional(),
    dimensions: z
      .record(DimensionKeySchema, DimensionMetricsSchema)
      .optional(),
    overall: OverallMetricsSchema.optional(),
  })
  .passthrough();

export const ProgressDataSchema = z
  .object({
    version: z.string(),
    generatedAt: z.string(),
    rootId: z.string(),
    dimensions: z.array(
      z.object({
        key: DimensionKeySchema,
        label: z.string(),
        description: z.string(),
      }),
    ),
    nodes: z.record(z.string(), ProgressNodeSchema),
  })
  .passthrough();

const OverrideDimensionMetricsSchema = DimensionMetricsSchema.partial();
const OverrideNodeSchema = z
  .object({
    name: z.string().optional(),
    description: z.string().optional(),
    order: z.number().int().optional(),
    overall: OverallMetricsSchema.partial().optional(),
    dimensions: z
      .record(DimensionKeySchema, OverrideDimensionMetricsSchema)
      .optional(),
  })
  .passthrough();

export const OverridesDataSchema = z
  .object({
    version: z.string(),
    updatedAt: z.string(),
    nodes: z.record(z.string(), OverrideNodeSchema),
  })
  .passthrough();
