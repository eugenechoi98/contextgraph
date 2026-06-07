# chunking_001 Graph Empty Traversal Diagnostic

- case_id: `chunking_001`
- query: `Tune structure-aware chunking for Python symbols and markdown sections`
- repo_id: `8bf02440-5d4e-5fa2-8916-a955c2c21fd2`
- scan_run_id: `9c14a8ca-f166-46d2-ad27-01cd7fd75a32`
- trace_id: `77cf149e-0d87-4a06-8459-b27114c74862`
- task_type: `general`
- allowed_edge_types: `["calls", "imports"]`
- graph_hops: `1`
- traversal_direction: `outgoing_only`
- graph diagnostics:
  - `seed_count = 6`
  - `seed_entity_count = 6`
  - `relations_examined = 0`
  - `relations_filtered = 6`
  - `expanded_entity_count = 0`
  - `mapped_chunk_count = 0`
  - `hit_count = 0`
  - `reason = "edge_type_filtered"`

## Seed Summary

| seed_rank | seed_source_lane | chunk_id | file_path | chunk_kind | entity_id | symbol_name | entity_type | category | selected_as_graph_seed | outgoing_relation_count | incoming_relation_count | relation_edge_types | allowed_edge_types_for_task | excluded_relation_count | exclusion_reason | traversal_result_count | mapped_chunk_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | --- | ---: | ---: |
| 1 | `bm25` | `dcaff840-2b96-5172-9528-3f73e1751a15` | `AGENTS.md` | `doc_section` | `0b2f0973-efb2-5179-a55e-c70ff0c6d387` | `AGENTS.md::Python 环境` | `doc_section` | `doc` | `true` | 0 | 1 | `incoming: contains` | `calls, imports` | 1 | `incoming contains is disallowed and traversal is outgoing-only` | 0 | 1 |
| 2 | `bm25` | `159d3600-c430-5118-b86f-b376dd09be3b` | `ARCHITECTURE.md` | `doc_section` | `22401a46-d3c9-547b-aa7c-cf5aac48a200` | `ARCHITECTURE.md::关键边界` | `doc_section` | `doc` | `true` | 0 | 1 | `incoming: contains` | `calls, imports` | 1 | `incoming contains is disallowed and traversal is outgoing-only` | 0 | 1 |
| 3 | `bm25` | `3ad3e07d-bc99-558e-80f7-1237cf4a9224` | `ARCHITECTURE.md` | `doc_section` | `59ffaa03-e813-571d-88a6-b0b8a705c9de` | `ARCHITECTURE.md::主链` | `doc_section` | `doc` | `true` | 0 | 1 | `incoming: contains` | `calls, imports` | 1 | `incoming contains is disallowed and traversal is outgoing-only` | 0 | 1 |
| 4 | `bm25` | `b0144027-9996-5dbb-a96d-2a1fe18db726` | `ARCHITECTURE.md` | `doc_section` | `f5b42cf5-c93b-54ad-802d-29d8e603f058` | `ARCHITECTURE.md::当前已验证能力` | `doc_section` | `doc` | `true` | 0 | 1 | `incoming: contains` | `calls, imports` | 1 | `incoming contains is disallowed and traversal is outgoing-only` | 0 | 1 |
| 5 | `bm25` | `afb19cdb-b565-5e5e-82f2-c48cd3c28397` | `CONTEXT.md` | `doc_section` | `acf5629c-08d0-5b2d-bda4-c18330192227` | `CONTEXT.md::注意事项` | `doc_section` | `doc` | `true` | 0 | 1 | `incoming: contains` | `calls, imports` | 1 | `incoming contains is disallowed and traversal is outgoing-only` | 0 | 1 |
| 6 | `bm25` | `bd3f112a-2f94-5d3d-9005-50c028cbf644` | `CONTEXT.md` | `doc_section` | `3677574d-f1cd-589b-b0bc-1c46fb3ec8bb` | `CONTEXT.md::2026-06-08 现状` | `doc_section` | `doc` | `true` | 0 | 1 | `incoming: contains` | `calls, imports` | 1 | `incoming contains is disallowed and traversal is outgoing-only` | 0 | 1 |

## Seed To Traversal Chain

1. BM25 merged candidates contain `40` hits.
2. Graph seed extraction uses the first `GRAPH_SEED_LIMIT=6` unique `entity_id` values from direct recall.
3. Those 6 seeds all come from the BM25 general lane, not the source-code lane.
4. The first source-code entities appear only at ranks `31-40`.
5. Representative source-code hits:
   - rank `31`: `contextgraph_studio/services/chunker.py` -> `contextgraph_studio.services.chunker.chunk_source_file`
   - rank `32`: `contextgraph_studio/services/chunker.py` -> `contextgraph_studio.services.chunker.chunk_markdown`
   - rank `33`: `contextgraph_studio/services/chunker.py` -> file summary entity
   - rank `39`: `contextgraph_studio/domain.py` -> `contextgraph_studio.domain.ChunkRecord`

## Validity Checks

- The 6 seed `entity_id` values all exist in `entities`.
- All 6 seeds belong to the latest successful scan `9c14a8ca-f166-46d2-ad27-01cd7fd75a32`.
- All 6 seeds belong to the current repo `8bf02440-5d4e-5fa2-8916-a955c2c21fd2`.
- This is not an `entity -> chunk` mapping failure for the seeds themselves; each seed maps to one chunk.
- This is not a stale-scan mismatch between seeds and relations.

## Relations Audit

- For the current task strategy, allowed edge types are only `calls` and `imports`.
- Every one of the 6 selected seeds has:
  - `outgoing relations = 0`
  - `incoming relations = 1`
  - incoming edge type = `contains`
- The repo-wide latest scan does contain rich allowed graph edges:
  - `calls = 508`
  - `imports = 265`
- Critical files also have valid graph entities and relations:
  - `contextgraph_studio/services/chunker.py`: 11 entities, multiple incoming and outgoing relations
  - `contextgraph_studio/parsers/python_parser.py`: 10 entities, multiple incoming and outgoing relations
  - `contextgraph_studio/domain.py`: 12 entities, multiple incoming relations

## Root Cause

The empty traversal is real, but it is not caused by missing graph data in the repo.

The root cause is:

1. Graph seed extraction is working as implemented, but it selects the first 6 unique entities from merged direct recall.
2. For `chunking_001`, those first 6 entities are all documentation `doc_section` seeds from the BM25 general lane.
3. Those `doc_section` entities have no outgoing `calls` or `imports`.
4. Their only relation is incoming `contains`, which is both:
   - excluded by the current task strategy edge filter
   - unreachable under the current `outgoing_only` traversal direction

So the true answer for Phase 4B.2 is:

- seed validity: `yes`
- relation existence: `yes, but only incoming contains on the chosen seeds`
- edge filter impact: `yes`
- direction impact: `yes, but secondary to the edge-type mismatch`
- entity -> chunk mapping: `normal for seeds; not the failure point`
- real root cause: `graph seeds are valid but structurally poor for traversal because the selected seeds are doc sections rather than code entities`

## Minimal Fix Decision

- Implemented this round: `graph diagnostics only`
- Not implemented this round:
  - no traversal direction change
  - no task strategy edge-type change
  - no graph seed selection rewrite

Reason:

- A direction-only fix would not solve this case because the only available incoming edge is still `contains`, which is disallowed for `general`.
- An edge-type-only fix would still be a larger retrieval-behavior change and would need separate product justification.
- The smallest safe change for this round is to make the graph failure legible in diagnostics, not to force graph contribution on a case already recovered by candidate recall.
