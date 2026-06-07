# DECISIONS

## 2026-06-07：MVP 先走单机单体主链

先把 `index -> retrieve -> trace -> eval` 做成可运行、可验证、可回放的本地能力，再考虑更重的部署和产品包装。

## 2026-06-07：SQLite + FTS5 作为默认离线底座

早期版本优先零外部依赖、可重建、可调试。`chunks_fts` 是 `chunks` 之上的派生层，不反向污染主真源。

## 2026-06-07：EmbeddingProvider 先抽象，再接真实模型

索引主链不写死具体 embedding 模型。默认 deterministic provider 只服务于离线开发、CI 和 pipeline 校验。

## 2026-06-07：Vector / Graph 先独立验证，再进入 Hybrid Retrieval

先把 `vector-search`、`graph-search` 做到能单独定位问题，再通过 RRF 融合进 `retrieve_context`。

## 2026-06-08：D:\contextgraph-studio 恢复为唯一 canonical workspace

C 盘目录是实际开发产生的最新快照，但不是正式仓库。最终决策是：
- D 盘作为唯一正式工作区
- C 盘只作为迁移来源快照保留
- 后续测试、index、eval、serve、mcp 只允许从 D 盘执行

## 2026-06-08：数据库以“最新完整主链证据”优先，而不是“历史记录最多”优先

旧 D 库虽然有更多历史 repo / relation / embedding 数据，但缺少 `eval_runs`，而 C 快照主库包含更晚的 `scan_runs / traces / eval_runs`。因此 canonical DB 选择迁入 C 的主数据库，再在 D 盘继续运行。

## 2026-06-08：评测污染必须在 intake 层防住

如果 `eval/fixtures`、`eval/reports`、`.tmp*` 被索引进去，retrieval 指标会失真。所以排除规则必须放在 intake 层，而不是靠人工习惯规避。

## 2026-06-08：RRF 需要保留 richer metadata，而不只是合分

同一个 chunk 同时来自 BM25 和 graph 时，如果只保留先到的 BM25 元数据，会丢失 `graph_distance / path`，导致 `graph_paths` 消失。融合层必须合并 richer metadata，而不只合并分数。

## 2026-06-08：deterministic embedding 的报告必须明确标记为非语义有效

`vector_quality_valid=false` 是刻意设计，用来区分“向量链路跑通”和“语义效果可信”两件不同的事。