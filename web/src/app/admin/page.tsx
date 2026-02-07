import Link from "next/link";

import { AdminClient } from "@/app/admin/AdminClient";
import { getProgressData } from "@/lib/progress/get.server";
import { readOverridesData } from "@/lib/progress/storage.server";
import { DIMENSION_KEYS, type DimensionKey } from "@/lib/progress/types";

export const dynamic = "force-dynamic";

export default function AdminPage() {
  const data = getProgressData();
  const overrides = readOverridesData();

  const requiresToken = Boolean(process.env.ADMIN_TOKEN) || process.env.NODE_ENV === "production";

  const nodes = Object.values(data.nodes)
    .sort((a, b) => (a.depth - b.depth) || (a.order ?? 0) - (b.order ?? 0))
    .map((n) => ({
      id: n.id,
      name: n.name,
      depth: n.depth,
      overallScore: n.overall.score,
      dimensions: DIMENSION_KEYS.reduce(
        (acc, k) => {
          acc[k] = n.dimensions[k].score;
          return acc;
        },
        {} as Record<DimensionKey, number>,
      ),
    }));

  return (
    <div className="min-h-screen bg-[radial-gradient(1000px_600px_at_20%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_75%_20%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Admin
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              Manual Overrides
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/60">
              用于纠偏自动评分：覆盖某节点的 overall 或某个维度的 score，并记录理由。
            </p>
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
        <AdminClient
          nodes={nodes}
          dimensions={data.dimensions.map((d) => ({ key: d.key, label: d.label }))}
          initialOverrides={overrides.nodes}
          requiresToken={requiresToken}
        />
      </main>
    </div>
  );
}
