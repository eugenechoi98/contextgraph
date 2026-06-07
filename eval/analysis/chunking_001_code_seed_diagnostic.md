# chunking_001 Code Seed Diagnostic

- case_id: `chunking_001`
- query: `Tune structure-aware chunking for Python symbols and markdown sections`
- task_hint: `general`
- critical file: `contextgraph_studio/services/chunker.py`
- helpful files:
  - `contextgraph_studio/parsers/python_parser.py`
  - `contextgraph_studio/domain.py`
- inspected scan_run: `9bf6bf89-303e-4296-adf8-0ba13fee674f`

## BM25 Top 30 Summary

Top 30 BM25 candidates are all documentation chunks:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `ARCHITECTURE.md`
4. `CONTEXT.md`
5. `CONTEXT.md`
6-30. `ContextGraph_Engineering_Design.md`

Every top-30 chunk has an `entity_id`, because `doc_section` chunks are represented as entities.

## Direct Answers

1. `contextgraph_studio/services/chunker.py` 是否进入 BM25 top 30？
   - 没有。
2. 如果进入，它排名多少？
   - 首次出现于 rank `172`，不是 top 30。
3. 它是否有 `entity_id`？
   - 有。`file_summary` 和多个 `symbol` chunk 都带 `entity_id`。
4. 它为什么没有进入 Graph seeds？
   - 当前 graph seed 提取只看全局前 `GRAPH_SEED_LIMIT=6` 个可 seed 候选；top 6 全是文档 `doc_section` 实体。
5. 当前 Graph seed 提取是否只取全局 top-N，导致文档 chunk 占满 seed 配额？
   - 是。
6. `python_parser.py` 或其他 source_code chunk 是否进入候选池？
   - 进入了更深层候选池，但不在 top 30。
   - `contextgraph_studio/domain.py` 首次出现于 rank `80`
   - `contextgraph_studio/parsers/python_parser.py` 首次出现于 rank `147`
   - `contextgraph_studio/services/chunker.py` 首次出现于 rank `172`
7. 当前 task strategy 是否有 `priority_categories` 但没有影响 Graph seed 选择？
   - 对当前 `general` case，现有 plan 没有 category-aware 的 graph seed 选择；seed 提取只按全局候选顺序和 `entity_id` 去重。
8. 问题属于哪类？
   - Primary: `候选召回不足`
   - Secondary: `seed 选择不足`
   - 不是 relation 缺失主导，也不是 entity 映射缺失主导。

## Evidence

- `bm25_graph` / `bm25_vector_graph` 现在已能明确记录：
  - `requested_routes = ["bm25", "graph"]` 或 `["bm25", "vector", "graph"]`
  - `executed_routes` 确实包含 `graph`
  - `chunking_001` 的 `graph.seed_count = 6`
  - 但 `graph.hit_count = 0`
  - `graph.reason = "empty_traversal"`
- 这说明 Graph 路径不是没有执行，而是被文档 seed 驱动后没有扩展出可用代码结果。
- 更关键的是，`chunker.py`、`python_parser.py`、`domain.py` 都不在 BM25 top 30；因此本轮 miss 先发生在候选召回层，而不是单纯发生在 graph seed 配额层。

## Disposition

本轮**不实施 Code Seed Reserve**。

原因：

- 用户允许的最小实验前提是：目标代码 chunk 已进入可用候选池，只是被文档 chunk 挤出 graph seed limit。
- 当前证据不满足这个前提，因为 `chunker.py` 首次出现于 rank `172`。
- reserve 无法修复“top 30 之前几乎全是文档”的问题，只会把非常靠后的低相关 code chunk 强行拉入 graph，容易制造误导性增益。

## Smallest Next Step

下一阶段应优先验证：

1. 这个 query 的 lexical surface 为什么更偏向架构文档而不是 `chunker.py`
2. 是否需要 query expansion 或 chunk text shaping 来让 `chunker.py` 更早进入候选池
3. 只有在代码候选已稳定进入前排后，再重新评估 code-seed reserve 是否值得做
