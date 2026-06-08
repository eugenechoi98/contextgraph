# RESEARCH

- 2026-06-08 Phase 4B.4 official-source check:
  - Hugging Face model card for `nomic-ai/nomic-embed-code` shows the intended split usage:
    - query side uses `prompt_name="query"`
    - code or document side uses plain `encode(...)`
  - Sentence Transformers official semantic-search docs also separate query/document encoding semantics (`encode_query` / `encode_document` style guidance), so the local adapter should not force a query prompt onto indexed code chunks.
  - The architecture fallback remains `sentence-transformers/all-MiniLM-L6-v2`; it is a lightweight semantic baseline, not a code-specialized final quality bar.
