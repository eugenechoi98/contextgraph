# ARCHITECTURE

## Canonical Workspace

唯一正式工作区：`D:\contextgraph-studio`

## 主链

1. Repository Intake
2. Source Classifier
3. Parser Layer
4. Structure-aware Chunker
5. SQLite / FTS5 / Embeddings / Relations
6. Retrieval Planner
7. BM25 / Vector / Graph Recall
8. Weighted RRF
9. ContextPack Builder
10. Trace Store
11. Eval Runner
12. CLI / FastAPI / MCP

## Source of Truth

- `files / entities / chunks` 是内容主真源
- `chunks_fts` 是 FTS 派生层
- `embeddings` 是向量派生层
- `relations` 是图派生层
- `eval_runs` 是评测附属层

## 当前已验证能力

- shared application services
- FastAPI lifespan
- MCP stdio tools：`retrieve_context`、`scan_repo`、`get_trace`
- hybrid retrieval with BM25 + graph and optional vector
- eval runner with golden dataset and ablation configs
- eval route diagnostics that separate requested, executed, and participating routes

## 关键边界

- intake 必须排除评测数据和临时目录，避免泄题
- RRF 融合必须保留 richer metadata，避免 graph path 丢失
- deterministic embedding 只验证 pipeline，不提供语义质量结论
- `chunking_001` 当前 miss 先发生在候选召回层，不是已证实的 graph seed 配额问题
