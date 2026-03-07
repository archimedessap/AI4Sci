import Link from "next/link";

import { ChartCard } from "@/components/ChartCard";
import { FirstPrinciplesScatterChart } from "@/components/FirstPrinciplesScatterChart";
import { readFirstPrinciplesData } from "@/lib/first-principles/read.server";
import {
  FIRST_PRINCIPLES_AXIS_KEYS,
  type FirstPrinciplesData,
  type FirstPrinciplesRankingEntry,
} from "@/lib/first-principles/types";

export const dynamic = "force-dynamic";

const AXIS_LABELS: Record<(typeof FIRST_PRINCIPLES_AXIS_KEYS)[number], string> = {
  observability: "Observability",
  compressibility: "Compressibility",
  causalGrasp: "Causal Grasp",
  intervention: "Intervention",
  autonomyReadiness: "Autonomy Readiness",
};

const DIM_COLORS: Record<string, string> = {
  data: "#22d3ee",
  model: "#a78bfa",
  predict: "#4ade80",
  experiment: "#fb7185",
  explain: "#fbbf24",
};

function RankingList({
  title,
  subtitle,
  items,
}: {
  title: string;
  subtitle: string;
  items: FirstPrinciplesRankingEntry[];
}) {
  return (
    <ChartCard title={title} subtitle={subtitle}>
      <div className="space-y-3">
        {items.length ? (
          items.map((item, idx) => (
            <div
              key={`${title}:${item.id}:${idx}`}
              className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-white/85">{item.name}</div>
                  <div className="mt-1 text-[11px] text-white/45">
                    {item.macroName} • {item.profileLabel}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold text-cyan-200">{item.value.toFixed(1)}</div>
                  <div className="text-[11px] text-white/40">{item.label}</div>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-white/55">
                <div className="rounded-lg border border-white/8 bg-white/[0.02] px-2 py-1.5">
                  closure {item.closureReadiness.toFixed(1)}
                </div>
                <div className="rounded-lg border border-white/8 bg-white/[0.02] px-2 py-1.5">
                  momentum {item.momentum7d.toFixed(1)}
                </div>
                <div className="rounded-lg border border-white/8 bg-white/[0.02] px-2 py-1.5">
                  new papers {item.newPapers7d}
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-sm text-white/45">
            No ranking data.
          </div>
        )}
      </div>
    </ChartCard>
  );
}

function FreshnessPill({
  name,
  ageHours,
  timestamp,
}: {
  name: string;
  ageHours?: number | null;
  timestamp?: string | null;
}) {
  const statusColor =
    typeof ageHours === "number" && ageHours <= 26
      ? "text-emerald-200 border-emerald-400/25 bg-emerald-400/10"
      : typeof ageHours === "number" && ageHours <= 72
        ? "text-amber-200 border-amber-400/25 bg-amber-400/10"
        : "text-rose-200 border-rose-400/25 bg-rose-400/10";

  return (
    <div className={`rounded-xl border px-3 py-2 ${statusColor}`}>
      <div className="text-[11px] uppercase tracking-[0.16em] opacity-80">{name}</div>
      <div className="mt-1 text-sm font-semibold">
        {typeof ageHours === "number" ? `${ageHours.toFixed(1)}h ago` : "unknown"}
      </div>
      <div className="mt-1 text-[11px] opacity-70">
        {timestamp ? new Date(timestamp).toLocaleString() : "timestamp missing"}
      </div>
    </div>
  );
}

function Watchboard({ data }: { data: FirstPrinciplesData }) {
  const monitor = data.monitor;
  const dimensionMix = monitor?.dimensionMix ?? {};
  const topUpdates = monitor?.latestUpdates ?? [];
  const watchlist = monitor?.watchlist ?? [];
  const diagnoses = monitor?.diagnoses ?? [];
  const recentPapers = monitor?.recentPapers;
  const directSources = monitor?.directSources;

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
      <div className="lg:col-span-7">
        <ChartCard
          title="Daily Watchboard"
          subtitle="把“新内容”转成可监测的认识论信号：哪些是观测扩张，哪些是机制推进，哪些接近闭环。"
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {(monitor?.freshness ?? []).map((item) => (
              <FreshnessPill
                key={item.name}
                name={item.name}
                ageHours={item.ageHours}
                timestamp={item.timestamp}
              />
            ))}
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-4">
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-white/45">Recent Papers</div>
              <div className="mt-3 space-y-2 text-sm text-white/75">
                <div className="flex items-center justify-between gap-4">
                  <span>last 1d</span>
                  <span className="font-semibold text-white">{recentPapers?.last1d ?? 0}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>last 3d</span>
                  <span className="font-semibold text-white">{recentPapers?.last3d ?? 0}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>last 7d</span>
                  <span className="font-semibold text-white">{recentPapers?.last7d ?? 0}</span>
                </div>
              </div>
              <div className="mt-3 text-[11px] text-white/45">
                latest publication: {recentPapers?.latestPublicationDate ?? "unknown"}
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-white/45">Direct Sources</div>
              <div className="mt-3 space-y-2 text-sm text-white/75">
                <div className="flex items-center justify-between gap-4">
                  <span>last 6h</span>
                  <span className="font-semibold text-white">{directSources?.counts?.last6h ?? 0}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>last 24h</span>
                  <span className="font-semibold text-white">{directSources?.counts?.last24h ?? 0}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>last 72h</span>
                  <span className="font-semibold text-white">{directSources?.counts?.last72h ?? 0}</span>
                </div>
              </div>
              <div className="mt-3 text-[11px] text-white/45">
                errors: {directSources?.errors ?? 0}
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 md:col-span-2">
              <div className="text-xs uppercase tracking-[0.16em] text-white/45">Update Mix</div>
              <div className="mt-4 space-y-3">
                {Object.entries(dimensionMix).map(([key, value]) => (
                  <div key={key}>
                    <div className="flex items-center justify-between gap-4 text-xs text-white/65">
                      <span>{key}</span>
                      <span>{Number(value).toFixed(1)}</span>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/10">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max(0, Math.min(100, Number(value) || 0))}%`,
                          backgroundColor: DIM_COLORS[key] ?? "#94a3b8",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {diagnoses.length ? (
            <div className="mt-4 rounded-2xl border border-cyan-400/15 bg-cyan-400/5 p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-cyan-100/70">Machine Diagnosis</div>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-white/75">
                {diagnoses.map((item, idx) => (
                  <li key={`diag:${idx}`}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </ChartCard>
      </div>

      <div className="lg:col-span-5">
        <ChartCard
          title="What To Watch"
          subtitle="优先跟踪那些“更新密集”且哲学上仍不稳定的领域。"
        >
          <div className="space-y-3">
            {watchlist.length ? (
              watchlist.map((item) => (
                <div
                  key={`watch:${item.id}`}
                  className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-white/85">{item.name}</div>
                      <div className="mt-1 text-[11px] text-white/45">
                        {item.macroName} • {item.profileLabel}
                      </div>
                    </div>
                    <Link
                      href={`/domain/${encodeURIComponent(item.id)}`}
                      className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold text-white/70 hover:bg-white/[0.08]"
                    >
                      Open
                    </Link>
                  </div>
                  <div className="mt-3 space-y-1 text-sm leading-6 text-white/65">
                    {item.reasons.map((reason, idx) => (
                      <div key={`reason:${idx}`}>{reason}</div>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-sm text-white/45">
                No active watchlist yet.
              </div>
            )}
          </div>

          {topUpdates.length ? (
            <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-white/45">Latest Updates</div>
              <div className="mt-3 space-y-3">
                {topUpdates.map((item, idx) => (
                  <div key={`update:${idx}`} className="border-l border-white/10 pl-3">
                    <div className="text-[11px] text-white/45">
                      {item.date} • {item.sourceType} • conf {Number(item.confidence ?? 0).toFixed(2)}
                    </div>
                    <div className="mt-1 text-sm leading-6 text-white/70">{item.summary}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {directSources?.recentItems?.length ? (
            <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-white/45">Latest Direct Hits</div>
              <div className="mt-3 space-y-3">
                {directSources.recentItems.slice(0, 4).map((item, idx) => (
                  <div key={`direct:${idx}`} className="border-l border-white/10 pl-3">
                    <div className="text-[11px] text-white/45">
                      {item.publishedAt} • {item.sourceName} • {item.isNew ? "new" : "seen"}
                    </div>
                    <div className="mt-1 text-sm leading-6 text-white/70">{item.title}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </ChartCard>
      </div>
    </div>
  );
}

export default function FirstPrinciplesPage() {
  const data = readFirstPrinciplesData();

  return (
    <div className="min-h-screen bg-[radial-gradient(1000px_600px_at_12%_10%,rgba(34,211,238,0.12),transparent_60%),radial-gradient(900px_600px_at_88%_12%,rgba(251,191,36,0.10),transparent_60%),radial-gradient(900px_700px_at_50%_95%,rgba(244,114,182,0.10),transparent_55%),linear-gradient(180deg,#05070d_0%,#040612_42%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / First Principles
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              First Principles Lens
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              不把 AI for Science 的进展混成单一热度分。这里把它拆成五个不可互相替代的层次：
              能否稳定观测，能否压缩规律，能否触到机制，能否形成干预，能否收束为自治闭环。
            </p>
            {data ? (
              <div className="mt-3 text-xs text-white/40">
                Updated: {new Date(data.updatedAt).toLocaleString()} • Domains: {data.domains.length}
                {data.window?.paperDays ? ` • watch window: ${data.window.paperDays}d` : ""}
              </div>
            ) : (
              <div className="mt-3 text-xs text-rose-200/80">
                Data not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/analyze_first_principles_lens.py
                </code>{" "}
                to generate <code>web/data/first_principles_lens.json</code>.
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/monitor"
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
            >
              Monitor
            </Link>
            <Link
              href="/trends"
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
            >
              Trends
            </Link>
            <Link
              href="/updates"
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
            >
              Updates
            </Link>
            <Link
              href="/"
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
            >
              Back
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 pb-16">
        {data ? <FirstPrinciplesBody data={data} /> : null}
      </main>
    </div>
  );
}

function FirstPrinciplesBody({ data }: { data: FirstPrinciplesData }) {
  const rankings = data.rankings ?? {};
  const domains = data.domains.slice().sort((a, b) => b.closureReadiness - a.closureReadiness);

  return (
    <>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <ChartCard
            title="Five Irreducible Axes"
            subtitle="这五个维度不能相互替代。预测得好，不等于理解得深；实验自动化强，也不等于已经接近统一理论。"
          >
            <div className="space-y-3">
              {FIRST_PRINCIPLES_AXIS_KEYS.map((key) => (
                <div
                  key={key}
                  className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3"
                >
                  <div className="text-sm font-semibold text-white/85">{AXIS_LABELS[key]}</div>
                  <div className="mt-2 text-sm leading-6 text-white/60">
                    {data.definitions?.[key] ?? "Definition unavailable."}
                  </div>
                </div>
              ))}
            </div>
          </ChartCard>
        </div>
        <div className="lg:col-span-7">
          <ChartCard
            title="Reading The Atlas"
            subtitle="第一性原理视角下，AI4Sci 的核心问题不是“热不热”，而是它到底在替代哪一段科学活动。"
          >
            <div className="space-y-4 text-sm leading-7 text-white/70">
              <p>
                如果某个领域的 <span className="font-semibold text-white/85">compressibility</span>{" "}
                明显高于 <span className="font-semibold text-white/85">causal grasp</span>，
                就意味着 AI 已经像高性能仪器一样抓到了可压缩规律，但还没有稳固进入机制层。
              </p>
              <p>
                如果 <span className="font-semibold text-white/85">intervention</span> 与{" "}
                <span className="font-semibold text-white/85">autonomy readiness</span> 一起抬升，
                那说明它开始接近“能自己改进证据结构”的科学代理，而不仅是离线分析器。
              </p>
              <p>
                这里的 <span className="font-semibold text-white/85">closure readiness</span>{" "}
                不是平均分，而是对最短板有惩罚的闭环就绪度。真正的 AI4Sci 进展，必须同时跨过观测、压缩、解释、干预和自治五个门槛。
              </p>
            </div>
          </ChartCard>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-6">
          <ChartCard
            title="Compression vs Causal Grasp"
            subtitle="右下象限通常是“工具主义前沿”：模型/预测先跑起来，但机制理解还没跟上。"
          >
            <FirstPrinciplesScatterChart
              domains={domains}
              xKey="compressibility"
              yKey="causalGrasp"
              xLabel="Compressibility"
              yLabel="Causal Grasp"
            />
          </ChartCard>
        </div>
        <div className="lg:col-span-6">
          <ChartCard
            title="Intervention vs Autonomy"
            subtitle="右上象限代表更接近科学闭环的领域：不仅能建议动作，还能承接实验/工作流自动化。"
          >
            <FirstPrinciplesScatterChart
              domains={domains}
              xKey="intervention"
              yKey="autonomyReadiness"
              xLabel="Intervention"
              yLabel="Autonomy Readiness"
            />
          </ChartCard>
        </div>
      </div>

      <div className="mt-5">
        <Watchboard data={data} />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <RankingList
          title="Instrumentalist Frontiers"
          subtitle="预测/压缩已经很强，但机制理解仍明显偏弱。"
          items={rankings.instrumentalistFrontiers ?? []}
        />
        <RankingList
          title="Closure Leaders"
          subtitle="更接近“可复用科学闭环”的领域。"
          items={rankings.closureLeaders ?? []}
        />
        <RankingList
          title="Mechanism Leaders"
          subtitle="解释、理论与统一性最靠前的领域。"
          items={rankings.mechanismLeaders ?? []}
        />
      </div>
    </>
  );
}
