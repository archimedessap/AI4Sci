import fs from "node:fs";
import path from "node:path";

import Link from "next/link";

import { ChartCard } from "@/components/ChartCard";
import { ProblemMethodHeatmap, type ProblemMethodMapData } from "@/components/ProblemMethodHeatmap";

export const dynamic = "force-dynamic";

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

function readMap(): ProblemMethodMapData | null {
  const p = dataPath("problem_method_map.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as ProblemMethodMapData;
  } catch {
    return null;
  }
}

export default function ProblemMethodPage() {
  const map = readMap();

  return (
    <div className="min-h-screen bg-[radial-gradient(1000px_600px_at_15%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_80%_15%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Problem ↔ Method
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              Problem Space ↔ Method Space
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              参考 Bridging AI and Science：用“学科子领域(问题空间) × AI 方法类型(方法空间)”画出研究交叉热力图，
              并提示“高期望但低覆盖”的空白区（可点击进入论文列表）。
            </p>
            {map?.generatedAt ? (
              <div className="mt-3 text-xs text-white/40">
                Generated: {new Date(map.generatedAt).toLocaleString()} • Window: last{" "}
                {map.window?.years ?? "?"}y (since {map.window?.sinceYear ?? "?"})
              </div>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/papers"
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
            >
              Papers
            </Link>
            <Link
              href="/methodology"
              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
            >
              Methodology
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
        <ChartCard
          title="Heatmap + Blank Spots"
          subtitle={
            map
              ? "y=subfields (problem proxy), x=AI methods (tags). Values are paper counts (log-scaled for color)."
              : "Run the analyzer to generate web/data/problem_method_map.json."
          }
          right={
            map ? (
              <a
                href="https://arxiv.org/html/2412.09628v2"
                target="_blank"
                rel="noreferrer"
                className="text-xs font-semibold text-white/70 hover:text-white/90"
              >
                Bridging AI & Science →
              </a>
            ) : null
          }
        >
          {map ? (
            <ProblemMethodHeatmap data={map} />
          ) : (
            <div className="text-sm text-white/60">
              Not found: <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">web/data/problem_method_map.json</code>
              . Run{" "}
              <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                python3 scripts/analyze_problem_method_map.py
              </code>{" "}
              to generate it.
            </div>
          )}
        </ChartCard>
      </main>
    </div>
  );
}

