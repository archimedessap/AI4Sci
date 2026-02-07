"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { KnowledgeVortexChart } from "@/components/KnowledgeVortexChart";

type DiscoveryLayerKey = "phenomena" | "empirical" | "theory" | "principles";

type LayerEntry = {
  layers?: Partial<Record<DiscoveryLayerKey, number>>;
  confidence?: number;
  stats?: { dbTotalPapers?: number };
};

type VortexNode = {
  id: string;
  name: string;
  parentId: string | null;
  children: string[];
};

function clamp01(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

export function VortexExplorer({
  rootId,
  nodes,
  layers,
  height = 540,
}: {
  rootId: string;
  nodes: Record<string, VortexNode>;
  layers: Record<string, LayerEntry>;
  height?: number;
}) {
  const router = useRouter();
  const [focusId, setFocusId] = useState(rootId);

  const focusNode = nodes[focusId] ?? nodes[rootId];
  const children = useMemo(() => {
    const focus = nodes[focusId] ?? nodes[rootId];
    const rootKids = nodes[rootId]?.children ?? [];
    return focus?.children?.length ? focus.children : rootKids;
  }, [focusId, nodes, rootId]);

  const breadcrumb = useMemo(() => {
    const out: Array<{ id: string; name: string }> = [];
    let cur = focusId !== rootId ? nodes[focusId] : null;
    while (cur && cur.parentId && nodes[cur.parentId]) {
      const p = nodes[cur.parentId];
      out.push({ id: p.id, name: p.name });
      cur = p.id === rootId ? null : p;
      if (p.id === rootId) break;
    }
    out.reverse();
    return out;
  }, [focusId, nodes, rootId]);

  const domains = useMemo(() => {
    function leafIds(startId: string): string[] {
      const start = nodes[startId];
      if (!start) return [];
      if (!start.children?.length) return [startId];
      const out: string[] = [];
      for (const cid of start.children) out.push(...leafIds(cid));
      return out;
    }

    function getLayerEntry(id: string) {
      const e = layers[id];
      if (!e?.layers) return null;
      const levels = {
        phenomena: clamp01(e.layers.phenomena ?? 0),
        empirical: clamp01(e.layers.empirical ?? 0),
        theory: clamp01(e.layers.theory ?? 0),
        principles: clamp01(e.layers.principles ?? 0),
      };
      const conf = clamp01(e.confidence ?? 0);
      const dbTotal = Math.max(1, Number(e.stats?.dbTotalPapers ?? 1));
      const weight = Math.sqrt(dbTotal) * Math.max(0.2, conf);
      return { levels, weight };
    }

    return children
      .map((id) => nodes[id])
      .filter(Boolean)
      .map((n) => {
        const direct = getLayerEntry(n.id);
        if (direct)
          return {
            id: n.id,
            name: n.name,
            hasChildren: n.children.length > 0,
            levels: direct.levels,
          };

        const leaves = leafIds(n.id);
        const entries = leaves
          .map(getLayerEntry)
          .filter(Boolean) as Array<{
          levels: Record<DiscoveryLayerKey, number>;
          weight: number;
        }>;
        if (entries.length) {
          const sumW = entries.reduce((acc, it) => acc + it.weight, 0) || 1;
          return {
            id: n.id,
            name: n.name,
            hasChildren: n.children.length > 0,
            levels: {
              phenomena: clamp01(
                entries.reduce((acc, it) => acc + it.weight * it.levels.phenomena, 0) / sumW,
              ),
              empirical: clamp01(
                entries.reduce((acc, it) => acc + it.weight * it.levels.empirical, 0) / sumW,
              ),
              theory: clamp01(
                entries.reduce((acc, it) => acc + it.weight * it.levels.theory, 0) / sumW,
              ),
              principles: clamp01(
                entries.reduce((acc, it) => acc + it.weight * it.levels.principles, 0) / sumW,
              ),
            },
          };
        }
        return {
          id: n.id,
          name: n.name,
          hasChildren: n.children.length > 0,
          levels: { phenomena: 0, empirical: 0, theory: 0, principles: 0 },
        };
      });
  }, [children, nodes, layers]);

  const canUp = Boolean(focusId !== rootId && focusNode?.parentId);

  const go = useCallback(
    (nextId: string | null) => {
      if (nextId && nodes[nextId]) setFocusId(nextId);
      else setFocusId(rootId);
    },
    [nodes, rootId],
  );

  const onSelectDomain = useCallback(
    (d: { id: string; hasChildren?: boolean }) => {
      if (!d?.id) return;
      if (d.hasChildren) {
        go(d.id);
        return;
      }
      router.push(`/domain/${encodeURIComponent(d.id)}`);
    },
    [go, router],
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-white/45">
          {focusId !== rootId ? (
            <>
              Focus:{" "}
              {breadcrumb.map((b) => (
                <span key={b.id} className="text-white/55">
                  {b.name} /{" "}
                </span>
              ))}
              <span className="text-white/80">{focusNode?.name ?? focusId}</span>
            </>
          ) : (
            <span className="text-white/55">Focus: Macro</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!canUp}
            onClick={() => go(focusNode?.parentId ?? null)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${canUp ? "border-white/10 bg-white/[0.03] text-white/75 hover:bg-white/[0.06]" : "border-white/10 bg-white/[0.02] text-white/35 opacity-70"}`}
          >
            Up
          </button>
          <button
            type="button"
            disabled={focusId === rootId}
            onClick={() => go(null)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${focusId === rootId ? "border-white/10 bg-white/[0.02] text-white/35 opacity-70" : "border-white/10 bg-white/[0.03] text-white/75 hover:bg-white/[0.06]"}`}
          >
            Reset
          </button>
        </div>
      </div>

      <KnowledgeVortexChart
        domains={domains}
        height={height}
        onSelectDomain={onSelectDomain}
      />
    </div>
  );
}
