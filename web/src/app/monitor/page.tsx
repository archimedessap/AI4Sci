import Link from "next/link";

import { ChartCard } from "@/components/ChartCard";
import { readMonitorStatus } from "@/lib/monitor/read.server";

export const dynamic = "force-dynamic";

function severityClasses(severity: string | undefined) {
  switch (severity) {
    case "critical":
      return "border-rose-400/25 bg-rose-400/10 text-rose-100";
    case "warn":
      return "border-amber-400/25 bg-amber-400/10 text-amber-100";
    default:
      return "border-cyan-400/20 bg-cyan-400/10 text-cyan-100";
  }
}

function freshnessClasses(status: string | undefined) {
  switch (status) {
    case "critical":
    case "missing":
      return "border-rose-400/25 bg-rose-400/10 text-rose-100";
    case "stale":
      return "border-amber-400/25 bg-amber-400/10 text-amber-100";
    default:
      return "border-emerald-400/25 bg-emerald-400/10 text-emerald-100";
  }
}

export default function MonitorPage() {
  const data = readMonitorStatus();

  return (
    <div className="min-h-screen bg-[radial-gradient(900px_600px_at_10%_10%,rgba(34,211,238,0.12),transparent_60%),radial-gradient(900px_600px_at_85%_12%,rgba(74,222,128,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#050714_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Monitor
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              Monitor Console
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              运行层视图：看刷新链路是否健康、哪些数据陈旧、当前应该优先追踪哪些领域。
            </p>
            {data ? (
              <div className="mt-3 text-xs text-white/40">
                Updated: {new Date(data.updatedAt).toLocaleString()} • Mode: {data.run?.mode ?? "unknown"}
                {" • "}Success: {String(data.run?.success ?? false)}
              </div>
            ) : (
              <div className="mt-3 text-xs text-rose-200/80">
                Data not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/run_monitor_cycle.py --mode fast
                </code>{" "}
                to generate <code>web/data/monitor_status.json</code>.
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/first-principles"
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
            >
              First Principles
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
        {data ? <MonitorBody data={data} /> : null}
      </main>
    </div>
  );
}

function MonitorBody({ data }: { data: NonNullable<ReturnType<typeof readMonitorStatus>> }) {
  const alerts = data.alerts ?? [];
  const freshness = data.freshness ?? [];
  const commands = data.run?.commands ?? [];
  const watchlist = data.pipeline?.watchlist ?? [];
  const diagnoses = data.pipeline?.diagnoses ?? [];
  const topMovers = data.pipeline?.topMovers ?? [];
  const latestUpdates = data.pipeline?.latestUpdates ?? [];
  const recentPapers = data.pipeline?.recentPapers;
  const directSources = data.pipeline?.directSources;

  return (
    <>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <ChartCard title="Run Summary" subtitle="这次监控周期做了什么、用了多久、是否成功。">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Mode</div>
                <div className="mt-2 font-semibold text-white/85">{data.run?.mode ?? "unknown"}</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Success</div>
                <div className="mt-2 font-semibold text-white/85">{String(data.run?.success ?? false)}</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Critical</div>
                <div className="mt-2 font-semibold text-white/85">{data.summary?.critical ?? 0}</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Warn</div>
                <div className="mt-2 font-semibold text-white/85">{data.summary?.warn ?? 0}</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 col-span-2">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Wall Clock</div>
                <div className="mt-2 font-semibold text-white/85">
                  {typeof data.run?.wallClockSeconds === "number"
                    ? `${data.run.wallClockSeconds.toFixed(2)}s`
                    : "unknown"}
                </div>
              </div>
            </div>
          </ChartCard>
        </div>

        <div className="lg:col-span-8">
          <ChartCard title="Alerts" subtitle="只要这里持续出现 warn/critical，就说明你的日更链路还不够稳。">
            <div className="space-y-3">
              {alerts.length ? (
                alerts.map((alert, idx) => (
                  <div
                    key={`${alert.code}:${idx}`}
                    className={`rounded-xl border px-4 py-3 ${severityClasses(alert.severity)}`}
                  >
                    <div className="text-[11px] uppercase tracking-[0.16em] opacity-80">
                      {alert.severity} • {alert.code}
                    </div>
                    <div className="mt-2 text-sm leading-6">{alert.message}</div>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-sm text-white/45">
                  No alerts.
                </div>
              )}
            </div>
          </ChartCard>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <ChartCard title="Freshness" subtitle="核心数据文件的时效性。这个视图直接回答“今天的数据是不是新鲜的”。">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {freshness.map((item) => (
                <div
                  key={item.name}
                  className={`rounded-xl border px-4 py-3 ${freshnessClasses(item.status)}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold">{item.name}</div>
                      <div className="mt-1 text-[11px] opacity-70">{item.path}</div>
                    </div>
                    <div className="rounded-full border border-current/20 px-2.5 py-1 text-[11px] uppercase tracking-[0.14em]">
                      {item.status ?? "unknown"}
                    </div>
                  </div>
                  <div className="mt-3 text-sm opacity-85">
                    {typeof item.ageHours === "number" ? `${item.ageHours.toFixed(1)}h old` : "age unknown"}
                  </div>
                  <div className="mt-1 text-[11px] opacity-70">
                    threshold {typeof item.thresholdHours === "number" ? `${item.thresholdHours}h` : "n/a"}
                  </div>
                </div>
              ))}
            </div>
          </ChartCard>
        </div>

        <div className="lg:col-span-5">
          <ChartCard title="Recent Signals" subtitle="把运行层和内容层接起来。">
            <div className="space-y-3 text-sm text-white/75">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Direct Sources</div>
                <div className="mt-3 space-y-2">
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
                  updated: {directSources?.updatedAt ? new Date(directSources.updatedAt).toLocaleString() : "unknown"}
                  {" • "}errors: {directSources?.errors ?? 0}
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Recent Papers</div>
                <div className="mt-3 space-y-2">
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
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Recent Updates</div>
                <div className="mt-3 space-y-3">
                  {latestUpdates.length ? (
                    latestUpdates.slice(0, 4).map((item, idx) => (
                      <div key={`update:${idx}`} className="border-l border-white/10 pl-3">
                        <div className="text-[11px] text-white/45">
                          {item.date} • {item.sourceType} • conf {Number(item.confidence ?? 0).toFixed(2)}
                        </div>
                        <div className="mt-1 text-sm leading-6 text-white/70">{item.summary}</div>
                      </div>
                    ))
                  ) : (
                    <div className="text-sm text-white/45">No recent update entries.</div>
                  )}
                </div>
              </div>

              {directSources?.recentItems?.length ? (
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
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
            </div>
          </ChartCard>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <ChartCard title="Commands" subtitle="实际执行的命令，便于排查哪一步慢或失败。">
            <div className="space-y-3">
              {commands.map((cmd, idx) => (
                <div
                  key={`${cmd.label}:${idx}`}
                  className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm font-semibold text-white/85">{cmd.label}</div>
                    <div className="text-[11px] text-white/45">
                      {String(cmd.ok)} • {typeof cmd.durationSeconds === "number" ? `${cmd.durationSeconds.toFixed(2)}s` : "unknown"}
                    </div>
                  </div>
                  <div className="mt-2 break-all font-mono text-[11px] leading-5 text-white/55">{cmd.cmd}</div>
                  {cmd.error ? <div className="mt-2 text-[11px] text-rose-200/80">{cmd.error}</div> : null}
                </div>
              ))}
            </div>
          </ChartCard>
        </div>

        <div className="lg:col-span-7">
          <ChartCard title="Priority Queue" subtitle="这就是你每天应该看的“少量高价值问题”。">
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
                  No watchlist entries.
                </div>
              )}
            </div>

            {diagnoses.length ? (
              <div className="mt-4 rounded-xl border border-cyan-400/15 bg-cyan-400/5 p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-cyan-100/70">Diagnoses</div>
                <div className="mt-3 space-y-2 text-sm leading-6 text-white/75">
                  {diagnoses.map((item, idx) => (
                    <div key={`diag:${idx}`}>{item}</div>
                  ))}
                </div>
              </div>
            ) : null}

            {topMovers.length ? (
              <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Top Movers</div>
                <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                  {topMovers.slice(0, 6).map((item) => (
                    <div
                      key={`mover:${item.id}`}
                      className="rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2 text-sm text-white/70"
                    >
                      <div className="font-semibold text-white/85">{item.name}</div>
                      <div className="mt-1 text-[11px] text-white/45">
                        {item.macroName} • {item.label} {item.value.toFixed(1)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {directSources?.topSources?.length ? (
              <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-white/45">Source Health</div>
                <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                  {directSources.topSources.map((item) => (
                    <div
                      key={`source:${item.id}`}
                      className="rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2 text-sm text-white/70"
                    >
                      <div className="font-semibold text-white/85">{item.name}</div>
                      <div className="mt-1 text-[11px] text-white/45">
                        {item.status ?? "unknown"} • new {item.newItems ?? 0} • included {item.includedItems ?? 0}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </ChartCard>
        </div>
      </div>
    </>
  );
}
