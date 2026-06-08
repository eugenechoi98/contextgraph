# Phase 4E-C.3 Index Reuse Performance Profile

Date: 2026-06-08

Workspace: `D:\contextgraph-studio`

Instance: `astropy__astropy-12907`

Checkout: `D:\contextgraph-swebench-cache\repos\astropy__astropy\d16bfe05a744909de4b27f5875fe0d4ed41ce607\astropy__astropy-12907\checkout`

Isolated DB: `D:\contextgraph-swebench-cache\db\astropy__astropy-12907.sqlite`

## Summary

`bm25_only reused_index=false` is runner-level naming, not proof that the runner indexed twice.

For a single instance, the runner now checks out once, indexes once, then retrieves once per config. The first config reports `reused_index=false` because it is the first config using that scan. The second config reports `reused_index=true` because it reuses the same `scan_run_id`.

The real bottleneck was indexer-level snapshot reuse. The old unchanged-file path created a new snapshot but copied relations by scanning the full previous `relations` table once per reused file.

## Baseline Profile

Baseline scan_run: `ec1cdb6b-0882-4e49-9ae6-8a8b723647e2`

Total elapsed: `1046594 ms`

Counts:

- files: `969`
- entities: `19369`
- chunks: `19463`
- relations: `57850`
- reused files: `969`
- parsed files: `0`
- parse errors current/reused/total: `0 / 13 / 13`

| stage | elapsed_ms | rows_read | rows_written | query_count | batch_count |
| --- | ---: | ---: | ---: | ---: | ---: |
| resolve repository | not isolated | 0 | 0 | 4 | 0 |
| scan files | 1430 | 969 | 0 | 0 | 0 |
| resolve previous successful scan | 6 | 969 | 0 | 1 | 0 |
| compare unchanged files | 4 | 13 | 0 | 4 | 0 |
| copy reused snapshot | 856534 | not fully counted | 80328 | 83235 | 969 |
| rebuild changed relations | 153804 | not fully counted | 57850 | 57852 | 0 |
| sync FTS | 28915 | 19463 inferred | 19463 inferred | 3 | 1 inferred |

## Root Cause

The slowest stage was `copy reused snapshot`.

The old path did this for every reused file:

```text
read previous file entities
read previous file chunks
read all previous scan relations
filter relations in Python
insert matched relations one by one
```

That made the relation copy shape close to:

```text
reused_files x previous_relations
969 x 57850
```

This confirmed a per-file relation full scan and a `files x relations` complexity problem.

FTS sync was visible but not the main bottleneck. Python/SQLite row-by-row file/entity/chunk copy was noticeable, but smaller than relation copy. The runner was not incorrectly indexing twice for the same instance.

## Optimization

Implemented one evidence-gated fix: bulk relation copy for unchanged snapshots.

The new unchanged snapshot path:

```text
copy reused files/entities/chunks
build old_entity_id -> new_entity_id mapping
read previous successful scan relations once
keep only relations where both endpoints are safely reused
write mapped relations in one executemany batch
skip graph rebuild when no files are new, changed, or deleted
```

If any file is new, changed, or deleted, the indexer keeps the previous conservative behavior and rebuilds relations for the full snapshot. That avoids changing graph semantics while the performance fix stays focused on the unchanged reuse case measured in Astropy.

## Optimized Profile

Optimized scan_run without SQL trace: `8d8b55e4-4337-4123-a77b-eca6323f1b1c`

Total elapsed: `180323 ms`

Optimized scan_run with SQL trace: `2366334a-49ba-4885-96a5-a81accbbdc01`

Total elapsed with trace overhead: `294802 ms`

Counts:

- files: `969`
- entities: `19369`
- chunks: `19463`
- relations: `57850`
- reused_file_count: `969`
- parsed_file_count: `0`
- reused_entity_count: `19369`
- generated_entity_count: `0`
- reused_chunk_count: `19463`
- generated_chunk_count: `0`
- reused_relation_count: `57850`
- generated_relation_count: `0`
- parse errors current/reused/total: `0 / 13 / 13`

| stage | elapsed_ms | rows_read | rows_written | query_count | batch_count |
| --- | ---: | ---: | ---: | ---: | ---: |
| resolve repository | 2 | 0 | 0 | 4 | 0 |
| scan files | 1241 | 969 | 0 | 0 | 0 |
| resolve previous successful scan | 8 | 969 | 0 | 1 | 0 |
| compare unchanged files | 30 | 13 | 0 | 7 | 0 |
| copy reused files/entities/chunks | 44240 | not fully counted | 39801 | 41739 | 969 |
| copy reused relations | 200116 with trace overhead | 57850 | 57850 | 57853 traced row events | 1 |
| sync FTS | 47642 with trace overhead | 19463 inferred | 19463 inferred | 3 | 1 inferred |

Use the non-traced optimized run for wall-clock acceptance because SQLite trace callbacks add overhead. Use the traced run for query-count shape.

## Acceptance

Baseline profile elapsed: `1046594 ms`

Optimized unchanged profile elapsed: `180323 ms`

Improvement: about `82.8%`

Latest localization smoke index elapsed: `261379 ms`

Compared with previous official smoke `1256801 ms`, improvement is about `79.2%`.

The optimized smoke stayed under 5 minutes for unchanged snapshot reuse.

## Semantics Check

The optimization does not change these rules:

- each index still creates a new `scan_run`
- latest successful scan remains the reuse source
- failed scans are ignored
- deleted files are not copied into the new snapshot
- changed files do not reuse old entities, chunks, or relations
- copied relations are rebound to the new `scan_run_id`
- parse error current/reused/total snapshot counts stay separate
- canonical DB is not touched by SWE-bench profiling

## Remaining Bottlenecks

After the fix, the largest remaining stages are:

- bulk relation insert/read
- file/entity/chunk row copy
- FTS sync

Those are left for later. This phase intentionally avoids a second optimization so the evidence remains clean.
