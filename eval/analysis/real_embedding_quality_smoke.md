# Real Embedding Quality Smoke

## Summary

- Date: `2026-06-08`
- Model used: `sentence-transformers/all-MiniLM-L6-v2`
- Model positioning: lightweight semantic fallback
- Code-specialized: `no`
- Device: `cpu`
- Cache directory: `D:\contextgraph-model-cache`
- Canonical repo embedding rebuild completed: `yes`
- `vector_quality_valid`: `true`
- `vector_quality_scope`: `lightweight semantic fallback; not code-specialized`
- `model_smoke_status`: `fallback_smoke_passed`

## Why fallback was used

- `nomic-ai/nomic-embed-code` is a `7B` code embedding model and was judged unsafe for this workstation smoke:
  - no CUDA device available in the active `.venv`
  - local GPU is `GTX 1050` with `2 GB` VRAM
  - the real semantic smoke had to stay inside a controlled D-drive cache budget
- This phase therefore establishes a real semantic baseline without claiming final code-retrieval quality.

## Smoke result

- Query/document encoding boundary is separated:
  - query path uses query-side encoding semantics
  - indexed code/document chunks use document-side encoding semantics
- Smoke sample result:
  - embedding dimension: `384`
  - dtype: `float32`
  - cosine similarity: `0.6690`
  - load time: `42466.84 ms`
  - encode time: `155.78 ms`

## Canonical rebuild

- DB backup:
  - `D:\contextgraph-backups\20260608_051022\before_real_embedding_smoke\contextgraph.db`
- Rebuild command class:
  - `cgstudio index .` with explicit sentence-transformer env vars, D-drive cache, and `EMBEDDING_LOCAL_FILES_ONLY=true`
- Result:
  - `scan_run_id = c822bca6-93d5-483a-b680-73dbb7a523bc`
  - files: `95`
  - chunks: `635`
  - embeddings: `635`
  - parse errors: `0`
  - elapsed: `69.11 s`
  - DB growth: `4042752 bytes`
  - model cache usage after smoke/download: `91578455 bytes`

## 13-case Ablation

| config | MRR | Recall@5 | critical_file_any_hit_rate |
| --- | ---: | ---: | ---: |
| `bm25_only` | `0.7538` | `0.8077` | `1.0000` |
| `bm25_graph` | `0.8179` | `0.8077` | `1.0000` |
| `bm25_vector` | `0.8295` | `0.8462` | `1.0000` |
| `bm25_vector_graph` | `0.8295` | `0.8846` | `1.0000` |

## Comparison Notes

- `bm25_only` vs `bm25_graph`
  - graph still helps ranking more than recall on this repo
  - graph does not fix `chunking_001`; that case still reports `edge_type_filtered`
- `bm25_only` vs `bm25_vector`
  - vector now adds real semantic lift instead of deterministic no-op behavior
  - `MRR` improves from `0.7538` to `0.8295`
  - `Recall@5` improves from `0.8077` to `0.8462`
- `bm25_graph` vs `bm25_vector_graph`
  - adding vector on top of graph keeps `MRR` at `0.8295`
  - `Recall@5` improves from `0.8077` to `0.8846`

## Per-case Highlights

- Vector gain cases:
  - `graph_traversal_001`: first relevant rank `2 -> 1`
  - `api_retrieve_001`: first relevant rank `10 -> 3`
  - `db_migration_001`: first relevant rank `2 -> 1`
- Vector no-clear-rank-gain cases:
  - `chunking_001` stays a rank-`1` critical hit
  - `eval_runner_001` stays rank `5`, but expected-hit coverage improves
- Vector regression case:
  - `cli_eval_001`: first relevant rank `2 -> 4`

## Recommendation

- The fallback model is worth keeping as a real semantic baseline for local eval.
- It should not be presented as the final code-specialized vector quality answer.
- The next model-quality phase should compare this fallback against a safe code-specialized baseline only after hardware/disk budget is explicitly re-approved.
