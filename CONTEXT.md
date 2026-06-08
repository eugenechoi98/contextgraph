# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 4E-C，官方 SWE-bench Lite 单实例网络 checkout + localization smoke
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前 SWE-bench cache：`D:\contextgraph-swebench-cache`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-08

## 当前目标

- 只验证 1 个官方 SWE-bench Lite 实例。
- 显式联网读取 HF 数据并从 GitHub 浅 fetch 指定 `base_commit`。
- 使用隔离 SQLite DB 做 index + localization，不写 canonical DB。

## 当前进度

- Phase 4E-B 已提交 checkpoint：`426628d feat(eval): add isolated SWE-bench localization runner`。
- 官方实例：`astropy__astropy-12907`，repo=`astropy/astropy`，base_commit=`d16bfe05a744909de4b27f5875fe0d4ed41ce607`。
- manifest 保存于：`D:\contextgraph-swebench-cache\manifests\official_single_instance.json`，不进入 Git。
- dry-run 已通过：不 fetch、不建 DB、不 index、不 retrieve。
- shallow checkout 已成功，未使用 full clone fallback。
- 第一次官方索引暴露重复 `relations.id` 问题，已做最小去重修复并新增回归测试。
- 修复后官方单实例 index + retrieve 跑通，报告在 `D:\contextgraph-swebench-cache\reports\swebench_localization_1780917565.json`。
- 本次 localization 未命中 critical file：`astropy/modeling/separable.py`，Graph 未产生 hit。
- canonical DB SHA256 前后完全一致：`75F9FE908AD4D7491F9A82EA31CFBB8B9B2A2D94C8E6ECCDBF2762E976D9B174`。
- 最新全量测试：`140 passed, 1 warning`。

## 下一步

- 下一轮建议只做 miss 诊断，不直接改算法。
- 优先检查 query lexical mismatch、candidate recall、Graph seed/edge coverage，仍不要进入 patch apply、Docker、目标仓库测试或 300-case benchmark。

## 注意事项

- 仍只在 D 盘正式仓库工作。
- 不要修改 BM25、RRF、Token Budget、Graph traversal、parser、embedding、ContextPack schema。
- 本轮未下载 embedding，未安装目标 repo 依赖，未执行目标 repo 脚本，未运行 Docker / patch / tests。
- 不要自动清理 `D:\contextgraph-swebench-cache`，除非 eugene 明确要求。
- `HANDOFF_2026-06-08_Phase4B.md` 是未跟踪旧交接文档，本轮不处理。
