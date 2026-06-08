# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 4E-C.3，Index Reuse Performance Audit + Evidence-gated Minimal Optimization
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前 SWE-bench cache：`D:\contextgraph-swebench-cache`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-08

## 当前目标

- 只处理官方 Astropy 单实例的 index reuse 性能问题。
- 不修改 retrieval、FTS normalizer、BM25、Graph、RRF、Token Budget、parser 或 embedding。

## 当前进度

- Phase 4E-C.2 已提交 checkpoint：`1fcb485 fix(retrieval): normalize FTS queries and rank fallback results`。
- 已确认 `bm25_only reused_index=false` 是 runner config 级字段，不代表同一实例重复 index。
- baseline profile：unchanged snapshot index `1046594 ms`，最慢阶段是 per-file relation copy。
- 已实施最小优化：unchanged snapshot 下 relations 改为一次读取上一成功 scan 并批量复制。
- 优化后 profile：unchanged snapshot index `180323 ms`，降幅约 `82.8%`。
- 官方 Astropy localization smoke 仍通过：`separable.py` rank 1，Recall@1=1，MRR=1，Graph hits=4。
- 正式分析文档：`eval/analysis/index_reuse_performance_profile.md`。

## 下一步

- 下一轮建议单独审计剩余的 relation bulk insert、file/entity/chunk copy 和 FTS sync 性能。

## 注意事项

- 仍只在 D 盘正式仓库工作。
- 不要修改 BM25、RRF、Token Budget、Graph traversal、parser、embedding、ContextPack schema。
- 本轮未运行 Docker、patch、目标仓库 tests，也未创建 Phase 4E-C.3 commit。
- 不要自动清理 `D:\contextgraph-swebench-cache`，除非 eugene 明确要求。
- `HANDOFF_2026-06-08_Phase4B.md` 是未跟踪旧交接文档，本轮不处理。
