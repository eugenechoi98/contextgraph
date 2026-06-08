# Astropy SWE-bench Retrieval Miss Diagnostic

## Scope

- instance: `astropy__astropy-12907`
- repo: `astropy/astropy`
- base commit: `d16bfe05a744909de4b27f5875fe0d4ed41ce607`
- critical file: `astropy/modeling/separable.py`
- diagnosis only: no BM25, Graph, RRF, token budget, parser, or query expansion changes

Full candidate evidence is stored in:

- `eval/analysis/astropy__astropy-12907_diagnostic_data.json`
- `eval/analysis/astropy__astropy-12907_anchor_diagnostics.json`

## Retrieval Miss

The critical file does not appear in:

- general lane top 100
- source-code lane top 100
- configured merged candidate pool

Its configured rank is therefore `not present`, not merely below the final token budget.

The full issue query normalizes to an FTS expression containing dotted tokens such as:

- `astropy.modeling`
- `astropy.modeling.separable`
- `m.Linear1D`
- `m.Pix2Sky_TAN`
- `other.`

SQLite FTS5 rejects that expression with:

```text
fts5: syntax error near "."
```

The retrieval code then uses the degraded lexical fallback. Fallback results all receive score `0.1` and have no relevance ordering, so early stored chunks from `.circleci/config.yml`, issue templates, PyInstaller helpers, and `astropy/__init__.py` fill the candidate limits.

The target file itself has strong lexical anchors:

| anchor | target evidence |
| --- | --- |
| `separability_matrix` | target rank 1 |
| `_separable` | target rank 1 |
| `_compute_n_outputs` | target rank 1 |
| `separability` | target rank 1 |
| `CompoundModel` | first target chunk rank 55 |

Target-file source counts:

- `separability_matrix`: `7`
- `CompoundModel`: `2`
- `_separable`: `19`
- `_compute_n_outputs`: `2`

Conclusion: this is an FTS query construction/fallback-ordering failure. It is not parser coverage, category filtering, or token-budget truncation. This phase records the evidence but does not change retrieval behavior.

## Graph Diagnosis

Graph was requested and executed for `bm25_graph`.

- seed_count: `6`
- seed_entity_count: `6`
- allowed_edge_types: `calls`, `imports`
- direction: `outgoing_only`
- relations_examined: `0`
- relations_filtered: `6`
- expanded_entity_count: `0`
- mapped_chunk_count: `0`
- hit_count: `0`
- reason: `edge_type_filtered`

All six seeds are `config_key` entities from `.circleci/config.yml`. They came from degraded general-lane fallback results, not from `astropy/modeling/separable.py`.

The critical file never entered the configured candidate pool, so it could not become a graph seed. Graph does not need a behavior change in this phase; its zero contribution is downstream of the malformed FTS query and wrong seed set.

## Runner Efficiency

Before:

```text
for each retrieval config:
  checkout
  index
  retrieve
```

After:

```text
for each instance:
  checkout once
  index once
  retrieve once per config
```

Final official re-smoke:

- checkout calls: `1`
- index calls: `1`
- retrieve calls: `2`
- shared scan_run_id: `d5d36771-d395-4705-bb3c-25406acf5c32`
- checkout reused: `true`
- index elapsed: `676553 ms`
- `bm25_only` retrieve: `70 ms`
- `bm25_graph` retrieve: `50 ms`

The prior `71.8 s` versus `607.5 s` difference came from indexing twice. The second index used the full reuse path, which is currently much slower on this repository. Runner reuse removes the unnecessary second index without changing indexer behavior.

## Parse Error Semantics

Historical evidence:

- first successful scan: `f4d7d15d-05d1-4d47-89eb-da5940dcd42f`
- first parse errors: `13`
- second successful scan: `9413aafe-1bf3-4594-9cf8-9563a3ff1abf`
- second reused files: `969`
- old second-scan parse errors: `0`

The old `parse_errors` field counted only errors produced by files parsed in that run. Reused files were not reparsed, so their existing errors disappeared from the summary even though the snapshot still represented the same content.

New fields:

- `parse_errors_current_scan`
- `parse_errors_reused`
- `parse_errors_total_snapshot`

Final official re-smoke:

- current_scan: `0`
- reused: `13`
- total_snapshot: `13`
- legacy `parse_errors`: `13`

Historical recovery only applies when file path and content hash both match, so an old error is not carried onto changed content.

## Relation Dedupe Review

Root cause: parser-level relation generation could emit the same stable tuple more than once:

```text
scan_run_id + from_entity_id + to_entity_id + edge_type
```

The second insert reused the same stable relation ID and raised a SQLite unique constraint error.

The fix uses idempotent insert semantics and counts only rows actually inserted. It keeps one equivalent edge while preserving:

- different edge types
- different targets
- different scan runs

No relation type or Graph traversal behavior changed.

## Final Localization

Both configurations completed:

| config | Recall@10 | MRR | critical hit | Graph hits |
| --- | ---: | ---: | --- | ---: |
| `bm25_only` | 0.000 | 0.000 | false | 0 |
| `bm25_graph` | 0.000 | 0.000 | false | 0 |

The critical miss remains intentionally unresolved because this phase did not authorize retrieval algorithm changes.
