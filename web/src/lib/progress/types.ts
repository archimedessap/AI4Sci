export const DIMENSION_KEYS = [
  "data",
  "model",
  "predict",
  "experiment",
  "explain",
] as const;

export type DimensionKey = (typeof DIMENSION_KEYS)[number];

export type MaturityLevel = 0 | 1 | 2 | 3 | 4;

export type EvidenceItem = {
  title: string;
  url: string;
  year?: number;
  citedBy?: number;
  venue?: string;
  source?: string;
};

export type DimensionMetrics = {
  score: number;
  maturity?: MaturityLevel;
  confidence?: number;
  signals?: Record<string, number>;
  evidence?: EvidenceItem[];
  note?: string;
};

export type OverallMetrics = {
  score?: number;
  maturity?: MaturityLevel;
  confidence?: number;
  note?: string;
};

export type ProgressNodeBase = {
  id: string;
  name: string;
  description?: string;
  parentId?: string | null;
  order?: number;
  openalex?: {
    concept?: {
      id?: string;
      name?: string;
    };
  };
  dimensions?: Partial<Record<DimensionKey, DimensionMetrics>>;
  overall?: OverallMetrics;
};

export type ProgressDataBase = {
  version: string;
  generatedAt: string;
  rootId: string;
  dimensions: Array<{
    key: DimensionKey;
    label: string;
    description: string;
  }>;
  nodes: Record<string, ProgressNodeBase>;
};

export type NodeOverride = {
  name?: string;
  description?: string;
  order?: number;
  overall?: Partial<OverallMetrics>;
  dimensions?: Partial<Record<DimensionKey, Partial<DimensionMetrics>>>;
};

export type OverridesData = {
  version: string;
  updatedAt: string;
  nodes: Record<string, NodeOverride>;
};

export type ProgressNodeComputed = ProgressNodeBase & {
  parentId: string | null;
  children: string[];
  depth: number;
  dimensions: Record<DimensionKey, DimensionMetrics>;
  overall: {
    score: number;
    maturity: MaturityLevel;
    confidence: number;
    note?: string;
  };
};

export type ProgressDataComputed = ProgressDataBase & {
  generatedAt: string;
  nodes: Record<string, ProgressNodeComputed>;
};
