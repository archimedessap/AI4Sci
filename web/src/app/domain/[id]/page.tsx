import fs from "node:fs";
import path from "node:path";

import Link from "next/link";
import { notFound } from "next/navigation";

import { ChartCard } from "@/components/ChartCard";
import { ProgressBar } from "@/components/ProgressBar";
import { RadarChart } from "@/components/RadarChart";
import { readPapersCatalog, type CatalogPaper } from "@/lib/papers/catalog.server";
import { scoreToMaturity } from "@/lib/progress/compute";
import { getProgressData } from "@/lib/progress/get.server";
import { evaluateNarrativeMilestones, narrativeStageColor, narrativeStageLabel } from "@/lib/progress/narrative";
import { DIMENSION_KEYS, type DimensionKey, type EvidenceItem } from "@/lib/progress/types";
import { maturityLabel } from "@/lib/ui/colors";

function collectEvidence(items: EvidenceItem[] | undefined, out: EvidenceItem[]) {
  if (!items?.length) return;
  for (const it of items) out.push(it);
}

function normString(v: unknown) {
  if (typeof v === "string") return v;
  if (Array.isArray(v) && typeof v[0] === "string") return v[0];
  return "";
}

function trunc(s: string, maxLen: number) {
  if (s.length <= maxLen) return s;
  return `${s.slice(0, Math.max(0, maxLen - 1))}…`;
}

const MS_PER_YEAR = 1000 * 60 * 60 * 24 * 365;

function publicationTimestamp(p: CatalogPaper): number {
  if (p.publicationDate) {
    const ts = Date.parse(p.publicationDate);
    if (!Number.isNaN(ts)) return ts;
  }
  if (typeof p.publicationYear === "number") {
    const ts = Date.parse(`${p.publicationYear}-07-01`);
    if (!Number.isNaN(ts)) return ts;
  }
  return 0;
}

function citationRate(p: CatalogPaper): number {
  const cited = p.citedBy ?? 0;
  if (!cited) return 0;
  const ts = publicationTimestamp(p);
  if (!ts) return 0;
  const ageYears = Math.max(1, (Date.now() - ts) / MS_PER_YEAR);
  return cited / ageYears;
}

type PaperSort = "cited" | "recent" | "rate";

type DomainExtraMetricsData = {
  generatedAt?: string;
  nodes?: Record<
    string,
    {
      tooling?: number;
      autonomy?: number;
      stats?: { totalPapersApprox?: number; totalPapers?: number };
    }
  >;
};

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

function readDomainExtraMetrics(): DomainExtraMetricsData {
  const p = dataPath("domain_extra_metrics.json");
  if (!fs.existsSync(p)) return {};
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as DomainExtraMetricsData;
  } catch {
    return {};
  }
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

function fmtMetric(metric: string | undefined, v: number | null) {
  if (typeof v !== "number") return "—";
  if (metric === "confidence") return v.toFixed(2);
  if (metric === "aiRecent") return Math.round(v).toLocaleString();
  if (metric === "theory" || metric === "principles") return v.toFixed(2);
  if (metric === "signalRatioExplain" || metric === "signalRatioExperiment") return v.toFixed(3);
  return v.toFixed(1);
}

export default function DomainPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  return DomainPageImpl({ params, searchParams });
}

async function DomainPageImpl({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  // Next.js (newer versions) may provide params/searchParams as Promises in RSC.
  // `await` is safe for both Promise and non-Promise values.
  const resolvedParams = await (params as unknown);
  const resolvedSearchParams = await (searchParams as unknown);

  const data = getProgressData();
  const id = (resolvedParams as { id?: unknown })?.id;
  const node = typeof id === "string" ? data.nodes[id] : undefined;
  if (!node) notFound();

  const extra = readDomainExtraMetrics();
  const extraEntry = extra.nodes?.[node.id];
  const toolingScore = Math.round(Math.max(0, Math.min(100, (extraEntry?.tooling ?? 0) * 100)));
  const autonomyScore = Math.round(Math.max(0, Math.min(100, (extraEntry?.autonomy ?? 0) * 100)));

  const discovery = readDiscoveryLayers();
  const layers = discovery.nodes?.[node.id]?.layers ?? {};
  const layerTheory = typeof layers.theory === "number" ? layers.theory : null;
  const layerPrinciples = typeof layers.principles === "number" ? layers.principles : null;

  const explainRatio = node.dimensions.explain.signals?.signal_ratio;
  const experimentRatio = node.dimensions.experiment.signals?.signal_ratio;
  const aiRecent = node.dimensions.model.signals?.ai_recent;

  const narrative = evaluateNarrativeMilestones({
    scores: {
      overall: node.overall.score,
      data: node.dimensions.data.score,
      model: node.dimensions.model.score,
      predict: node.dimensions.predict.score,
      experiment: node.dimensions.experiment.score,
      explain: node.dimensions.explain.score,
    },
    confidence: node.overall.confidence,
    aiRecent: typeof aiRecent === "number" ? aiRecent : null,
    signalRatioExplain: typeof explainRatio === "number" ? explainRatio : null,
    signalRatioExperiment: typeof experimentRatio === "number" ? experimentRatio : null,
    tooling: extraEntry ? toolingScore : null,
    autonomy: extraEntry ? autonomyScore : null,
    theory: layerTheory,
    principles: layerPrinciples,
  });

  const ancestors: Array<{ id: string; name: string }> = [];
  let p = node.parentId ? data.nodes[node.parentId] : null;
  while (p) {
    ancestors.push({ id: p.id, name: p.name });
    p = p.parentId ? data.nodes[p.parentId] : null;
  }
  ancestors.reverse();

  const radarValues = DIMENSION_KEYS.reduce(
    (acc, k) => {
      acc[k] = node.dimensions[k].score;
      return acc;
    },
    {} as Record<DimensionKey, number>,
  );

  const mergedEvidence: EvidenceItem[] = [];
  for (const k of DIMENSION_KEYS) collectEvidence(node.dimensions[k].evidence, mergedEvidence);
  const evidenceByUrl = new Map<string, EvidenceItem>();
  for (const e of mergedEvidence) {
    const url = e.url;
    const existing = evidenceByUrl.get(url);
    if (!existing) evidenceByUrl.set(url, e);
    else if ((e.citedBy ?? -1) > (existing.citedBy ?? -1)) evidenceByUrl.set(url, e);
  }
  const evidence = Array.from(evidenceByUrl.values())
    .sort((a, b) => (b.citedBy ?? 0) - (a.citedBy ?? 0))
    .slice(0, 18);

  const catalog = readPapersCatalog();
  const sp = (resolvedSearchParams as Record<string, unknown> | undefined) ?? {};
  const rawSort = normString(sp.psort).trim();
  const paperSort: PaperSort =
    rawSort === "recent" || rawSort === "rate" || rawSort === "cited" ? rawSort : "cited";

  const leafIds = (() => {
    const out: string[] = [];
    const visited = new Set<string>();
    const walk = (id: string) => {
      if (visited.has(id)) return;
      visited.add(id);
      const n = data.nodes[id];
      if (!n) return;
      if (!n.children.length) {
        out.push(id);
        return;
      }
      for (const c of n.children) walk(c);
    };
    walk(node.id);
    return out;
  })();

  const domainInfoById = new Map((catalog?.domains ?? []).map((d) => [d.id, d]));
  const leafDomainIds = leafIds.filter((id) => domainInfoById.has(id));
  const leafDomainSet = new Set(leafDomainIds);
  const dbCount = leafDomainIds.reduce((acc, id) => acc + (domainInfoById.get(id)?.count ?? 0), 0);

  const relatedPapers = (catalog?.papers ?? []).filter((p) =>
    (p.domains ?? []).some((d) => leafDomainSet.has(d)),
  );
  relatedPapers.sort((a, b) => {
    if (paperSort === "recent") {
      const ad = publicationTimestamp(a);
      const bd = publicationTimestamp(b);
      if (ad !== bd) return bd - ad;
      const ac = a.citedBy ?? 0;
      const bc = b.citedBy ?? 0;
      return bc - ac;
    }
    if (paperSort === "rate") {
      const ar = citationRate(a);
      const br = citationRate(b);
      if (ar !== br) return br - ar;
    }
    const ac = a.citedBy ?? 0;
    const bc = b.citedBy ?? 0;
    if (ac !== bc) return bc - ac;
    return publicationTimestamp(b) - publicationTimestamp(a);
  });
  const viewPapers = relatedPapers.slice(0, 24);

  const methodsByTag = new Map((catalog?.methods ?? []).map((m) => [m.tag, m]));
  const topMethods = (() => {
    const counts = new Map<string, number>();
    for (const p of relatedPapers) {
      for (const t of p.methodTags ?? []) counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([tag, count]) => ({
        tag,
        label: methodsByTag.get(tag)?.label ?? tag,
        count,
      }));
  })();

  const topVenues = (() => {
    const counts = new Map<string, number>();
    for (const p of relatedPapers) {
      const s = (p.source ?? "").trim();
      if (!s) continue;
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([name, count]) => ({ name, count }));
  })();

  const yearBars = (() => {
    const nowYear = new Date().getFullYear();
    const years = [nowYear - 4, nowYear - 3, nowYear - 2, nowYear - 1, nowYear];
    const counts = new Map<number, number>();
    for (const y of years) counts.set(y, 0);
    for (const p of relatedPapers) {
      const y = p.publicationYear ?? null;
      if (typeof y === "number" && counts.has(y)) counts.set(y, (counts.get(y) ?? 0) + 1);
    }
    const max = Math.max(1, ...Array.from(counts.values()));
    return years.map((y) => ({ year: y, count: counts.get(y) ?? 0, pct: (counts.get(y) ?? 0) / max }));
  })();

  return (
    <div className="min-h-screen bg-[radial-gradient(1000px_600px_at_20%_10%,rgba(34,211,238,0.12),transparent_60%),radial-gradient(900px_600px_at_75%_10%,rgba(167,139,250,0.12),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>
              {ancestors.map((a) => (
                <span key={a.id}>
                  {" "}
                  /{" "}
                  <Link
                    href={`/domain/${encodeURIComponent(a.id)}`}
                    className="hover:text-white/80"
                  >
                    {a.name}
                  </Link>
                </span>
              ))}
              <span className="opacity-70"> / {node.name}</span>
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              {node.name}
            </h1>
            {node.description ? (
              <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
                {node.description}
              </p>
            ) : null}
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4">
            <div className="text-xs text-white/60">Overall</div>
            <div className="mt-1 text-2xl font-semibold">
              {node.overall.score.toFixed(1)}
            </div>
            <div className="mt-1 text-xs text-white/55">
              {maturityLabel(node.overall.maturity)}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 pb-16">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <ChartCard
              title="Five-Dimension Profile"
              subtitle="Data / Modeling / Prediction & Control / Experiment / Explanation"
            >
              <RadarChart
                dimensions={data.dimensions.map((d) => ({
                  key: d.key,
                  label: d.label,
                }))}
                values={radarValues}
                height={360}
              />
            </ChartCard>
          </div>
          <div className="lg:col-span-7">
            <ChartCard
              title="Dimension Progress"
              subtitle="Scores are auto‑computed; use Admin overrides to correct bias."
            >
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {data.dimensions.map((d) => (
                  <ProgressBar
                    key={d.key}
                    label={d.label}
                    score={node.dimensions[d.key].score}
                    maturity={node.dimensions[d.key].maturity!}
                    note={d.description}
                  />
                ))}
              </div>
            </ChartCard>
          </div>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Tooling & Autonomy (Separate Axes)"
            subtitle={
              extra.generatedAt
                ? `Keyword-based heuristics (Generated: ${new Date(extra.generatedAt).toLocaleString()})`
                : "Keyword-based heuristics (title+abstract)."
            }
          >
            {extraEntry ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <ProgressBar
                  label="Tooling / Infrastructure"
                  score={toolingScore}
                  maturity={scoreToMaturity(toolingScore)}
                  note="Keyword hits (dataset/benchmark/tool/framework/pipeline...). Interpreted as enabling infrastructure, not “discovery depth”."
                />
                <ProgressBar
                  label="Autonomy / Closed‑Loop"
                  score={autonomyScore}
                  maturity={scoreToMaturity(autonomyScore)}
                  note="Keyword hits (closed-loop/autonomous/robotic/active-learning...). Approximates how much work moves toward self-driving scientific loops."
                />
              </div>
            ) : (
              <div className="text-sm text-white/55">
                Extra metrics not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/analyze_domain_extra_metrics.py
                </code>{" "}
                to generate <code>web/data/domain_extra_metrics.json</code>.
              </div>
            )}
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Narrative Milestones (相关→因果→机制→统一→闭环探索)"
            subtitle="多指标门槛判断是否“全面达到”。建议结合证据列表与本地论文库一起看。"
            right={
              <Link
                href={`/trends?id=${encodeURIComponent(node.id)}`}
                className="text-xs font-semibold text-white/70 hover:text-white/90"
              >
                Timeline →
              </Link>
            }
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-xs text-white/55">Current</div>
                <div className="mt-1 flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ background: narrativeStageColor(narrative.currentStageKey) }}
                  />
                  <div className="text-sm font-semibold text-white/90">
                    {narrativeStageLabel(narrative.currentStageKey)}
                  </div>
                </div>
                {narrative.nextStageKey ? (
                  <div className="mt-1 text-xs text-white/50">
                    Next: {narrativeStageLabel(narrative.nextStageKey)}
                  </div>
                ) : (
                  <div className="mt-1 text-xs text-white/50">Next: —</div>
                )}
              </div>
              <div className="text-xs text-white/45">
                Tip: milestones are sequential; later stages require earlier ones.
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              {narrative.stages.map((s, idx) => {
                const reached = narrative.currentStageIndex >= 0 && idx <= narrative.currentStageIndex;
                const next = idx === narrative.currentStageIndex + 1;
                const locked = idx > narrative.currentStageIndex + 1;
                const status = reached ? "Reached" : locked ? "Locked" : s.coverage >= 0.5 ? "Partial" : "Not yet";
                const statusColor = reached
                  ? "rgba(74,222,128,0.9)"
                  : locked
                    ? "rgba(148,163,184,0.75)"
                    : s.coverage >= 0.5
                      ? "rgba(251,191,36,0.9)"
                      : "rgba(148,163,184,0.8)";
                return (
                  <div
                    key={s.key}
                    className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-white/90">
                          {idx + 1}. {s.label}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-white/55">
                          {s.description}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="text-xs font-semibold" style={{ color: statusColor }}>
                          {status}
                        </div>
                        <div className="mt-1 text-[11px] text-white/45">
                          {next || reached ? `${(s.coverage * 100).toFixed(0)}%` : "—"}
                        </div>
                      </div>
                    </div>
                    <ul className="mt-3 space-y-1 text-[12px] text-white/65">
                      {s.criteria.map((c) => (
                        <li key={c.key} className="flex items-start justify-between gap-3">
                          <span className="min-w-0">
                            <span
                              className="mr-2 inline-block w-4 text-center"
                              style={{
                                color: c.passed ? "rgba(74,222,128,0.95)" : "rgba(148,163,184,0.8)",
                              }}
                            >
                              {c.passed ? "✓" : "•"}
                            </span>
                            <span className="text-white/75">{c.label}</span>
                            {c.note ? <span className="ml-2 text-white/35">({c.note})</span> : null}
                          </span>
                          <span className="shrink-0 text-[11px] text-white/45">
                            {fmtMetric(c.metric, c.current)} / {fmtMetric(c.metric, c.threshold)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Paper Library (Local DB)"
            subtitle="与该领域相关的 AI4Sci 论文（从本地 SQLite 库导出；按每个叶子领域 Top‑k 抽样，便于浏览）。"
            right={
              <div className="flex items-center gap-2 text-xs">
                <Link
                  href={`/domain/${encodeURIComponent(node.id)}?psort=cited`}
                  className={`rounded-full border px-3 py-1 font-semibold ${paperSort === "cited" ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"}`}
                >
                  Most cited
                </Link>
                <Link
                  href={`/domain/${encodeURIComponent(node.id)}?psort=rate`}
                  className={`rounded-full border px-3 py-1 font-semibold ${paperSort === "rate" ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"}`}
                >
                  Citation rate
                </Link>
                <Link
                  href={`/domain/${encodeURIComponent(node.id)}?psort=recent`}
                  className={`rounded-full border px-3 py-1 font-semibold ${paperSort === "recent" ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100" : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.05]"}`}
                >
                  Most recent
                </Link>
                {leafDomainIds.length === 1 ? (
                  <Link
                    href={`/papers?domain=${encodeURIComponent(leafDomainIds[0])}&sort=${encodeURIComponent(paperSort)}`}
                    className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-semibold text-white/70 hover:bg-white/[0.05]"
                  >
                    Browse →
                  </Link>
                ) : (
                  <Link
                    href="/papers"
                    className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-semibold text-white/70 hover:bg-white/[0.05]"
                  >
                    Browse →
                  </Link>
                )}
              </div>
            }
          >
            {catalog ? (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
                <div className="lg:col-span-4">
                  <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                    <div className="text-xs font-semibold text-white/70">Stats</div>
                    <div className="mt-2 grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <div className="text-white/45 text-[11px]">DB papers</div>
                        <div className="mt-1 font-semibold text-white/85">
                          {dbCount.toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div className="text-white/45 text-[11px]">Shown in page</div>
                        <div className="mt-1 font-semibold text-white/85">
                          {Math.min(24, relatedPapers.length)} / {relatedPapers.length.toLocaleString()}
                        </div>
                      </div>
                    </div>
                    {leafDomainIds.length > 1 ? (
                      <div className="mt-2 text-[11px] text-white/45">
                        Note: aggregated over {leafDomainIds.length} leaf subdomains (DB count sums leaf counts; may overlap).
                      </div>
                    ) : null}

                    <div className="mt-4">
                      <div className="text-xs font-semibold text-white/70">Last 5 years</div>
                      <div className="mt-2 space-y-2">
                        {yearBars.map((y) => (
                          <div key={y.year} className="flex items-center gap-3">
                            <div className="w-10 text-[11px] text-white/55">{y.year}</div>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-cyan-400/80 via-violet-400/80 to-rose-400/80"
                                style={{ width: `${Math.round(y.pct * 100)}%` }}
                              />
                            </div>
                            <div className="w-10 text-right text-[11px] text-white/60 tabular-nums">
                              {y.count}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="lg:col-span-8">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                      <div className="text-xs font-semibold text-white/70">Top AI methods</div>
                      {topMethods.length ? (
                        <div className="mt-2 space-y-2">
                          {(() => {
                            const max = Math.max(1, ...topMethods.map((m) => m.count));
                            return topMethods.map((m) => (
                              <div key={m.tag} className="flex items-center gap-3">
                                <div className="w-28 truncate text-[11px] text-white/65">
                                  {m.label}
                                </div>
                                <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                                  <div
                                    className="h-full rounded-full bg-cyan-400/35"
                                    style={{ width: `${Math.round((m.count / max) * 100)}%` }}
                                  />
                                </div>
                                <div className="w-10 text-right text-[11px] text-white/60 tabular-nums">
                                  {m.count}
                                </div>
                              </div>
                            ));
                          })()}
                        </div>
                      ) : (
                        <div className="mt-2 text-sm text-white/55">No method tags yet.</div>
                      )}
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                      <div className="text-xs font-semibold text-white/70">Top venues</div>
                      {topVenues.length ? (
                        <div className="mt-2 space-y-2">
                          {(() => {
                            const max = Math.max(1, ...topVenues.map((v) => v.count));
                            return topVenues.map((v) => (
                              <div key={v.name} className="flex items-center gap-3">
                                <div className="w-28 truncate text-[11px] text-white/65">
                                  {v.name}
                                </div>
                                <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                                  <div
                                    className="h-full rounded-full bg-violet-400/35"
                                    style={{ width: `${Math.round((v.count / max) * 100)}%` }}
                                  />
                                </div>
                                <div className="w-10 text-right text-[11px] text-white/60 tabular-nums">
                                  {v.count}
                                </div>
                              </div>
                            ));
                          })()}
                        </div>
                      ) : (
                        <div className="mt-2 text-sm text-white/55">No venue info in export.</div>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-1 gap-3">
                    {viewPapers.length ? (
                      viewPapers.map((p) => (
                        <a
                          key={p.id}
                          href={p.url ?? p.id}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-xl border border-white/10 bg-white/[0.02] p-4 hover:bg-white/[0.05]"
                        >
                          <div className="text-sm font-semibold text-white/90">{p.title}</div>
                          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-white/55">
                            {p.publicationYear ? <span>{p.publicationYear}</span> : null}
                            {typeof p.citedBy === "number" ? (
                              <span>Cited by {p.citedBy.toLocaleString()}</span>
                            ) : null}
                            {p.source ? <span>{p.source}</span> : null}
                          </div>
                          {p.methodTags?.length ? (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {p.methodTags.slice(0, 6).map((t) => (
                                <span
                                  key={t}
                                  className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[11px] text-white/70"
                                >
                                  {methodsByTag.get(t)?.label ?? t}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          {p.abstract ? (
                            <div className="mt-3 text-xs leading-5 text-white/55">
                              {trunc(p.abstract, 240)}
                            </div>
                          ) : null}
                        </a>
                      ))
                    ) : (
                      <div className="text-sm text-white/55">
                        No papers found in export for this domain yet. Re-run{" "}
                        <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                          python3 scripts/export_papers_catalog.py
                        </code>{" "}
                        after ingesting more papers.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-white/55">
                Catalog not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/export_papers_catalog.py
                </code>{" "}
                to generate <code>web/data/papers_catalog.json</code>.
              </div>
            )}
          </ChartCard>
        </div>

        {node.children.length ? (
          <div className="mt-5">
            <ChartCard
              title="Subdomains"
              subtitle="Aggregate values are computed from children."
            >
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                {node.children.map((cid) => {
                  const c = data.nodes[cid];
                  return (
                    <Link
                      key={cid}
                      href={`/domain/${encodeURIComponent(cid)}`}
                      className="group rounded-xl border border-white/10 bg-white/[0.02] p-4 hover:bg-white/[0.05]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-white/85">
                          {c.name}
                        </div>
                        <div className="text-xs text-white/60">
                          {c.overall.score.toFixed(1)}
                        </div>
                      </div>
                      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/5">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-400 to-rose-400 opacity-80"
                          style={{
                            width: `${Math.max(
                              0,
                              Math.min(100, c.overall.score),
                            )}%`,
                          }}
                        />
                      </div>
                      <div className="mt-2 text-[11px] text-white/45 group-hover:text-white/60">
                        Open →
                      </div>
                    </Link>
                  );
                })}
              </div>
            </ChartCard>
          </div>
        ) : null}

        <div className="mt-5">
          <ChartCard
            title="Evidence (Top papers)"
            subtitle="Auto-collected from open literature (OpenAlex)."
            right={
              node.openalex?.concept?.name ? (
                <a
                  className="text-xs font-semibold text-white/70 hover:text-white/90"
                  href={`https://openalex.org/works?filter=concept.id:${encodeURIComponent(
                    node.openalex.concept.id ?? "",
                  )}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  OpenAlex →
                </a>
              ) : null
            }
          >
            {evidence.length ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {evidence.map((e) => (
                  <a
                    key={e.url}
                    href={e.url}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-xl border border-white/10 bg-white/[0.02] p-4 hover:bg-white/[0.05]"
                  >
                    <div className="text-sm font-semibold text-white/85">
                      {e.title}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-white/55">
                      {e.year ? <span>{e.year}</span> : null}
                      {typeof e.citedBy === "number" ? (
                        <span>Cited by {e.citedBy}</span>
                      ) : null}
                      {e.venue ? <span>{e.venue}</span> : null}
                      {e.source ? <span>Source: {e.source}</span> : null}
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-sm text-white/55">
                No evidence yet. Run the update script to populate OpenAlex
                signals.
              </div>
            )}
          </ChartCard>
        </div>
      </main>
    </div>
  );
}
