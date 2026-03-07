# AI4Sci Progress Atlas

一个“可自动 + 可手动纠偏”的 AI for Science 进展网站：用跨学科知识树 + 五维雷达（Data / Modeling / Prediction & Control / Experiment / Explanation）来可视化“相关→因果→机制→统一→闭环探索”的宏观进度。

额外宏观镜头（避免单一指标误导）：
- **Discovery depth**：现象→经验定律→理论→原理（LLM 判定）
- **Agency**：助手→协同→自治（Tooling/Autonomy + Experiment 信号）
- 首页新增 `Depth × Agency Map`（y=深度，x=代理程度，点大小≈AI×领域交叉论文量）

## 运行（本地）

```bash
cd web
npm install
npm run dev
```

打开 `http://localhost:3000/`。

## 自动更新数据（OpenAlex）

```bash
python3 scripts/update_progress_openalex.py
# 或
cd web && npm run update-data
```

会更新 `web/data/base.json`（自动评分 + 证据列表）。

可选：只更新新增/缺失节点（更快）：

```bash
python3 scripts/update_progress_openalex.py --only-missing
# 也可以强制包含某些节点（比如修正过 concept 的 physics_hep）
python3 scripts/update_progress_openalex.py --only-missing --include physics_hep
```

说明：`openalex.concept.id`（`C123...`）会被优先使用，避免概念搜索歧义。

## 一键更新（推荐）

把「OpenAlex 自动评分」+「论文库同步」+「期刊/会议补抓」+「方法标签」+「各类可视化数据文件」串起来：

```bash
python3 scripts/update_all.py --years 3
# 或
cd web && npm run update-all
```

补抓默认读取：
- `scripts/ai4sci_sources.txt`（重要期刊 source 清单）
- `scripts/ai4sci_top_journals.txt`（顶刊/旗舰期刊 source pack）
- `scripts/ai4sci_ai_keywords.txt`（AI 关键词）
- `scripts/ai4sci_conference_keywords.txt`（会议兜底关键词，如 UAI/ISMB）

此外还会跑一层直连增量源：
- `scripts/ai4sci_incremental_sources.json`（arXiv + RSS/TOC 源配置）
- `scripts/ai4sci_incremental_ai_keywords.txt`（增量抓取的 AI 关键词）
- 输出：`web/data/incremental_sources.json` + `web/data/incremental_sources.md`

可通过 `--skip-supplement` 跳过补抓。

## 每日更新（LLM 分类 → 可视化）

把每天的更新写成一个文件放进 `updates/`（文件名需包含 `YYYY-MM-DD`），例如：`updates/2025-12-22.md`。
也支持从 `web/data/papers_catalog.json` 自动生成“当天新论文摘要”条目（适合无人值守日更）。

然后运行：

```bash
python3 scripts/update_daily_updates.py
python3 scripts/update_daily_updates.py --auto-from-catalog
# 或
cd web && npm run update-updates
```

会生成：
- `web/data/daily_updates.json`
- `web/data/daily_updates.md`

网站页面：`http://localhost:3000/updates`

也可以纳入一键更新（可选禁用 LLM，走启发式分类）：

```bash
python3 scripts/update_all.py --daily-updates
python3 scripts/update_all.py --daily-updates --daily-updates-no-llm
python3 scripts/update_all.py --daily-updates --daily-updates-no-catalog
```

## 进展历史（里程碑/趋势）

生成“进展快照”的时间序列文件：`web/data/progress_history.json`，用于展示最近变化与里程碑（maturity 阈值）预测。

```bash
python3 scripts/update_progress_history.py
# 或者一键更新（已包含该步骤）
python3 scripts/update_all.py --openalex-full
```

网站页面：`http://localhost:3000/trends`

## 构建论文库（AI4Sci：AI × 领域交叉）

用 OpenAlex 抓取并落库（SQLite），保存 `title + abstract` 等字段，默认写入 `data/papers.sqlite`：

```bash
python3 scripts/ingest_ai4sci_openalex.py --years 5
# 或限制时间窗/数量
python3 scripts/ingest_ai4sci_openalex.py --from-date 2024-01-01 --max-works 2000
```

说明：
- OpenAlex **包含 arXiv**（脚本会尽量提取 `arxiv_id` 并写入库）
- 只收“领域概念 ∩ AI 概念(ML/AI/DL)”的论文，避免把纯领域论文全量灌进来
- 每次 ingest 会同步保存 OpenAlex 的 `concepts`（用于后续细分领域 / 方法类型标签）
- 每次 ingest 会自动导出可浏览目录：`web/data/papers_catalog.json` + `web/data/papers_catalog.md`，并可在网站打开 `http://localhost:3000/papers`

## 补抓 AI4Sci 论文（关键词 / 期刊）

OpenAlex 的 concept 标注可能漏掉 AI 标签，可用关键词或期刊做补抓，再用领域 concept 自动映射到叶子节点：

```bash
python3 scripts/ingest_ai4sci_openalex_supplement.py \
  --keywords "Uncertainty in Artificial Intelligence,Intelligent Systems for Molecular Biology" \
  --sources "Nature,Science" \
  --ai-keywords "machine learning,deep learning,neural network,transformer" \
  --years 5
```

提示：
- 支持 `--keywords-file` / `--sources-file` / `--ai-keywords-file`（每行一个；`--sources-file` 可重复传入多份 pack）
- 推荐：期刊/主流会议放 `--sources-file`，难解析会议放 `--keywords-file` 兜底
- 例如：`--sources-file scripts/ai4sci_sources.txt --sources-file scripts/ai4sci_top_journals.txt`
- 默认会更新 `web/data/papers_catalog.json`（如需跳过可加 `--no-export`）

## 直连增量源（arXiv + RSS / Journal TOC）

这层用于缩短上游延迟，不等 OpenAlex 补齐再看新内容。

```bash
python3 scripts/ingest_incremental_sources.py
# 控制窗口 / 每个源的抓取量
python3 scripts/ingest_incremental_sources.py --lookback-hours 336 --max-items-per-source 12
```

默认行为：
- 抓取 `scripts/ai4sci_incremental_sources.json` 里的 arXiv 分类与顶刊 RSS/TOC
- 用 `scripts/ai4sci_incremental_ai_keywords.txt` 做 AI 相关过滤
- 命中的条目直接落到 `data/papers.sqlite`
- 自动导出 `web/data/papers_catalog.json`
- 额外生成 `web/data/incremental_sources.json`，供 `/monitor` 和 `/first-principles` 使用

说明：
- 这是“直连源”，所以比 OpenAlex 更接近小时级
- 领域映射目前是 best-effort（基于领域别名和 source hints），允许少量新论文先以“未映射领域”进入 catalog

## 给论文打“AI 方法类型”标签（CNN / Transformer / LLM …）

用规则/关键词（可结合 OpenAlex concepts）给每篇论文写入 `paper_tags`（`tag_type=method`），网站 `/papers` 会出现 Method 下拉筛选：

```bash
python3 scripts/tag_ai_methods.py --only-missing
python3 scripts/export_papers_catalog.py
```

## LLM 自动纠偏（OpenAI / Gemini / DeepSeek / Grok）

可选：用大模型基于论文库给每个叶子领域输出五维分数建议，写入 `web/data/auto_overrides.json`（合并顺序：`base.json` → `auto_overrides.json` → `overrides.json`）。

1) 配置环境变量（推荐：复制 `.env.example` 为 `.env` 并填入密钥；不要提交）  
2) 运行：

```bash
python3 scripts/judge_progress_llm.py
```

## LLM 四层“发现深度”（同心圆）

同心圆的四层（现象→经验定律→理论→原理）可用大模型从论文库抽样评估得到，输出到：
- `web/data/discovery_layers.json`
- `web/data/discovery_layers.md`（方便直接查阅）

运行：

```bash
python3 scripts/judge_discovery_layers_llm.py --papers 10
```

常用选项（推荐用于“近一年”刷新）：

```bash
# 近 365 天窗口，每个领域抽样 20 篇；支持中断保护（每个领域写一次 JSON）
python3 scripts/judge_discovery_layers_llm.py --provider gemini --since-days 365 --papers 20 --flush-each

# 只补齐缺失领域（用于分批跑完所有领域）
python3 scripts/judge_discovery_layers_llm.py --provider gemini --since-days 365 --papers 20 --only-missing --max-domains 20 --order-by ai_recent --flush-each
```

注：
- Gemini 支持 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`；默认模型为 `gemini-2.5-flash`（不同 key 可用模型可能不同）。

## Formal Sciences 四层（单独同心圆）

形式科学（数学/逻辑/自动定理证明等）不适用“现象→原理”，本站单独使用四层：
实例 → 猜想/命题 → 证明/验证 → 基础/统一框架。

输出：
- `web/data/formal_layers.json`
- `web/data/formal_layers.md`

运行：

```bash
python3 scripts/judge_formal_layers_llm.py --provider gemini --since-days 365 --papers 20
```

## “问题空间 ↔ 方法空间”总览（Bridging AI and Science 风格）

用本地论文库（AI4Sci 交叉论文）统计：`leaf domain × AI method tags` 的热力图，并给出“空白区提示”（高期望但低覆盖）。

生成数据：

```bash
python3 scripts/analyze_problem_method_map.py
```

输出到：
- `web/data/problem_method_map.json`
- `web/data/problem_method_map.md`

网站页面：`http://localhost:3000/problem-method`

## 扩展领域/子领域（taxonomy）

编辑并运行：

```bash
python3 scripts/expand_taxonomy.py
python3 scripts/update_progress_openalex.py --only-missing
```

目前已新增：`Engineering & Technology`、`Formal Sciences`，并补充了物理天文方向、医学影像/临床试验、环境（冰冻圈/污染/土壤）等子领域。

## OpenAlex 信号逻辑（简述）

`scripts/update_progress_openalex.py` 以每个领域的 OpenAlex concept 为过滤条件，统计近 5 年：
- 领域总论文数 vs（领域 ∩ Machine learning）论文数 → 渗透率
- 近一年 vs 前一年 → 增长
- 结合关键词检索（dataset/benchmark、forecast/control、closed-loop/robotic、causal/symbolic 等）→ 维度信号
- 抽取高被引论文作为 evidence

## 手动更新/纠偏（Admin）

- 可选：设置管理口令（推荐）
  - 在 `web/.env.local` 写入：`ADMIN_TOKEN=your_token`
- 打开 `http://localhost:3000/admin`
  - 覆盖某节点的 overall 或某个维度 score，并写 note
  - 结果写入 `web/data/overrides.json`（可回滚/可版本化）

## 数据文件

- `web/data/base.json`：自动生成的“基础快照”（来源/时间窗在 `meta` 字段）
- `web/data/overrides.json`：人工覆盖（用于修正偏差、补充里程碑）

## 定时任务（建议）

推荐拆成两层：

- 小时级轻刷新：
  - `python3 scripts/run_monitor_cycle.py --mode fast --no-llm`
  - 用于刷新 `daily_updates / progress_history / first_principles_lens / monitor_status`
- 每日全量刷新：
  - `python3 scripts/run_monitor_cycle.py --mode daily-full`
  - 内部会跑完整 `update_all`，并产出 `web/data/monitor_status.json`

网站新增页面：
- `/first-principles`：第一性原理透镜
- `/monitor`：运行状态 / 数据新鲜度 / watchlist

GitHub Actions 示例见 `.github/workflows/daily-update.yml`。

本地 Mac 可直接用 `launchd` 模板：
- `ops/launchd/README.md`
- `ops/launchd/com.ai4sci.monitor.fast.plist`
- `ops/launchd/com.ai4sci.monitor.daily.plist`
