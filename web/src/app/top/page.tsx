import fs from "node:fs";
import path from "node:path";

import Link from "next/link";

export const dynamic = "force-dynamic";

type TopPaper = {
  id: string;
  title: string;
  url?: string | null;
  publicationDate?: string | null;
  publicationYear?: number | null;
  citedBy?: number | null;
  source?: string | null;
  score?: number | null;
  domainIds?: string[];
  domainNames?: string[];
};

type DomainTop = {
  domainId: string;
  domainName: string;
  totalInDb: number;
  totalInLastYear: number;
  top: TopPaper[];
};

type TopPapersData = {
  version: string;
  generatedAt: string;
  since: string;
  globalTotalInLastYear?: number;
  globalTop?: TopPaper[];
  byDomain?: DomainTop[];
};

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

function readTop(): TopPapersData | null {
  const p = dataPath("top_papers_last_year.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as TopPapersData;
  } catch {
    return null;
  }
}

function fmtDomains(p: TopPaper) {
  const names = (p.domainNames ?? []).filter(Boolean);
  if (names.length) return names.slice(0, 3).join(", ") + (names.length > 3 ? "…" : "");
  const ids = (p.domainIds ?? []).filter(Boolean);
  return ids.slice(0, 3).join(", ") + (ids.length > 3 ? "…" : "");
}

export default function TopPapersPage() {
  const data = readTop();

  return (
    <div className="min-h-screen bg-[radial-gradient(900px_600px_at_15%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_80%_15%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Top (1y)
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              Top AI4Sci Papers (Last Year)
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              近一年窗口内的“综合靠前”论文：综合分数=0.7×被引(归一化log) + 0.3×新近度（剔除未来日期）。
            </p>
            {data ? (
              <div className="mt-3 text-xs text-white/40">
                Generated: {new Date(data.generatedAt).toLocaleString()} • Since:{" "}
                <span className="opacity-80">{data.since}</span> • Papers in window:{" "}
                {data.globalTotalInLastYear ?? "?"}
              </div>
            ) : (
              <div className="mt-3 text-xs text-rose-200/80">
                Data not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/analyze_top_papers_last_year.py
                </code>{" "}
                to generate <code>web/data/top_papers_last_year.json</code>.
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
        {data?.globalTop?.length ? (
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <div className="text-xs font-semibold text-white/70">Global Top</div>
            <div className="mt-4 grid grid-cols-1 gap-3">
              {data.globalTop.map((p, idx) => {
                const title = (p.title ?? "").trim() || "(untitled)";
                const url = (p.url ?? p.id ?? "").trim();
                const dom = fmtDomains(p);
                const meta = [
                  dom ? `domains: ${dom}` : "",
                  p.publicationDate ? `date: ${p.publicationDate}` : "",
                  typeof p.citedBy === "number" ? `cited_by=${p.citedBy}` : "",
                  typeof p.score === "number" ? `score=${p.score}` : "",
                ]
                  .filter(Boolean)
                  .join(" • ");
                return (
                  <a
                    key={p.id || String(idx)}
                    href={url || undefined}
                    target="_blank"
                    rel="noreferrer"
                    className="group block rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 hover:bg-white/[0.05]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-sm font-semibold text-white/85 group-hover:text-white">
                        {idx + 1}. {title}
                      </div>
                      <div className="text-xs text-white/55">{meta}</div>
                    </div>
                  </a>
                );
              })}
            </div>
          </section>
        ) : null}

        {data?.byDomain?.length ? (
          <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <div className="text-xs font-semibold text-white/70">By Domain</div>
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              {data.byDomain.map((d) => (
                <div
                  key={d.domainId}
                  className="rounded-xl border border-white/10 bg-black/20 p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-white/85">
                      {d.domainName}{" "}
                      <span className="text-xs font-normal text-white/45">
                        ({d.domainId})
                      </span>
                    </div>
                    <div className="text-xs text-white/55">
                      last_year: {d.totalInLastYear} • db: {d.totalInDb}
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2">
                    {(d.top ?? []).map((p, idx) => {
                      const title = (p.title ?? "").trim() || "(untitled)";
                      const url = (p.url ?? p.id ?? "").trim();
                      const meta = [
                        p.publicationDate ? `date: ${p.publicationDate}` : "",
                        typeof p.citedBy === "number" ? `cited_by=${p.citedBy}` : "",
                        typeof p.score === "number" ? `score=${p.score}` : "",
                      ]
                        .filter(Boolean)
                        .join(" • ");
                      return (
                        <a
                          key={`${d.domainId}:${p.id || idx}`}
                          href={url || undefined}
                          target="_blank"
                          rel="noreferrer"
                          className="block rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 hover:bg-white/[0.05]"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="text-[13px] text-white/85">
                              {idx + 1}. {title}
                            </div>
                            <div className="text-[11px] text-white/55">{meta}</div>
                          </div>
                        </a>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
}

