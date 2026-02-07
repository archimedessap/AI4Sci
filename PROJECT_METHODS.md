# AI4Sci Classification & Scoring Methods

This document summarizes how the project classifies content and computes scores.
It is derived directly from the repository logic (Python scripts + Next.js UI).

## 1) Taxonomy (Problem Space)
- Root: `ai4sci` (see `web/data/base.json`).
- Top-level macros (8): Chemistry & Materials, Earth & Environment, Engineering & Technology,
  Formal Sciences, Life Science, Methods, Fundamental Physics, Human Society.
- Leaf nodes are the operational units for scoring and analysis.
- Each leaf node is mapped to an OpenAlex concept (by id or name).
- The `methods` branch is a special taxonomy branch and is excluded from most "problem space" analyses.

## 2) Five Dimensions (Per-Domain Scores)
Definitions come from `web/data/base.json`:
- data: AI-ready data, measurement, benchmarks (FAIR/labeling/benchmark).
- model: modeling and simulation replacement/augmentation (surrogate/neural operator).
- predict: prediction and control (forecast/RL/control).
- experiment: experimental/closed-loop design (active learning/robotic lab).
- explain: causality/mechanism/theory (causal/symbolic/theory).

## 3) OpenAlex Signal Model (Auto Scores)
Computed in `scripts/update_progress_openalex.py`.

### Data window and counts
- Time window: last 5 years (from Jan 1 of current_year-4).
- AI concept: OpenAlex "Machine learning".
- Per domain:
  - total_recent = works_count(domain concept, last 5y)
  - ai_recent = works_count(domain concept + AI concept, last 5y)
  - ai_last_year = works_count(domain + AI, last 365 days)
  - ai_prev_year = works_count(domain + AI, 365-730 days)

### Core signals
- penetration = ai_recent / total_recent (0..1)
- growth_norm = clamp01(0.5 + 0.25 * log2((ai_last_year+1)/(ai_prev_year+1)))
- volume_norm = clamp01(log10(ai_recent+1) / max_log10(ai_recent+1) across domains)
- confidence = clamp01(0.15 + 0.85 * volume_norm)

### Dimension keyword signal ratios
Terms (OpenAlex search, within AI+domain):
- data: dataset, benchmark
- predict: forecast, control, reinforcement learning
- experiment: closed loop, autonomous, robotic
- explain: causal, interpretability, symbolic
- model: uses signal_ratio = 1.0 (no keyword ratio)

signal_ratio(dim) = sum(term_counts for dim) / ai_recent (clamped to 0..1).

### Dimension score formula (0..100)
Let p=penetration, v=volume_norm, g=growth_norm, s=signal_ratio.
- model: 100 * (0.45*p + 0.35*v + 0.20*g)
- data: 100 * (0.40*p + 0.40*s + 0.20*g)
- predict: 100 * (0.35*p + 0.45*s + 0.20*g)
- experiment: 100 * (0.25*p + 0.55*s + 0.20*g)
- explain: 100 * (0.35*p + 0.45*s + 0.20*g)

### Evidence list
For each domain, `model` dimension includes top 12 AI+domain works
sorted by `cited_by_count` (OpenAlex). Evidence items store title, url,
year, citedBy, venue, and source.

## 4) Overall Score and Maturity Levels
Defined in `web/src/lib/progress/compute.ts`.
- Leaf overall score = mean of 5 dimension scores.
- Leaf overall confidence = mean of dimension confidences.
- Non-leaf nodes aggregate children by confidence-weighted mean.
- Maturity mapping:
  - 0: score < 10
  - 1: 10 <= score < 30
  - 2: 30 <= score < 55
  - 3: 55 <= score < 75
  - 4: score >= 75

## 5) LLM Auto Overrides (Optional)
`scripts/judge_progress_llm.py` proposes adjustments on top of OpenAlex baseline:
- Inputs: per-domain baseline scores + DB stats + top cited + most recent papers.
- Output JSON: per-dimension scores (0..100), confidence (0..1), note (<=200 chars).
- Intended to be conservative: follow baseline unless evidence is strong.

## 6) Discovery Layers (LLM, Science Domains)
`scripts/judge_discovery_layers_llm.py` classifies AI-driven scientific discoveries.

### Layer definitions (outer -> inner)
1) phenomena: new phenomena/patterns/observations (repeatable, but no stable law).
2) empirical: reusable empirical laws/statistical relations.
3) theory: testable mechanisms/theoretical models with falsifiable predictions.
4) principles: deeper unifying principles (compression/axiomatization/symmetry).

### Rules
- layerScores each in 0..1, can be multi-layer (not required to sum to 1).
- If paper is primarily tooling/model performance/datasets/benchmarks:
  isDiscovery=false and all layerScores = 0.
- Judgement must be based only on title+abstract.

### Sampling and aggregation
- For each domain, combine top cited + most recent papers from local DB.
- Optional window filter: `--since-days`.
- Paper weight = log1p(citations) * recency factor:
  - <=1y: 1.0
  - <=3y: 0.85
  - <=6y: 0.7
  - older: 0.55
- Domain layer score = weighted average of paper layerScores.

## 7) Formal Sciences Layers (LLM, Formal Domains)
`scripts/judge_formal_layers_llm.py` uses a separate four-layer scheme:
1) instances: instance solving / constructive examples.
2) conjectures: new conjectures / patterns / reusable heuristics (no proof).
3) proofs: provable or formally verified results.
4) foundations: new formal systems / unifying frameworks / meta-theorems.

Rules and aggregation mirror the discovery-layer logic, with the same
"isDiscovery=false => all zeros" rule for non-formal contributions.

## 8) Tooling & Autonomy (Heuristic Metrics)
`scripts/analyze_domain_extra_metrics.py` computes separate axes:
- Tooling keywords: dataset, benchmark, corpus, database, knowledge base,
  repository, open source, software, library, tool, framework, pipeline, platform, workflow, etc.
- Autonomy keywords: closed-loop, autonomous, self-driving, robotic,
  lab automation, automated experiment, high-throughput, active learning, etc.

Per-paper flags are derived from title+abstract regex hits.
Per-domain rate = hits / total papers in that domain (0..1).
Aggregated to higher nodes using weighted mean with weights = sqrt(domain paper count).

## 9) Daily Updates Classification
`scripts/update_daily_updates.py` processes `updates/YYYY-MM-DD*.md`.

LLM output schema:
```
{
  "summary": "<=40 chars",
  "highlights": ["3-6 items, <=60 chars each"],
  "dimensions": {"data":0,"model":0,"predict":0,"experiment":0,"explain":0},
  "tags": ["optional 3-8 short tags"],
  "confidence": 0.0-1.0
}
```
Rules:
- Dimension weights must sum to 100.
- If LLM unavailable, a heuristic keyword classifier assigns weights and normalizes to 100.

## 10) Method Tagging (AI Method Space)
`scripts/tag_ai_methods.py` assigns method tags to papers based on title/abstract/concepts.
Method tags and example patterns include:
- cnn: CNN/ResNet/U-Net
- gnn: graph neural / GCN / GraphSAGE
- transformer: transformer / attention / BERT / T5 / ViT
- llm: LLM / GPT / ChatGPT / prompting / RAG
- diffusion: diffusion / DDPM / score-based
- rl: reinforcement learning / actor-critic / Q-learning
- bayesian: Bayesian / GP / variational inference
- causal: causal inference / SCM / do-calculus
- symbolic: symbolic regression / program synthesis
- pinn: physics-informed NN
- neural_operator: neural operator / FNO / DeepONet
- hybrid: added if multiple families detected

Confidence thresholds:
- per-tag score derived from matches in concepts/title/abstract.
- tags stored only if score >= 0.65 (default).

## 11) Problem-Method Map (Opportunity Detection)
`scripts/analyze_problem_method_map.py`:
- Problem space = leaf domains (excluding `methods` branch).
- Method space = method tags in SQLite (from tag_ai_methods).
- Time window default: last 3 years.
- Matrix cell count = papers tagged with method AND linked to domain.

Blank spot formula:
expected = domain_total * method_total / total_papers
opportunity = (expected + 1) / (observed + 1)
Only report if expected >= 3 and opportunity > 1.25.

## 12) Top Papers (Last Year)
`scripts/analyze_top_papers_last_year.py` ranks papers within last 365 days:
- score = 0.7 * normalized log citations + 0.3 * recency
- recency = 1 - age_days/365 (clamped)
- future dates are ignored

## 13) Depth x Agency / Infrastructure
Computed in `web/src/app/page.tsx` (for visualization):
- Depth (0..100) from discovery layers:
  depth = 100 * (1*phenomena + 2*empirical + 3*theory + 4*principles) / 10
- If LLM layers missing, depthProxy = 0.7*explain + 0.2*model + 0.1*predict.
- Agency (0..100) = 0.6*autonomy + 0.3*experiment + 0.1*tooling.
- Infrastructure (0..100) = 0.4*data + 0.4*tooling + 0.2*adoption.
  adoption = log1p(ai_recent) normalized by max across leaves.

