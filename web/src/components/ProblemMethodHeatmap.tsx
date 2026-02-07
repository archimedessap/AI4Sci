"use client";

import type { EChartsOption } from "echarts";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ECharts } from "@/components/ECharts";

type DomainRow = {
  id: string;
  name: string;
  macroId: string;
  macroName: string;
  midId?: string;
  midName?: string;
  path?: string[];
  totalPapers?: number;
};

type MethodCol = {
  tag: string;
  label: string;
  description?: string | null;
  count?: number;
};

export type ProblemMethodMapData = {
  version?: string;
  generatedAt?: string;
  window?: { sinceYear?: number; years?: number };
  totals?: { papers?: number };
  domains?: DomainRow[];
  methods?: MethodCol[];
  cells?: Array<[number, number, number]>; // [x(method), y(domain), count]
  topPairs?: Array<{
    domainId: string;
    domainPath?: string;
    methodTag: string;
    methodLabel?: string;
    count: number;
  }>;
  blankSpots?: Array<{
    domainId: string;
    domainPath?: string;
    methodTag: string;
    methodLabel?: string;
    count: number;
    expected?: number;
    opportunity?: number;
  }>;
};

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function safeInt(v: unknown) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : 0;
}

const MACRO_PALETTE = [
  "#22d3ee",
  "#a78bfa",
  "#4ade80",
  "#fb7185",
  "#fbbf24",
  "#60a5fa",
];

export function ProblemMethodHeatmap({ data }: { data: ProblemMethodMapData }) {
  const router = useRouter();

  const domains: DomainRow[] = (data.domains ?? []).filter(Boolean);
  const methods: MethodCol[] = (data.methods ?? []).filter(Boolean);
  const cells = (data.cells ?? []).filter((c) => Array.isArray(c) && c.length >= 3);
  const totalPapers = safeInt(data.totals?.papers);

  const macroOptions = useMemo(() => {
    const byId = new Map<string, { id: string; name: string; count: number }>();
    for (const d of domains) {
      const id = d.macroId || "unknown";
      const name = d.macroName || id;
      const cur = byId.get(id);
      if (cur) cur.count += 1;
      else byId.set(id, { id, name, count: 1 });
    }
    return Array.from(byId.values()).sort((a, b) => b.count - a.count);
  }, [domains]);

  const macroColor = useMemo(() => {
    const out = new Map<string, string>();
    macroOptions.forEach((m, i) => out.set(m.id, MACRO_PALETTE[i % MACRO_PALETTE.length]));
    return out;
  }, [macroOptions]);

  const [macro, setMacro] = useState<string>("all");

  const filtered = useMemo(() => {
    const domainIdx: number[] = [];
    for (let i = 0; i < domains.length; i += 1) {
      const d = domains[i];
      if (macro === "all" || d.macroId === macro) domainIdx.push(i);
    }
    const idxSet = new Set(domainIdx);
    const remap = new Map<number, number>();
    domainIdx.forEach((old, ni) => remap.set(old, ni));

    const nextDomains = domainIdx.map((i) => domains[i]);
    const nextCells: Array<{ x: number; y: number; count: number; domain: DomainRow; method: MethodCol }> = [];

    let maxCount = 0;
    for (const [x, y, c] of cells) {
      if (!idxSet.has(y)) continue;
      const ny = remap.get(y);
      if (ny === undefined) continue;
      const count = safeInt(c);
      maxCount = Math.max(maxCount, count);
      nextCells.push({
        x,
        y: ny,
        count,
        domain: domains[y],
        method: methods[x],
      });
    }

    // Ensure 0-cells exist for a full matrix (better visual continuity).
    const seen = new Set<string>();
    for (const it of nextCells) seen.add(`${it.x}:${it.y}`);
    for (let yi = 0; yi < nextDomains.length; yi += 1) {
      for (let xi = 0; xi < methods.length; xi += 1) {
        const key = `${xi}:${yi}`;
        if (seen.has(key)) continue;
        nextCells.push({ x: xi, y: yi, count: 0, domain: nextDomains[yi], method: methods[xi] });
      }
    }

    return { domains: nextDomains, cells: nextCells, maxCount };
  }, [cells, domains, macro, methods]);

  const option: EChartsOption = useMemo(() => {
    const xLabels = methods.map((m) => m.label || m.tag);
    const yLabels = filtered.domains.map((d) => d.name || d.id);
    const maxCount = Math.max(1, filtered.maxCount);
    const maxLog = Math.log10(maxCount + 1);

    const seriesData = filtered.cells.map((it) => {
      const logValue = Math.log10(it.count + 1);
      const dt = safeInt(it.domain.totalPapers);
      const mt = safeInt(it.method.count);
      const expected = totalPapers > 0 ? (dt * mt) / totalPapers : 0;
      const ratio = (expected + 1) / (it.count + 1);
      const domainPath = (it.domain.path ?? []).join(" / ") || it.domain.name || it.domain.id;
      const methodLabel = it.method.label || it.method.tag;
      return {
        value: [it.x, it.y, logValue],
        count: it.count,
        expected,
        ratio,
        domainId: it.domain.id,
        domainPath,
        methodTag: it.method.tag,
        methodLabel,
        itemStyle: { borderColor: "rgba(255,255,255,0.06)" },
      };
    });

    return {
      backgroundColor: "transparent",
      tooltip: {
        position: "top",
        formatter: (params: unknown) => {
          const p = params as { data?: unknown };
          const d = p?.data;
          if (!d || typeof d !== "object") return "";
          const dd = d as Record<string, unknown>;
          const count = safeInt(dd.count);
          const expected = Number(dd.expected || 0);
          const ratio = Number(dd.ratio || 0);
          const domainPath = String(dd.domainPath || "");
          const methodLabel = String(dd.methodLabel || "");
          const hint = `<div style="opacity:.6">Click to open /papers (domain+method)</div>`;
          return `<div style="font-weight:700;margin-bottom:2px">${domainPath}</div><div style="opacity:.9">${methodLabel}: <span style="font-weight:700">${count}</span></div><div style="opacity:.75">expected≈${expected.toFixed(
            2,
          )}, ratio≈${ratio.toFixed(2)}</div>${hint}`;
        },
      },
      grid: { left: 240, right: 18, top: 24, bottom: 72 },
      xAxis: {
        type: "category",
        data: xLabels,
        axisLabel: {
          color: "rgba(255,255,255,0.7)",
          fontSize: 11,
          rotate: 22,
        },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
      },
      yAxis: {
        type: "category",
        data: yLabels,
        axisLabel: {
          fontSize: 11,
          color: (_value?: string | number, index?: number) => {
            const d = filtered.domains[index ?? 0];
            if (!d) return "rgba(255,255,255,0.65)";
            return macroColor.get(d.macroId) ?? "rgba(255,255,255,0.65)";
          },
        },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.15)" } },
      },
      dataZoom: [
        { type: "inside", yAxisIndex: 0, start: 0, end: clamp((26 / Math.max(1, yLabels.length)) * 100, 15, 100) },
        {
          type: "slider",
          yAxisIndex: 0,
          right: 2,
          top: 24,
          bottom: 78,
          width: 10,
          brushSelect: false,
          borderColor: "rgba(255,255,255,0.10)",
          fillerColor: "rgba(34,211,238,0.15)",
          handleStyle: { color: "rgba(255,255,255,0.25)", borderColor: "rgba(255,255,255,0.25)" },
          textStyle: { color: "rgba(255,255,255,0.35)" },
        },
      ],
      visualMap: {
        min: 0,
        max: maxLog,
        calculable: false,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        text: ["More", "Less"],
        textStyle: { color: "rgba(255,255,255,0.6)", fontSize: 10 },
        inRange: { color: ["#060a14", "#22d3ee", "#a78bfa", "#fb7185"] },
      },
      series: [
        {
          name: "Count(log10)",
          type: "heatmap",
          data: seriesData,
          emphasis: {
            itemStyle: { shadowBlur: 16, shadowColor: "rgba(255,255,255,0.25)" },
          },
        },
      ],
    } satisfies EChartsOption;
  }, [filtered, macroColor, methods, totalPapers]);

  const filteredBlankSpots = useMemo(() => {
    const list = (data.blankSpots ?? []).filter(Boolean);
    if (macro === "all") return list;
    const domMacro = new Map(domains.map((d) => [d.id, d.macroId]));
    return list.filter((it) => domMacro.get(it.domainId) === macro);
  }, [data.blankSpots, domains, macro]);

  const filteredTopPairs = useMemo(() => {
    const list = (data.topPairs ?? []).filter(Boolean);
    if (macro === "all") return list;
    const domMacro = new Map(domains.map((d) => [d.id, d.macroId]));
    return list.filter((it) => domMacro.get(it.domainId) === macro);
  }, [data.topPairs, domains, macro]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <div className="lg:col-span-9">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-white/60">
            <span className="font-semibold text-white/80">Macro</span>
            <select
              value={macro}
              onChange={(e) => setMacro(e.target.value)}
              className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white/85 outline-none focus:border-cyan-400/60"
            >
              <option value="all">All</option>
              {macroOptions.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.count})
                </option>
              ))}
            </select>
            <span className="text-white/35">
              Window: last {data.window?.years ?? "?"}y • papers: {totalPapers || "?"}
            </span>
          </div>
          <div className="text-xs text-white/45">
            Color = log10(count+1). Click a cell to open filtered papers.
          </div>
        </div>

        <ECharts
          option={option}
          style={{ height: 860 }}
          onEvents={{
            click: (params: unknown) => {
              const p = params as { data?: unknown };
              const d = p?.data;
              if (!d || typeof d !== "object") return;
              const dd = d as Record<string, unknown>;
              const domainId = dd.domainId;
              const methodTag = dd.methodTag;
              if (typeof domainId !== "string" || typeof methodTag !== "string") return;
              router.push(`/papers?domain=${encodeURIComponent(domainId)}&method=${encodeURIComponent(methodTag)}`);
            },
          }}
        />
      </div>

      <aside className="lg:col-span-3">
        <div className="space-y-4">
          <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="text-xs font-semibold text-white/70">Blank Spots</div>
            <div className="mt-2 text-[11px] leading-5 text-white/50">
              Ranked by expectation gap: expected = domain_total × method_total / total_papers; ratio = (expected+1)/(observed+1).
            </div>
            <div className="mt-3 space-y-2">
              {filteredBlankSpots.length ? (
                filteredBlankSpots.slice(0, 16).map((it) => (
                  <div key={`${it.domainId}:${it.methodTag}`} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
                    <div className="text-[11px] font-semibold text-white/85">{it.methodLabel || it.methodTag}</div>
                    <div className="mt-1 text-[11px] text-white/55">{it.domainPath || it.domainId}</div>
                    <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-white/55">
                      <span>obs {it.count}</span>
                      <span>exp≈{Number(it.expected || 0).toFixed(1)}</span>
                      <span>×{Number(it.opportunity || 0).toFixed(2)}</span>
                    </div>
                    <div className="mt-2">
                      <Link
                        href={`/papers?domain=${encodeURIComponent(it.domainId)}&method=${encodeURIComponent(it.methodTag)}`}
                        className="text-[11px] font-semibold text-cyan-200 hover:text-cyan-100"
                      >
                        Open papers →
                      </Link>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-white/55">No blank spots found for this filter.</div>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="text-xs font-semibold text-white/70">Hot Intersections</div>
            <div className="mt-3 space-y-2">
              {filteredTopPairs.length ? (
                filteredTopPairs.slice(0, 10).map((it) => (
                  <div key={`${it.domainId}:${it.methodTag}`} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
                    <div className="text-[11px] font-semibold text-white/85">
                      {it.methodLabel || it.methodTag} · {it.count}
                    </div>
                    <div className="mt-1 text-[11px] text-white/55">{it.domainPath || it.domainId}</div>
                    <div className="mt-2">
                      <Link
                        href={`/papers?domain=${encodeURIComponent(it.domainId)}&method=${encodeURIComponent(it.methodTag)}`}
                        className="text-[11px] font-semibold text-cyan-200 hover:text-cyan-100"
                      >
                        Open papers →
                      </Link>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-white/55">No intersections found.</div>
              )}
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}
