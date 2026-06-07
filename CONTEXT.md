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
