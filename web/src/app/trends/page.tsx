import Link from "next/link";
import fs from "node:fs";
import path from "node:path";

import { TrendsClient, type TrendsLeaf, type TrendsMover, type TrendsNarrative } from "./TrendsClient";
import { getProgressData } from "@/lib/progress/get.server";
import { readProgressHistory } from "@/lib/progress/history.server";
import { evaluateNarrativeMilestones } from "@/lib/progress/narrative";

export const dynamic = "force-dynamic";

function parseDateUtc(dateStr: string): number | null {
  const ts = Date.parse(`${dateStr}T00:00:00Z`);
  return Number.isNaN(ts) ? null : ts;
}

type DiscoveryLayersData = {
  nodes?: Record<
    string,
    {
      layers?: Partial<Record<"phenomena" | "empirical" | "theory" | "principles", number>>;
      confidence?: number;
    }
  >;
};

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

function readDiscoveryLayers(): DiscoveryLayersData {
  const p = dataPath("discovery_layers.json");
  if (!fs.existsSync(p)) return {};
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as DiscoveryLayersData;
  } catch {
    return {};
  }
}

function linearFitPerDay(points: Array<{ t: number; y: number }>): { slope: number | null; r2: number | null } {
  if (points.length < 2) return { slope: null, r2: null };
  const t0 = points[0].t;
  const xs = points.map((p) => (p.t - t0) / 86400000);
  const ys = points.map((p) => p.y);
  const n = xs.length;
  const meanX = xs.reduce((a, b) => a + b, 0) / n;
  const meanY = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = xs[i] - meanX;
    num += dx * (ys[i] - meanY);
    den += dx * dx;
  }
  if (den <= 0) return { slope: null, r2: null };
  const slope = num / den;
  if (!Number.isFinite(slope)) return { slope: null, r2: null };

  const intercept = meanY - slope * meanX;
  let ssTot = 0;
  let ssRes = 0;
  for (let i = 0; i < n; i += 1) {
    const y = ys[i];
    const yHat = intercept + slope * xs[i];
    ssTot += (y - meanY) * (y - meanY);
    ssRes += (y - yHat) * (y - yHat);
  }
  const r2 =
    ssTot > 0 && Number.isFinite(ssTot) && Number.isFinite(ssRes)
      ? Math.max(-1, Math.min(1, 1 - ssRes / ssTot))
      : null;

  return { slope, r2 };
}

const ETA_MAX_WINDOW = 45;
const ETA_MIN_POINTS = 6;
const ETA_MIN_R2 = 0.08;

export default function TrendsPage({
  searchParams,
}: {
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const history = readProgressHistory();

  return (
    <div className="min-h-screen bg-[radial-gradient(900px_600px_at_15%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_80%_15%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Trends
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              Milestones & Trends
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              基于每日快照的时间序列：展示“最近变化”，并在“相关→因果→机制→统一→闭环探索”的主叙事下做里程碑刻画与 ETA 预测。
            </p>
            {!history ? (
              <div className="mt-3 text-xs text-rose-200/80">
                Data not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/update_progress_history.py
                </code>{" "}
                to generate <code>web/data/progress_history.json</code>.
              </div>
            ) : (
              <div className="mt-3 text-xs text-white/40">
                Updated: {new Date(history.updatedAt).toLocaleString()} • Snapshots:{" "}
                {history.snapshots.length} • Leaves: {history.leaves.length}
              </div>
            )}
          </div>
          <Link
            href="/"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Back
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 pb-16">
        {history ? <TrendsPageBody history={history} searchParams={searchParams} /> : null}
      </main>
    </div>
  );
}

function TrendsPageBody({
  history,
  searchParams,
}: {
  history: NonNullable<ReturnType<typeof readProgressHistory>>;
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const leaves: TrendsLeaf[] = history.leaves
    .map((l) => ({
      id: l.id,
      name: l.name,
      macroName: l.macroName ?? null,
    }))
    .sort((a, b) => {
      const am = (a.macroName ?? "").localeCompare(b.macroName ?? "");
      if (am !== 0) return am;
      return a.name.localeCompare(b.name);
    });

  const indexById = new Map(history.leaves.map((l, idx) => [l.id, idx]));

  const sp = searchParams ?? {};
  const rawId = sp.id;
  const selectedId =
    typeof rawId === "string" && indexById.has(rawId) ? rawId : leaves[0]?.id ?? "";
  const selIndex = indexById.get(selectedId) ?? 0;

  const dates = history.snapshots.map((s) => s.date);
  const scores = history.snapshots.map((s) => s.overall[selIndex] ?? null);

  const lastSnap = history.snapshots[history.snapshots.length - 1];
  const prevSnap = history.snapshots.length >= 2 ? history.snapshots[history.snapshots.length - 2] : null;

  const movers: TrendsMover[] = (() => {
    if (!lastSnap || !prevSnap) return [];
    const out: TrendsMover[] = [];
    for (let i = 0; i < history.leaves.length; i += 1) {
      const a = lastSnap.overall[i];
      const b = prevSnap.overall[i];
      if (typeof a !== "number" || typeof b !== "number") continue;
      const leaf = history.leaves[i];
      out.push({
        id: leaf.id,
        name: leaf.name,
        macroName: leaf.macroName ?? null,
        score: a,
        delta: a - b,
      });
    }
    out.sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta));
    return out.slice(0, 12);
  })();

  const narrative: TrendsNarrative | null = (() => {
    if (!lastSnap) return null;

    const progress = getProgressData();
    const node = progress.nodes[selectedId];
    const explainRatio = node?.dimensions?.explain?.signals?.signal_ratio;
    const experimentRatio = node?.dimensions?.experiment?.signals?.signal_ratio;
    const aiRecentLive = node?.dimensions?.model?.signals?.ai_recent;

    const discovery = readDiscoveryLayers();
    const layers = discovery.nodes?.[selectedId]?.layers ?? {};
    const theory = typeof layers.theory === "number" ? layers.theory : null;
    const principles = typeof layers.principles === "number" ? layers.principles : null;

    const latestScores = {
      overall: lastSnap.overall[selIndex] ?? null,
      data: lastSnap.data[selIndex] ?? null,
      model: lastSnap.model[selIndex] ?? null,
      predict: lastSnap.predict[selIndex] ?? null,
      experiment: lastSnap.experiment[selIndex] ?? null,
      explain: lastSnap.explain[selIndex] ?? null,
    };

    const evalResult = evaluateNarrativeMilestones({
      scores: Object.fromEntries(
        Object.entries(latestScores).filter(([, v]) => typeof v === "number"),
      ) as Record<keyof typeof latestScores, number>,
      confidence: (lastSnap.confidence?.[selIndex] ?? null) as number | null,
      aiRecent: (lastSnap.aiRecent?.[selIndex] ?? (typeof aiRecentLive === "number" ? aiRecentLive : null)) as
        | number
        | null,
      signalRatioExplain: typeof explainRatio === "number" ? explainRatio : null,
      signalRatioExperiment: typeof experimentRatio === "number" ? experimentRatio : null,
      tooling: (lastSnap.tooling?.[selIndex] ?? null) as number | null,
      autonomy: (lastSnap.autonomy?.[selIndex] ?? null) as number | null,
      theory,
      principles,
    });

    const nextStageKey = evalResult.nextStageKey;
    const nextStage = nextStageKey ? evalResult.stages.find((s) => s.key === nextStageKey) : null;
    const nextCriteria = nextStage?.criteria ?? [];

    const metricField: Record<string, string> = {
      overall: "overall",
      data: "data",
      model: "model",
      predict: "predict",
      experiment: "experiment",
      explain: "explain",
      confidence: "confidence",
      aiRecent: "aiRecent",
      tooling: "tooling",
      autonomy: "autonomy",
    };

    const estimateEta = (metric: string, threshold: number) => {
      const field = metricField[metric];
      if (!field) return { etaDays: null as number | null, pointsUsed: 0 };

      const points: Array<{ t: number; y: number }> = [];
      for (const s of history.snapshots) {
        const t = parseDateUtc(s.date);
        if (t == null) continue;
        const arr = (s as unknown as Record<string, unknown>)[field];
        if (!Array.isArray(arr)) continue;
        const y = arr[selIndex];
        if (typeof y !== "number") continue;
        points.push({ t, y });
      }
      if (!points.length) return { etaDays: null as number | null, pointsUsed: 0 };

      const windowed = points.slice(Math.max(0, points.length - ETA_MAX_WINDOW));
      const last = windowed[windowed.length - 1];
      const current = last?.y;
      if (typeof current !== "number") return { etaDays: null as number | null, pointsUsed: windowed.length };
      if (current >= threshold) return { etaDays: 0, pointsUsed: windowed.length };
      if (windowed.length < ETA_MIN_POINTS) {
        return { etaDays: null as number | null, pointsUsed: windowed.length };
      }
      const fit = linearFitPerDay(windowed);
      const slope = fit.slope;
      if (slope == null || slope <= 0) return { etaDays: null as number | null, pointsUsed: windowed.length };
      if (typeof fit.r2 === "number" && fit.r2 < ETA_MIN_R2) {
        return { etaDays: null as number | null, pointsUsed: windowed.length };
      }
      const etaDays = (threshold - current) / slope;
      if (!Number.isFinite(etaDays) || etaDays < 0 || etaDays > 3650) {
        return { etaDays: null as number | null, pointsUsed: windowed.length };
      }
      return { etaDays, pointsUsed: windowed.length };
    };

    const criteriaRows = nextCriteria.map((c) => {
      const metric = typeof c.metric === "string" ? c.metric : null;
      const eta = metric ? estimateEta(metric, c.threshold) : { etaDays: null as number | null, pointsUsed: 0 };
      return { ...c, etaDays: eta.etaDays };
    });

    const missingWithEta = criteriaRows
      .filter((c) => !c.passed && typeof c.etaDays === "number")
      .map((c) => c.etaDays as number);
    const etaDays = missingWithEta.length ? Math.max(...missingWithEta) : null;

    const lastT = parseDateUtc(lastSnap.date);
    const etaDate =
      typeof etaDays === "number" && lastT != null
        ? new Date(lastT + etaDays * 86400000).toISOString().slice(0, 10)
        : null;

    // Approximate: use the max pointsUsed among estimable criteria as a proxy.
    const pointsUsed = (() => {
      const used: number[] = [];
      for (const c of nextCriteria) {
        if (typeof c.metric !== "string") continue;
        used.push(estimateEta(c.metric, c.threshold).pointsUsed);
      }
      return Math.max(0, ...used);
    })();

    return {
      currentStageKey: evalResult.currentStageKey,
      nextStageKey: evalResult.nextStageKey,
      etaDays,
      etaDate,
      pointsUsed,
      nextCriteria: criteriaRows,
    };
  })();

  return (
    <TrendsClient
      leaves={leaves}
      selectedId={selectedId}
      dates={dates}
      scores={scores}
      narrative={narrative}
      movers={movers}
      updatedAt={history.updatedAt}
    />
  );
}
