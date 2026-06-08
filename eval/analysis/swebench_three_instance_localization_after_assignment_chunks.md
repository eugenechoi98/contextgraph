# Phase 4E-D.1 Three-instance Regression After Assignment Chunks

Date: 2026-06-08

Manifest: `D:\contextgraph-swebench-cache\manifests\official_three_instances.json`

Report: `D:\contextgraph-swebench-cache\reports\swebench_localization_1780932929.json`

## Change Under Test

Python module-level static assignments now produce `module_assignment` entities and independent `symbol` chunks.

Assignment chunks include:

- file path
- language
- entity type
- symbol name
- value type
- safe value preview or redacted marker
- immediate leading comment context
- line range

No retrieval algorithm, BM25 weight, FTS normalizer, Graph traversal, RRF, Token Budget, embedding, or ContextPack schema was changed.

## Django Before / After

Instance: `django__django-10914`

Critical file: `django/conf/global_settings.py`

Before:

- `bm25_only`: miss
- `bm25_graph`: miss
- target not found in general/source-code top 100
- target file existed, but `FILE_UPLOAD_PERMISSIONS` was absent from indexed chunks

After:

- `bm25_only`: rank `7`
- `bm25_graph`: rank `7`
- critical hit: `true`
- Recall@10: `1.0`
- MRR: `0.14285714285714285`
- Graph hit count: `4` under `bm25_graph`
- Graph did not improve rank; the recovery came from BM25 candidate recall after assignment chunking

Why it recovered:

`FILE_UPLOAD_PERMISSIONS = None` now has its own searchable chunk, including the nearby comment:

```text
The numeric mode to set newly-uploaded files to.
```

That local source context aligns with the issue query without query expansion.

## Three-instance Regression

| instance | bm25_only rank | bm25_graph rank | status |
| --- | ---: | ---: | --- |
| `astropy__astropy-12907` | 1 | 1 | no regression |
| `django__django-10914` | 7 | 7 | recovered |
| `matplotlib__matplotlib-18869` | 2 | 2 | no regression |

Summary:

| config | hit rate | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `bm25_only` | 1.000 | 0.333 | 0.667 | 0.667 | 1.000 | 0.548 |
| `bm25_graph` | 1.000 | 0.333 | 0.667 | 0.667 | 1.000 | 0.548 |

Graph summary:

- Astropy: `4` graph hits, no rank change
- Django: `4` graph hits, no rank change
- Matplotlib: `3` graph hits, no rank change

## Integrity

Canonical DB SHA256 after the run:

`75F9FE908AD4D7491F9A82EA31CFBB8B9B2A2D94C8E6ECCDBF2762E976D9B174`

The canonical DB was unchanged. No Docker, patch apply, target repo tests, embedding download, or fourth official instance was used.
