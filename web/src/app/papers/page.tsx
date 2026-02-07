import fs from "node:fs";
import path from "node:path";

import Link from "next/link";

export const dynamic = "force-dynamic";

type CatalogDomain = {
  id: string;
  name: string;
  count: number;
};

type CatalogMethod = {
  tag: string;
  label: string;
  description?: string | null;
  count: number;
};

type CatalogPaper = {
  id: string;
  title: string;
  abstract?: string | null;
  publicationYear?: number | null;
  publicationDate?: string | null;
  citedBy?: number | null;
  url?: string | null;
  source?: string | null;
  domains?: string[];
  methodTags?: string[];
};

type PapersCatalog = {
  version: string;
  generatedAt: string;
  db?: { path?: string; papers?: number; links?: number };
  domains?: CatalogDomain[];
  methods?: CatalogMethod[];
  papers?: CatalogPaper[];
};

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

function readCatalog(): PapersCatalog | null {
  const p = dataPath("papers_catalog.json");
  if (!fs.existsSync(p)) return null;
  try {
    const raw = fs.readFileSync(p, "utf8");
    return JSON.parse(raw) as PapersCatalog;
  } catch {
    return null;
  }
}

function normString(v: unknown) {
  return typeof v === "string" ? v : "";
}

function normInt(v: unknown, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function buildQuery(params: Record<string, string | number | undefined>) {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined) continue;
    const s = String(v);
    if (!s) continue;
    out.set(k, s);
  }
  const q = out.toString();
  return q ? `?${q}` : "";
}

const MS_PER_YEAR = 1000 * 60 * 60 * 24 * 365;

type PaperSort = "cited" | "recent" | "rate";

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

export default function PapersPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const catalog = readCatalog();

  const q = normString(searchParams.q).trim();
  const domain = normString(searchParams.domain).trim();
  const method = normString(searchParams.method).trim();
  const rawSort = normString(searchParams.sort).trim();
  const sort: PaperSort =
    rawSort === "recent" || rawSort === "rate" || rawSort === "cited" ? rawSort : "cited";
  const page = Math.max(1, normInt(searchParams.page, 1));
  const perPage = Math.max(10, Math.min(100, normInt(searchParams.perPage, 30)));

  const domains: CatalogDomain[] = (catalog?.domains ?? []).filter(Boolean);
  const methods: CatalogMethod[] = (catalog?.methods ?? []).filter(Boolean);
  const nameByDomain = new Map(domains.map((d) => [d.id, d.name]));
  const labelByMethod = new Map(methods.map((m) => [m.tag, m.label]));
  let papers: CatalogPaper[] = (catalog?.papers ?? []).filter(Boolean);

  if (domain) {
    papers = papers.filter((p) => (p.domains ?? []).includes(domain));
  }

  if (method) {
    papers = papers.filter((p) => (p.methodTags ?? []).includes(method));
  }

  if (q) {
    const needle = q.toLowerCase();
    papers = papers.filter((p) => {
      const t = (p.title ?? "").toLowerCase();
      const a = (p.abstract ?? "").toLowerCase();
      return t.includes(needle) || a.includes(needle);
    });
  }

  papers.sort((a, b) => {
    if (sort === "recent") {
      const ad = publicationTimestamp(a);
      const bd = publicationTimestamp(b);
      if (ad !== bd) return bd - ad;
      const ac = a.citedBy ?? 0;
      const bc = b.citedBy ?? 0;
      return bc - ac;
    }
    if (sort === "rate") {
      const ar = citationRate(a);
      const br = citationRate(b);
      if (ar !== br) return br - ar;
    }
    const ac = a.citedBy ?? 0;
    const bc = b.citedBy ?? 0;
    if (ac !== bc) return bc - ac;
    return publicationTimestamp(b) - publicationTimestamp(a);
  });

  const total = papers.length;
  const pageCount = Math.max(1, Math.ceil(total / perPage));
  const safePage = Math.min(page, pageCount);
  const start = (safePage - 1) * perPage;
  const view = papers.slice(start, start + perPage);

  return (
    <div className="min-h-screen bg-[radial-gradient(900px_600px_at_15%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_80%_15%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Papers
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              AI4Sci Paper Library
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              从本地 SQLite 论文库导出的可查阅目录（title + abstract + 链接，按领域 Top‑k 抽样）。运行{" "}
              <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                python3 scripts/ingest_ai4sci_openalex.py
              </code>{" "}
              会自动同步更新。
            </p>
            {catalog ? (
              <div className="mt-3 text-xs text-white/40">
                Generated: {new Date(catalog.generatedAt).toLocaleString()} • DB:{" "}
                <span className="opacity-80">{catalog.db?.path ?? "data/papers.sqlite"}</span>{" "}
                • papers: {catalog.db?.papers ?? "?"}
              </div>
            ) : (
              <div className="mt-3 text-xs text-rose-200/80">
                Catalog not found. Run{" "}
                <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/export_papers_catalog.py
                </code>{" "}
                (or ingest) to generate <code>web/data/papers_catalog.json</code>.
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
        <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <form className="grid grid-cols-1 gap-3 md:grid-cols-12" method="GET" action="/papers">
            <div className="md:col-span-5">
              <div className="text-xs font-semibold text-white/70">Search</div>
              <input
                name="q"
                defaultValue={q}
                placeholder="title / abstract keyword"
                className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none placeholder:text-white/30 focus:border-cyan-400/60"
              />
            </div>
            <div className="md:col-span-3">
              <div className="text-xs font-semibold text-white/70">Domain</div>
              <select
                name="domain"
                defaultValue={domain}
                className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none focus:border-cyan-400/60"
              >
                <option value="">All domains</option>
                {domains.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.count})
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <div className="text-xs font-semibold text-white/70">Method</div>
              <select
                name="method"
                defaultValue={method}
                className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none focus:border-cyan-400/60"
              >
                <option value="">All methods</option>
                {methods.map((m) => (
                  <option key={m.tag} value={m.tag}>
                    {m.label} ({m.count})
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <div className="text-xs font-semibold text-white/70">Sort</div>
              <select
                name="sort"
                defaultValue={sort}
                className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none focus:border-cyan-400/60"
              >
                <option value="cited">Most cited</option>
                <option value="rate">Citation rate</option>
                <option value="recent">Most recent</option>
              </select>
            </div>
            <div className="md:col-span-1">
              <div className="text-xs font-semibold text-white/70"> </div>
              <button
                type="submit"
                className="mt-2 w-full rounded-xl bg-cyan-400/15 px-4 py-2 text-sm font-semibold text-cyan-200 hover:bg-cyan-400/20"
              >
                Go
              </button>
            </div>
            <input type="hidden" name="perPage" value={String(perPage)} />
          </form>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-white/55">
            <div>
              Showing {total ? start + 1 : 0}–{Math.min(start + perPage, total)} of{" "}
              {total} results
            </div>
            <div className="flex items-center gap-2">
              <Link
                href={`/papers${buildQuery({ q, domain, method, sort, perPage, page: Math.max(1, safePage - 1) })}`}
                className={`rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 font-semibold ${safePage <= 1 ? "pointer-events-none opacity-40" : "hover:bg-white/[0.06]"}`}
              >
                Prev
              </Link>
              <span className="text-white/45">
                Page {safePage} / {pageCount}
              </span>
              <Link
                href={`/papers${buildQuery({ q, domain, method, sort, perPage, page: Math.min(pageCount, safePage + 1) })}`}
                className={`rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 font-semibold ${safePage >= pageCount ? "pointer-events-none opacity-40" : "hover:bg-white/[0.06]"}`}
              >
                Next
              </Link>
            </div>
          </div>
        </section>

        <div className="mt-5 grid grid-cols-1 gap-3">
          {view.map((p) => {
            const url = p.url || p.id;
            const doms = (p.domains ?? [])
              .map((d) => ({ id: d, name: nameByDomain.get(d) ?? d }))
              .slice(0, 6);
            const meths = (p.methodTags ?? [])
              .map((t) => ({ tag: t, label: labelByMethod.get(t) ?? t }))
              .slice(0, 4);
            return (
              <article
                key={p.id}
                className="rounded-2xl border border-white/10 bg-white/[0.02] p-5 hover:bg-white/[0.04]"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-semibold text-white/90 hover:text-cyan-200"
                  >
                    {p.title}
                  </a>
                  <div className="text-xs text-white/55">
                    {p.publicationYear ? <span>{p.publicationYear}</span> : null}
                    {typeof p.citedBy === "number" ? (
                      <span className="ml-3">Cited by {p.citedBy}</span>
                    ) : null}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-white/55">
                  {doms.map((d) => (
                    <Link
                      key={d.id}
                      href={`/papers${buildQuery({ q, domain: d.id, method, sort, perPage, page: 1 })}`}
                      className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 hover:bg-white/[0.06]"
                    >
                      {d.name}
                    </Link>
                  ))}
                  {meths.map((m) => (
                    <Link
                      key={`m:${m.tag}`}
                      href={`/papers${buildQuery({ q, domain, method: m.tag, sort, perPage, page: 1 })}`}
                      className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-cyan-100 hover:bg-cyan-400/15"
                      title={m.label}
                    >
                      {m.label}
                    </Link>
                  ))}
                  {p.source ? (
                    <span className="rounded-full border border-white/10 bg-white/[0.02] px-2.5 py-1">
                      {p.source}
                    </span>
                  ) : null}
                </div>
                {p.abstract ? (
                  <p className="mt-3 text-sm leading-6 text-white/60">
                    {p.abstract}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      </main>
    </div>
  );
}
