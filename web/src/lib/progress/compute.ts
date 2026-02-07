import { DIMENSION_KEYS, type DimensionKey, type MaturityLevel } from "./types";
import type {
  ProgressDataBase,
  ProgressDataComputed,
  ProgressNodeBase,
  ProgressNodeComputed,
} from "./types";

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const clampScore = (value: number) => Math.max(0, Math.min(100, value));

export function scoreToMaturity(score: number): MaturityLevel {
  const s = clampScore(score);
  if (s < 10) return 0;
  if (s < 30) return 1;
  if (s < 55) return 2;
  if (s < 75) return 3;
  return 4;
}

function weightedMean(values: number[], weights: number[]): number {
  if (values.length === 0) return 0;
  let num = 0;
  let den = 0;
  for (let i = 0; i < values.length; i += 1) {
    const w = weights[i] ?? 0;
    num += values[i] * w;
    den += w;
  }
  if (den <= 0) return values.reduce((a, b) => a + b, 0) / values.length;
  return num / den;
}

function computeDepth(nodes: Record<string, ProgressNodeBase>, rootId: string) {
  const depthById = new Map<string, number>();
  const visiting = new Set<string>();

  const visit = (id: string): number => {
    if (depthById.has(id)) return depthById.get(id)!;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const node = nodes[id];
    const parentId = node?.parentId ?? null;
    const depth = parentId && nodes[parentId] ? visit(parentId) + 1 : id === rootId ? 0 : 1;
    visiting.delete(id);
    depthById.set(id, depth);
    return depth;
  };

  for (const id of Object.keys(nodes)) visit(id);
  return depthById;
}

export function computeProgress(data: ProgressDataBase): ProgressDataComputed {
  const nodesBase = data.nodes;
  const childrenById: Record<string, string[]> = {};
  for (const node of Object.values(nodesBase)) childrenById[node.id] = [];
  for (const node of Object.values(nodesBase)) {
    const parentId = node.parentId ?? null;
    if (parentId && childrenById[parentId]) childrenById[parentId].push(node.id);
  }
  for (const id of Object.keys(childrenById)) {
    childrenById[id].sort((a, b) => {
      const ao = nodesBase[a]?.order ?? 0;
      const bo = nodesBase[b]?.order ?? 0;
      return ao - bo;
    });
  }

  const depthById = computeDepth(nodesBase, data.rootId);
  const idsByDepthDesc = Object.keys(nodesBase).sort(
    (a, b) => (depthById.get(b) ?? 0) - (depthById.get(a) ?? 0),
  );

  const computed: Record<string, ProgressNodeComputed> = {};

  for (const id of idsByDepthDesc) {
    const node = nodesBase[id];
    const children = childrenById[id] ?? [];
    const isLeaf = children.length === 0;

    const computedNode: ProgressNodeComputed = {
      ...node,
      parentId: node.parentId ?? null,
      children,
      depth: depthById.get(id) ?? 0,
      dimensions: DIMENSION_KEYS.reduce(
        (acc, k) => {
          acc[k] = { score: 0 };
          return acc;
        },
        {} as Record<DimensionKey, { score: number }>,
      ),
      overall: {
        score: 0,
        maturity: 0,
        confidence: 0.25,
        note: node.overall?.note,
      },
    };

    if (isLeaf) {
      for (const key of DIMENSION_KEYS) {
        const dim = node.dimensions?.[key];
        const score = clampScore(dim?.score ?? 0);
        const confidence = clamp01(dim?.confidence ?? computedNode.overall.confidence);
        computedNode.dimensions[key] = {
          ...dim,
          score,
          confidence,
          maturity: dim?.maturity ?? scoreToMaturity(score),
        };
      }

      const scores = DIMENSION_KEYS.map((k) => computedNode.dimensions[k].score);
      const overallScore = scores.reduce((a, b) => a + b, 0) / scores.length;
      const overallConfidence =
        DIMENSION_KEYS.map((k) => computedNode.dimensions[k].confidence ?? 0.25).reduce(
          (a, b) => a + b,
          0,
        ) / DIMENSION_KEYS.length;
      computedNode.overall = {
        ...node.overall,
        score: clampScore(node.overall?.score ?? overallScore),
        confidence: clamp01(node.overall?.confidence ?? overallConfidence),
        maturity: node.overall?.maturity ?? scoreToMaturity(node.overall?.score ?? overallScore),
      };
    } else {
      const childNodes = children.map((cid) => computed[cid]).filter(Boolean);
      const childWeights = childNodes.map((cn) => cn.overall.confidence);

      for (const key of DIMENSION_KEYS) {
        const childScores = childNodes.map((cn) => cn.dimensions[key].score);
        const score = weightedMean(childScores, childWeights);
        const confidence = clamp01(weightedMean(childWeights, childWeights));
        computedNode.dimensions[key] = {
          score: clampScore(score),
          confidence,
          maturity: scoreToMaturity(score),
        };
      }

      const overallScore =
        DIMENSION_KEYS.map((k) => computedNode.dimensions[k].score).reduce((a, b) => a + b, 0) /
        DIMENSION_KEYS.length;
      const overallConfidence =
        DIMENSION_KEYS.map((k) => computedNode.dimensions[k].confidence ?? 0.25).reduce(
          (a, b) => a + b,
          0,
        ) / DIMENSION_KEYS.length;

      computedNode.overall = {
        score: clampScore(overallScore),
        confidence: clamp01(overallConfidence),
        maturity: scoreToMaturity(overallScore),
        note: node.overall?.note,
      };
    }

    computed[id] = computedNode;
  }

  return {
    ...data,
    nodes: computed,
    generatedAt: data.generatedAt,
  };
}
