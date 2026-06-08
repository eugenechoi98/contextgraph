# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 4E-C.1，官方单实例 miss diagnosis + runner efficiency audit
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前 SWE-bench cache：`D:\contextgraph-swebench-cache`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-08

## 当前目标

- 只诊断 `astropy__astropy-12907` 的 retrieval miss、Graph 无贡献、runner 重复索引和 parse error 统计口径。
- 不修改 BM25、Graph、RRF、Token Budget、parser 或 query expansion。

## 当前进度

- Phase 4E-C 已提交 checkpoint：`46263ad fix(eval): stabilize official SWE-bench localization smoke`。
- 官方实例：`astropy__astropy-12907`，repo=`astropy/astropy`，base_commit=`d16bfe05a744909de4b27f5875fe0d4ed41ce607`。
- manifest 保存于：`D:\contextgraph-swebench-cache\manifests\official_single_instance.json`，不进入 Git。
- dry-run 已通过：不 fetch、不建 DB、不 index、不 retrieve。
- shallow checkout 已成功，未使用 full clone fallback。
- miss 根因：完整 query 中的 dotted tokens 触发 FTS5 syntax error，随后进入无排序 lexical fallback；`separable.py` 不在 general/source-code top 100。
- Graph 的 6 个 seed 全是 `.circleci/config.yml` 的 `config_key`，最终 `edge_type_filtered`。
- runner 已改为单实例 checkout 一次、index 一次、每 config 分别 retrieve。
- parse stats 已拆为 current/reused/total snapshot，并按路径 + content hash 恢复旧口径遗漏的复用错误。
- 最终官方报告：`D:\contextgraph-swebench-cache\reports\swebench_localization_1780920792.json`。
- 正式诊断：`eval/analysis/astropy__astropy-12907_retrieval_miss_diagnostic.md`。
- canonical DB SHA256 前后完全一致：`75F9FE908AD4D7491F9A82EA31CFBB8B9B2A2D94C8E6ECCDBF2762E976D9B174`。
- 当前定向测试：`15 passed`；全量测试：`143 passed, 1 warning`。

## 下一步

- 下一轮建议单独评审 FTS dotted-token escaping 与 fallback ranking 方案，不在本轮直接实现。

## 注意事项

- 仍只在 D 盘正式仓库工作。
- 不要修改 BM25、RRF、Token Budget、Graph traversal、parser、embedding、ContextPack schema。
- 本轮未下载 embedding，未安装目标 repo 依赖，未执行目标 repo 脚本，未运行 Docker / patch / tests。
- 不要自动清理 `D:\contextgraph-swebench-cache`，除非 eugene 明确要求。
- `HANDOFF_2026-06-08_Phase4B.md` 是未跟踪旧交接文档，本轮不处理。
