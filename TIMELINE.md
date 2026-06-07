# TIMELINE

- 2026-06-07: 初始化 ContextGraph Studio 仓库与基础工程骨架
- 2026-06-07: 完成 `repository / scan_run / files / entities / chunks / traces / FTS5` 主链
- 2026-06-07: 完成本地 embedding 抽象、SQLite `embeddings`、增量向量同步与 `vector-search`
- 2026-06-07: 完成 `relations`、静态 Python graph builder、`graph-search` 与 `graph_score`
- 2026-06-07: 完成 Hybrid Retrieval 主链，支持 BM25、可选 Vector、可选 Graph、RRF、token budget 与 ContextPack
- 2026-06-08: 完成 Phase 4A eval runner、golden dataset、ablation metrics、`eval_runs` 与 JSON / Markdown 报告
- 2026-06-08: 修复 intake 防泄题规则，排除 `.tmp*`、`tmp_pytest*`、`eval/fixtures`、`eval/reports`
- 2026-06-08: 纠正工作区漂移，完成 C -> D 受控同步，恢复 `D:\contextgraph-studio` 为唯一 canonical workspace
- 2026-06-08: 重建 D 盘 `.venv`，初始化 D 盘 Git，迁入 canonical DB
- 2026-06-08: 恢复 Phase 3 入口层、MCP stdio、FastAPI lifespan、共享模型与 richer metadata 融合
- 2026-06-08: 建立 canonical baseline commit `a39f02d`，并补充 eval 基线说明 commit `fe4b47e`
- 2026-06-08: 完成 Phase 4B.0，补齐 eval route diagnostics，新增 `tests/test_eval_ablation_wiring.py`
- 2026-06-08: 完成 `chunking_001` code-seed 诊断，确认 `chunker.py` 不在 BM25 top 30，本轮不实施 Code Seed Reserve
- 2026-06-08: 完成 Phase 4B.1，接入最小 `source_code candidate lane` 与轻量 lexical expansion，新增 `tests/test_bm25_candidate_lanes.py`
- 2026-06-08: `chunking_001` 从 critical miss 提升为 critical hit，但 graph 对该 case 仍未扩展出有效命中
