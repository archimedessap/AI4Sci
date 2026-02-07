# Daily updates

在 `updates/` 目录下新增一个以日期命名的 Markdown 文件（文件名需包含 `YYYY-MM-DD`），例如：

- `updates/2025-12-22.md`

内容可以是任意文本/要点列表。然后运行：

```bash
python3 scripts/update_daily_updates.py
# 自动汇总 papers_catalog.json 里的近期新论文（可与手工 updates 混合）
python3 scripts/update_daily_updates.py --auto-from-catalog
```

常用选项：
- `--force`：忽略缓存 hash，全量重跑
- `--no-llm`：不调用大模型，走启发式分类（用于离线/调试）
- `--auto-from-catalog`：从 `web/data/papers_catalog.json` 生成自动日更条目
- `--catalog-days`：自动条目回看天数（默认 7）

会生成：
- `web/data/daily_updates.json`
- `web/data/daily_updates.md`

网站页面：`/updates`
