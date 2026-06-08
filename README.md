# ContextGraph Studio

ContextGraph Studio is a local retrieval stack for AI coding agents. The canonical workspace is `D:\contextgraph-studio`.

## What works now

- Repository indexing with `files / entities / chunks / traces / embeddings / relations / eval_runs`
- Python plus minimal TypeScript / JavaScript parsing for `.ts`, `.tsx`, `.js`, and `.jsx`
- Minimal structured parsing for `.sql`, `.json`, `.yaml`, `.yml`, and `.toml`
- BM25 retrieval
- Optional graph retrieval
- Optional vector retrieval
- RRF fusion
- Golden-dataset eval

## Default mode

Default startup is still the safe no-model path:

```env
VECTOR_INDEX_ENABLED=false
HYBRID_VECTOR_ENABLED=false
```

That means:

- no embedding model download
- no `trust_remote_code` requirement
- BM25 + Graph can still run

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe index .
.\.venv\Scripts\cgstudio.exe retrieve "verify token auth flow" --task-hint security_auth --max-tokens 8000 --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2
```

## TypeScript / JavaScript support

The current MVP parser loop supports:

- `.ts`
- `.tsx`
- `.js`
- `.jsx`

Current extracted entities:

- `module`
- `class`
- `function`
- `method`
- `api_route`

Current extracted relations:

- `contains`
- `imports`
- `calls`
- `route_to_handler`

Route extraction is intentionally narrow. It only covers clear static Express-like patterns such as `router.post("/login", loginHandler)`.

## SQL and config support

The current structured parser loop also supports:

- `.sql`
- `.json`
- `.yaml`
- `.yml`
- `.toml`

Current extracted structured entities:

- `db_table`
- `db_view`
- `db_index`
- `config_key`

Current limits:

- SQL only covers small `CREATE` statement parsing
- config arrays use a simple `[]` path notation such as `servers[].host`
- this phase does not add `uses_table` or `configures`
- sensitive config values are masked and are not stored as raw chunk text

Database and configuration task hints are now supported by the planner:

- `task_hint=database` prioritizes schema files and can run a bounded `schema` BM25 candidate lane
- `task_hint=configuration` prioritizes config files and can run a bounded `config` BM25 candidate lane
- obvious database/configuration keywords can classify the task when no explicit hint is supplied

These lanes only add candidates. They do not change BM25 scoring, RRF, graph traversal, token budget, or the public `ContextPack` schema.

## Recommended local vector model

Current recommended local code-specialized semantic baseline:

- model: `nomic-ai/CodeRankEmbed`
- revision: `3c4b60807d71f79b43f3c4363786d9493691f8b1`
- license: `MIT`
- dimension: `768`
- device used in this repo smoke: `cpu`
- query prefix: `Represent this query for searching relevant code:`

Important:

- it is only loaded when you explicitly enable vector indexing
- `trust_remote_code=true` must be explicitly enabled
- cache must live outside the repo
- after the first download, normal local use should switch back to `EMBEDDING_LOCAL_FILES_ONLY=true`

Example config is in [.env.example](/D:/contextgraph-studio/.env.example).

## Lightweight fallback

If you want a lighter real semantic fallback instead of the code-specialized baseline:

- model: `sentence-transformers/all-MiniLM-L6-v2`
- scope: `lightweight semantic fallback; not code-specialized`

## High-resource deferred target

Long-term target model kept deferred on current hardware:

- `nomic-ai/nomic-embed-code`

It is not the current default because this machine is still a poor fit for a safe local `7B` smoke.

## Current smoke reference numbers

These are current-machine smoke numbers only. They are not a general SLA.

- CodeRankEmbed rebuild on this machine: about `35.74 s`
- Cache footprint after download: about `640 MB`
- 13-case eval: CodeRankEmbed beat MiniLM on this repo

## Current validation status

- `pytest tests` -> `111 passed, 1 warning`
- `cgstudio eval ...` -> `13 active cases`, `failed_case_count = 0`
- offline CodeRankEmbed eval metadata now records `model_smoke_status = coderankembed_smoke_passed`
- `cgstudio index tests\fixtures\sample_ts_repo` -> `files=7`, `chunks=20`, `entities=27`, `relations=45`
- `cgstudio index tests\fixtures\sample_structured_repo` -> `files=7`, `chunks=29`, `entities=32`, `relations=25`, `parse_errors=2`
- `cgstudio eval --dataset eval\fixtures\structured_golden.json --config bm25_only --config bm25_graph` -> `4 active cases`, `failed_case_count = 0`
