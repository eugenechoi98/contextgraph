# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 4E-D，3 个官方 SWE-bench Lite 实例小样本 Localization Report
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前 SWE-bench cache：`D:\contextgraph-swebench-cache`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-08

## 当前目标

- 用 3 个官方 SWE-bench Lite 实例做隔离 localization 小样本报告。
- 不修改 retrieval、FTS normalizer、BM25、Graph、RRF、Token Budget、parser 或 embedding。

## 当前进度

- Phase 4E-C.3 已提交 checkpoint：`03bfd4f perf(index): bulk copy reused snapshot relations`。
- 3 实例 manifest 已生成在仓库外：`D:\contextgraph-swebench-cache\manifests\official_three_instances.json`。
- localization 原始报告在仓库外：`D:\contextgraph-swebench-cache\reports\swebench_localization_1780928519.json`。
- localization 汇总报告在仓库外：`D:\contextgraph-swebench-cache\reports\swebench_three_instance_summary_1780928519.json`。
- 仓库内人工分析文档：`eval/analysis/swebench_three_instance_localization_report.md`。
- 样本结果：Astropy rank 1，Matplotlib rank 2，Django miss。
- Django miss 分类：`D. parser coverage 不足`，目标文件有 chunk/entity，但模块级 settings assignment 没有被 chunk 成强可检索内容。
- canonical DB SHA256 前后一致：`75F9FE908AD4D7491F9A82EA31CFBB8B9B2A2D94C8E6ECCDBF2762E976D9B174`。

## 下一步

- 下一轮建议只做 Python module-level assignment parser/chunker 诊断，不直接改检索算法。

## 注意事项

- 仍只在 D 盘正式仓库工作。
- 不要修改 BM25、RRF、Token Budget、Graph traversal、parser、embedding、ContextPack schema。
- 本轮未运行 Docker、patch、目标仓库 tests，也未创建 Phase 4E-D commit。
- 不要提交仓库外 manifest、localization report、隔离 DB、checkout 或 cache。
- `HANDOFF_2026-06-08_Phase4B.md` 是未跟踪旧交接文档，本轮不处理。
