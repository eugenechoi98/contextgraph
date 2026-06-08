# Phase 4E-D Three-instance SWE-bench Localization Report

Date: 2026-06-08

Workspace: `D:\contextgraph-studio`

Cache root: `D:\contextgraph-swebench-cache`

Manifest: `D:\contextgraph-swebench-cache\manifests\official_three_instances.json`

Generated reports:

- JSON: `D:\contextgraph-swebench-cache\reports\swebench_localization_1780928519.json`
- Markdown: `D:\contextgraph-swebench-cache\reports\swebench_localization_1780928519.md`
- Summary JSON: `D:\contextgraph-swebench-cache\reports\swebench_three_instance_summary_1780928519.json`
- Summary Markdown: `D:\contextgraph-swebench-cache\reports\swebench_three_instance_summary_1780928519.md`

## Scope

This run used exactly three official SWE-bench Lite instances:

- `astropy__astropy-12907`
- `django__django-10914`
- `matplotlib__matplotlib-18869`

Boundaries:

- vector disabled
- Docker disabled
- patch execution disabled
- target repo tests disabled
- dependency install disabled
- full clone fallback disabled
- no retrieval, BM25, Graph, parser, embedding, RRF, or Token Budget changes

## Instance Results

| instance | repo | critical file | checkout_reused | checkout_ms | index_ms | bm25_only first rank | bm25_graph first rank |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| `astropy__astropy-12907` | `astropy/astropy` | `astropy/modeling/separable.py` | true | 94 | 348409 | 1 | 1 |
| `django__django-10914` | `django/django` | `django/conf/global_settings.py` | false | 10908 | 196907 | miss | miss |
| `matplotlib__matplotlib-18869` | `matplotlib/matplotlib` | `lib/matplotlib/__init__.py` | false | 17820 | 52318 | 2 | 2 |

Each instance used one checkout, one isolated SQLite DB, one index, and two retrieval configs.

## Metrics

| config | critical hit rate | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `bm25_only` | 0.667 | 0.333 | 0.667 | 0.667 | 0.667 | 0.500 |
| `bm25_graph` | 0.667 | 0.333 | 0.667 | 0.667 | 0.667 | 0.500 |

Graph summary:

- improved by MRR: none
- no contribution by MRR: `astropy__astropy-12907`, `django__django-10914`, `matplotlib__matplotlib-18869`
- regressed by MRR: none

Graph still executed and produced hits for graph-enabled configs:

- Astropy: `4` graph hits
- Django: `4` graph hits
- Matplotlib: `10` graph hits

Those hits did not change file-level MRR in this three-instance sample.

## Performance

| instance | files | chunks | entities | relations | parse errors current/reused/total | index_ms |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| `astropy__astropy-12907` | 969 | 19463 | 19369 | 57850 | 0 / 13 / 13 | 348409 |
| `django__django-10914` | 2939 | 33535 | 33344 | 94506 | 16 / 0 / 16 | 196907 |
| `matplotlib__matplotlib-18869` | 972 | 11370 | 11833 | 33264 | 8 / 0 / 8 | 52318 |

Aggregate:

- avg checkout elapsed: about `9607 ms`
- avg index elapsed: about `199105 ms`
- avg retrieve elapsed across six config runs: about `2482 ms`
- cache size after run: about `0.96 GB`
- D drive free space after run: about `16.04 GB`
- 10 GB disk gate was not triggered

## Miss Diagnosis

### `django__django-10914`

Missed critical file:

- `django/conf/global_settings.py`

Observed retrieval:

- general BM25 top 100: target file did not appear
- manually checked source-code BM25 top 100: target file did not appear
- final context pack: target file did not appear
- target has indexed chunks and entity_id
- Graph ran for `bm25_graph`, but target did not enter graph expansion output
- token estimate was near budget, but the target was absent from candidates before token packing, so this is not primarily token-budget truncation

Indexed target chunks:

- `file_summary` for `django/conf/global_settings.py`
- symbol chunk for `django.conf.global_settings.gettext_noop`

Root-cause category:

- `D. parser coverage 不足`

Reason:

The task asks about `FILE_UPLOAD_PERMISSIONS`, but the current Python parser/chunker does not expose module-level settings assignments from `global_settings.py` as retrievable chunks. The target file exists in the snapshot, but the relevant constant assignment is not represented strongly enough for BM25 or Graph seeds.

Deferred next directions:

- consider module-level assignment extraction for Python config-like source files
- consider a read-only diagnostic for assignment-heavy files before changing retrieval behavior

No query expansion, Graph change, parser fix, or algorithm change was implemented in this phase.

## Integrity

Canonical DB SHA256 before and after:

`75F9FE908AD4D7491F9A82EA31CFBB8B9B2A2D94C8E6ECCDBF2762E976D9B174`

The canonical workspace DB was unchanged.
