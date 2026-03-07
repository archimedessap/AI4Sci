export const FIRST_PRINCIPLES_AXIS_KEYS = [
  "observability",
  "compressibility",
  "causalGrasp",
  "intervention",
  "autonomyReadiness",
] as const;

export type FirstPrinciplesAxisKey = (typeof FIRST_PRINCIPLES_AXIS_KEYS)[number];

export type FirstPrinciplesDomain = {
  id: string;
  name: string;
  macroId: string;
  macroName: string;
  axes: Record<FirstPrinciplesAxisKey | "closureReadiness", number>;
  scores: Record<string, number>;
  layers: Record<string, number>;
  gaps: {
    instrumentalism: number;
    theoryAction: number;
    observationCompression: number;
  };
  closureReadiness: number;
  profile: {
    key: string;
    label: string;
    summary: string;
  };
  signals: {
    aiRecent: number;
    momentum7d: number;
    newPapers7d: number;
  };
};

export type FirstPrinciplesRankingEntry = {
  id: string;
  name: string;
  macroId: string;
  macroName: string;
  profileLabel: string;
  field: string;
  label: string;
  value: number;
  closureReadiness: number;
  momentum7d: number;
  newPapers7d: number;
};

export type FirstPrinciplesData = {
  version: string;
  updatedAt: string;
  definitions?: Partial<Record<FirstPrinciplesAxisKey, string>>;
  window?: {
    paperDays?: number;
    updateDays?: number;
    historyDays?: number;
  };
  monitor?: {
    freshness?: Array<{
      name: string;
      path: string;
      timestamp?: string | null;
      ageHours?: number | null;
    }>;
    recentPapers?: {
      last1d?: number;
      last3d?: number;
      last7d?: number;
      windowDays?: number;
      latestPublicationDate?: string | null;
    };
    dimensionMix?: Record<string, number>;
    directSources?: {
      updatedAt?: string | null;
      counts?: {
        last6h?: number;
        last24h?: number;
        last72h?: number;
      };
      errors?: number;
      topSources?: Array<{
        id?: string;
        name?: string;
        type?: string;
        status?: string;
        newItems?: number;
        includedItems?: number;
        lastPublishedAt?: string | null;
      }>;
      recentItems?: Array<{
        sourceName?: string;
        title?: string;
        publishedAt?: string | null;
        isNew?: boolean;
        domains?: string[];
        url?: string | null;
      }>;
    };
    latestUpdates?: Array<{
      date?: string;
      summary?: string;
      sourceType?: string;
      confidence?: number;
    }>;
    topMovers?: FirstPrinciplesRankingEntry[];
    topNewPaperDomains?: Array<{
      id: string;
      name: string;
      macroName: string;
      count: number;
    }>;
    watchlist?: Array<{
      id: string;
      name: string;
      macroName: string;
      profileLabel: string;
      reasons: string[];
    }>;
    diagnoses?: string[];
  };
  rankings?: {
    instrumentalistFrontiers?: FirstPrinciplesRankingEntry[];
    closureLeaders?: FirstPrinciplesRankingEntry[];
    mechanismLeaders?: FirstPrinciplesRankingEntry[];
    fastMovers?: FirstPrinciplesRankingEntry[];
    observationHeavy?: FirstPrinciplesRankingEntry[];
  };
  domains: FirstPrinciplesDomain[];
};
