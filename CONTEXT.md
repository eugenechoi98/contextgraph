# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 4E-B，SWE-bench Lite isolated checkout + localization smoke
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-08

## 当前目标

- 在不运行完整 SWE-bench benchmark 的前提下，验证单个或最多 3 个 SWE-bench Lite case 能否安全 checkout、独立建库、索引并做文件级 localization。
- 默认 `max_instances=1`，硬上限 `3`。
- Phase 4E-B 不创建 commit，除非 eugene 明确要求。

## 当前进度

- Phase 4E-A 已提交 checkpoint：`8ec3ac9 feat(eval): add SWE-bench Lite manifest loader`。
- 已新增 checkout manager：只支持 `owner/repo` 网络 opt-in 或 `file://` 本地 fixture remote。
- checkout 使用 `git init` + `git fetch --depth 1 origin <base_commit>` + detached checkout，不做 full clone fallback。
- 已新增 `cgstudio swebench-localize`，支持 dry-run、隔离 cache、隔离 SQLite DB、JSON / Markdown 报告。
- dry-run 不 clone、不建 DB、不 index、不 retrieve。
- 本地动态 Git fixture smoke 已覆盖 checkout、索引和 localization。

## 下一步

- 下一轮建议做官方单 instance 网络 smoke，前提是明确允许网络 checkout，并指定 cache / disk budget。
- 不建议下一轮直接进入 patch apply、Docker harness 或 target repo tests。

## 注意事项

- 仍只在 D 盘正式仓库工作。
- 不要修改 BM25、RRF、Token Budget、Graph traversal、parser、embedding、ContextPack schema。
- SWE-bench localization 使用 per-instance DB：`<cache_dir>\db\<safe_instance_id>.sqlite`。
- `HANDOFF_2026-06-08_Phase4B.md` 是未跟踪旧交接文档，本轮不处理。
