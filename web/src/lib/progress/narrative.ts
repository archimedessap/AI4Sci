export const NARRATIVE_STAGE_KEYS = [
  "related",
  "causal",
  "mechanism",
  "unification",
  "closed_loop",
] as const;

export type NarrativeStageKey = (typeof NARRATIVE_STAGE_KEYS)[number];

export type NarrativeMetricKey =
  | "overall"
  | "data"
  | "model"
  | "predict"
  | "experiment"
  | "explain"
  | "confidence"
  | "aiRecent"
  | "signalRatioExplain"
  | "signalRatioExperiment"
  | "tooling"
  | "autonomy"
  | "theory"
  | "principles";

export type NarrativeCriterion = {
  key: string;
  label: string;
  metric?: NarrativeMetricKey;
  current: number | null;
  threshold: number;
  passed: boolean;
  note?: string;
};

export type NarrativeStageEvaluation = {
  key: NarrativeStageKey;
  label: string;
  description: string;
  passed: boolean;
  coverage: number; // 0..1
  criteria: NarrativeCriterion[];
};

export type NarrativeEvaluation = {
  currentStageIndex: number; // -1..4
  currentStageKey: NarrativeStageKey | "none";
  nextStageKey: NarrativeStageKey | null;
  stages: NarrativeStageEvaluation[];
};

export type NarrativeInputs = {
  scores: Partial<Record<"overall" | "data" | "model" | "predict" | "experiment" | "explain", number>>;
  confidence?: number | null; // 0..1
  aiRecent?: number | null;
  signalRatioExplain?: number | null; // 0..1
  signalRatioExperiment?: number | null; // 0..1
  tooling?: number | null; // 0..100
  autonomy?: number | null; // 0..100
  theory?: number | null; // 0..1 (LLM layers)
  principles?: number | null; // 0..1 (LLM layers)
};

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function passGte(current: number | null, threshold: number): boolean {
  return typeof current === "number" && Number.isFinite(current) && current >= threshold;
}

function criterion({
  key,
  label,
  metric,
  current,
  threshold,
  note,
}: {
  key: string;
  label: string;
  metric?: NarrativeMetricKey;
  current: number | null;
  threshold: number;
  note?: string;
}): NarrativeCriterion {
  return { key, label, metric, current, threshold, passed: passGte(current, threshold), note };
}

export function narrativeStageLabel(key: NarrativeStageKey | "none") {
  switch (key) {
    case "related":
      return "相关 / Related";
    case "causal":
      return "因果 / Causal";
    case "mechanism":
      return "机制 / Mechanism";
    case "unification":
      return "统一 / Unification";
    case "closed_loop":
      return "闭环探索 / Closed‑Loop";
    default:
      return "未进入叙事 / Not yet";
  }
}

export function narrativeStageColor(key: NarrativeStageKey | "none") {
  switch (key) {
    case "related":
      return "#22d3ee"; // cyan-400
    case "causal":
      return "#fbbf24"; // amber-400
    case "mechanism":
      return "#4ade80"; // green-400
    case "unification":
      return "#a78bfa"; // violet-400
    case "closed_loop":
      return "#fb7185"; // rose-400
    default:
      return "#475569"; // slate-600
  }
}

export function evaluateNarrativeMilestones(input: NarrativeInputs): NarrativeEvaluation {
  const scores = input.scores ?? {};
  const confidence = num(input.confidence);
  const aiRecent = num(input.aiRecent);
  const ratioExplain = num(input.signalRatioExplain);
  const ratioExperiment = num(input.signalRatioExperiment);
  const tooling = num(input.tooling);
  const autonomy = num(input.autonomy);
  const theory = num(input.theory);
  const principles = num(input.principles);

  const overall = num(scores.overall);
  const data = num(scores.data);
  const model = num(scores.model);
  const predict = num(scores.predict);
  const experiment = num(scores.experiment);
  const explain = num(scores.explain);

  const stages: NarrativeStageEvaluation[] = [
    {
      key: "related",
      label: narrativeStageLabel("related"),
      description: "能在该领域稳定做“相关性/模式”层面的建模与预测（数据与模型已可用）。",
      criteria: [
        criterion({ key: "data", label: "Data score ≥ 15", metric: "data", current: data, threshold: 15 }),
        criterion({
          key: "model_or_predict",
          label: "Modeling/Predict score ≥ 25 (max)",
          metric: "model",
          current: typeof model === "number" || typeof predict === "number" ? Math.max(model ?? 0, predict ?? 0) : null,
          threshold: 25,
          note: "Uses max(model,predict) as a proxy for correlation-level capability.",
        }),
        criterion({
          key: "confidence",
          label: "Evidence strength (confidence) ≥ 0.40",
          metric: "confidence",
          current: confidence,
          threshold: 0.4,
        }),
        criterion({
          key: "ai_recent",
          label: "AI×domain volume (ai_recent) ≥ 50",
          metric: "aiRecent",
          current: aiRecent,
          threshold: 50,
        }),
      ],
      passed: false,
      coverage: 0,
    },
    {
      key: "causal",
      label: narrativeStageLabel("causal"),
      description: "从“能预测”走向“能解释因果/可干预”，强调因果与可解释信号。",
      criteria: [
        criterion({
          key: "explain",
          label: "Explain score ≥ 26",
          metric: "explain",
          current: explain,
          threshold: 26,
        }),
        criterion({
          key: "explain_ratio",
          label: "Explain keyword ratio ≥ 0.18",
          metric: "signalRatioExplain",
          current: ratioExplain,
          threshold: 0.18,
          note: "OpenAlex keyword ratio inside AI×domain (causal/interpretability/symbolic).",
        }),
        criterion({
          key: "confidence",
          label: "Evidence strength (confidence) ≥ 0.55",
          metric: "confidence",
          current: confidence,
          threshold: 0.55,
        }),
      ],
      passed: false,
      coverage: 0,
    },
    {
      key: "mechanism",
      label: narrativeStageLabel("mechanism"),
      description: "出现可检验的机制/理论贡献（不仅相关性解释），能支持反事实与可证伪推论。",
      criteria: [
        ...(typeof theory === "number"
          ? [
              criterion({
                key: "theory",
                label: "Discovery layer: theory ≥ 0.20",
                metric: "theory",
                current: theory,
                threshold: 0.2,
              }),
            ]
          : [
              criterion({
                key: "theory_proxy_explain",
                label: "Proxy: Explain score ≥ 30",
                metric: "explain",
                current: explain,
                threshold: 30,
                note: "Discovery layers missing; use explain as proxy.",
              }),
              criterion({
                key: "theory_proxy_model",
                label: "Proxy: Model score ≥ 35",
                metric: "model",
                current: model,
                threshold: 35,
                note: "Discovery layers missing; use model as proxy.",
              }),
            ]),
        criterion({
          key: "explain",
          label: "Explain score ≥ 26",
          metric: "explain",
          current: explain,
          threshold: 26,
        }),
        criterion({
          key: "confidence",
          label: "Evidence strength (confidence) ≥ 0.65",
          metric: "confidence",
          current: confidence,
          threshold: 0.65,
        }),
      ],
      passed: false,
      coverage: 0,
    },
    {
      key: "unification",
      label: narrativeStageLabel("unification"),
      description: "出现“统一/压缩”的更深层贡献（原理/统一框架），跨任务/跨子问题可迁移。",
      criteria: [
        ...(typeof principles === "number"
          ? [
              criterion({
                key: "principles",
                label: "Discovery layer: principles ≥ 0.20",
                metric: "principles",
                current: principles,
                threshold: 0.2,
              }),
            ]
          : [
              criterion({
                key: "principles_proxy_explain",
                label: "Proxy: Explain score ≥ 35",
                metric: "explain",
                current: explain,
                threshold: 35,
                note: "Discovery layers missing; use explain as proxy.",
              }),
            ]),
        ...(typeof theory === "number"
          ? [
              criterion({
                key: "theory",
                label: "Discovery layer: theory ≥ 0.20",
                metric: "theory",
                current: theory,
                threshold: 0.2,
              }),
            ]
          : [
              criterion({
                key: "theory_proxy",
                label: "Proxy: Explain score ≥ 30",
                metric: "explain",
                current: explain,
                threshold: 30,
                note: "Discovery layers missing; use explain as proxy.",
              }),
            ]),
        criterion({
          key: "confidence",
          label: "Evidence strength (confidence) ≥ 0.70",
          metric: "confidence",
          current: confidence,
          threshold: 0.7,
        }),
      ],
      passed: false,
      coverage: 0,
    },
    {
      key: "closed_loop",
      label: narrativeStageLabel("closed_loop"),
      description: "形成可复用的闭环：设问→实验/仿真→分析→更新（人主导减少）。",
      criteria: [
        criterion({
          key: "experiment",
          label: "Experiment score ≥ 25",
          metric: "experiment",
          current: experiment,
          threshold: 25,
        }),
        criterion({
          key: "experiment_ratio",
          label: "Experiment keyword ratio ≥ 0.07",
          metric: "signalRatioExperiment",
          current: ratioExperiment,
          threshold: 0.07,
          note: "OpenAlex keyword ratio inside AI×domain (closed-loop/autonomous/robotic).",
        }),
        criterion({
          key: "autonomy",
          label: "Autonomy (DB heuristics) ≥ 12",
          metric: "autonomy",
          current: autonomy,
          threshold: 12,
        }),
        criterion({
          key: "confidence",
          label: "Evidence strength (confidence) ≥ 0.70",
          metric: "confidence",
          current: confidence,
          threshold: 0.7,
        }),
      ],
      passed: false,
      coverage: 0,
    },
  ];

  for (const stage of stages) {
    const passedCount = stage.criteria.filter((c) => c.passed).length;
    stage.coverage = stage.criteria.length ? passedCount / stage.criteria.length : 0;
    stage.passed = stage.criteria.every((c) => c.passed);
  }

  let currentStageIndex = -1;
  for (let i = 0; i < stages.length; i += 1) {
    if (stages[i].passed && currentStageIndex === i - 1) {
      currentStageIndex = i;
    } else {
      break;
    }
  }

  const currentStageKey: NarrativeStageKey | "none" =
    currentStageIndex >= 0 ? stages[currentStageIndex].key : "none";

  const nextStageKey: NarrativeStageKey | null =
    currentStageIndex + 1 < stages.length ? stages[currentStageIndex + 1].key : null;

  // Note: `overall` is not directly used as a gate yet, but keeping it in inputs allows future tuning.
  void overall;
  void tooling;

  return { currentStageIndex, currentStageKey, nextStageKey, stages };
}

