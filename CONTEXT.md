# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 当前迁移来源快照：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`，仅保留，不再继续开发
- 当前阶段：完成工作区恢复、Phase 3 基线恢复、Phase 4A Eval runner 恢复验证
- 当前稳定主链：`index -> BM25 / optional Vector / optional Graph -> RRF -> ContextPack -> trace -> eval`
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`

## 2026-06-08 现状

- 已完成从 C 快照到 D 正式仓库的受控同步，未复制 `.venv`、`.git`、临时目录、数据库和 eval reports。
- 已在 `D:\contextgraph-backups\20260608_020740` 备份 D 盘同步前代码快照，并单独备份了 C / D 两边数据库。
- D 盘主数据库已切换为来自 C 快照的最新主库；原因是它包含更新的 `scan_runs / traces / eval_runs`，而旧 D 库缺少 `eval_runs`。
- D 盘 `.venv` 已重建；旧 `.venv` 的 `pyvenv.cfg` 指向 C 路径，已不再使用。
- D 盘 Git 已初始化；当前没有 commit，整个仓库处于未跟踪初始状态，这是预期的。
- `pytest --collect-only -q tests` 当前稳定收集 `59` 个测试。
- `pytest tests` 当前结果：`59 passed, 1 warning`。
- `cgstudio index .` 当前稳定 repo_id：`8bf02440-5d4e-5fa2-8916-a955c2c21fd2`。
- `cgstudio retrieve "verify token auth flow" --task-hint security_auth` 当前返回 `retrieval_strategy=["bm25", "graph"]`。
- `cgstudio eval --max-cases 5` 当前 `failed_case_count=0`，并生成最新 JSON / Markdown 报告。
- `vector_quality_valid=false` 仍是预期行为，因为当前 embedding provider 仍是 deterministic。
- Phase 4B.0 已补齐 eval ablation 诊断字段：`requested_routes / executed_routes / participating_routes / effective_flags / route_diagnostics`。
- 全量测试现为 `61 passed, 1 warning`，新增覆盖 `tests/test_eval_ablation_wiring.py`。
- Phase 4B.1 已接入最小 `source_code candidate lane`，并新增 `tests/test_bm25_candidate_lanes.py`。
- 当前全量测试结果：`67 passed, 1 warning`。

## 基线一致性说明

- 之前的 `38 passed` 来自 C 盘临时快照，不应再作为正式口径。
- 之前的 `51 passed` 来自较早的 D 盘阶段性状态；当前 canonical D 盘经过受控合并后，测试集合是 Phase 3B 与 Phase 4A 的并集，最终 collect-only 为 `59`。
- `repo_id` 从 `cf6b8d0a-...` 回到 `8bf02440-...` 的主要原因是：正式工作区已回到 D 盘，且 canonical DB 采用 D 盘正式仓库路径下的仓库记录；不是算法随机漂移。
- FastAPI 的 `@app.on_event("startup")` 已不存在；当前唯一 warning 来自 `starlette.testclient` 对 `httpx` 适配层的弃用提示，不来自项目代码。

## 注意事项

- `chunks` 仍是 source of truth；`chunks_fts`、`embeddings`、`relations`、`eval_runs` 都是派生或附属层。
- intake 当前默认排除 `.tmp*`、`tmp_pytest*`、`eval/fixtures`、`eval/reports`，避免评测泄题。
- `chunking_001` 在当前 eval 报告中仍有 miss；最新 code-seed 诊断表明 `chunker.py` 不在 BM25 top 30，首次出现于 rank 172，因此本轮不实施 Code Seed Reserve。
- `chunking_001` 已通过 `source_code candidate lane` 从 critical miss 变为 critical hit；但 graph 对该 case 仍是 `seed_count=6, hit_count=0, reason=empty_traversal`。
- `cgstudio mcp` 的真实协议可用性已由 `tests/test_mcp_stdio_integration.py` 通过验证；无 client 直接以关闭 stdin 启动时进程返回码为 1，不作为协议不可用结论。
## Phase 4B.2 Note

- `chunking_001` now stays a critical hit because candidate recall improved, but graph still does not participate for this case.
- The six graph seeds are valid latest-scan entities, but they are all BM25 general-lane `doc_section` entities.
- Those seeds each map to a chunk correctly, so this is not an entity-to-chunk mapping failure.
- Those seeds have no outgoing `calls` or `imports`; they only have incoming `contains`.
- Current `general` graph traversal is `outgoing_only` and only allows `calls` / `imports`, so the case is now diagnosed as `edge_type_filtered` instead of a generic `empty_traversal`.
- This round only adds internal graph diagnostics. It does not change BM25, RRF, graph weights, graph seed policy, task strategies, or traversal direction.

## Phase 4B.3 Note

- The first-party golden dataset is now stabilized at `13` active cases and carries a non-scoring `graph_expectation` label: `required`, `helpful`, or `none`.
- Latest full validation is `77 passed, 1 warning`.
- Latest full eval runs without `--max-cases` and keeps `failed_case_count=0`.
- Under graph-enabled configs, `graph_participation_rate=12/13`, `graph_required_case_participation_rate=4/4`, and the only observed non-participation reason is `edge_type_filtered` on `chunking_001`.
- `bm25_graph` improves `MRR` over `bm25_only` from `0.7538` to `0.8179` while `Recall@5` stays flat at `0.8077`, so graph currently looks more useful for ranking than for raw recall on this repo.
- `graph_expectation` is diagnostic only; it does not change strict retrieval metrics or `ContextPack` schema.
- `vector_quality_valid` remains `false`.

## Phase 4B.4 Note

- Local `nomic-ai/nomic-embed-code` smoke was deferred as unsafe on this workstation because the active environment has no CUDA device, the visible GPU budget is only `2 GB`, and the phase required a controlled D-drive cache budget.
- The embedding adapter now separates query encoding from document/code-chunk encoding.
- Query-side encoding uses query semantics only when the loaded sentence-transformer model actually exposes a `query` prompt.
- Indexed chunks continue to use document/code encoding without forcing the query prompt.
- Real semantic fallback smoke succeeded with `sentence-transformers/all-MiniLM-L6-v2` on `cpu` using repository-external cache at `D:\contextgraph-model-cache`.
- Canonical DB was backed up before rebuild, then the canonical repo was re-indexed with `635` stored embeddings under the fallback model.
- Latest full validation is now `85 passed, 1 warning`.
- Latest full 13-case eval under the fallback model still has `failed_case_count=0`.
- `vector_quality_valid=true` is now allowed for this run, but the scope is explicitly `lightweight semantic fallback; not code-specialized`.
- `bm25_vector` now improves over `bm25_only` on both `MRR` and `Recall@5`, so vector is no longer only a pipeline check in this configuration.

## Phase 4B.5 Note

- `nomic-ai/CodeRankEmbed` is now the tested code-specialized comparison target for local CPU usage.
- Official pinned revision for this phase is `3c4b60807d71f79b43f3c4363786d9493691f8b1`.
- The adapter now uses model profiles instead of scattering model-name checks through business logic.
- CodeRankEmbed query encoding now applies the official prefix `Represent this query for searching relevant code: `.
- CodeRankEmbed requires explicit `trust_remote_code=true`; it is no longer silently enabled by default.
- Embedding fingerprinting now distinguishes provider, model, and revision so different model revisions do not silently reuse old vectors.
- Official custom code review found no obvious unsafe behavior in the two reviewed Python files.
- CodeRankEmbed smoke succeeded on `cpu`, and offline second load with `local_files_only=true` also succeeded from `D:\contextgraph-model-cache`.
- Current like-for-like eval comparison on the same `13` active cases shows:
  - deterministic vector is still only a pipeline baseline
  - MiniLM is a good real-semantic fallback
  - CodeRankEmbed is better than MiniLM on this repo and is now the preferred local code-specialized baseline
- Canonical DB is currently back on CodeRankEmbed embeddings.

## Phase 4B.6 Note

- Default startup remains no-model mode:
  - `VECTOR_INDEX_ENABLED=false`
  - `HYBRID_VECTOR_ENABLED=false`
- Default mode does not auto-download any embedding model and does not require `trust_remote_code`.
- `cgstudio index .` now reports lightweight vector observability fields without changing retrieval behavior:
  - `vector_index_enabled`
  - `embedding_provider`
  - `embedding_model`
  - `embedding_revision`
  - `embedding_dimension`
  - `embedding_count`
  - `embedding_reused_count`
  - `embedding_generated_count`
- `.env.example` now documents three supported local states:
  - default no-model mode
  - CodeRankEmbed first-download mode
  - CodeRankEmbed offline mode
- Local model policy is now settled:
  - `nomic-ai/CodeRankEmbed` is the recommended local code-specialized baseline
  - `sentence-transformers/all-MiniLM-L6-v2` remains the lightweight fallback
  - `nomic-ai/nomic-embed-code` remains deferred on current hardware
- Eval metadata now keeps a stable distinction across deterministic, MiniLM, and CodeRankEmbed runs, including `embedding_revision`, `vector_quality_scope`, `model_smoke_status`, and `code_specialized`.
- Latest full validation is now `95 passed, 1 warning`.
- Latest offline CodeRankEmbed smoke succeeded with:
  - `local_files_only=true`
  - `model_smoke_status=coderankembed_smoke_passed`
  - full `13`-case eval still at `failed_case_count=0`
- Phase 4B ends here. The next suggested round is `TypeScript / JavaScript parser`, not more embedding model exploration.

## Phase 4C Note

- The repo now has a minimal Tree-sitter parser loop for:
  - `.ts`
  - `.tsx`
  - `.js`
  - `.jsx`
- Added runtime dependencies:
  - `tree-sitter`
  - `tree-sitter-typescript`
  - `tree-sitter-javascript`
- The new parser reuses the existing indexing pipeline and current domain models:
  - `ParseResult`
  - `EntityRecord`
  - `RelationRecord`
- Current extracted entities are:
  - `file`
  - `module`
  - `class`
  - `function`
  - `method`
  - `api_route`
- Current extracted relations are:
  - `contains`
  - `imports`
  - `calls`
  - `route_to_handler`
- Route support is intentionally minimal and only covers clear Express-like static patterns such as `router.post("/login", loginHandler)`.
- Dynamic route registration and broader Node framework coverage are still out of scope.
- Added `tests/fixtures/sample_ts_repo` and confirmed fixture indexing plus retrieval work end to end.
- Latest full validation is now `102 passed, 1 warning`.
- Fixture smoke showed:
  - repo_id `562fa47b-b5c9-5752-be3b-e0bf65ad2ef0`
  - latest successful scan_run_id `6362f6f6-d6af-4a0d-b81f-e83e8304c859`
  - `files=7`
  - `chunks=20`
  - `entities=27`
  - `relations=45`
- Retrieval smoke on the fixture now includes real graph evidence through `calls`:
  - `src/auth.loginHandler -> src/auth.verifyToken`
  - `src/auth.verifyToken -> src/auth.parseToken`
- Canonical repo regression passed after excluding `tests/fixtures` from normal workspace indexing:
  - repo_id `8bf02440-5d4e-5fa2-8916-a955c2c21fd2`
  - scan_run_id `4586616d-31fa-48f6-a022-f9005b85ef5e`
  - `parse_errors=0`
  - default mode still does not auto-download embedding models

## Phase 4D Note

- The repo now has two additional minimal structured parsers:
  - `contextgraph_studio/parsers/sql_parser.py`
  - `contextgraph_studio/parsers/config_parser.py`
- Current SQL coverage is intentionally small:
  - `db_table`
  - `db_view`
  - `db_index`
- Current config coverage is intentionally small:
  - `config_key`
  - file types: `.json`, `.yaml`, `.yml`, `.toml`
- SQL chunks now use `schema_unit`.
- Config files now produce:
  - `file_summary`
  - bounded `schema_unit` chunks for key paths
- Sensitive config values are masked by key-name rules and do not enter chunk text or retrieval output as raw values.
- Current array strategy is:
  - keep parent key
  - add a simple `[]` key path
  - continue nested object keys such as `servers[].host`
- Current graph boundary stays minimal:
  - only `contains`
  - no `uses_table`
  - no `configures`
- Structured fixture smoke succeeded:
  - repo_id `4d8c11cb-8735-5b60-bb71-924909bcf77e`
  - scan_run_id `f41ffe02-6448-4ff0-b9ce-cb3ffbbf9ae2`
  - `files=7`
  - `chunks=27`
  - `entities=30`
  - `relations=23`
  - `parse_errors=2`
- Structured retrieval smoke succeeded:
  - SQL query hit `schema.sql` and `migration.sql` `schema_unit` chunks
  - config query hit `config.json`, `settings.yaml`, and `pyproject.toml` config keys
  - raw secret values did not appear in the returned content
- Latest full validation is now `108 passed, 1 warning`.
- Latest canonical regression scan is:
  - repo_id `8bf02440-5d4e-5fa2-8916-a955c2c21fd2`
  - scan_run_id `b05edac4-3a82-45f8-a53a-0a6b3b18b1fa`
  - `parse_errors=0`

## Phase 4D.1 Note

- Phase 4D was checkpointed as commit `39509f1` (`feat(parser): add SQL and config structured indexing`).
- `database` and `configuration` are now first-class task strategies in `config/task_strategies.yaml`.
- Explicit `task_hint` is honored first, and keyword matching can now classify obvious database/configuration queries when no hint is provided.
- `RetrievalPlan` now records structured candidate lane intent through:
  - `candidate_lanes`
  - `schema_lane_enabled`
  - `schema_candidate_limit`
  - `config_lane_enabled`
  - `config_candidate_limit`
- BM25 recall now has two additional bounded supplemental lanes:
  - `schema` for `database` tasks
  - `config` for `configuration` tasks
- These lanes add candidates only. They do not change BM25 scoring, RRF, token budget, graph traversal, or `ContextPack` schema.
- Route diagnostics now expose lane-level evidence under `route_diagnostics.bm25_lanes`.
- Current graph boundary is unchanged:
  - no `uses_table`
  - no `configures`
  - no new edge types
- A separate structured eval dataset was added at `eval/fixtures/structured_golden.json` to avoid mixing fixture cases into the canonical repo golden dataset.
- Structured fixture smoke used a fresh DB and passed:
  - repo_id `4d8c11cb-8735-5b60-bb71-924909bcf77e`
  - scan_run_id `43d6ab8f-fa98-42c9-86c1-a710308936af`
  - `files=7`
  - `chunks=29`
  - `entities=32`
  - `relations=25`
  - `parse_errors=2`
- Structured eval smoke passed:
  - dataset `eval/fixtures/structured_golden.json`
  - configs `bm25_only`, `bm25_graph`
  - `active_case_count=4`
  - `failed_case_count=0`
- Latest full validation is now `111 passed, 1 warning`.
- Latest canonical regression scan is:
  - repo_id `8bf02440-5d4e-5fa2-8916-a955c2c21fd2`
  - scan_run_id `008a0b47-659f-4243-a20e-052322c4da0f`
  - `parse_errors=0`
  - default mode still does not auto-download embedding models

## Phase 4D.2 Note

- Phase 4D.1 was checkpointed as commit `256e33a` (`feat(retrieval): add structured task candidate lanes`).
- Added read-only structured relation diagnostics:
  - `contextgraph_studio/graph/structured_diagnostics.py`
  - `tests/test_structured_relation_diagnostics.py`
- Expanded the structured fixture with small source consumers:
  - `src/user_repository.py`
  - `src/config_loader.py`
  - `src/server.py`
- Added audit report:
  - `eval/analysis/structured_relation_value_audit.md`
- Audit result:
  - `uses_table` candidates: `4 total`, `3 safe`, `1 skipped`
  - `configures` candidates: `11 total`, `4 safe`, `7 skipped`
- Retrieval gap conclusion:
  - database queries already hit both structured SQL files and `src/user_repository.py`
  - configuration queries already hit both config files and `src/config_loader.py`
  - Graph still does not contribute, but there is no current bad case that needs a new edge
- Phase 4D.2 did not implement `uses_table` or `configures`.
- Fresh structured fixture smoke:
  - repo_id `4d8c11cb-8735-5b60-bb71-924909bcf77e`
  - scan_run_id `f77a6437-d3b7-402f-aa95-38618122b36c`
  - `files=10`
  - `chunks=37`
  - `entities=43`
  - `relations=38`
  - `parse_errors=2`
- Structured eval smoke:
  - dataset `eval/fixtures/structured_golden.json`
  - configs `bm25_only`, `bm25_graph`
  - `active_case_count=4`
  - `failed_case_count=0`
  - both configs: `MRR=0.6458`, `Recall@5=1.0`, `critical_file_hit_rate=1.0`
- Latest full validation is now `114 passed, 1 warning`.
- Latest canonical regression scan is:
  - repo_id `8bf02440-5d4e-5fa2-8916-a955c2c21fd2`
  - scan_run_id `c1615878-dba7-46f7-9357-a69588a62db8`
  - `parse_errors=0`
  - default mode still does not auto-download embedding models
