import Link from "next/link";

import { ChartCard } from "@/components/ChartCard";
import { getProgressData } from "@/lib/progress/get.server";

export const dynamic = "force-dynamic";

export default function MethodologyPage() {
  const data = getProgressData();

  return (
    <div className="min-h-screen bg-[radial-gradient(1000px_600px_at_20%_10%,rgba(34,211,238,0.10),transparent_60%),radial-gradient(900px_600px_at_75%_20%,rgba(167,139,250,0.10),transparent_60%),linear-gradient(180deg,#05070d_0%,#040616_40%,#02030a_100%)] text-white">
      <header className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-xs text-white/50">
              <Link href="/" className="hover:text-white/80">
                Atlas
              </Link>{" "}
              / Methodology
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
              How Scores Are Computed
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/60">
              这个网站把“AI 统一人类知识”的宏观进展拆成跨学科知识树 × 五个科学活动维度，
              再从开放文献与公开信号中自动计算分数（并允许人工纠偏）。
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
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <ChartCard
              title="Five Dimensions"
              subtitle="每个领域都会给出五维分数（0–100）。"
            >
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {data.dimensions.map((d) => (
                  <div
                    key={d.key}
                    className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
                  >
                    <div className="text-sm font-semibold text-white/90">
                      {d.label}
                    </div>
                    <div className="mt-2 text-sm leading-6 text-white/60">
                      {d.description}
                    </div>
                  </div>
                ))}
              </div>
            </ChartCard>
          </div>
          <div className="lg:col-span-5">
            <ChartCard
              title="Maturity Levels (0–4)"
              subtitle="用“闭环成熟度”解释进度条。"
            >
              <ol className="space-y-3 text-sm leading-6 text-white/65">
                <li>
                  <span className="font-semibold text-white/85">0 None</span>：
                  几乎无 AI 参与或仅零散试验。
                </li>
                <li>
                  <span className="font-semibold text-white/85">1 Assist</span>：
                  AI 作为数据/工具辅助（清洗、检索、可视化、粗预测）。
                </li>
                <li>
                  <span className="font-semibold text-white/85">2 Competitive</span>：
                  在关键任务/基准上稳定可用或超过传统方法（但流程仍人主导）。
                </li>
                <li>
                  <span className="font-semibold text-white/85">3 Co‑Scientist</span>：
                  AI 能生成可检验假设、参与实验/仿真设计，并可复现验证。
                </li>
                <li>
                  <span className="font-semibold text-white/85">4 Closed‑Loop</span>：
                  形成可迁移的自驱动闭环（设问→实验/仿真→分析→更新理论），人类主要做目标与约束。
                </li>
              </ol>
            </ChartCard>
          </div>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Auto Signals"
            subtitle="当前实现：基于 OpenAlex 的文献交叉信号 + 关键词强度 + 增长率 + 置信度。"
          >
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-sm font-semibold text-white/90">Sources</div>
                <ul className="mt-2 list-disc pl-5 text-sm leading-6 text-white/65">
                  <li>OpenAlex concepts × works counts</li>
                  <li>Top-cited evidence list per domain</li>
                  <li>Dimension keyword signals (dataset/benchmark/closed-loop/causal…)</li>
                </ul>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <div className="text-sm font-semibold text-white/90">What “Score” Means</div>
                <p className="mt-2 text-sm leading-6 text-white/65">
                  分数是启发式聚合：渗透率（AI×领域交叉占比）+ 体量（近 5 年交叉论文量）
                  + 增速（近 12 个月 vs 前 12 个月）+ 维度信号强度（关键词占比），再映射到成熟度等级。
                </p>
              </div>
            </div>
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Discovery Layers (Concentric)"
            subtitle="外→内：现象→经验定律→理论→原理（仅用 LLM 从论文库判定）。"
          >
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-white/65">
              <p>
                同心圆展示的是“AI 帮助科学发现”的知识深度分层。数据默认来自
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  data/discovery_layers.json
                </code>
                ，由脚本
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/judge_discovery_layers_llm.py
                </code>
                从本地论文库抽样（title+abstract）并用大模型评估得到。
              </p>
              <p className="mt-3">
                时间窗由脚本参数 <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">--since-days</code>{" "}
                控制（例如 365 表示近一年），会写入 JSON 的 <code className="rounded bg-white/10 px-1.5 py-0.5 text-[12px]">window</code>{" "}
                字段供前端展示。
              </p>
              <p className="mt-3">未运行分层脚本的领域会显示为 0。</p>
            </div>
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Formal Sciences Layers (Separate)"
            subtitle="形式科学不适用“现象→原理”，改用独立四层：实例→猜想→证明→基础。"
          >
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-white/65">
              <p>
                对数学/逻辑/自动定理证明等形式科学，核心进展通常表现为“从实例求解到可证明的可迁移理论结构”，
                因此本站使用单独的四层同心图：{" "}
                <span className="font-semibold text-white/85">Instances</span>（实例求解/构造）→{" "}
                <span className="font-semibold text-white/85">Conjectures</span>（猜想/命题）→{" "}
                <span className="font-semibold text-white/85">Proofs</span>（证明/验证）→{" "}
                <span className="font-semibold text-white/85">Foundations</span>（基础/统一框架）。
              </p>
              <p className="mt-3">
                数据文件：
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  data/formal_layers.json
                </code>
                （以及同目录下的
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  data/formal_layers.md
                </code>
                方便直接查阅）。
              </p>
              <p className="mt-3">
                生成命令：
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/judge_formal_layers_llm.py
                </code>
              </p>
            </div>
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Separate Axes: Tooling & Autonomy"
            subtitle="用“外侧薄环/额外进度条”避免把“发现深度=全部进展”。"
          >
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-white/65">
              <p>
                很多领域可能在“发现深度”上暂时看起来为 0，但实际上已经在数据、工具链、基准、实验自动化等方面快速积累。
                因此本站把{" "}
                <span className="font-semibold text-white/85">Tooling</span>（数据/工具/基准基础设施）与{" "}
                <span className="font-semibold text-white/85">Autonomy</span>（闭环自治/自驱动实验）作为独立轴，
                通过关键词统计生成：
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  data/domain_extra_metrics.json
                </code>
                ，并显示在首页同心图外侧薄环与领域详情页。
              </p>
              <p className="mt-3">
                生成命令：
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/analyze_domain_extra_metrics.py
                </code>
              </p>
            </div>
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="3D Cube: Infrastructure / Adoption"
            subtitle="用第三条正交轴表达“数据/工具链/基准/渗透”强度（不是能力分）。"
          >
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-white/65">
              <p>
                首页 3D 图的 z 轴是{" "}
                <span className="font-semibold text-white/85">Infrastructure</span>（基础设施/渗透度），
                用来捕捉“该领域是否已经形成可复用的数据与工具链”，避免只看发现深度或能力分。
              </p>
              <p className="mt-3">
                当前实现（0–100）：Infrastructure ≈ 0.4×Data + 0.4×Tooling + 0.2×Adoption，其中 Adoption 由
                <span className="mx-1 font-semibold text-white/85">AI×领域交叉论文量</span>（近 5 年）做 log 归一化得到。
              </p>
            </div>
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Problem ↔ Method Map"
            subtitle="Bridging AI and Science 风格：问题空间 × 方法空间 + 空白区提示。"
          >
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-white/65">
              <p>
                “问题空间”用本站知识树的叶子子领域近似，“方法空间”用论文库中的 AI 方法类型标签近似（CNN/GNN/Transformer/LLM/…）。
                统计得到子领域×方法的交叉热力图，并给出“高期望但低覆盖”的空白区提示，便于发现机会区。
              </p>
              <p className="mt-3">
                生成命令：
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  python3 scripts/analyze_problem_method_map.py
                </code>
                ，页面：
                <Link href="/problem-method" className="mx-1 font-semibold text-cyan-200 hover:text-cyan-100">
                  /problem-method
                </Link>
              </p>
            </div>
          </ChartCard>
        </div>

        <div className="mt-5">
          <ChartCard
            title="Macro Lens: Depth × Agency"
            subtitle="用两条正交轴表达“助手→协同→超越”与“现象→原理”。"
          >
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-white/65">
              <p>
                为了从更宏观的科学哲学视角避免“单一指标误导”，本站额外提供一个二维视图：
                <span className="mx-1 font-semibold text-white/85">Epistemic Depth</span>
                （认识论深度：现象→经验定律→理论→原理）与
                <span className="mx-1 font-semibold text-white/85">Agency</span>
                （科学代理：助手→协同→自治/自驱动）。
              </p>
              <p className="mt-3">
                当前实现：Depth 来自 LLM 四层分级（
                <code className="mx-1 rounded bg-white/10 px-1.5 py-0.5 text-[12px]">
                  data/discovery_layers.json
                </code>
                ），Agency 由 Autonomy/Tooling（关键词统计）与 Experiment 维度（OpenAlex 信号）组合得到。
              </p>
              <p className="mt-3">
                首页图表：
                <Link href="/" className="mx-1 font-semibold text-cyan-200 hover:text-cyan-100">
                  Depth × Agency Map
                </Link>
              </p>
            </div>
          </ChartCard>
        </div>
      </main>
    </div>
  );
}
