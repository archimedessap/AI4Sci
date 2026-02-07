"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type LayerKey = string;

type LayerDef = { key: LayerKey; label: string; color: string };

type LayerEntry = {
  layers?: Record<string, number | undefined>;
  confidence?: number;
  note?: string;
  stats?: { dbTotalPapers?: number; sampledPapers?: number; discoveryPapers?: number };
};

type ExtraMetricsEntry = {
  tooling?: number; // 0..1
  autonomy?: number; // 0..1
  stats?: { totalPapersApprox?: number; totalPapers?: number };
};

type TreeNode = {
  id: string;
  name: string;
  parentId: string | null;
  children: string[];
};

const DEFAULT_LAYER_DEFS: LayerDef[] = [
  { key: "phenomena", label: "现象 Phenomena", color: "#22d3ee" },
  { key: "empirical", label: "经验 Empirical", color: "#4ade80" },
  { key: "theory", label: "理论 Theory", color: "#a78bfa" },
  { key: "principles", label: "原理 Principles", color: "#fb7185" },
];

function clamp01(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

function hexToRgb(hex: string) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return { r: 255, g: 255, b: 255 };
  const v = Number.parseInt(m[1], 16);
  return { r: (v >> 16) & 255, g: (v >> 8) & 255, b: v & 255 };
}

function rgba(hex: string, a: number) {
  const { r, g, b } = hexToRgb(hex);
  const alpha = Math.max(0, Math.min(1, a));
  return `rgba(${r},${g},${b},${alpha})`;
}

function sectorPath(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  a0: number,
  a1: number,
  rOuter: number,
  rInner: number,
) {
  ctx.beginPath();
  ctx.moveTo(cx + rOuter * Math.cos(a0), cy + rOuter * Math.sin(a0));
  ctx.arc(cx, cy, rOuter, a0, a1, false);
  ctx.lineTo(cx + rInner * Math.cos(a1), cy + rInner * Math.sin(a1));
  ctx.arc(cx, cy, rInner, a1, a0, true);
  ctx.closePath();
}

type LeafSegment = {
  id: string;
  name: string;
  macroId: string;
  macroName: string;
  midId: string;
  midName: string;
  start: number;
  end: number;
  levels: Record<string, number>;
  confidence: number;
  tooling: number;
  autonomy: number;
  note?: string;
};

type MacroBand = {
  id: string;
  name: string;
  start: number;
  end: number;
};

type Geometry = {
  w: number;
  h: number;
  cx: number;
  cy: number;
  rOuter: number;
  rCore: number;
  bounds: [number, number, number, number, number];
  macroSpan: number;
  macroIds: string[];
  leavesByMacro: Record<string, LeafSegment[]>;
};

function leafDescendants(startId: string, nodes: Record<string, TreeNode>) {
  const out: string[] = [];
  const visited = new Set<string>();
  const walk = (id: string) => {
    if (visited.has(id)) return;
    visited.add(id);
    const n = nodes[id];
    if (!n) return;
    if (!n.children?.length) {
      out.push(id);
      return;
    }
    for (const c of n.children) walk(c);
  };
  walk(startId);
  return out;
}

function topChildUnderMacro(leafId: string, macroId: string, nodes: Record<string, TreeNode>) {
  let cur = leafId;
  const visited = new Set<string>();
  while (true) {
    if (visited.has(cur)) return leafId;
    visited.add(cur);
    const p = nodes[cur]?.parentId;
    if (!p) return leafId;
    if (p === macroId) return cur;
    cur = p;
  }
}

type HoverInfo = {
  seg: LeafSegment;
  x: number;
  y: number;
};

export function DiscoverySunburstChart({
  rootId,
  nodes,
  layers,
  extras,
  layerDefs,
  includeMacroIds,
  excludeMacroIds,
  linkIdByLeaf,
  height = 580,
}: {
  rootId: string;
  nodes: Record<string, TreeNode>;
  layers: Record<string, LayerEntry>;
  extras?: Record<string, ExtraMetricsEntry>;
  layerDefs?: LayerDef[];
  includeMacroIds?: string[];
  excludeMacroIds?: string[];
  linkIdByLeaf?: Record<string, string>;
  height?: number;
}) {
  const router = useRouter();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const geomRef = useRef<Geometry | null>(null);
  const segmentsRef = useRef<LeafSegment[]>([]);
  const macrosRef = useRef<MacroBand[]>([]);
  const hoverSegRef = useRef<LeafSegment | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [wrapWidth, setWrapWidth] = useState<number>(0);

  const resolvedLayerDefs = useMemo(() => {
    if (Array.isArray(layerDefs) && layerDefs.length === 4 && layerDefs.every((d) => d?.key)) {
      return layerDefs;
    }
    return DEFAULT_LAYER_DEFS;
  }, [layerDefs]);

  const model = useMemo(() => {
    const root = nodes[rootId];
    const include = new Set((includeMacroIds ?? []).filter(Boolean));
    const exclude = new Set((excludeMacroIds ?? []).filter(Boolean));
    const macroIdsAll = root?.children?.filter((id) => nodes[id]) ?? [];
    const macroIds =
      include.size > 0
        ? macroIdsAll.filter((id) => include.has(id))
        : macroIdsAll.filter((id) => !exclude.has(id));
    const macroSpan = (Math.PI * 2) / Math.max(1, macroIds.length);
    const leavesByMacro: Record<string, LeafSegment[]> = {};

    for (let mi = 0; mi < macroIds.length; mi += 1) {
      const macroId = macroIds[mi];
      const macroNode = nodes[macroId];
      const leafIds = leafDescendants(macroId, nodes).filter((id) => id !== macroId);
      const leafNodes = leafIds.filter((id) => nodes[id] && nodes[id].children.length === 0);
      const leafCount = Math.max(1, leafNodes.length);
      const leafSpan = macroSpan / leafCount;
      const macroStart = -Math.PI / 2 + mi * macroSpan;

      const segs: LeafSegment[] = [];
      for (let li = 0; li < leafNodes.length; li += 1) {
        const id = leafNodes[li];
        const leaf = nodes[id];
        const start = macroStart + li * leafSpan;
        const end = start + leafSpan;
        const midId = topChildUnderMacro(id, macroId, nodes);
        const mid = nodes[midId] ?? leaf;
        const entry = layers[id];
        const l: Record<string, number | undefined> = entry?.layers ?? {};
        const ex = extras?.[id];
        const levelMap: Record<string, number> = {};
        for (const def of resolvedLayerDefs) {
          levelMap[def.key] = clamp01(l[def.key]);
        }
        segs.push({
          id,
          name: leaf?.name ?? id,
          macroId,
          macroName: macroNode?.name ?? macroId,
          midId,
          midName: mid?.name ?? midId,
          start,
          end,
          levels: levelMap,
          confidence: clamp01(entry?.confidence ?? 0),
          tooling: clamp01(ex?.tooling ?? 0),
          autonomy: clamp01(ex?.autonomy ?? 0),
          note: entry?.note,
        });
      }
      leavesByMacro[macroId] = segs;
    }

    return { macroIds, macroSpan, leavesByMacro };
  }, [excludeMacroIds, extras, includeMacroIds, layers, nodes, resolvedLayerDefs, rootId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let destroyed = false;

    const resize = () => {
      const dpr = Math.max(1, window.devicePixelRatio || 1);
      const w = Math.max(1, wrap.clientWidth || 1);
      const h = Math.max(1, wrap.clientHeight || 1);
      setWrapWidth(w);
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;

      const cx = w / 2;
      const cy = h / 2;
      const minDim = Math.min(w, h);
      const rOuter = minDim * 0.39;
      const rCore = rOuter * 0.13;
      const ringCount = Math.max(1, resolvedLayerDefs.length);
      const ring = (rOuter - rCore) / ringCount;
      const bounds = Array.from({ length: ringCount + 1 }, (_, i) =>
        i === ringCount ? rCore : rOuter - i * ring,
      );

      const segs: LeafSegment[] = [];
      for (const macroId of model.macroIds) segs.push(...(model.leavesByMacro[macroId] ?? []));
      segmentsRef.current = segs;

      const macros: MacroBand[] = [];
      for (let mi = 0; mi < model.macroIds.length; mi += 1) {
        const id = model.macroIds[mi];
        const start = -Math.PI / 2 + mi * model.macroSpan;
        macros.push({ id, name: nodes[id]?.name ?? id, start, end: start + model.macroSpan });
      }
      macrosRef.current = macros;

      geomRef.current = {
        w,
        h,
        cx,
        cy,
        rOuter,
        rCore,
        bounds: bounds as unknown as [number, number, number, number, number],
        macroSpan: model.macroSpan,
        macroIds: model.macroIds,
        leavesByMacro: model.leavesByMacro,
      };
    };

    const segmentFromPoint = (x: number, y: number) => {
      const g = geomRef.current;
      if (!g) return null;
      const dx = x - g.cx;
      const dy = y - g.cy;
      const r = Math.hypot(dx, dy);
      if (r < g.rCore * 0.8) return null;
      if (r > g.rOuter + 80) return null; // include extra rings + label zone
      let theta = Math.atan2(dy, dx);
      if (theta < 0) theta += Math.PI * 2;
      const a = (theta + Math.PI / 2 + Math.PI * 2) % (Math.PI * 2); // 0..2pi
      const mi = Math.floor(a / g.macroSpan);
      const macroId = g.macroIds[mi];
      if (!macroId) return null;
      const segs = g.leavesByMacro[macroId] ?? [];
      if (!segs.length) return null;
      const local = a - mi * g.macroSpan;
      const leafSpan = g.macroSpan / segs.length;
      const li = Math.floor(local / leafSpan);
      const seg = segs[Math.max(0, Math.min(segs.length - 1, li))];
      return seg ?? null;
    };

    const draw = (timeMs: number) => {
      if (destroyed) return;
      const g = geomRef.current;
      if (!g) return;
      const dpr = Math.max(1, window.devicePixelRatio || 1);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, g.w, g.h);

      // Background.
      const bg = ctx.createRadialGradient(g.cx, g.cy, g.rCore * 0.2, g.cx, g.cy, g.rOuter * 1.35);
      bg.addColorStop(0, "rgba(80, 155, 255, 0.08)");
      bg.addColorStop(0.35, "rgba(80, 90, 255, 0.05)");
      bg.addColorStop(0.75, "rgba(0, 0, 0, 0.0)");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, g.w, g.h);

      // Ring grid.
      ctx.save();
      ctx.strokeStyle = "rgba(255,255,255,0.09)";
      ctx.lineWidth = 1;
      for (const r of g.bounds) {
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, r, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();

      // Extra rings: separate signals for "tooling/infrastructure" and "autonomy/closed-loop".
      // These are intentionally outside the discovery rings so "0 discovery" does not imply "no progress".
      const toolOuter = g.rOuter + 20;
      const toolInner = g.rOuter + 12;
      const autoOuter = g.rOuter + 11;
      const autoInner = g.rOuter + 4;

      const drawExtraRing = (
        outer: number,
        inner: number,
        color: string,
        key: "tooling" | "autonomy",
      ) => {
        // Baseline.
        ctx.save();
        ctx.fillStyle = "rgba(255,255,255,0.02)";
        for (const s of segmentsRef.current) {
          sectorPath(ctx, g.cx, g.cy, s.start, s.end, outer, inner);
          ctx.fill();
        }
        ctx.restore();

        // Value (opacity encodes percent).
        for (const s of segmentsRef.current) {
          const p = clamp01(key === "tooling" ? s.tooling : s.autonomy);
          if (p <= 0.001) continue;
          ctx.save();
          ctx.globalCompositeOperation = "lighter";
          ctx.fillStyle = rgba(color, 0.10 + 0.70 * p);
          sectorPath(ctx, g.cx, g.cy, s.start, s.end, outer, inner);
          ctx.fill();
          ctx.restore();
        }

        // Outline.
        ctx.save();
        ctx.strokeStyle = rgba(color, 0.12);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, outer, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, inner, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      };

      drawExtraRing(toolOuter, toolInner, "#fbbf24", "tooling");
      drawExtraRing(autoOuter, autoInner, "#60a5fa", "autonomy");

      // Baseline sectors.
      const segs = segmentsRef.current;
      for (let k = 0; k < resolvedLayerDefs.length; k += 1) {
        const ro = g.bounds[k]!;
        const ri = g.bounds[k + 1]!;
        ctx.save();
        ctx.fillStyle = "rgba(255,255,255,0.018)";
        for (const s of segs) {
          sectorPath(ctx, g.cx, g.cy, s.start, s.end, ro, ri);
          ctx.fill();
        }
        ctx.restore();
      }

      // Filled progress (per ring).
      for (let k = 0; k < resolvedLayerDefs.length; k += 1) {
        const meta = resolvedLayerDefs[k]!;
        const ro = g.bounds[k]!;
        const ri = g.bounds[k + 1]!;
        const thick = ro - ri;
        for (const s of segs) {
          const p = clamp01(s.levels[meta.key]);
          if (p <= 0.001) continue;
          const conf = Math.max(0.15, s.confidence || 0);
          const inner = Math.max(ri, ro - thick * p);
          const wave = 0.35 + 0.65 * (0.5 - 0.5 * Math.cos(2 * Math.PI * (timeMs * 0.00018 + s.start)));
          const glow = 0.18 + 0.22 * p * wave;

          ctx.save();
          ctx.globalCompositeOperation = "lighter";
          ctx.fillStyle = rgba(meta.color, glow * conf);
          sectorPath(ctx, g.cx, g.cy, s.start, s.end, ro, inner);
          ctx.fill();
          ctx.restore();

          ctx.save();
          ctx.fillStyle = rgba(meta.color, (0.30 + 0.42 * p) * conf);
          sectorPath(ctx, g.cx, g.cy, s.start, s.end, ro, inner);
          ctx.fill();
          ctx.restore();
        }
      }

      // Separators: leaf / mid / macro.
      const drawRadial = (angle: number, width: number, color: string) => {
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.beginPath();
        ctx.moveTo(g.cx + g.bounds[0] * Math.cos(angle), g.cy + g.bounds[0] * Math.sin(angle));
        ctx.lineTo(g.cx + g.bounds[4] * Math.cos(angle), g.cy + g.bounds[4] * Math.sin(angle));
        ctx.stroke();
        ctx.restore();
      };

      // Leaf boundaries (subdomains): subtle.
      for (const s of segs) drawRadial(s.start, 0.8, "rgba(255,255,255,0.07)");

      // Mid boundaries: slightly brighter.
      for (const macroId of g.macroIds) {
        const segList = g.leavesByMacro[macroId] ?? [];
        if (!segList.length) continue;
        let prevMid = segList[0]?.midId;
        for (let i = 1; i < segList.length; i += 1) {
          const curMid = segList[i]?.midId;
          if (curMid && prevMid && curMid !== prevMid) drawRadial(segList[i].start, 1.4, "rgba(255,255,255,0.14)");
          prevMid = curMid;
        }
      }

      // Macro boundaries.
      for (const m of macrosRef.current) drawRadial(m.start, 2.2, "rgba(255,255,255,0.22)");

      // Macro labels.
      ctx.save();
      const rLabel = g.rOuter + 28;
      for (const m of macrosRef.current) {
        const aMid = (m.start + m.end) / 2;
        const x = g.cx + rLabel * Math.cos(aMid);
        const y = g.cy + rLabel * Math.sin(aMid);
        const right = Math.cos(aMid) >= 0;
        ctx.font = "600 12px ui-sans-serif, system-ui";
        ctx.fillStyle = "rgba(255,255,255,0.72)";
        ctx.textAlign = right ? "left" : "right";
        ctx.textBaseline = "middle";
        ctx.fillText(m.name, x, y);
      }
      ctx.restore();

      // Hover highlight.
      const hoverSeg = hoverSegRef.current;
      if (hoverSeg) {
        const s = hoverSeg;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.strokeStyle = "rgba(255,255,255,0.55)";
        ctx.lineWidth = 2.2;
        sectorPath(ctx, g.cx, g.cy, s.start, s.end, g.bounds[0], g.bounds[4]);
        ctx.stroke();
        ctx.restore();
      }

      // Core glow (principles avg).
      const coreKey = resolvedLayerDefs[resolvedLayerDefs.length - 1]?.key ?? "principles";
      const coreAvg =
        segs.reduce((acc, s) => acc + clamp01(s.levels[coreKey]), 0) / Math.max(1, segs.length);
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      const core = ctx.createRadialGradient(g.cx, g.cy, 0, g.cx, g.cy, g.rCore * 1.9);
      const c0 = resolvedLayerDefs[resolvedLayerDefs.length - 1]?.color ?? "#fb7185";
      const c1 = resolvedLayerDefs[Math.max(0, resolvedLayerDefs.length - 2)]?.color ?? "#a78bfa";
      core.addColorStop(0, rgba(c0, 0.18 + 0.55 * coreAvg));
      core.addColorStop(0.4, rgba(c1, 0.10 + 0.35 * coreAvg));
      core.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(g.cx, g.cy, g.rCore * 1.9, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      raf = requestAnimationFrame(draw);
    };

    resize();
    window.addEventListener("resize", resize);
    raf = requestAnimationFrame(draw);

    const onMove = (ev: PointerEvent) => {
      const g = geomRef.current;
      const wrapEl = wrapRef.current;
      if (!g || !wrapEl) return;
      const rect = wrapEl.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      const seg = segmentFromPoint(x, y);
      if (!seg) {
        hoverSegRef.current = null;
        setHover(null);
        return;
      }
      hoverSegRef.current = seg;
      setHover({ seg, x, y });
    };
    const onLeave = () => {
      hoverSegRef.current = null;
      setHover(null);
    };
    const onClick = (ev: MouseEvent) => {
      const wrapEl = wrapRef.current;
      if (!wrapEl) return;
      const rect = wrapEl.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      const seg = segmentFromPoint(x, y) ?? hoverSegRef.current;
      if (!seg?.id) return;
      const linkId = linkIdByLeaf?.[seg.id] ?? seg.id;
      router.push(`/domain/${encodeURIComponent(linkId)}`);
    };

    wrap.addEventListener("pointermove", onMove);
    wrap.addEventListener("pointerleave", onLeave);
    wrap.addEventListener("click", onClick);

    return () => {
      destroyed = true;
      window.removeEventListener("resize", resize);
      wrap.removeEventListener("pointermove", onMove);
      wrap.removeEventListener("pointerleave", onLeave);
      wrap.removeEventListener("click", onClick);
      cancelAnimationFrame(raf);
    };
  }, [model, nodes, resolvedLayerDefs, router, linkIdByLeaf]);

  const hoverEntry = hover ? layers[hover.seg.id] : null;
  const hoverHasData = Boolean(hoverEntry?.layers);

  return (
    <div ref={wrapRef} className="relative w-full cursor-pointer" style={{ height }}>
      <canvas ref={canvasRef} className="h-full w-full" />

      {/* Legend */}
      <div className="pointer-events-none absolute left-3 top-3 rounded-xl border border-white/10 bg-black/35 px-3 py-2 text-[11px] text-white/75 backdrop-blur">
        <div className="font-semibold text-white/85">外 → 内</div>
        <div className="mt-1 grid grid-cols-1 gap-1">
          {resolvedLayerDefs.map((l) => (
            <div key={l.key} className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ background: l.color, boxShadow: `0 0 14px ${l.color}66` }}
              />
              <span>{l.label}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 grid grid-cols-1 gap-1 text-white/65">
          <div className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 rounded-sm"
              style={{ background: "#fbbf24", boxShadow: "0 0 14px rgba(251,191,36,0.35)" }}
            />
            <span>工具/基础设施 Tooling (outer rim)</span>
          </div>
          <div className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 rounded-sm"
              style={{ background: "#60a5fa", boxShadow: "0 0 14px rgba(96,165,250,0.35)" }}
            />
            <span>闭环自治 Autonomy (outer rim)</span>
          </div>
        </div>
        <div className="mt-2 text-white/55">
          Click: open subdomain • Hover: details
        </div>
      </div>

      {/* Tooltip */}
      {hover ? (
        <div
          className="pointer-events-none absolute z-10 w-[320px] rounded-xl border border-white/10 bg-black/60 px-3 py-2 text-xs text-white/85 shadow-[0_0_0_1px_rgba(255,255,255,0.06)] backdrop-blur"
          style={{
            left: Math.max(10, Math.min(hover.x + 14, Math.max(10, wrapWidth - 340))),
            top: Math.max(10, hover.y - 12),
          }}
        >
          <div className="text-sm font-semibold text-white/95">{hover.seg.name}</div>
          <div className="mt-1 text-[11px] text-white/60">
            {hover.seg.macroName}
            {hover.seg.midName && hover.seg.midName !== hover.seg.name ? ` · ${hover.seg.midName}` : ""}
          </div>

          <div className="mt-2 grid grid-cols-1 gap-1">
            {resolvedLayerDefs.map((l) => (
              <div key={l.key} className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-sm"
                    style={{ background: l.color, boxShadow: `0 0 14px ${l.color}55` }}
                  />
                  <span className="text-white/75">{l.label}</span>
                </div>
                <div className="tabular-nums text-white/90">
                  {Math.round(clamp01(hover.seg.levels[l.key]) * 100)}%
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 grid grid-cols-1 gap-1">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-sm"
                  style={{ background: "#fbbf24", boxShadow: "0 0 14px rgba(251,191,36,0.35)" }}
                />
                <span className="text-white/75">Tooling</span>
              </div>
              <div className="tabular-nums text-white/90">
                {Math.round(clamp01(hover.seg.tooling) * 100)}%
              </div>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-sm"
                  style={{ background: "#60a5fa", boxShadow: "0 0 14px rgba(96,165,250,0.35)" }}
                />
                <span className="text-white/75">Autonomy</span>
              </div>
              <div className="tabular-nums text-white/90">
                {Math.round(clamp01(hover.seg.autonomy) * 100)}%
              </div>
            </div>
          </div>

          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-white/55">
            <span>LLM conf {Math.round(clamp01(hover.seg.confidence) * 100)}%</span>
            {typeof hoverEntry?.stats?.dbTotalPapers === "number" ? (
              <span>DB {hoverEntry.stats.dbTotalPapers}</span>
            ) : null}
            {typeof hoverEntry?.stats?.sampledPapers === "number" ? (
              <span>sample {hoverEntry.stats.sampledPapers}</span>
            ) : null}
          </div>
          {hover.seg.note && hover.seg.note.startsWith("Inherited from") ? (
            <div className="mt-2 text-[11px] text-white/55">{hover.seg.note}</div>
          ) : null}
          {!hoverHasData ? (
            <div className="mt-2 text-[11px] text-white/55">
              No LLM layer data yet for this subdomain.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
