export type MonitorAlert = {
  severity: "info" | "warn" | "critical" | string;
  code: string;
  message: string;
};

export type MonitorStatusData = {
  version: string;
  updatedAt: string;
  run?: {
    mode?: string;
    startedAt?: string;
    finishedAt?: string;
    durationSeconds?: number | null;
    wallClockSeconds?: number | null;
    success?: boolean;
    commands?: Array<{
      label: string;
      cmd: string;
      ok: boolean;
      returnCode?: number;
      durationSeconds?: number | null;
      error?: string | null;
    }>;
  };
  freshness?: Array<{
    name: string;
    path: string;
    timestamp?: string | null;
    ageHours?: number | null;
    thresholdHours?: number | null;
    status?: string;
  }>;
  alerts?: MonitorAlert[];
  summary?: {
    critical?: number;
    warn?: number;
    info?: number;
  };
  pipeline?: {
    recentPapers?: {
      last1d?: number;
      last3d?: number;
      last7d?: number;
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
        id: string;
        name: string;
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
    diagnoses?: string[];
    watchlist?: Array<{
      id: string;
      name: string;
      macroName: string;
      profileLabel: string;
      reasons: string[];
    }>;
    topMovers?: Array<{
      id: string;
      name: string;
      macroName: string;
      value: number;
      label: string;
    }>;
    latestUpdates?: Array<{
      date?: string;
      summary?: string;
      sourceType?: string;
      confidence?: number;
    }>;
  };
};
