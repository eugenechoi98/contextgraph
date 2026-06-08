# CodeRankEmbed Quality Comparison

## Summary

- Date: `2026-06-08`
- Compared models:
  - `deterministic-sha256`
  - `sentence-transformers/all-MiniLM-L6-v2`
  - `nomic-ai/CodeRankEmbed`
- Official long-term target kept deferred:
  - `nomic-ai/nomic-embed-code`
- Recommendation:
  - adopt `nomic-ai/CodeRankEmbed` as the local MVP code-specialized baseline

## Why `nomic-ai/nomic-embed-code` stays deferred

- It is still the intended long-term code-specialized target.
- But this workstation gate is unchanged:
  - CPU only in the active `.venv`
  - no CUDA device available
  - visible GPU budget is only `2 GB`
  - this phase prioritized safe local comparison over risky `7B` smoke

## Why CodeRankEmbed was chosen

- Official Nomic release on Hugging Face
- `137M` bi-encoder
- code retrieval focus
- `8192` context length
- `MIT` license
- realistic for local CPU smoke on this machine

## Official Source and Revision

- Official repo:
  - [nomic-ai/CodeRankEmbed](https://huggingface.co/nomic-ai/CodeRankEmbed)
- Pinned revision:
  - `3c4b60807d71f79b43f3c4363786d9493691f8b1`
- Required official query prefix:
  - `Represent this query for searching relevant code: `

## trust_remote_code Review

- Reviewed custom code files:
  - `configuration_hf_nomic_bert.py`
  - `modeling_hf_nomic_bert.py`
- Obvious unsafe behavior found:
  - `no`
- The review specifically checked for obvious:
  - shell execution
  - subprocess launch
  - network exfiltration helpers
  - destructive file deletion helpers

## Local Hardware and Cache

- Device: `cpu`
- Cache directory: `D:\contextgraph-model-cache`
- Cache usage after download:
  - `639641247` bytes

## Smoke Result

- Model: `nomic-ai/CodeRankEmbed`
- Revision: `3c4b60807d71f79b43f3c4363786d9493691f8b1`
- Dimension: `768`
- Dtype: `float32`
- First load plus query encode:
  - `75319.94 ms`
- Document encode:
  - `304.7 ms`
- Positive cosine:
  - `0.2911`
- Negative cosine:
  - `-0.0914`
- Positive similarity higher than negative:
  - `yes`

## Offline Load Result

- `local_files_only=true` second load:
  - `passed`
- Offline reload latency:
  - `12424.42 ms`

## Canonical Rebuild Result

- Backup path:
  - `D:\contextgraph-backups\20260608_143646\before_coderankembed_rebuild\contextgraph.db`
- First CodeRankEmbed rebuild scan:
  - `1221c451-337e-4631-aa1a-1b677bef497f`
- Final restored canonical CodeRankEmbed scan:
  - `cc2512de-440d-418c-89df-78fd12a9034a`
- Current canonical repo state:
  - files: `97`
  - chunks: `684`
  - embeddings: `684`
  - parse errors: `0`
- DB size before rebuild:
  - `33906688` bytes
- DB size after rebuild and comparisons:
  - `39321600` bytes

## Eval Metrics

### deterministic

- `bm25_only`: `MRR=0.7769`, `Recall@5=0.8077`
- `bm25_graph`: `MRR=0.8410`, `Recall@5=0.8077`
- `bm25_vector`: `MRR=0.3112`, `Recall@5=0.3077`
- `bm25_vector_graph`: `MRR=0.6538`, `Recall@5=0.6154`
- `vector_quality_valid=false`

### MiniLM

- `bm25_only`: `MRR=0.7769`, `Recall@5=0.8077`
- `bm25_graph`: `MRR=0.8410`, `Recall@5=0.8077`
- `bm25_vector`: `MRR=0.8295`, `Recall@5=0.8462`
- `bm25_vector_graph`: `MRR=0.8295`, `Recall@5=0.8846`
- `vector_quality_scope=lightweight semantic fallback; not code-specialized`

### CodeRankEmbed

- `bm25_only`: `MRR=0.7769`, `Recall@5=0.8077`
- `bm25_graph`: `MRR=0.8410`, `Recall@5=0.8077`
- `bm25_vector`: `MRR=0.9487`, `Recall@5=0.9231`
- `bm25_vector_graph`: `MRR=0.9487`, `Recall@5=0.9231`
- `vector_quality_scope=lightweight code-specialized local baseline`

## Case-Level Comparison

- CodeRankEmbed better than MiniLM:
  - `cli_eval_001`: first relevant rank `4 -> 1`
  - `eval_runner_001`: first relevant rank `5 -> 1`
- MiniLM better than CodeRankEmbed:
  - none observed
- No rank change between MiniLM and CodeRankEmbed:
  - `11` cases
- CodeRankEmbed gain over deterministic:
  - `hybrid_retrieval_001`
  - `chunking_001`
  - `vector_store_001`
  - `graph_builder_001`
  - `graph_traversal_001`
  - `fusion_001`
  - `cli_eval_001`
  - `db_migration_001`
  - `eval_metrics_001`
  - `eval_runner_001`
- CodeRankEmbed regressions vs deterministic:
  - none observed

## Conclusion

- MiniLM is still a solid real-semantic fallback.
- CodeRankEmbed is better for this repo and this dataset.
- It gives a stronger local code-retrieval baseline without needing the unsafe `7B` nomic path.
- That makes it the better local MVP default right now.

## Next Step

- Keep CodeRankEmbed as the local default code-specialized baseline.
- Only reopen the `nomic-ai/nomic-embed-code` path in a later round if hardware and disk budget are explicitly re-approved.
