# launchd Templates

这些模板用于本地 Mac 自动调度：

- `com.ai4sci.monitor.fast.plist`：小时级轻刷新
- `com.ai4sci.monitor.daily.plist`：每日全量刷新

## 使用

1. 复制模板到 `~/Library/LaunchAgents/`
2. 把文件里的 `__PROJECT_ROOT__` 替换成你的仓库绝对路径
3. 把 `__PYTHON_BIN__` 替换成你实际使用的 Python
4. 把 `__USER__` 替换成你的 macOS 用户名
5. 确认日志目录 `~/Library/Logs/AI4Sci/` 存在
6. 加载任务：

```bash
launchctl unload ~/Library/LaunchAgents/com.ai4sci.monitor.fast.plist 2>/dev/null || true
launchctl unload ~/Library/LaunchAgents/com.ai4sci.monitor.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ai4sci.monitor.fast.plist
launchctl load ~/Library/LaunchAgents/com.ai4sci.monitor.daily.plist
```

## 建议

- `fast`：每小时 1 次，适合刷新 `daily_updates / progress_history / first_principles / monitor_status`
- `daily`：每天凌晨 1 次，适合跑全量 `update_all`

## 手动测试

```bash
cd __PROJECT_ROOT__
__PYTHON_BIN__ scripts/run_monitor_cycle.py --mode fast
__PYTHON_BIN__ scripts/run_monitor_cycle.py --mode daily-full
```
