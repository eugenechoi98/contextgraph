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

## 2026-06-08: Phase 4E-B uses isolated SWE-bench checkout and DB state

SWE-bench case localization can touch external repos and create many index records, so it must not write into the canonical workspace DB.

This phase uses a separate cache root, per-instance SQLite DB files, an explicit disk-free gate, and no-network-by-default checkout. The checkout path only supports a GitHub `owner/repo` slug when network is explicitly allowed, or a `file://` local fixture remote for tests.

The runner only performs localization smoke. It does not apply patches, run target repo tests, run Docker, change retrieval algorithms, change graph traversal, or modify the public `ContextPack` schema.

## 2026-06-08: Phase 4E-C keeps official smoke dependency-light

The official single-instance smoke needed Hugging Face data, but the local venv did not have the optional `datasets` package installed and this phase should not install dependencies. The loader therefore falls back to the official Hugging Face datasets-server rows API.

The official Astropy checkout also exposed duplicate stable `relations.id` inserts during indexing. The fix is limited to ignoring duplicate relation inserts and counting only rows actually inserted. This prevents index failure without adding relation types, changing graph traversal, or changing retrieval ranking.

## 2026-06-08: Phase 4E-C.1 separates indexing from retrieval configs

`bm25_only` and `bm25_graph` use the same indexed snapshot. The localization runner now checks out and indexes once per instance, then performs one independent retrieval per config. This removes duplicate indexing without changing retrieval semantics.

Parse errors now distinguish current parsing, reused-file errors, and total snapshot errors. Reused errors are restored only when path and content hash match, so snapshot reports stay honest without reparsing unchanged files.

The Astropy miss is recorded but not fixed in this phase because its direct cause is FTS query construction and fallback ordering, which is retrieval behavior outside the authorized infrastructure-only scope.

## 2026-06-08: Phase 4E-C.2 normalizes FTS queries before MATCH

Dotted natural-language tokens should not be passed into SQLite FTS5 as syntax. The retrieval layer now converts user text into safe tokens and builds a quoted OR query.

Fallback remains only for exceptional no-FTS cases, but it now ranks by deterministic lexical overlap across path, symbol, and chunk text. This fixes the official Astropy miss without changing BM25 weights, RRF, Graph, Token Budget, parser behavior, embeddings, or query expansion.

The index reuse performance problem remains deferred because it is a separate indexing efficiency issue, not the retrieval correctness bug being closed here.
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
## 2026-06-08: Put model-specific query behavior behind adapter profiles

Phase 4B.5 needs to support three distinct local behaviors:

- MiniLM: no special query prompt or prefix
- CodeRankEmbed: fixed query prefix plus explicit `trust_remote_code`
- nomic-embed-code: `prompt_name="query"` on the query side only

We do not want those rules scattered through indexing, retrieval, or eval code. The adapter therefore owns a small profile map that centralizes:

- query prefix
- query prompt name
- document prompt name
- pinned revision
- trust requirement
- quality scope
- whether the model is code-specialized
## 2026-06-08: CodeRankEmbed must be pinned and explicitly trusted

Because `nomic-ai/CodeRankEmbed` requires `trust_remote_code=True`, Phase 4B.5 treats that as an explicit security gate:

- pin the revision
- review the custom Python files
- keep cache outside the repo
- default `embedding_trust_remote_code=false`
- require an explicit opt-in before loading the model

This is stricter than the prior adapter behavior, which was too permissive for custom-code models.
## 2026-06-08: Revision changes must invalidate embedding reuse

Changing only the model revision is enough to change vector semantics, even when the model name and dimension stay the same.

Phase 4B.5 therefore extends the embedding fingerprint to include revision so that:

- old vectors are not silently reused across model revisions
- local rebuilds stay auditable
- MiniLM and CodeRankEmbed historical vectors remain cleanly separated
## 2026-06-08: Adopt CodeRankEmbed as the local MVP code-specialized baseline

On the current repo state and the same 13-case golden dataset:

- deterministic remains a non-semantic pipeline baseline
- MiniLM remains a useful fallback
- CodeRankEmbed outperforms MiniLM on `bm25_vector` MRR and Recall@5 and does not introduce observed case regressions

So the local recommendation now becomes:

- keep `nomic-ai/nomic-embed-code` as the long-term intended target
- use `nomic-ai/CodeRankEmbed` as the current local MVP code-specialized baseline

## 2026-06-08: Keep default startup in no-model mode

Even after validating local embeddings, the default project behavior stays:

- `VECTOR_INDEX_ENABLED=false`
- `HYBRID_VECTOR_ENABLED=false`

Reason:

- first-time users should be able to run BM25 + Graph without waiting for a model download
- CodeRankEmbed requires explicit `trust_remote_code=true`
- the recommended local semantic baseline should be opt-in, not silently activated

## 2026-06-08: Final local model policy for Phase 4B

Phase 4B closes with four clearly separated local states:

- default no-model mode: safe startup, no download, BM25 + Graph only
- CodeRankEmbed: recommended local code-specialized baseline
- MiniLM: lightweight fallback when users need a smaller semantic option
- nomic-embed-code: deferred high-resource target, not validated on this workstation

This avoids mixing "recommended now", "fallback", and "future target" into one ambiguous embedding story.

## 2026-06-08: Index CLI should expose lightweight vector observability

When vector indexing is enabled, `cgstudio index .` should report:

- whether vector indexing is enabled
- which provider/model/revision produced vectors
- vector dimension
- how many embeddings were reused versus freshly generated

This is enough to debug local embedding state without changing retrieval logic or expanding `ContextPack` schema.

## 2026-06-08: Phase 4C uses official Tree-sitter wheels only

For the first TypeScript / JavaScript parser loop, the project now depends on:

- `tree-sitter`
- `tree-sitter-typescript`
- `tree-sitter-javascript`

This phase does not add a Node.js build step, local grammar compilation, or a large multi-language pack.

## 2026-06-08: Keep TS/JS parsing inside the existing pipeline

The new TS/JS parser must feed the same indexing and retrieval pipeline as Python:

- same `ParseResult`
- same `EntityRecord`
- same `RelationRecord`
- same SQLite `entities / relations / chunks`
- same `ContextPack` schema

This keeps TS/JS support as an extension of the current MVP rather than a second indexing system.

## 2026-06-08: Route extraction stays narrow and explicit

Phase 4C only recognizes clear, static Express-like route registrations such as:

- `app.get("/users", listUsers)`
- `router.post("/login", loginHandler)`

It intentionally skips dynamic paths, chained runtime builders, and framework-specific magic.

## 2026-06-08: Exclude local test fixtures from canonical workspace indexing

The canonical repo now excludes `tests/fixtures` during normal workspace indexing.

Reason:

- fixture repos are useful as standalone parser smoke targets
- fixture syntax-error files should not pollute the canonical repo scan
- indexing `tests/fixtures/sample_ts_repo` directly still works because the fixture becomes the repo root in that mode

## 2026-06-08: Phase 4D keeps structured parsing intentionally shallow

For SQL and config files, this phase only aims to get stable structured nodes into the existing index.

That means:

- SQL stops at `db_table`, `db_view`, and `db_index`
- config stops at `config_key`
- cross-file semantics such as `uses_table` and `configures` are intentionally deferred

## 2026-06-08: Sensitive config values must not enter chunks or retrieval output

This phase uses a simple key-name rule instead of a full secret scanner.

If a config key path contains markers such as:

- `password`
- `secret`
- `token`
- `api_key`
- `private_key`
- `credential`

then the raw value is masked and does not get written into structured chunk text.

## 2026-06-08: Config arrays use one stable notation

The current array policy is intentionally simple:

- keep the parent key
- emit a representative `[]` node
- continue nested object keys using paths such as `servers[].host`

This keeps config retrieval understandable without exploding chunk count.

## 2026-06-08: Database and configuration tasks use structured BM25 lanes

Phase 4D.1 makes `database` and `configuration` real planner strategies.

The retrieval change is deliberately narrow:

- `database` can run a bounded `schema` BM25 candidate lane
- `configuration` can run a bounded `config` BM25 candidate lane
- the existing general BM25 lane stays in place
- source-code lane behavior is preserved

This gives SQL and config chunks a fair chance to enter the candidate pool without changing BM25 scoring, RRF, token budget, graph traversal, or `ContextPack`.

## 2026-06-08: Structured eval stays separate from canonical golden eval

The structured SQL/config fixture uses its own dataset:

- `eval/fixtures/structured_golden.json`

Reason:

- the canonical golden dataset targets the canonical repo
- the structured fixture is a standalone parser/retrieval smoke repo
- mixing both in one default dataset would make eval runs depend on which repos happened to be indexed in the local DB

## 2026-06-08: Defer structured cross-file edges until a real retrieval gap appears

Phase 4D.2 audited potential structured graph edges before materializing them.

Result:

- `uses_table` is detectable with simple static rules in the fixture
- `configures` is also detectable, but has more ambiguity from repeated keys and natural-language matches
- current structured retrieval already returns both the structured file and the consumer source file

Decision:

- do not implement `uses_table` yet
- do not implement `configures` yet
- keep the read-only diagnostics and audit report as evidence for a later round

Reason:

- a new graph edge should solve a real retrieval gap, not just add graph activity
- adding an edge now would not improve the measured structured fixture eval

## 2026-06-08: SWE-bench Lite starts as a manifest layer, not a harness

Phase 4E-A adds SWE-bench Lite intake only.

Decision:

- support local JSON / JSONL first
- support Hugging Face only behind explicit `allow_network`
- generate changed-file ground truth manifests
- do not clone repositories
- do not checkout commits
- do not run Docker
- do not run retrieval benchmarks yet

Reason:

- the project first needs trustworthy external ground truth extraction
- running the full SWE-bench harness is a separate, higher-cost phase
