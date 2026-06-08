# FTS Query Safety Root Cause

## Current Behavior Before Phase 4E-C.2

`contextgraph_studio/services/retriever.py` built an FTS5 `MATCH` expression by extracting raw terms with:

```text
[A-Za-z0-9_./-]+
```

Then it joined those terms with `OR`.

That meant natural-language queries containing dotted identifiers could produce tokens such as:

- `astropy.modeling`
- `astropy.modeling.separable`
- `m.Linear1D`
- `m.Pix2Sky_TAN`

SQLite FTS5 treats `.` as syntax, not as a normal token character. The official Astropy query therefore failed with:

```text
fts5: syntax error near "."
```

## Old Fallback Problem

When FTS failed, the old fallback used `LIKE` clauses and assigned every row a fixed score:

```text
0.1
```

It also had no explicit relevance ordering. Results were therefore effectively ordered by database/storage behavior, which pushed unrelated early chunks such as CircleCI config, issue templates, and PyInstaller helpers into the candidate pool.

## Lane Impact

The following lanes all reused the same `search_bm25` helper:

- general
- source_code
- schema
- config

So the dotted-token bug and unranked fallback could affect every BM25 candidate lane.

## Phase 4E-C.2 Fix Scope

This phase adds a centralized FTS query normalizer and a deterministic ranked fallback.

It does not change:

- BM25 weights
- RRF
- Graph traversal
- Token Budget
- parser behavior
- embedding behavior
- query expansion

The index-reuse performance issue remains confirmed but deferred.
