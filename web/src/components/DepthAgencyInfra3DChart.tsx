"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

export type DepthAgencyInfraPoint = {
  id: string;
  name: string;
  macroId: string;
  macroName: string;
  agency: number; // 0..100
  depth: number; // 0..100
  depthSource: "llm" | "proxy";
  infrastructure: number; // 0..100
  aiRecent: number;
  autonomy: number;
  tooling: number;
  experiment: number;
  data: number;
};

const MACRO_PALETTE = [
  "#00E5FF", // cyan
  "#FF3D00", // red-orange
  "#FFEA00", // yellow
  "#00E676", // green
  "#2979FF", // blue
  "#D500F9", // magenta
  "#FF9100", // orange
  "#76FF03", // lime
];

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

function hexToRgb(hex: string) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return { r: 255, g: 255, b: 255 };
  const v = Number.parseInt(m[1], 16);
  return { r: (v >> 16) & 255, g: (v >> 8) & 255, b: v & 255 };
}

type HoverInfo = {
  point: DepthAgencyInfraPoint;
  x: number;
  y: number;
};

export function DepthAgencyInfra3DChart({
  points,
  height = 640,
}: {
  points: DepthAgencyInfraPoint[];
  height?: number;
}) {
  const router = useRouter();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const hoverIdRef = useRef<string | null>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [wrapSize, setWrapSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [spread, setSpread] = useState<boolean>(true);
  const [autoRotate, setAutoRotate] = useState<boolean>(true);

  const macroInfo = useMemo(() => {
    const macros = Array.from(
      new Map(points.map((p) => [p.macroId, p.macroName] as const)).entries(),
    ).map(([id, name]) => ({ id, name }));
    const colorByMacro = new Map<string, string>();
    macros.forEach((m, i) => colorByMacro.set(m.id, MACRO_PALETTE[i % MACRO_PALETTE.length]));
    return { macros, colorByMacro };
  }, [points]);

  const displayParams = useMemo(() => {
    // Low-score clustering is common early on; use gamma to spread values visually.
    // gamma < 1 expands the low-end while preserving ordering.
    return {
      cube: 12,
      gamma: spread ? 0.38 : 1.0,
      jitter: spread ? 0.085 : 0.03,
      pointSize: spread ? 7 : 6,
      markerScale: spread ? 0.7 : 0.6,
    };
  }, [spread]);

  const paletteByMacro = useMemo(() => macroInfo.colorByMacro, [macroInfo.colorByMacro]);

  useEffect(() => {
    let destroyed = false;
    let raf = 0;
    const wrap = wrapRef.current;
    if (!wrap) return;

    const ro = new ResizeObserver(() => {
      const w = Math.max(1, wrap.clientWidth || 1);
      const h = Math.max(1, wrap.clientHeight || 1);
      setWrapSize({ w, h });
    });
    ro.observe(wrap);

    (async () => {
      const [THREE, controlsModule] = await Promise.all([
        import("three"),
        import("three/examples/jsm/controls/OrbitControls.js"),
      ]);
      const { OrbitControls } = controlsModule;
      if (destroyed) return;

      const w = Math.max(1, wrap.clientWidth || 1);
      const h = Math.max(1, wrap.clientHeight || 1);
      setWrapSize({ w, h });

      const scene = new THREE.Scene();
      scene.fog = new THREE.Fog(0x040616, 22, 84);

      const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 200);
      camera.position.set(18, 14, 18);

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
      renderer.setPixelRatio(Math.max(1, window.devicePixelRatio || 1));
      renderer.setSize(w, h);
      renderer.setClearColor(0x000000, 0);
      wrap.appendChild(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.085;
      controls.minDistance = 8;
      controls.maxDistance = 42;
      controls.autoRotate = autoRotate;
      controls.autoRotateSpeed = 0.22;

      const ambient = new THREE.AmbientLight(0xffffff, 0.62);
      scene.add(ambient);
      const keyLight = new THREE.DirectionalLight(0xffffff, 0.55);
      keyLight.position.set(8, 10, 6);
      scene.add(keyLight);

      const cube = displayParams.cube; // world size
      const half = cube / 2;

      // Wireframe cube
      const boxGeo = new THREE.BoxGeometry(cube, cube, cube);
      const edges = new THREE.EdgesGeometry(boxGeo);
      const boxMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.07 });
      const boxLines = new THREE.LineSegments(edges, boxMat);
      scene.add(boxLines);

      // Axes (x=agency, y=depth, z=infrastructure)
      const axis = (from: [number, number, number], to: [number, number, number], color: number) => {
        const geo = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(...from),
          new THREE.Vector3(...to),
        ]);
        return new THREE.Line(
          geo,
          new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.38 }),
        );
      };
      scene.add(axis([-half, -half, -half], [half, -half, -half], 0x22d3ee)); // x
      scene.add(axis([-half, -half, -half], [-half, half, -half], 0xa78bfa)); // y
      scene.add(axis([-half, -half, -half], [-half, -half, half], 0x4ade80)); // z

      const axisGeos: Array<import("three").BufferGeometry> = [];
      const axisMats: Array<import("three").Material> = [];

      const addAxisRod = (
        start: [number, number, number],
        end: [number, number, number],
        color: number,
      ) => {
        const s = new THREE.Vector3(...start);
        const e = new THREE.Vector3(...end);
        const dir = new THREE.Vector3().subVectors(e, s);
        const length = dir.length();
        if (length <= 0) return;
        const mid = new THREE.Vector3().addVectors(s, e).multiplyScalar(0.5);
        const unit = dir.clone().normalize();

        const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85 });
        const rodGeo = new THREE.CylinderGeometry(0.045, 0.045, length, 14);
        const rod = new THREE.Mesh(rodGeo, mat);
        rod.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), unit);
        rod.position.copy(mid);
        scene.add(rod);

        const coneGeo = new THREE.ConeGeometry(0.13, 0.34, 14);
        const cone = new THREE.Mesh(coneGeo, mat);
        cone.quaternion.copy(rod.quaternion);
        cone.position.copy(e.clone().add(unit.multiplyScalar(0.17)));
        scene.add(cone);

        axisGeos.push(rodGeo, coneGeo);
        axisMats.push(mat);
      };

      addAxisRod([-half, -half, -half], [half, -half, -half], 0x22d3ee);
      addAxisRod([-half, -half, -half], [-half, half, -half], 0xa78bfa);
      addAxisRod([-half, -half, -half], [-half, -half, half], 0x4ade80);

      const originGeo = new THREE.SphereGeometry(0.11, 16, 16);
      const originMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.55 });
      const origin = new THREE.Mesh(originGeo, originMat);
      origin.position.set(-half, -half, -half);
      scene.add(origin);
      axisGeos.push(originGeo);
      axisMats.push(originMat);

      // Subtle grid planes
      const gridMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.03 });
      const gridPlane = (normal: "x" | "y" | "z") => {
        const lines: Array<import("three").Line> = [];
        const step = cube / 5;
        for (let i = 1; i < 5; i += 1) {
          const t = -half + i * step;
          if (normal === "z") {
            const g1 = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-half, t, -half), new THREE.Vector3(half, t, -half)]);
            const g2 = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(t, -half, -half), new THREE.Vector3(t, half, -half)]);
            lines.push(new THREE.Line(g1, gridMat), new THREE.Line(g2, gridMat));
          } else if (normal === "y") {
            const g1 = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-half, -half, t), new THREE.Vector3(half, -half, t)]);
            const g2 = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(t, -half, -half), new THREE.Vector3(t, -half, half)]);
            lines.push(new THREE.Line(g1, gridMat), new THREE.Line(g2, gridMat));
          } else {
            const g1 = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-half, t, -half), new THREE.Vector3(-half, t, half)]);
            const g2 = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-half, -half, t), new THREE.Vector3(-half, half, t)]);
            lines.push(new THREE.Line(g1, gridMat), new THREE.Line(g2, gridMat));
          }
        }
        return lines;
      };
      for (const l of gridPlane("z")) scene.add(l);
      for (const l of gridPlane("y")) scene.add(l);
      for (const l of gridPlane("x")) scene.add(l);

      // Point sprites for clear, bright color separation.
      const positions = new Float32Array(points.length * 3);
      const colors = new Float32Array(points.length * 3);

      const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
      const gamma = Math.max(0.1, Math.min(2.0, displayParams.gamma));
      const warp = (v01: number) => Math.pow(clamp01(v01), gamma);

      const hash32 = (s: string) => {
        let h = 2166136261;
        for (let i = 0; i < s.length; i += 1) {
          h ^= s.charCodeAt(i);
          h = Math.imul(h, 16777619);
        }
        return h >>> 0;
      };
      const xorshift32 = (x: number) => {
        x ^= x << 13;
        x ^= x >>> 17;
        x ^= x << 5;
        return x >>> 0;
      };
      const jitter3 = (id: string) => {
        let x = hash32(id);
        x = xorshift32(x);
        const a = x / 0xffffffff - 0.5;
        x = xorshift32(x);
        const b = x / 0xffffffff - 0.5;
        x = xorshift32(x);
        const c = x / 0xffffffff - 0.5;
        return { a, b, c };
      };

      for (let i = 0; i < points.length; i += 1) {
        const p = points[i];
        const j = jitter3(p.id);
        const jScale = displayParams.jitter;
        const x = (warp(clamp(p.agency, 0, 100) / 100) - 0.5) * cube + jScale * j.a;
        const y = (warp(clamp(p.depth, 0, 100) / 100) - 0.5) * cube + jScale * j.b;
        const z = (warp(clamp(p.infrastructure, 0, 100) / 100) - 0.5) * cube + jScale * j.c;
        positions[i * 3] = x;
        positions[i * 3 + 1] = y;
        positions[i * 3 + 2] = z;

        const hex = paletteByMacro.get(p.macroId) ?? "#ffffff";
        const { r, g, b } = hexToRgb(hex);
        colors[i * 3] = r / 255;
        colors[i * 3 + 1] = g / 255;
        colors[i * 3 + 2] = b / 255;
      }

      const pointCanvas = document.createElement("canvas");
      const texSize = 64;
      pointCanvas.width = texSize;
      pointCanvas.height = texSize;
      const ctx = pointCanvas.getContext("2d");
      if (ctx) {
        const cx = texSize / 2;
        const grad = ctx.createRadialGradient(cx, cx, 0, cx, cx, cx);
        grad.addColorStop(0, "rgba(255,255,255,1)");
        grad.addColorStop(0.45, "rgba(255,255,255,1)");
        grad.addColorStop(0.75, "rgba(255,255,255,0.35)");
        grad.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, texSize, texSize);
      }
      const pointTexture = new THREE.CanvasTexture(pointCanvas);
      pointTexture.colorSpace = THREE.SRGBColorSpace;

      const cloudGeo = new THREE.BufferGeometry();
      cloudGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      cloudGeo.setAttribute("color", new THREE.BufferAttribute(colors, 3));

      const cloudMat = new THREE.PointsMaterial({
        size: displayParams.pointSize,
        sizeAttenuation: false,
        vertexColors: true,
        map: pointTexture,
        transparent: true,
        opacity: 0.95,
        blending: THREE.AdditiveBlending,
        alphaTest: 0.12,
        depthWrite: false,
      });

      const cloud = new THREE.Points(cloudGeo, cloudMat);
      scene.add(cloud);

      // Hover marker (sprite)
      const marker = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: pointTexture,
          color: 0xffffff,
          transparent: true,
          opacity: 0.9,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      );
      marker.scale.setScalar(displayParams.markerScale);
      marker.visible = false;
      scene.add(marker);

      const raycaster = new THREE.Raycaster();
      if (!raycaster.params.Points) raycaster.params.Points = { threshold: 0.3 };
      else raycaster.params.Points.threshold = 0.3;
      const mouse = new THREE.Vector2();

      const setHoverFromIndex = (index: number, localX: number, localY: number) => {
        const p = points[index];
        if (!p) return;
        hoverIdRef.current = p.id;
        setHover({ point: p, x: localX, y: localY });

        marker.visible = true;
        marker.position.set(positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2]);
        marker.scale.setScalar(displayParams.markerScale);
      };

      const clearHover = () => {
        hoverIdRef.current = null;
        setHover(null);
        marker.visible = false;
      };

      const onPointerMove = (ev: PointerEvent) => {
        const rect = renderer.domElement.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        mouse.x = (x / rect.width) * 2 - 1;
        mouse.y = -(y / rect.height) * 2 + 1;

        raycaster.setFromCamera(mouse, camera);
        const hits = raycaster.intersectObject(cloud, false);
        if (!hits.length) {
          clearHover();
          return;
        }
        const idx = (hits[0] as unknown as { index?: number }).index;
        if (typeof idx !== "number") {
          clearHover();
          return;
        }
        setHoverFromIndex(idx, x, y);
      };

      const onClick = () => {
        const id = hoverIdRef.current;
        if (!id) return;
        router.push(`/domain/${encodeURIComponent(id)}`);
      };

      renderer.domElement.addEventListener("pointermove", onPointerMove);
      renderer.domElement.addEventListener("pointerleave", clearHover);
      renderer.domElement.addEventListener("click", onClick);

      const resize = () => {
        const ww = Math.max(1, wrap.clientWidth || 1);
        const hh = Math.max(1, wrap.clientHeight || 1);
        renderer.setSize(ww, hh);
        camera.aspect = ww / hh;
        camera.updateProjectionMatrix();
        setWrapSize({ w: ww, h: hh });
      };
      window.addEventListener("resize", resize);

      const animate = () => {
        if (destroyed) return;
        controls.update();
        renderer.render(scene, camera);
        raf = requestAnimationFrame(animate);
      };
      animate();

      const cleanup = () => {
        renderer.domElement.removeEventListener("pointermove", onPointerMove);
        renderer.domElement.removeEventListener("pointerleave", clearHover);
        renderer.domElement.removeEventListener("click", onClick);
        window.removeEventListener("resize", resize);
        controls.dispose();
        cloudGeo.dispose();
        cloudMat.dispose();
        pointTexture.dispose();
        marker.geometry.dispose();
        if (Array.isArray(marker.material)) marker.material.forEach((m) => m.dispose());
        else marker.material.dispose();
        boxGeo.dispose();
        edges.dispose();
        boxMat.dispose();
        gridMat.dispose();
        axisGeos.forEach((g) => g.dispose());
        axisMats.forEach((m) => m.dispose());
        renderer.dispose();
        if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      };

      cleanupRef.current = cleanup;
    })().catch(() => {
      // ignore; will show empty container
    });

    return () => {
      destroyed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      cleanupRef.current?.();
      cleanupRef.current = null;
    };
  }, [autoRotate, displayParams, paletteByMacro, points, router]);

  const tooltip = hover ? (
    <div
      className="pointer-events-none absolute z-10 w-[340px] rounded-xl border border-white/10 bg-black/60 px-3 py-2 text-xs text-white/85 shadow-[0_0_0_1px_rgba(255,255,255,0.06)] backdrop-blur"
      style={{
        left: Math.max(10, Math.min(hover.x + 14, Math.max(10, wrapSize.w - 360))),
        top: Math.max(10, Math.min(hover.y - 10, Math.max(10, wrapSize.h - 220))),
      }}
    >
      <div className="text-sm font-semibold text-white/95">{hover.point.name}</div>
      <div className="mt-1 text-[11px] text-white/60">{hover.point.macroName}</div>
      <div className="mt-2 grid grid-cols-1 gap-1">
        <div className="flex items-center justify-between gap-3">
          <span className="text-white/70">Agency (x)</span>
          <span className="tabular-nums text-white/90">{hover.point.agency.toFixed(1)}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-white/70">Depth (y)</span>
          <span className="tabular-nums text-white/90">
            {hover.point.depth.toFixed(1)}{" "}
            <span className="text-white/45">({hover.point.depthSource})</span>
          </span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-white/70">Infrastructure (z)</span>
          <span className="tabular-nums text-white/90">
            {hover.point.infrastructure.toFixed(1)}
          </span>
        </div>
      </div>
      <div className="mt-2 text-[11px] text-white/60">
        data {Math.round(hover.point.data)}% · tooling {Math.round(hover.point.tooling)}% · autonomy{" "}
        {Math.round(hover.point.autonomy)}% · experiment {Math.round(hover.point.experiment)}%
      </div>
      <div className="mt-2 text-[11px] text-white/55">
        AI×Domain (5y): {Math.trunc(hover.point.aiRecent).toLocaleString()} • Click to open
      </div>
    </div>
  ) : null;

  return (
    <div className="relative w-full" style={{ height }}>
      <div ref={wrapRef} className="h-full w-full" />

      {/* Controls */}
      <div className="absolute bottom-3 left-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setSpread((v) => !v)}
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
            spread
              ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
              : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.06]"
          }`}
        >
          Spread
        </button>
        <button
          type="button"
          onClick={() => setAutoRotate((v) => !v)}
          className={`rounded-full border px-3 py-1 text-xs font-semibold ${
            autoRotate
              ? "border-violet-400/30 bg-violet-400/10 text-violet-100"
              : "border-white/10 bg-white/[0.03] text-white/70 hover:bg-white/[0.06]"
          }`}
        >
          Auto‑rotate
        </button>
      </div>

      {/* Overlay legend */}
      <div className="pointer-events-none absolute left-3 top-3 rounded-xl border border-white/10 bg-black/35 px-3 py-2 text-[11px] text-white/75 backdrop-blur">
        <div className="font-semibold text-white/85">3D Axes</div>
        <div className="mt-1 grid grid-cols-1 gap-1 text-white/65">
          <div>
            <span className="text-cyan-200">x</span>: Agency (assistant→collaborator→autonomous)
          </div>
          <div>
            <span className="text-violet-200">y</span>: Depth (phenomena→principles)
          </div>
          <div>
            <span className="text-emerald-200">z</span>: Infrastructure/Adoption (data+tooling+volume)
          </div>
        </div>
        <div className="mt-2 text-white/55">
          Drag: orbit • Scroll: zoom • Click: open{spread ? " • Display: gamma spread" : ""}
        </div>
      </div>

      {/* Macro legend */}
      <div className="pointer-events-none absolute right-3 top-3 hidden max-w-[280px] flex-col gap-1 rounded-xl border border-white/10 bg-black/35 px-3 py-2 text-[11px] text-white/75 backdrop-blur md:flex">
        <div className="font-semibold text-white/85">Macro</div>
        <div className="mt-1 grid grid-cols-1 gap-1">
          {macroInfo.macros.map((m) => (
            <div key={m.id} className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{
                  background: macroInfo.colorByMacro.get(m.id) ?? "rgba(255,255,255,0.5)",
                  boxShadow: `0 0 14px ${
                    macroInfo.colorByMacro.get(m.id) ?? "rgba(255,255,255,0.25)"
                  }66`,
                }}
              />
              <span className="truncate">{m.name}</span>
            </div>
          ))}
        </div>
      </div>

      {tooltip}
    </div>
  );
}
