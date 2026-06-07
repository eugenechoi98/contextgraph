# chunking_001 Root Cause Note

- case_id: `chunking_001`
- query: `Tune structure-aware chunking for Python symbols and markdown sections`
- task_hint: `general`
- expected_files:
  - `contextgraph_studio/services/chunker.py`
- critical_files:
  - `contextgraph_studio/services/chunker.py`
- helpful_files:
  - `contextgraph_studio/parsers/python_parser.py`
  - `contextgraph_studio/domain.py`

## Observed Retrieval

- latest eval report: `eval/reports/latest_eval_report.json`
- configs checked:
  - `bm25_only`
  - `bm25_graph`
  - `bm25_vector`
  - `bm25_vector_graph`
- effective retrieval_strategy for all four configs: `["bm25"]`
- vector hits: `0`
- graph hits: `0`
- helpful_files hit: `no`
- critical miss file: `contextgraph_studio/services/chunker.py`

## Retrieved Top Hits

Top chunk hits in the trace are all `bm25`:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `ARCHITECTURE.md`
4. `CONTEXT.md`
5. `CONTEXT.md`
6. `ContextGraph_Engineering_Design.md`
7. `ContextGraph_Engineering_Design.md`
8. `ContextGraph_Engineering_Design.md`
9. `ContextGraph_Engineering_Design.md`
10. `ContextGraph_Engineering_Design.md`

Collapsed to unique files, the final retrieved files are:

1. `AGENTS.md` (`bm25`)
2. `ARCHITECTURE.md` (`bm25`)
3. `CONTEXT.md` (`bm25`)
4. `ContextGraph_Engineering_Design.md` (`bm25`)

## Evidence

- `latest_eval_report.json` shows `retrieved_files` for `chunking_001` are only docs, across all four configs.
- Trace records for `chunking_001` show:
  - `bm25_hits_json` has 10 lexical hits, all from docs.
  - `vector_hits_json` is empty.
  - `graph_hits_json` is empty.
  - `final_selection_json.retrieval_strategy` remains `["bm25"]`.
- Query terms align strongly with docs:
  - `ARCHITECTURE.md` contains `Structure-aware Chunker`.
  - `ContextGraph_Engineering_Design.md` contains `chunking`, `Markdown`, `symbol`, and the chunking decision tree.
- `contextgraph_studio/services/chunker.py` does contain `Markdown section`, `chunk_markdown`, `MAX_SYMBOL_TOKENS`, and `chunk_kind="symbol"`, but it does not expose the exact high-signal phrase `structure-aware`.
- Because no code hit survives into the seed set, graph traversal never contributes for this case.
- `bm25_vector*` configs still record vector recall as skipped because the current eval baseline keeps vector quality non-semantic (`vector_quality_valid = false`).

## Preliminary Root Cause

Primary: `B. BM25 排名被配置/文档文件挤占`

Secondary: `A. Query 表述与目标文件关键词弱匹配`

This miss currently looks lexical, not a parser failure, not a chunk deletion bug, and not evidence that the golden truth is wrong.

## Smallest Next Validation

For Phase 4B, keep the golden dataset unchanged and validate one thing at a time:

1. inspect why this query produces no usable code seed before graph expansion
2. compare the lexical surface of `chunker.py` file-summary / symbol chunks against the query wording
3. only after that, decide whether the next experiment belongs in retrieval fusion, chunk text shaping, or task-specific routing
