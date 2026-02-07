import Link from "next/link";
import fs from "node:fs";
import path from "node:path";

import { ChartCard } from "@/components/ChartCard";
import { DepthAgencyChart, type DepthAgencyPoint } from "@/components/DepthAgencyChart";
import {
  DepthAgencyInfra3DChart,
  type DepthAgencyInfraPoint,
} from "@/components/DepthAgencyInfra3DChart";
import { DiscoverySunburstChart } from "@/components/DiscoverySunburstChart";
import { KnowledgeMapExplorer } from "@/components/KnowledgeMapExplorer";
import { ProgressHeatmap } from "@/components/ProgressHeatmap";
import { ProgressBar } from "@/components/ProgressBar";
import { getProgressData } from "@/lib/progress/get.server";
import { DIMENSION_KEYS, type DimensionKey } from "@/lib/progress/types";
import { readOverridesData } from "@/lib/progress/storage.server";

export const dynamic = "force-dynamic";

type DiscoveryLayerKey = "phenomena" | "empirical" | "theory" | "principles";

type DiscoveryLayersData = {
  window?: { sinceDays?: number; sinceDate?: string | null };
  nodes?: Record<
    string,
    {
      layers?: Partial<Record<DiscoveryLayerKey, number>>;
      confidence?: number;
      stats?: { dbTotalPapers?: number };
    }
  >;
};

type FormalLayersData = {
  window?: { sinceDays?: number; sinceDate?: string | null };
  nodes?: Record<
    string,
    {
      layers?: Partial<Record<"instances" | "conjectures" | "proofs" | "foundations", number>>;
      confidence?: number;
      note?: string;
      stats?: { dbTotalPapers?: number; sampledPapers?: number; discoveryPapers?: number };
    }
  >;
};

type DomainExtraMetricsData = {
  nodes?: Record<
    string,
    {
      tooling?: number;
      autonomy?: number;
      stats?: { totalPapersApprox?: number; totalPapers?: number };
    }
  >;
};

type SunburstTreeNode = {
  id: string;
  name: string;
  parentId: string | null;
  children: string[];
};

type FormalLayerEntry = NonNullable<FormalLayersData["nodes"]>[string];
type ExtraMetricsEntry = NonNullable<DomainExtraMetricsData["nodes"]>[string];

const FORMAL_SUBFIELDS: Record<string, string[]> = {
  formal_math: ["Algebra", "Analysis", "Geometry & Topology", "Number Theory", "Combinatorics"],
  formal_stats: [
    "Bayesian Inference",
    "Frequentist Inference",
    "Causal Inference",
    "Time Series",
    "Statistical Learning",
  ],
  formal_optimization: [
    "Convex Optimization",
    "Nonconvex Optimization",
    "Combinatorial Optimization",
    "Stochastic Optimization",
    "Optimal Control",
  ],
  formal_logic: ["Proof Theory", "Model Theory", "Set Theory", "Type Theory", "Modal Logic"],
  formal_atp: [
    "SAT/SMT Solving",
    "Automated Deduction",
    "Proof Search",
    "Formal Verification",
    "Proof Assistants",
  ],
};

function readDiscoveryLayers(): DiscoveryLayersData {
  try {
    const p = path.join(process.cwd(), "data", "discovery_layers.json");
    if (!fs.existsSync(p)) return {};
    return JSON.parse(fs.readFileSync(p, "utf8")) as DiscoveryLayersData;
  } catch {
    return {};
  }
}

function readFormalLayers(): FormalLayersData {
  try {
    const p = path.join(process.cwd(), "data", "formal_layers.json");
    if (!fs.existsSync(p)) return {};
    return JSON.parse(fs.readFileSync(p, "utf8")) as FormalLayersData;
  } catch {
    return {};
  }
}

function readDomainExtraMetrics(): DomainExtraMetricsData {
  try {
    const p = path.join(process.cwd(), "data", "domain_extra_metrics.json");
    if (!fs.existsSync(p)) return {};
    return JSON.parse(fs.readFileSync(p, "utf8")) as DomainExtraMetricsData;
  } catch {
    return {};
  }
}

function clamp01(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function clamp100(v: number) {
  return Math.max(0, Math.min(100, v));
}

function slugifySubfieldId(value: string) {
  return value
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function buildFormalSubfieldSunburstData(
  tree: Record<string, SunburstTreeNode>,
  layers: Record<string, FormalLayerEntry>,
  extras: Record<string, ExtraMetricsEntry>,
) {
  const nextTree: Record<string, SunburstTreeNode> = {};
  for (const [id, node] of Object.entries(tree)) {
    nextTree[id] = { ...node, children: [...node.children] };
  }

  const nextLayers: Record<string, FormalLayerEntry> = { ...layers };
  const nextExtras: Record<string, ExtraMetricsEntry> = { ...extras };
  const usedIds = new Set(Object.keys(nextTree));
  const linkIdByLeaf: Record<string, string> = {};

  for (const [parentId, subfields] of Object.entries(FORMAL_SUBFIELDS)) {
    const parent = nextTree[parentId];
    if (!parent || parent.children.length > 0 || subfields.length === 0) continue;

    const parentEntry = layers[parentId];
    const parentExtra = extras[parentId];
    const childIds: string[] = [];

    for (const name of subfields) {
      const slug = slugifySubfieldId(name) || "subfield";
      let id = `${parentId}_${slug}`;
      let suffix = 2;
      while (usedIds.has(id)) {
        id = `${parentId}_${slug}_${suffix}`;
        suffix += 1;
      }
      usedIds.add(id);

      nextTree[id] = { id, name, parentId, children: [] };
      childIds.push(id);
      linkIdByLeaf[id] = parentId;

      if (parentEntry) {
        nextLayers[id] = {
          ...parentEntry,
          layers: parentEntry.layers ? { ...parentEntry.layers } : undefined,
          stats: undefined,
          note: `Inherited from ${parent.name}`,
        };
      }

      if (parentExtra) {
        nextExtras[id] = {
          ...parentExtra,
          stats: undefined,
        };
      }
    }

    nextTree[parentId] = { ...parent, children: childIds };
  }

  return { tree: nextTree, layers: nextLayers, extras: nextExtras, linkIdByLeaf };
}

export default function Home() {
  const data = getProgressData();
  const overrides = readOverridesData();
  const root = data.nodes[data.rootId];
  const discoveryLayers = readDiscoveryLayers();
  const formalLayers = readFormalLayers();
  const layerNodes = discoveryLayers.nodes ?? {};
  const formalLayerNodes = formalLayers.nodes ?? {};
  const discoveryWin = discoveryLayers.window;
  const formalWin = formalLayers.window;
  const extraMetrics = readDomainExtraMetrics();
  const extraNodes = extraMetrics.nodes ?? {};

  const nodes = Object.values(data.nodes);
  const macroOf = (id: string) => {
    const visited = new Set<string>();
    let cur = id;
    while (true) {
      if (visited.has(cur)) return id;
      visited.add(cur);
      const p = data.nodes[cur]?.parentId ?? null;
      if (!p) return id;
      if (p === data.rootId) return cur;
      cur = p;
    }
  };
  const macroIdById = new Map(nodes.map((n) => [n.id, macroOf(n.id)]));
  const isMethods = (id: string) => macroIdById.get(id) === "methods" && id !== data.rootId;

  const leafRows = nodes
    .filter(
      (n) => n.children.length === 0 && n.id !== data.rootId && !isMethods(n.id),
    )
    .sort((a, b) => b.overall.score - a.overall.score)
    .slice(0, 18)
    .map((n) => ({
      id: n.id,
      name: n.name,
      maturity: n.overall.maturity,
      values: DIMENSION_KEYS.reduce(
        (acc, k) => {
          acc[k] = n.dimensions[k].score;
          return acc;
        },
        {} as Record<DimensionKey, number>,
      ),
    }));

  const vortexTree = Object.fromEntries(
    nodes.map((n) => [
      n.id,
      { id: n.id, name: n.name, parentId: n.parentId, children: n.children },
    ]),
  );

  const graphAllNodes = nodes.map((n) => {
    const macroId = macroIdById.get(n.id) ?? n.id;
    const macroName = data.nodes[macroId]?.name ?? macroId;
    const tooling = (extraNodes[n.id]?.tooling ?? 0) * 100;
    const autonomy = (extraNodes[n.id]?.autonomy ?? 0) * 100;
    return {
      id: n.id,
      name: n.name,
      depth: n.depth,
      parentId: n.parentId,
      macroId,
      macroName,
      metrics: {
        overall: n.overall.score,
        data: n.dimensions.data.score,
        model: n.dimensions.model.score,
        predict: n.dimensions.predict.score,
        experiment: n.dimensions.experiment.score,
        explain: n.dimensions.explain.score,
        tooling,
        autonomy,
      },
    };
  });

  const graphAllLinks = nodes
    .filter((n) => n.parentId)
    .map((n) => ({ source: n.parentId!, target: n.id }));

  const depthAgencyPoints: DepthAgencyPoint[] = nodes
    .filter((n) => n.children.length === 0 && n.id !== data.rootId && !isMethods(n.id))
    .map((n) => {
      const entry = layerNodes[n.id];
      const l = entry?.layers ?? {};
      const phenomena = clamp01(l.phenomena ?? 0);
      const empirical = clamp01(l.empirical ?? 0);
      const theory = clamp01(l.theory ?? 0);
      const principles = clamp01(l.principles ?? 0);

      // 0..100, weighted by "deeper is harder": (1..4) / 10.
      const depth = (100 * (1 * phenomena + 2 * empirical + 3 * theory + 4 * principles)) / 10;

      const tooling = (extraNodes[n.id]?.tooling ?? 0) * 100;
      const autonomy = (extraNodes[n.id]?.autonomy ?? 0) * 100;
      const experiment = n.dimensions.experiment.score;

      // 0..100, interpret as “assistant → collaborator → autonomous”.
      const agency = Math.max(
        0,
        Math.min(100, 0.6 * autonomy + 0.3 * experiment + 0.1 * tooling),
      );

      const aiRecent = Number(n.dimensions.model.signals?.ai_recent ?? 0) || 0;
      const macroId = macroIdById.get(n.id) ?? n.id;
      const macroName = data.nodes[macroId]?.name ?? macroId;

      return {
        id: n.id,
        name: n.name,
        macroId,
        macroName,
        agency,
        depth,
        aiRecent,
        autonomy,
        tooling,
        experiment,
        layers: {
          phenomena: phenomena * 100,
          empirical: empirical * 100,
          theory: theory * 100,
          principles: principles * 100,
        },
      };
    })
    .sort((a, b) => b.aiRecent - a.aiRecent)
    .slice(0, 120);

  const leafNodes = nodes.filter(
    (n) => n.children.length === 0 && n.id !== data.rootId && !isMethods(n.id),
  );
  const maxAiRecent = Math.max(
    1,
    ...leafNodes.map((n) => Number(n.dimensions.model.signals?.ai_recent ?? 0) || 0),
  );
  const cubePoints: DepthAgencyInfraPoint[] = leafNodes
    .map((n) => {
      const entry = layerNodes[n.id];
      const l = entry?.layers ?? {};
      const hasLlmLayers = Boolean(entry && entry.layers);
      const phenomena = clamp01(l.phenomena ?? 0);
      const empirical = clamp01(l.empirical ?? 0);
      const theory = clamp01(l.theory ?? 0);
      const principles = clamp01(l.principles ?? 0);
      const depthLlm = (100 * (1 * phenomena + 2 * empirical + 3 * theory + 4 * principles)) / 10;

      const tooling = (extraNodes[n.id]?.tooling ?? 0) * 100;
      const autonomy = (extraNodes[n.id]?.autonomy ?? 0) * 100;
      const experiment = n.dimensions.experiment.score;
      const agency = clamp100(0.6 * autonomy + 0.3 * experiment + 0.1 * tooling);

      const aiRecent = Number(n.dimensions.model.signals?.ai_recent ?? 0) || 0;
      const adoptionNorm =
        (100 * Math.log1p(Math.max(0, aiRecent))) / Math.log1p(Math.max(1, maxAiRecent));

      const dataScore = n.dimensions.data.score;
      const infrastructure = clamp100(0.4 * dataScore + 0.4 * tooling + 0.2 * adoptionNorm);

      const depthProxy = clamp100(
        0.7 * n.dimensions.explain.score + 0.2 * n.dimensions.model.score + 0.1 * n.dimensions.predict.score,
      );
      const depth = hasLlmLayers ? depthLlm : depthProxy;
      const depthSource: "llm" | "proxy" = hasLlmLayers ? "llm" : "proxy";

      const macroId = macroIdById.get(n.id) ?? n.id;
      const macroName = data.nodes[macroId]?.name ?? macroId;

      return {
        id: n.id,
        name: n.name,
        macroId,
        macroName,
        agency,
        depth,
        depthSource,
        infrastructure,
        aiRecent,
        autonomy,
        tooling,
        experiment,
        data: dataScore,
      };
    })
    .sort((a, b) => b.aiRecent - a.aiRecent)
    .slice(0, 120);

  const formalSunburst = buildFormalSubfieldSunburstData(
    vortexTree,
    formalLayerNodes,
    extraNodes,
  );

  return (
    <div className="min-h-screen bg-[radial-gradient(1000px_600px_at_15%_10%,rgba(34,211,238,0.12),transparent_60%),radial-gradient(900px_600px_at_75%_20%,rgba(167,139,250,0.12),transparent_60%),radial-gradient(900px_700px_at_55%_95%,rgba(251,113,133,0.10),transparent_55%),linear-gradient(180deg,#05070d_0%,#050714_35%,#02030a_100%)] text-white">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-6 px-6 py-8">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-white/70">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_14px_rgba(34,211,238,0.9)]" />
            Auto + Manual • Evidence‑linked
          </div>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight md:text-3xl">
            AI4Sci Progress Atlas
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/60">
            宏观追踪 AI 统一人类知识的进度：相关 → 因果 → 机制 → 统一（理论压缩） → 闭环探索。
          </p>
          <div className="mt-3 text-xs text-white/40">
            Auto snapshot: {new Date(data.generatedAt).toLocaleString()} • Manual
            overrides: {new Date(overrides.updatedAt).toLocaleString()}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/papers"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Papers
          </Link>
          <Link
            href="/updates"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Updates
          </Link>
          <Link
            href="/top"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Top (1y)
          </Link>
          <Link
            href="/coverage"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Coverage
          </Link>
          <Link
            href="/trends"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Trends
          </Link>
          <Link
            href="/methodology"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Methodology
          </Link>
          <Link
            href="/problem-method"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Problem↔Method
          </Link>
          <Link
            href="/admin"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Admin
          </Link>
          <a
            href="https://openalex.org/"
            target="_blank"
            rel="noreferrer"
            className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/[0.07]"
          >
            Sources
          </a>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 pb-16">
        <div className="mb-5">
          <ChartCard
            title="Discovery Sunburst (Macro → Subfields)"
            subtitle={`外→内：现象→经验→理论→原理（LLM 判定${discoveryWin?.sinceDays ? `；窗口=近 ${discoveryWin.sinceDays} 天` : ""}）。外侧薄环：Tooling/Autonomy（关键词统计，用于避免“无发现=无进展”的误读）。`}
          >
            <DiscoverySunburstChart
              rootId={data.rootId}
              nodes={vortexTree}
              layers={layerNodes}
              extras={extraNodes}
              excludeMacroIds={["methods", "formal"]}
            />
          </ChartCard>
        </div>

        <div className="mb-5">
          <ChartCard
            title="Formal Sciences Sunburst"
            subtitle={`Formal sciences 用独立四层（外→内）：实例→猜想→证明→基础${formalWin?.sinceDays ? `；窗口=近 ${formalWin.sinceDays} 天` : ""}。子领域为可视化拆分，层级分数继承父类。`}
          >
            <DiscoverySunburstChart
              rootId={data.rootId}
              nodes={formalSunburst.tree}
              layers={formalSunburst.layers}
              extras={formalSunburst.extras}
              linkIdByLeaf={formalSunburst.linkIdByLeaf}
              includeMacroIds={["formal"]}
              layerDefs={[
                { key: "instances", label: "实例 Instances", color: "#22d3ee" },
                { key: "conjectures", label: "猜想 Conjectures", color: "#fbbf24" },
                { key: "proofs", label: "证明 Proofs", color: "#4ade80" },
                { key: "foundations", label: "基础 Foundations", color: "#a78bfa" },
              ]}
            />
          </ChartCard>
        </div>

        <div className="mb-5">
          <ChartCard
            title="Depth × Agency Map"
            subtitle="y=认识论深度（现象→原理），x=科学代理程度（助手→协同→自治）。点大小≈AI×领域交叉论文量（5y）。"
          >
            <DepthAgencyChart points={depthAgencyPoints} height={520} />
          </ChartCard>
        </div>

        <div className="mb-5">
          <ChartCard
            title="3D Macro Cube (Depth × Agency × Infrastructure)"
            subtitle="x=Agency（助手→协同→自治），y=Depth（现象→原理），z=Infrastructure/Adoption（Data+Tooling+Volume）。"
          >
            <DepthAgencyInfra3DChart points={cubePoints} height={640} />
          </ChartCard>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <ChartCard
              title="Knowledge‑Map (Click nodes)"
              subtitle="树结构 + 可切换指标（Overall/五维/Tooling/Autonomy）。Click 节点进入领域页。"
            >
              <KnowledgeMapExplorer
                rootId={data.rootId}
                nodes={graphAllNodes}
                links={graphAllLinks}
                initialScope="sub"
                height={560}
              />
            </ChartCard>
          </div>
          <div className="lg:col-span-4">
            <div className="flex flex-col gap-5">
              <ChartCard
                title="Global Progress"
                subtitle="Aggregate score across domains & dimensions."
              >
                <ProgressBar
                  label={root.name}
                  score={root.overall.score}
                  maturity={root.overall.maturity}
                  note={root.description}
                />
                <div className="mt-4 grid grid-cols-1 gap-3">
                  {data.dimensions.map((d) => (
                    <ProgressBar
                      key={d.key}
                      label={d.label}
                      score={root.dimensions[d.key].score}
                      maturity={root.dimensions[d.key].maturity!}
                      note={d.description}
                    />
                  ))}
                </div>
              </ChartCard>
              <ChartCard
                title="Quick Drill‑Down"
                subtitle="Top domains by overall score."
              >
                <div className="space-y-3">
                  {leafRows.slice(0, 8).map((r) => (
                    <Link
                      key={r.id}
                      href={`/domain/${encodeURIComponent(r.id)}`}
                      className="group block rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3 hover:bg-white/[0.05]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold text-white/85">
                          {r.name}
                        </div>
                        <div className="text-xs text-white/60">
                          {data.nodes[r.id].overall.score.toFixed(1)}
                        </div>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-violet-400 to-rose-400 opacity-80"
                          style={{
                            width: `${Math.max(
                              0,
                              Math.min(100, data.nodes[r.id].overall.score),
                            )}%`,
                          }}
                        />
                      </div>
                      <div className="mt-2 text-[11px] text-white/45 group-hover:text-white/60">
                        Open →
                      </div>
                    </Link>
                  ))}
                </div>
              </ChartCard>
            </div>
          </div>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Domain × Dimension Heatmap"
            subtitle="Scores are automatically computed from open literature signals (with manual overrides)."
          >
            <ProgressHeatmap
              dimensions={data.dimensions.map((d) => ({
                key: d.key,
                label: d.label,
              }))}
              rows={leafRows}
              height={560}
            />
          </ChartCard>
        </div>
      </main>
    </div>
  );
}
