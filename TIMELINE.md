# TIMELINE

- 2026-06-07：初始化 ContextGraph Studio 仓库与基础工程骨架。
- 2026-06-07：完成 repository / scan_run / files / entities / chunks / traces / FTS5 的正式索引主链。
- 2026-06-07：完成本地 embedding 抽象、SQLite `embeddings`、增量向量同步与 `vector-search`。
- 2026-06-07：完成 `relations` 派生层、静态 Python graph builder、`graph-search` 与 `graph_score`。
- 2026-06-07：完成 Hybrid Retrieval 主链，支持 BM25、可选 Vector、可选 Graph、RRF、token budget 与 ContextPack。
- 2026-06-08：完成 Phase 4A eval runner、golden dataset、ablation metrics、`eval_runs` 与 JSON / Markdown 报告输出。
- 2026-06-08：修复 intake 防泄题规则，排除 `.tmp*`、`tmp_pytest*`、`eval/fixtures`、`eval/reports`。
- 2026-06-08：发现并修复工作区漂移，执行 C -> D 受控同步，恢复 D 为唯一 canonical workspace。
- 2026-06-08：重建 D 盘 `.venv`，初始化 D 盘 Git，迁入 canonical DB。
- 2026-06-08：恢复 Phase 3 入口层、MCP stdio、FastAPI lifespan、共享模型与 Hybrid Retrieval richer metadata。
- 2026-06-08：完成 D 盘全量验证：`59 tests collected`、`59 passed`、`index/retrieve/eval` smoke 通过。