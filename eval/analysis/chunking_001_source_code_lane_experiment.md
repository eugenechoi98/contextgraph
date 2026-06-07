# chunking_001 Source-Code Candidate Lane Experiment

- case_id: `chunking_001`
- query: `Tune structure-aware chunking for Python symbols and markdown sections`
- critical file: `contextgraph_studio/services/chunker.py`
- helpful files:
  - `contextgraph_studio/parsers/python_parser.py`
  - `contextgraph_studio/domain.py`

## Read-only Lane Experiment

Using the same lexical query, three read-only lanes were compared before production integration:

### 1. general lane

- query terms: `tune structure aware chunking python symbols markdown sections`
- `chunker.py` first appeared at rank `3`
- `domain.py` first appeared at rank `12`
- `python_parser.py` first appeared at rank `30`

Note: after the Phase 4B.0 documentation work, this lane was already influenced by nearby analysis/docs in the canonical repo, but it still showed that code chunks could now enter the top candidate region when FTS tokenization was handled more carefully.

### 2. source_code lane

- category filter: `source_code`
- same lexical query
- `chunker.py` rank `1`
- `domain.py` rank `5`
- `python_parser.py` rank `15`

### 3. source_code + lexical expansion lane

- category filter: `source_code`
- expanded query:
  - `tune structure aware chunking python symbols markdown sections chunk chunker`
- `chunker.py` rank `1`
- `domain.py` rank `8`
- `python_parser.py` did not improve into the top 10, but `chunker.py` became more dominant and multiple chunker-related symbol chunks moved forward

## Gate Decision

接入门槛满足：

1. `chunker.py` 在 `source_code` lane 和 `source_code + lexical expansion` lane 中都显著前移
2. 改进不是通过硬编码目标文件路径、symbol 或 golden truth 实现
3. 普通 BM25 lane 保留
4. 候选总量仍受上限控制

因此本轮允许接入最小的 `Source-Code Candidate Lane`。

## Production Wiring

The integrated path is:

1. run normal BM25 lane
2. optionally run source-code-only BM25 lane
3. optionally apply lightweight lexical expansion for the source-code lane
4. stable-merge and dedupe the candidates
5. keep existing graph seed extraction, weighted RRF, and token budget unchanged

Public `ContextPack` schema remains unchanged.

## Eval Outcome

After integration on the canonical repo:

- `chunking_001` changed from a critical miss to a critical hit
- retrieved files now include:
  - `contextgraph_studio/services/chunker.py`
  - `contextgraph_studio/services/indexer.py`
  - `contextgraph_studio/domain.py`
  - docs files after those code hits
- `first_relevant_rank` improved from `None` to `1`
- `helpful_hits` now includes `contextgraph_studio/domain.py`
- `graph.seed_count` remains `6`
- `graph.hit_count` remains `0`
- `graph.reason` remains `empty_traversal`

This means the experiment successfully improved candidate recall, but it did not by itself solve graph expansion for this case.

## Regression Check

Canonical eval smoke after integration:

- all four configs reached `mrr = 1.0`
- `critical_file_hit_rate = 1.0`
- `critical_file_any_hit_rate = 1.0`
- `recall_at_5 = 0.9`
- no leakage from fixtures, reports, or tmp directories
- `vector_quality_valid` remains `false`

No obvious regression was observed in the other four active cases.
