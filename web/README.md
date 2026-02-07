# AI4Sci Progress Atlas (Web)

Next.js 前端：主页知识图谱 + 热力图、领域详情页雷达图、`/admin` 手动纠偏、`/api/progress` 数据接口。

## Dev

```bash
npm run dev
```

打开 `http://localhost:3000/`。

## Update Data (OpenAlex)

```bash
npm run update-data
```

会生成/更新 `data/base.json`（自动评分 + 证据列表）。

可选：只更新缺失/新增节点（更快）：

```bash
python3 ../scripts/update_progress_openalex.py --only-missing
```

## Daily Updates (LLM classify)

- 输入目录：`../updates/*.md`（文件名包含 `YYYY-MM-DD`）
- 生成：`npm run update-updates`
- 数据文件：`data/daily_updates.json` + `data/daily_updates.md`
- 页面：`/updates`

## Paper Catalog (from SQLite)

- 导出文件：`data/papers_catalog.json` + `data/papers_catalog.md`
- 浏览页面：`/papers`

## Auto Overrides (LLM, optional)

- `data/auto_overrides.json`：脚本生成的“机器建议纠偏”（合并优先级低于手动 overrides）
- 合并顺序：`base.json` → `auto_overrides.json` → `overrides.json`

## Discovery Layers (LLM, optional)

- `data/discovery_layers.json`：LLM 基于论文库抽样输出的四层发现深度（同心圆）
- `data/discovery_layers.md`：可读摘要（按领域列出各层证据论文）

## Problem ↔ Method (overview + blank spots)

- 数据文件：`data/problem_method_map.json` + `data/problem_method_map.md`
- 生成脚本：`python3 ../scripts/analyze_problem_method_map.py`
- 页面：`/problem-method`

## Depth × Agency (macro lens)

- 首页新增二维视图：`Depth × Agency Map`（y=认识论深度，x=科学代理程度，点大小≈论文量）
- 数据源：`data/discovery_layers.json`（Depth） + `data/domain_extra_metrics.json`（Tooling/Autonomy） + `data/base.json`（Experiment / volume）

## Manual Overrides

- 推荐：创建 `web/.env.local` 并写入 `ADMIN_TOKEN=...`
- 打开 `http://localhost:3000/admin` 覆盖分数（写入 `data/overrides.json`）

## Notes

- `/` 已强制动态渲染：更新 `data/base.json` 后无需重新 build 即可生效。

## Progress History (Milestones & Trends)

- 生成：`npm run update-history`（输出 `data/progress_history.json`）
- 页面：`/trends`
