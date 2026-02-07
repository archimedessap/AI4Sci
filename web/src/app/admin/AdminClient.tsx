"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { DimensionKey, NodeOverride } from "@/lib/progress/types";

type AdminNode = {
  id: string;
  name: string;
  depth: number;
  overallScore: number;
  dimensions: Record<DimensionKey, number>;
};

const storageKey = "ai4sci_admin_token";

export function AdminClient({
  nodes,
  dimensions,
  initialOverrides,
  requiresToken,
}: {
  nodes: AdminNode[];
  dimensions: Array<{ key: DimensionKey; label: string }>;
  initialOverrides: Record<string, NodeOverride>;
  requiresToken: boolean;
}) {
  const router = useRouter();
  const [token, setToken] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(storageKey) ?? "";
  });
  const [nodeId, setNodeId] = useState<string>(nodes[0]?.id ?? "");
  const [target, setTarget] = useState<"overall" | DimensionKey>("overall");
  const [score, setScore] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const [status, setStatus] = useState<string>("");

  const node = useMemo(() => nodes.find((n) => n.id === nodeId) ?? null, [nodeId, nodes]);
  const currentScore = useMemo(() => {
    if (!node) return 0;
    if (target === "overall") return node.overallScore;
    return node.dimensions[target];
  }, [node, target]);

  const currentOverride = initialOverrides[nodeId];

  async function submit(patch: unknown) {
    setStatus("Saving...");
    if (typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, token);
    }

    const headers: Record<string, string> = { "content-type": "application/json" };
    if (token) headers.authorization = `Bearer ${token}`;
    const res = await fetch("/api/admin/overrides", {
      method: "POST",
      headers,
      body: JSON.stringify({ nodeId, patch }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatus(`Error: ${json?.error ?? res.status}`);
      return;
    }
    setStatus("Saved. Refreshing...");
    router.refresh();
    setTimeout(() => setStatus(""), 1200);
  }

  async function clearNode() {
    setStatus("Clearing...");
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (token) headers.authorization = `Bearer ${token}`;
    const res = await fetch("/api/admin/overrides", {
      method: "POST",
      headers,
      body: JSON.stringify({ nodeId, clearNode: true }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatus(`Error: ${json?.error ?? res.status}`);
      return;
    }
    router.refresh();
    setTimeout(() => setStatus(""), 1200);
  }

  async function clearDimension(dim: DimensionKey) {
    setStatus("Clearing...");
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (token) headers.authorization = `Bearer ${token}`;
    const res = await fetch("/api/admin/overrides", {
      method: "POST",
      headers,
      body: JSON.stringify({ nodeId, clearDimension: dim }),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatus(`Error: ${json?.error ?? res.status}`);
      return;
    }
    router.refresh();
    setTimeout(() => setStatus(""), 1200);
  }

  return (
    <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-12">
      <div className="lg:col-span-5">
        <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-sm font-semibold text-white/90">Auth</h2>
          <p className="mt-1 text-xs leading-5 text-white/55">
            {requiresToken
              ? "Set ADMIN_TOKEN and paste it here to enable writes."
              : "ADMIN_TOKEN not set (writes allowed in non-production)."}
          </p>
          <input
            className="mt-3 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none ring-0 placeholder:text-white/30 focus:border-cyan-400/60"
            placeholder="ADMIN_TOKEN (optional in dev)"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <div className="mt-3 text-xs text-white/40">{status}</div>
        </section>

        <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-sm font-semibold text-white/90">Select Node</h2>
          <select
            className="mt-3 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none focus:border-cyan-400/60"
            value={nodeId}
            onChange={(e) => setNodeId(e.target.value)}
          >
            {nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {"  ".repeat(Math.max(0, n.depth))}{n.name} ({n.id})
              </option>
            ))}
          </select>

          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="text-xs text-white/55">Current score</div>
            <div className="text-sm font-semibold text-white/90">
              {currentScore.toFixed(1)}
            </div>
          </div>

          <div className="mt-4">
            <div className="text-xs font-semibold text-white/80">Target</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                  target === "overall"
                    ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-200"
                    : "border-white/10 bg-white/[0.02] text-white/70 hover:bg-white/[0.05]"
                }`}
                onClick={() => setTarget("overall")}
              >
                Overall
              </button>
              {dimensions.map((d) => (
                <button
                  key={d.key}
                  type="button"
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                    target === d.key
                      ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-200"
                      : "border-white/10 bg-white/[0.02] text-white/70 hover:bg-white/[0.05]"
                  }`}
                  onClick={() => setTarget(d.key)}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3">
            <div>
              <div className="text-xs font-semibold text-white/80">Override score</div>
              <input
                className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none placeholder:text-white/30 focus:border-cyan-400/60"
                placeholder="0-100 (leave empty to use auto)"
                value={score}
                onChange={(e) => setScore(e.target.value)}
              />
            </div>
            <div>
              <div className="text-xs font-semibold text-white/80">Note</div>
              <textarea
                className="mt-2 w-full resize-none rounded-xl border border-white/10 bg-black/30 px-4 py-2 text-sm text-white/85 outline-none placeholder:text-white/30 focus:border-cyan-400/60"
                placeholder="Why override? (bias, missing source, milestone, etc.)"
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-full bg-cyan-400/15 px-4 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-400/20"
              onClick={() => {
                const parsed = Number(score);
                if (!Number.isFinite(parsed)) {
                  setStatus("Invalid score.");
                  return;
                }
                if (target === "overall") {
                  submit({ overall: { score: parsed, note: note || undefined } });
                } else {
                  submit({
                    dimensions: {
                      [target]: { score: parsed, note: note || undefined },
                    },
                  });
                }
              }}
            >
              Save override
            </button>

            {target !== "overall" ? (
              <button
                type="button"
                className="rounded-full border border-white/10 bg-white/[0.03] px-4 py-2 text-xs font-semibold text-white/75 hover:bg-white/[0.06]"
                onClick={() => clearDimension(target)}
              >
                Clear dimension override
              </button>
            ) : null}

            <button
              type="button"
              className="rounded-full border border-rose-400/20 bg-rose-400/10 px-4 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-400/15"
              onClick={() => clearNode()}
            >
              Clear node overrides
            </button>
          </div>
        </section>
      </div>

      <div className="lg:col-span-7">
        <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-sm font-semibold text-white/90">Current Override (JSON)</h2>
            <a
              className="text-xs font-semibold text-white/60 hover:text-white/80"
              href={`/domain/${encodeURIComponent(nodeId)}`}
              target="_blank"
              rel="noreferrer"
            >
              Open node →
            </a>
          </div>
          <pre className="mt-4 overflow-auto rounded-xl border border-white/10 bg-black/40 p-4 text-xs leading-5 text-white/70">
            {JSON.stringify(currentOverride ?? {}, null, 2)}
          </pre>
        </section>

        <section className="mt-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-sm font-semibold text-white/90">Auto Snapshot</h2>
          <p className="mt-1 text-xs leading-5 text-white/55">
            This panel shows current auto scores (after overrides are applied on the server).
          </p>
          {node ? (
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-xs text-white/55">Overall</div>
                <div className="mt-1 text-lg font-semibold text-white/90">
                  {node.overallScore.toFixed(1)}
                </div>
              </div>
              {dimensions.map((d) => (
                <div
                  key={d.key}
                  className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
                >
                  <div className="text-xs text-white/55">{d.label}</div>
                  <div className="mt-1 text-lg font-semibold text-white/90">
                    {node.dimensions[d.key].toFixed(1)}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
