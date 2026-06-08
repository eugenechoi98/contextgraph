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
## 2026-06-08: Phase 4B.2 only adds graph diagnostics

`chunking_001` graph empty traversal is now evidence-backed as a seed-shape problem, not a missing-graph-data problem.

- The current six seeds are valid latest-scan entities.
- They are all BM25 general-lane `doc_section` entities rather than code entities from `chunker.py`.
- Those seeds only expose incoming `contains`.
- The current `general` task strategy only allows `calls` and `imports`.
- The current traversal only expands outgoing edges.

This means the real failure mode is the combination of seed type, edge filtering, and directionality. For Phase 4B.2 we only expose that state in diagnostics. We do not change traversal direction, task-strategy edge types, graph seed policy, BM25 scoring, RRF, or token budget.
## 2026-06-08: Graph expectation is a characterization label, not a scoring gate

Phase 4B.3 expands the first-party golden dataset and adds `graph_expectation` with three values:

- `required`
- `helpful`
- `none`

This label is used to analyze where graph participation is structurally valuable, but it does not directly alter:

- strict pass/fail
- Recall@K
- MRR
- critical hit rate
- `ContextPack` schema

The reason is that graph participation by itself does not prove necessity, especially when `graph_expectation=none` cases can still receive graph hits under the current seeded traversal design.
## 2026-06-08: Characterize graph value before changing retrieval behavior

The expanded dataset currently shows that graph-enabled configs improve `MRR` while leaving `Recall@5` flat, and all `required` graph cases participate successfully.

That means the next decision should not start from "force graph to help `chunking_001`". It should start from evidence:

- graph is already adding value on structurally connected tasks
- `chunking_001` is an outlier with a diagnosed seed-shape failure mode
- graph also participates in several `none` cases, so the open product question is selectivity, not mere participation

Therefore this phase stops at characterization and does not change BM25, graph traversal, edge types, RRF, token budget, or graph seed policy.
## 2026-06-08: Defer local nomic smoke when hardware safety is weak

Phase 4B.4 checks real semantic embeddings, but it does not authorize unsafe large-model downloads just to satisfy a preferred model name.

- `nomic-ai/nomic-embed-code` remains the intended code-specialized target.
- The local smoke is deferred when disk, RAM, GPU, or active runtime support are not comfortably safe for a `7B` model.
- In that case we prefer a repository-external-cache fallback smoke over risky local model churn.

This keeps the canonical workspace clean and avoids damaging the canonical DB or developer machine state for a non-essential experiment.
## 2026-06-08: Separate query and document encoding in the adapter

Official model usage for `nomic-ai/nomic-embed-code` distinguishes query encoding from code/document encoding. The adapter therefore now exposes separate methods:

- `embed_queries(...)`
- `embed_documents(...)`

Indexing only calls document encoding, while vector retrieval only calls query encoding.

The adapter only applies `prompt_name="query"` when the loaded model actually declares that prompt. This keeps the code compatible with fallback sentence-transformer models that do not expose Nomic-specific prompts.
## 2026-06-08: Lightweight semantic fallback can count as vector-quality-valid, but only with scoped wording

Deterministic embeddings still mean `vector_quality_valid=false`.

For Phase 4B.4, `sentence-transformers/all-MiniLM-L6-v2` is allowed to set `vector_quality_valid=true` only when:

- a real model was loaded successfully
- canonical embeddings were rebuilt successfully
- the full eval completed successfully

But the run must also record:

- `model_smoke_status`
- `embedding_device`
- `vector_quality_scope = "lightweight semantic fallback; not code-specialized"`

This allows the team to claim a real semantic baseline without overstating it as final code-retrieval quality.
