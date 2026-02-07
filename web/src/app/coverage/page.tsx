import fs from "node:fs";
import path from "node:path";

import Link from "next/link";

export const dynamic = "force-dynamic";

type CoverageMacro = {
  id: string;
  name: string;
  leafDomains: number;
  withDb: number;
  dbPapers: number;
};

type CoverageDomain = {
  id: string;
  name: string;
  macroId: string;
  macroName: string;
  db: { total: number; y0: number; y1: number };
  hasDiscoveryLayers: boolean;
  hasFormalLayers?: boolean;
  llm?: {
    scheme?: string | null;
    sampledPapers?: number | null;
    discoveryPapers?: number | null;
    confidence?: number | null;
  };
  scores?: Record<string, number>;
};

type CoverageReport = {
  version: string;
  generatedAt: string;
  db?: { path?: string; papers?: number; domainLinks?: number };
  summary?: {
    leafDomains?: number;
    domainsWithDb?: number;
    domainsMissingDb?: number;
    domainsWithLayers?: number;
  };
  macros?: CoverageMacro[];
  domains?: CoverageDomain[];
};

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

function readCoverage(): CoverageReport | null {
  const p = dataPath("coverage_report.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as CoverageReport;
  } catch {
    return null;
  }
}

function clampScore(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

export default function CoveragePage() {
  const data = readCoverage();
  const domains = (data?.domains ?? []).filter(Boolean);
  const macros = (data?.macros ?? []).filter(Boolean);
  const missing = domains.filter((d) => (d.db?.total ?? 0) <= 0);

  const byMacro = new Map(macros.map((m) => [m.id, m]));
  const ordered = [...domains].sort((a, b) => {
    if (a.macroId !== b.macroId) return a.macroId.localeCompare(b.macroId);
    const at = a.db?.total ?? 0;
    const bt = b.db?.total ?? 0;
    if (at !== bt) return bt - at;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="min-h-screen bg-[radial-gradient(900px_600px_at_15%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_80%_15%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Coverage
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              Coverage (Taxonomy × Paper DB)
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              用来回答“哪些领域缺数据/缺分层/缺近一年信号”。运行{" "}
              <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                python3 scripts/analyze_coverage_report.py
              </code>{" "}
              可刷新本页所用的 <code>web/data/coverage_report.json</code>。
            </p>
            {data ? (
              <div className="mt-3 text-xs text-white/40">
                Generated: {new Date(data.generatedAt).toLocaleString()} • DB:{" "}
                <span className="opacity-80">{data.db?.path ?? "data/papers.sqlite"}</span>{" "}
                • papers: {data.db?.papers ?? "?"} • leaf:{" "}
                {data.summary?.leafDomains ?? "?"} • with_db:{" "}
                {data.summary?.domainsWithDb ?? "?"}
              </div>
            ) : (
              <div className="mt-3 text-xs text-rose-200/80">
                Data not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/analyze_coverage_report.py
                </code>{" "}
                to generate <code>web/data/coverage_report.json</code>.
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
          <>
            <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <div className="text-xs font-semibold text-white/70">By macro</div>
              <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-white/65">
                {macros.map((m) => (
                  <span
                    key={m.id}
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.02] px-3 py-1"
                  >
                    <span className="font-semibold text-white/85">{m.name}</span>
                    <span className="opacity-70">leaf {m.leafDomains}</span>
                    <span className="opacity-70">with_db {m.withDb}</span>
                    <span className="opacity-70">papers {m.dbPapers.toLocaleString()}</span>
                  </span>
                ))}
              </div>
            </section>

            {missing.length ? (
              <section className="mt-5 rounded-2xl border border-rose-500/20 bg-rose-500/5 p-5">
                <div className="text-xs font-semibold text-rose-100/90">
                  Missing DB coverage (0 papers)
                </div>
                <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                  {missing.map((d) => (
                    <Link
                      key={d.id}
                      href={`/domain/${encodeURIComponent(d.id)}`}
                      className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-2 text-sm text-white/75 hover:bg-white/[0.05]"
                    >
                      <span className="text-white/55">{d.macroName} / </span>
                      <span className="font-semibold text-white/90">{d.name}</span>{" "}
                      <span className="text-xs text-white/45">({d.id})</span>
                    </Link>
                  ))}
                </div>
              </section>
            ) : null}

            <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <div className="text-xs font-semibold text-white/70">Domains</div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[880px] text-left text-sm">
                  <thead className="text-xs text-white/50">
                    <tr>
                      <th className="py-2 pr-4">Macro</th>
                      <th className="py-2 pr-4">Domain</th>
                      <th className="py-2 pr-4 text-right">DB</th>
                      <th className="py-2 pr-4 text-right">This year</th>
                      <th className="py-2 pr-4 text-right">Last year</th>
                      <th className="py-2 pr-4 text-center">LLM</th>
                      <th className="py-2 pr-4 text-right">Sample</th>
                      <th className="py-2 pr-0 text-right">OA overall</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {ordered.map((d) => {
                      const macro = byMacro.get(d.macroId);
                      const macroName = macro?.name ?? d.macroName ?? d.macroId;
                      const overall = clampScore(d.scores?.overall);
                      const llmLabel = (() => {
                        const parts: string[] = [];
                        if (d.hasDiscoveryLayers) parts.push("D");
                        if (d.hasFormalLayers) parts.push("F");
                        return parts.join("+");
                      })();
                      const sampled = Number(d.llm?.sampledPapers ?? 0) || 0;
                      return (
                        <tr key={d.id} className="hover:bg-white/[0.02]">
                          <td className="py-2 pr-4 text-white/65">{macroName}</td>
                          <td className="py-2 pr-4">
                            <Link
                              href={`/domain/${encodeURIComponent(d.id)}`}
                              className="font-semibold text-white/85 hover:text-white"
                            >
                              {d.name}
                            </Link>{" "}
                            <span className="text-xs text-white/45">({d.id})</span>
                          </td>
                          <td className="py-2 pr-4 text-right tabular-nums text-white/75">
                            {(d.db?.total ?? 0).toLocaleString()}
                          </td>
                          <td className="py-2 pr-4 text-right tabular-nums text-white/55">
                            {(d.db?.y0 ?? 0).toLocaleString()}
                          </td>
                          <td className="py-2 pr-4 text-right tabular-nums text-white/55">
                            {(d.db?.y1 ?? 0).toLocaleString()}
                          </td>
                          <td className="py-2 pr-4 text-center text-white/70">
                            {llmLabel}
                          </td>
                          <td className="py-2 pr-4 text-right tabular-nums text-white/60">
                            {sampled ? sampled.toLocaleString() : ""}
                          </td>
                          <td className="py-2 pr-0 text-right tabular-nums text-white/75">
                            {overall.toFixed(1)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 text-xs text-white/45">
                OA overall here = five-dimension average (quick scan).
              </div>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
