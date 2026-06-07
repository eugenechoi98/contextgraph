# DECISIONS

## 2026-06-07: MVP 先走本地单机主链

先把 `index -> retrieve -> trace -> eval` 做成可运行、可验证、可回放的本地能力，再考虑更重的部署和产品包装。

## 2026-06-07: SQLite + FTS5 作为默认离线底座

早期版本优先零外部依赖、可重建、可调试。`chunks_fts` 是 `chunks` 之上的派生层，不能反向污染主真源。

## 2026-06-07: EmbeddingProvider 先抽象，再接真实模型

索引主链不写死具体 embedding 模型。默认 deterministic provider 只服务于离线开发、CI 和 pipeline 校验。

## 2026-06-07: Vector / Graph 先独立验证，再进入 Hybrid Retrieval

先把 `vector-search`、`graph-search` 做到能单独定位问题，再通过 RRF 融合进 `retrieve_context`。

## 2026-06-08: D:\contextgraph-studio 是唯一 canonical workspace

- D 盘作为唯一正式工作区
- C 盘只作为迁移来源快照保留
- 后续测试、`index`、`eval`、`serve`、`mcp` 只允许从 D 盘执行

## 2026-06-08: canonical DB 优先“最新完整主链证据”

旧 D 库虽然历史记录更多，但缺少 `eval_runs`。canonical DB 采用迁入 D 盘的最新主库，以保证 `scan_runs / traces / eval_runs` 链路完整。

## 2026-06-08: 评测泄漏必须在 intake 层防住

如果 `eval/fixtures`、`eval/reports`、`.tmp*` 被索引进来，retrieval 指标会失真。排除规则必须放在 intake 层，而不是靠人工习惯规避。

## 2026-06-08: RRF 需要保留 richer metadata

同一 chunk 同时来自 BM25 和 graph 时，融合层不能只合分数，还要保住 `graph_distance / path` 这类解释信息。

## 2026-06-08: deterministic embedding 只验证链路，不代表语义质量

`vector_quality_valid=false` 是刻意设计，用来区分“向量链路跑通”和“语义效果可信”这两件不同的事。

## 2026-06-08: Eval ablation 必须区分 requested / executed / participating

只记录 `ContextPack.retrieval_strategy` 不足以解释 ablation 是否真的进入 retrieval pipeline。Phase 4B.0 起，eval case result 额外记录：

- `requested_routes`
- `executed_routes`
- `participating_routes`
- `effective_flags`
- `route_diagnostics`

这样可以区分路由是被 ablation 关闭、已执行但无 seed、已执行但空 traversal、缺 embeddings，还是确实产生命中并参与融合。

## 2026-06-08: chunking_001 本轮不做 Code Seed Reserve

`chunking_001` 的关键问题不是代码 seed 已进前排却被 seed limit 挤掉，而是 `contextgraph_studio/services/chunker.py` 连 BM25 top 30 都没进，首次出现于 rank 172。当前应先把它视为候选召回问题，而不是 graph seed 配额问题。

## 2026-06-08: 用 Source-Code Candidate Lane 先补候选召回，不改 RRF / Graph / Token Budget

Phase 4B.1 的最小实验选择是：

- 保留原始 BM25 general lane
- 增加一个 `category=source_code` 的 BM25 lane
- 只在 source-code lane 上启用轻量 lexical expansion
- stable merge + dedupe 候选
- 不改公共 `ContextPack` schema
- 不改 RRF 公式、graph seed limit、token budget、required/supporting 语义

这个决策的原因是：`chunking_001` 的 primary 问题已经被证据化为 candidate recall，而不是融合层或 graph 层。
