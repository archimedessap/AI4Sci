"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type DomainLevels = {
  id: string;
  name: string;
  hasChildren?: boolean;
  levels: {
    phenomena: number; // 0..1
    empirical: number; // 0..1
    theory: number; // 0..1
    principles: number; // 0..1
  };
};

const LAYERS = [
  { key: "phenomena", label: "现象 Phenomena", color: "#22d3ee" },
  { key: "empirical", label: "经验 Empirical", color: "#4ade80" },
  { key: "theory", label: "理论 Theory", color: "#a78bfa" },
  { key: "principles", label: "原理 Principles", color: "#fb7185" },
] as const;

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

function cumulativeLevels(levels: DomainLevels["levels"]) {
  const p0 = clamp01(levels.phenomena);
  const p1 = Math.min(p0, clamp01(levels.empirical));
  const p2 = Math.min(p1, clamp01(levels.theory));
  const p3 = Math.min(p2, clamp01(levels.principles));
  return { phenomena: p0, empirical: p1, theory: p2, principles: p3 };
}

type HoverInfo = {
  domain: DomainLevels;
  x: number;
  y: number;
};

type Star = {
  x: number;
  y: number;
  r: number;
  a: number;
  phase: number;
};

export function KnowledgeVortexChart({
  domains,
  height = 520,
  onSelectDomain,
}: {
  domains: DomainLevels[];
  height?: number;
  onSelectDomain?: (domain: DomainLevels) => void;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const onSelectRef = useRef<typeof onSelectDomain>(onSelectDomain);
  const starsRef = useRef<Star[]>([]);
  const geomRef = useRef<{
    w: number;
    h: number;
    cx: number;
    cy: number;
    rOuter: number;
    rCore: number;
    bounds: [number, number, number, number, number];
    wedge: number;
  } | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [wrapWidth, setWrapWidth] = useState<number>(0);

  useEffect(() => {
    onSelectRef.current = onSelectDomain;
  }, [onSelectDomain]);

  const enriched = useMemo(() => {
    const n = Math.max(1, domains.length);
    const wedge = (Math.PI * 2) / n;
    return domains.map((d, i) => {
      const cum = cumulativeLevels(d.levels);
      return {
        domain: d,
        index: i,
        wedge,
        angle: -Math.PI / 2 + i * wedge,
        cum,
      };
    });
  }, [domains]);

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

      const minDim = Math.min(w, h);
      const cx = w / 2;
      const cy = h / 2;
      const rOuter = minDim * 0.41;
      const rCore = rOuter * 0.14;
      const bounds: [number, number, number, number, number] = [
        rOuter,
        rOuter * 0.76,
        rOuter * 0.54,
        rOuter * 0.33,
        rCore,
      ];
      const wedge = (Math.PI * 2) / Math.max(1, domains.length);
      geomRef.current = { w, h, cx, cy, rOuter, rCore, bounds, wedge };

      // Starfield for "depth" feeling.
      const stars: Star[] = [];
      const count = Math.max(60, Math.min(160, Math.floor((w * h) / 9000)));
      for (let i = 0; i < count; i++) {
        const rx = Math.random() * w;
        const ry = Math.random() * h;
        const dist = Math.hypot(rx - cx, ry - cy);
        const maxDist = Math.max(1, Math.hypot(cx, cy));
        const depth = Math.min(1, dist / maxDist);
        stars.push({
          x: rx,
          y: ry,
          r: 0.6 + Math.random() * 1.2,
          a: 0.10 + 0.22 * (1 - depth) + Math.random() * 0.08,
          phase: Math.random() * Math.PI * 2,
        });
      }
      starsRef.current = stars;
    };

    const domainIndexFromPoint = (x: number, y: number) => {
      const g = geomRef.current;
      if (!g) return -1;
      const dx = x - g.cx;
      const dy = y - g.cy;
      const r = Math.hypot(dx, dy);
      // Make labels (slightly outside the outer ring) clickable.
      if (r > g.rOuter + 72) return -1;
      let theta = Math.atan2(dy, dx);
      if (theta < 0) theta += Math.PI * 2;
      // Domain i starts at -90deg (top), clockwise.
      const a = (theta + Math.PI / 2 + Math.PI * 2) % (Math.PI * 2);
      return Math.floor(a / g.wedge);
    };

    const drawSpiral = (
      g: NonNullable<typeof geomRef.current>,
      angle0: number,
      twist: number,
      rStart: number,
      rEnd: number,
      step: number,
      cb: (x: number, y: number, first: boolean) => void,
    ) => {
      const n = Math.max(2, Math.ceil((rStart - rEnd) / Math.max(1, step)));
      for (let i = 0; i <= n; i++) {
        const t = i / n;
        const r = rStart - (rStart - rEnd) * t;
        const u = 1 - r / g.rOuter; // 0..1
        // Bend inward then return to the same ray at the core, so tracks stay
        // inside each domain sector (more intuitive for hover/click).
        const bend = Math.sin(Math.PI * u);
        const theta = angle0 + twist * bend;
        const x = g.cx + r * Math.cos(theta);
        const y = g.cy + r * Math.sin(theta);
        cb(x, y, i === 0);
      }
    };

    const draw = (timeMs: number) => {
      if (destroyed) return;
      const g = geomRef.current;
      if (!g) return;
      const dpr = Math.max(1, window.devicePixelRatio || 1);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, g.w, g.h);

      // Background gradient.
      const bg = ctx.createRadialGradient(g.cx, g.cy, g.rCore * 0.2, g.cx, g.cy, g.rOuter * 1.35);
      bg.addColorStop(0, "rgba(80, 155, 255, 0.10)");
      bg.addColorStop(0.35, "rgba(80, 90, 255, 0.06)");
      bg.addColorStop(0.7, "rgba(0, 0, 0, 0.0)");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, g.w, g.h);

      // Stars.
      for (const s of starsRef.current) {
        const tw = 0.55 + 0.45 * Math.sin(timeMs * 0.0012 + s.phase);
        ctx.fillStyle = `rgba(255,255,255,${Math.max(0, Math.min(1, s.a * tw))})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // Ring boundaries (outer -> inner).
      ctx.save();
      ctx.strokeStyle = "rgba(255,255,255,0.10)";
      ctx.lineWidth = 1;
      for (const r of g.bounds) {
        ctx.beginPath();
        ctx.arc(g.cx, g.cy, r, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();

      // Subtle domain separators.
      if (enriched.length > 1) {
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,0.06)";
        ctx.lineWidth = 1;
        for (const it of enriched) {
          const a = it.angle - it.wedge / 2;
          const x0 = g.cx + g.bounds[0] * Math.cos(a);
          const y0 = g.cy + g.bounds[0] * Math.sin(a);
          const x1 = g.cx + g.bounds[4] * Math.cos(a);
          const y1 = g.cy + g.bounds[4] * Math.sin(a);
          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(x1, y1);
          ctx.stroke();
        }
        ctx.restore();
      }

      // Paths + progress segments.
      for (const it of enriched) {
        const a0 = it.angle;
        const sign = it.index % 2 === 0 ? 1 : -1;
        const twist = sign * it.wedge * 0.45;

        // Baseline spiral track.
        ctx.save();
        ctx.strokeStyle = "rgba(255,255,255,0.10)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        drawSpiral(g, a0, twist, g.bounds[0], g.bounds[4], 14, (x, y, first) => {
          if (first) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.restore();

        // Filled segments per layer (outside -> inside), using cumulative levels.
        const cum = it.cum;
        const cumArr = [cum.phenomena, cum.empirical, cum.theory, cum.principles];
        for (let k = 0; k < 4; k++) {
          const outer = g.bounds[k];
          const inner = g.bounds[k + 1];
          const thick = outer - inner;
          const p = clamp01(cumArr[k]);
          if (p <= 0) continue;
          const rEnd = outer - thick * p;
          const meta = LAYERS[k];
          const glowAlpha = 0.22 + 0.28 * p;
          const lineAlpha = 0.55 + 0.35 * p;

          // Glow pass.
          ctx.save();
          ctx.globalCompositeOperation = "lighter";
          ctx.strokeStyle = rgba(meta.color, glowAlpha);
          ctx.lineWidth = 12;
          ctx.shadowBlur = 22;
          ctx.shadowColor = rgba(meta.color, 0.45);
          ctx.beginPath();
          drawSpiral(g, a0, twist, outer, rEnd, 10, (x, y, first) => {
            if (first) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });
          ctx.stroke();

          // Core line pass.
          ctx.shadowBlur = 10;
          ctx.shadowColor = rgba(meta.color, 0.35);
          ctx.strokeStyle = rgba(meta.color, lineAlpha);
          ctx.lineWidth = 5;
          ctx.beginPath();
          drawSpiral(g, a0, twist, outer, rEnd, 10, (x, y, first) => {
            if (first) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });
          ctx.stroke();
          ctx.restore();
        }

        // Animated pulse reaching current "frontier" (cumulative depth).
        const depths = [
          (g.bounds[0] - g.bounds[1]) * clamp01(cum.phenomena),
          (g.bounds[1] - g.bounds[2]) * clamp01(cum.empirical),
          (g.bounds[2] - g.bounds[3]) * clamp01(cum.theory),
          (g.bounds[3] - g.bounds[4]) * clamp01(cum.principles),
        ];
        const depthTotal = depths.reduce((acc, v) => acc + v, 0);
        if (depthTotal > 2) {
          const phase = it.index * 0.23;
          const wave = 0.5 - 0.5 * Math.cos(2 * Math.PI * (timeMs * 0.00018 + phase));
          const rPulse = g.bounds[0] - wave * depthTotal;
          let layerIdx = 0;
          if (rPulse <= g.bounds[4]) layerIdx = 3;
          else if (rPulse <= g.bounds[3]) layerIdx = 3;
          else if (rPulse <= g.bounds[2]) layerIdx = 2;
          else if (rPulse <= g.bounds[1]) layerIdx = 1;
          else layerIdx = 0;
          const meta = LAYERS[layerIdx];

          let px = 0;
          let py = 0;
          drawSpiral(g, a0, twist, rPulse, rPulse, 1, (x, y) => {
            px = x;
            py = y;
          });

          ctx.save();
          ctx.globalCompositeOperation = "lighter";
          const grad = ctx.createRadialGradient(px, py, 0, px, py, 14);
          grad.addColorStop(0, rgba(meta.color, 0.95));
          grad.addColorStop(0.4, rgba(meta.color, 0.28));
          grad.addColorStop(1, rgba(meta.color, 0.0));
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(px, py, 14, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = rgba(meta.color, 0.95);
          ctx.beginPath();
          ctx.arc(px, py, 2.2, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }

        // Domain label (outside).
        ctx.save();
        const rText = g.bounds[0] + 22;
        const tx = g.cx + rText * Math.cos(a0);
        const ty = g.cy + rText * Math.sin(a0);
        const rightSide = Math.cos(a0) >= 0;
        ctx.font = "600 11px ui-sans-serif, system-ui";
        ctx.fillStyle = "rgba(255,255,255,0.65)";
        ctx.textAlign = rightSide ? "left" : "right";
        ctx.textBaseline = "middle";
        ctx.fillText(it.domain.name, tx, ty);
        ctx.restore();
      }

      // Core glow (principles average).
      const pCore =
        enriched.reduce((acc, it) => acc + clamp01(it.cum.principles), 0) /
        Math.max(1, enriched.length);
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      const core = ctx.createRadialGradient(g.cx, g.cy, 0, g.cx, g.cy, g.rCore * 1.8);
      core.addColorStop(0, `rgba(251,113,133,${0.20 + 0.55 * pCore})`);
      core.addColorStop(0.35, `rgba(167,139,250,${0.10 + 0.35 * pCore})`);
      core.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(g.cx, g.cy, g.rCore * 1.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      raf = requestAnimationFrame(draw);
    };

    resize();
    window.addEventListener("resize", resize);
    raf = requestAnimationFrame(draw);

    // Interaction.
    const onMove = (ev: PointerEvent) => {
      const g = geomRef.current;
      const wrapEl = wrapRef.current;
      if (!g || !wrapEl) return;
      const rect = wrapEl.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      const idx = domainIndexFromPoint(x, y);
      if (idx < 0 || idx >= domains.length) {
        setHover(null);
        return;
      }
      setHover({ domain: domains[idx], x, y });
    };
    const onLeave = () => setHover(null);
    const onClick = (ev: MouseEvent) => {
      const g = geomRef.current;
      const wrapEl = wrapRef.current;
      if (!g || !wrapEl) return;
      const rect = wrapEl.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      const idx = domainIndexFromPoint(x, y);
      if (idx < 0 || idx >= domains.length) return;
      const d = domains[idx];
      if (!d?.id) return;
      onSelectRef.current?.(d);
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
  }, [domains, enriched, height]);

  const hoverCum = hover ? cumulativeLevels(hover.domain.levels) : null;

  return (
    <div ref={wrapRef} className="relative w-full cursor-pointer" style={{ height }}>
      <canvas ref={canvasRef} className="h-full w-full" />

      {/* Legend overlay */}
      <div className="pointer-events-none absolute left-3 top-3 rounded-xl border border-white/10 bg-black/35 px-3 py-2 text-[11px] text-white/75 backdrop-blur">
        <div className="font-semibold text-white/85">Outside → Core</div>
        <div className="mt-1 grid grid-cols-1 gap-1">
          {LAYERS.map((l) => (
            <div key={l.key} className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{
                  background: l.color,
                  boxShadow: `0 0 14px ${l.color}66`,
                }}
              />
              <span>{l.label}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 text-white/55">Click: drill down / open.</div>
      </div>

      {/* Tooltip */}
      {hover ? (
        <div
          className="pointer-events-none absolute z-10 w-[260px] rounded-xl border border-white/10 bg-black/55 px-3 py-2 text-xs text-white/80 shadow-[0_0_0_1px_rgba(255,255,255,0.06)] backdrop-blur"
          style={{
            left: Math.max(
              10,
              Math.min(
                hover.x + 14,
                Math.max(10, wrapWidth - 280),
              ),
            ),
            top: Math.max(10, hover.y - 12),
          }}
        >
          <div className="text-sm font-semibold text-white/90">
            {hover.domain.name}
          </div>
          <div className="mt-2 grid grid-cols-1 gap-1">
            {LAYERS.map((l) => {
              const raw = clamp01(hover.domain.levels[l.key]);
              const eff = hoverCum ? clamp01(hoverCum[l.key]) : raw;
              return (
                <div key={l.key} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 rounded-sm"
                      style={{
                        background: l.color,
                        boxShadow: `0 0 14px ${l.color}55`,
                      }}
                    />
                    <span className="text-white/75">{l.label}</span>
                  </div>
                  <div className="tabular-nums text-white/85">
                    {Math.round(eff * 100)}%
                    <span className="ml-1 text-white/45">raw {Math.round(raw * 100)}%</span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-2 text-[11px] text-white/55">
            Effective = cumulative min (for “inward reach” feeling).
          </div>
        </div>
      ) : null}
    </div>
  );
}
