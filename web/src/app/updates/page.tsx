import Link from "next/link";

import { ChartCard } from "@/components/ChartCard";
import { DailyUpdatesStackedBarChart } from "@/components/DailyUpdatesStackedBarChart";
import { getProgressData } from "@/lib/progress/get.server";
import { DIMENSION_KEYS } from "@/lib/progress/types";
import { readDailyUpdates } from "@/lib/updates/read.server";

export const dynamic = "force-dynamic";

const DIM_COLORS: Record<(typeof DIMENSION_KEYS)[number], string> = {
  data: "#22d3ee",
  model: "#a78bfa",
  predict: "#4ade80",
  experiment: "#fb7185",
  explain: "#fbbf24",
};

export default function UpdatesPage() {
  const data = readDailyUpdates();
  const progress = getProgressData();
  const dims = progress.dimensions.map((d) => ({ key: d.key, label: d.label }));

  const entries = (data?.entries ?? []).slice().sort((a, b) => (b.date || "").localeCompare(a.date || ""));

  return (
    <div className="min-h-screen bg-[radial-gradient(900px_600px_at_15%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_80%_15%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Updates
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              Daily Updates
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              将每日更新过一遍 LLM 分类成五维分布，并在这里做时间序列可视化。
            </p>
            {data ? (
              <div className="mt-3 text-xs text-white/40">
                Updated: {new Date(data.updatedAt).toLocaleString()} • Entries:{" "}
                {data.stats?.total ?? data.entries.length}
                {data.stats?.sourceTypes ? (
                  <>
                    {" "}
                    • manual: {data.stats.sourceTypes.manual ?? 0} • catalog:{" "}
                    {data.stats.sourceTypes.catalog ?? 0}
                  </>
                ) : null}
              </div>
            ) : (
              <div className="mt-3 text-xs text-rose-200/80">
                Data not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/update_daily_updates.py
                </code>{" "}
                to generate <code>web/data/daily_updates.json</code>.
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
        {data ? (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <ChartCard title="Timeline" subtitle="按天展示五维分布（堆叠=100）。">
                <DailyUpdatesStackedBarChart entries={data.entries} dimensions={dims} height={380} />
              </ChartCard>
            </div>
            <div className="lg:col-span-5">
              <ChartCard title="Recent Entries" subtitle="最近的更新条目与要点。">
                <div className="space-y-3">
                  {entries.slice(0, 12).map((e) => {
                    const summary = (e.summary ?? "").trim() || "(no summary)";
                    const tags = (e.tags ?? []).filter(Boolean).slice(0, 8);
                    return (
                      <div
                        key={e.id}
                        className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="text-sm font-semibold text-white/85">{e.date}</div>
                          <div className="text-[11px] text-white/45">
                            {e.sourceType ?? "manual"}
                            {" • "}
                            {e.mode}
                            {typeof e.confidence === "number"
                              ? ` • conf=${e.confidence.toFixed(2)}`
                              : ""}
                          </div>
                        </div>
                        <div className="mt-2 text-sm leading-6 text-white/70">{summary}</div>
                        <div className="mt-3 flex h-2 w-full overflow-hidden rounded-full bg-white/10">
                          {DIMENSION_KEYS.map((k) => (
                            <div
                              key={k}
                              style={{
                                width: `${Math.max(0, Math.min(100, Number(e.dimensions?.[k] ?? 0)))}%`,
                                backgroundColor: DIM_COLORS[k],
                              }}
                            />
                          ))}
                        </div>
                        {tags.length ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {tags.map((t) => (
                              <span
                                key={t}
                                className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-white/70"
                              >
                                {t}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        {e.highlights?.length ? (
                          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-6 text-white/60">
                            {e.highlights.slice(0, 6).map((h, idx) => (
                              <li key={`${e.id}:${idx}`}>{h}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </ChartCard>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  );
}
