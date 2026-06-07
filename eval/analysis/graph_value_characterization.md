# Graph Value Characterization

Date: `2026-06-08`
Eval report: `eval/reports/eval_report_1780865211.json`
Dataset: `eval/fixtures/contextgraph_golden.json`

## Dataset Shape

- active cases: `13`
- draft cases: `0`
- graph_expectation distribution:
  - `required = 4`
  - `helpful = 5`
  - `none = 4`

## Ablation Summary

- `bm25_only`
  - `mrr = 0.7538`
  - `critical_file_hit_rate = 1.0`
  - `critical_file_any_hit_rate = 1.0`
  - `recall_at_5 = 0.8077`
- `bm25_graph`
  - `mrr = 0.8179`
  - `critical_file_hit_rate = 1.0`
  - `critical_file_any_hit_rate = 1.0`
  - `recall_at_5 = 0.8077`
- `bm25_vector`
  - `mrr = 0.7538`
  - `critical_file_hit_rate = 1.0`
  - `critical_file_any_hit_rate = 1.0`
  - `recall_at_5 = 0.8077`
- `bm25_vector_graph`
  - `mrr = 0.8179`
  - `critical_file_hit_rate = 1.0`
  - `critical_file_any_hit_rate = 1.0`
  - `recall_at_5 = 0.8077`

## Graph Characterization

For both `bm25_graph` and `bm25_vector_graph`:

- `graph_participation_rate = 12 / 13 = 0.9231`
- `graph_required_case_participation_rate = 4 / 4 = 1.0`
- `graph_helpful_case_participation_rate = 5 / 5 = 1.0`
- `graph_none_case_participation_rate = 3 / 4 = 0.75`
- `graph_requested_case_count = 13`
- `graph_executed_case_count = 13`
- `graph_participating_case_count = 12`
- non-participation reason counts:
  - `edge_type_filtered = 1`

## Per-expectation Findings

### required

Participated in all four cases:

- `hybrid_retrieval_001`
- `graph_builder_001`
- `graph_traversal_001`
- `api_retrieve_001`

Interpretation:

- Graph is consistently contributing on tasks that naturally span retrieval orchestration, graph building, traversal logic, or API-to-service boundaries.
- For this dataset, required-graph cases are not currently blocked by `no_entity_seed`, `no_relations`, `direction_filtered`, or `no_chunk_mapping`.

### helpful

Participated in all five cases:

- `index_pipeline_001`
- `vector_store_001`
- `fusion_001`
- `cli_eval_001`
- `eval_runner_001`

Interpretation:

- Graph is often present even when the task is not purely graph-centric.
- The current system appears to use graph mostly as a ranking/context-shaping signal rather than as a recall unlock for these cases.

### none

Participated in three of four cases:

- participated:
  - `python_parser_001`
  - `db_migration_001`
  - `eval_metrics_001`
- did not participate:
  - `chunking_001`

Interpretation:

- `chunking_001` remains the one clear case where graph non-participation is understandable and evidence-backed.
- The other three `none` cases still receive graph hits, which means graph participation alone should not be interpreted as proof that graph was necessary.
- This validates the decision to keep `graph_expectation` as a diagnostic label instead of turning it into a hard pass/fail metric.

## Stable Patterns

1. Graph improves ranking more clearly than recall on the current first-party dataset.
   - `MRR` improves from `0.7538` to `0.8179`
   - `Recall@5` stays flat at `0.8077`

2. Required-graph tasks are currently well covered.
   - All `required` cases participate under graph-enabled configs.

3. The main diagnosed graph miss pattern is still seed shape plus edge filtering.
   - Only `chunking_001` fails to participate.
   - Reason remains `edge_type_filtered`.

4. Graph is currently broad rather than selective.
   - It participates in `75%` of `none` cases.
   - That is not a bug by itself, but it means participation rate is a characterization metric, not a product-quality verdict.

## Conclusion

The expanded dataset supports a narrower and more confident statement than before:

- Graph has real value on this repo, especially by improving ranking on tasks with structural dependencies.
- `chunking_001` should not be used as evidence that graph is globally weak; it is now better understood as a structurally poor seed case.
- There is not yet evidence in this round that traversal direction, edge types, or graph seed policy must be changed.

## Next-round Candidate

If a next round is needed, the best candidate is not "force graph to help `chunking_001`".

The stronger candidate question is:

- should graph become more selective on `graph_expectation=none` tasks, or is broad participation acceptable as long as strict retrieval metrics remain healthy?
