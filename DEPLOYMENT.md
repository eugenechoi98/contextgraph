# DEPLOYMENT

## Canonical Workspace

Only official workspace:

`D:\contextgraph-studio`

Always check first:

```powershell
Get-Location
git rev-parse --show-toplevel
```

Both must point to `D:\contextgraph-studio`.

## Default startup mode

Default behavior stays safe and lightweight:

```env
VECTOR_INDEX_ENABLED=false
HYBRID_VECTOR_ENABLED=false
```

That means:

- no automatic model download
- no `trust_remote_code` requirement
- BM25 + Graph still work

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe serve --host 127.0.0.1 --port 8000
```

## Common commands

```powershell
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe index .
.\.venv\Scripts\cgstudio.exe retrieve "verify token auth flow" --task-hint security_auth --max-tokens 8000 --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2
.\.venv\Scripts\cgstudio.exe eval --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2 --dataset eval\fixtures\contextgraph_golden.json
.\.venv\Scripts\python.exe -m pytest tests
```

## Current canonical DB

- DB: `.data/contextgraph.db`
- repo_id: `8bf02440-5d4e-5fa2-8916-a955c2c21fd2`

## Current validation baseline

- `pytest tests` -> `102 passed, 1 warning`
- `cgstudio index .` -> `parse_errors = 0`
- `cgstudio retrieve ...` -> BM25 + Graph works in default mode
- `cgstudio eval ...` -> `13 active cases`, `failed_case_count = 0`
- offline CodeRankEmbed eval metadata records `model_smoke_status = coderankembed_smoke_passed`
- `cgstudio index tests\fixtures\sample_ts_repo` -> `files=7`, `chunks=20`, `entities=27`, `relations=45`

## TypeScript / JavaScript parser scope

Current parser support covers:

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

Current limits:

- route detection only supports clear static Express-like registrations
- dynamic route builders are skipped
- `tests/fixtures` is excluded from normal canonical workspace indexing
- fixture repos can still be indexed directly when they are used as the repo root

## Model policy

### Recommended local code-specialized baseline

- model: `nomic-ai/CodeRankEmbed`
- revision: `3c4b60807d71f79b43f3c4363786d9493691f8b1`
- license: `MIT`
- dimension: `768`
- scope: `lightweight code-specialized local baseline`

Rules:

- cache must stay outside the repo
- `trust_remote_code=true` must be explicitly enabled
- revision must stay pinned
- first download uses `EMBEDDING_LOCAL_FILES_ONLY=false`
- normal later use should switch back to `EMBEDDING_LOCAL_FILES_ONLY=true`

### Lightweight fallback

- model: `sentence-transformers/all-MiniLM-L6-v2`
- scope: `lightweight semantic fallback; not code-specialized`

### Deferred high-resource target

- model: `nomic-ai/nomic-embed-code`
- status: deferred on current hardware

## Cache and safety rules

- Use the project venv Python: `.\.venv\Scripts\python.exe`
- Keep model cache outside the repo, for example:
  - `D:\contextgraph-model-cache`
- On Windows, redirect temp space off the system drive when doing the first download smoke:
  - `TEMP`
  - `TMP`
  - `HF_HOME`
  - `SENTENCE_TRANSFORMERS_HOME`
- Do not write model cache, temp files, or eval reports into Git-tracked paths.

## Why `trust_remote_code` needs care

Some models, including CodeRankEmbed, load custom Python code from the model repo.

That is why this project requires:

- pinned revision
- explicit `EMBEDDING_TRUST_REMOTE_CODE=true`
- a small manual review before adoption

It should never be treated as a silent default.

## How to back up the canonical DB

Before rebuilding embeddings:

```text
D:\contextgraph-studio\.data\contextgraph.db
```

Copy it to:

```text
D:\contextgraph-backups\<timestamp>\
```

## How to rebuild embeddings

1. Choose the model explicitly in env vars or `.env`.
2. Make sure cache is outside the repo.
3. Run:

```powershell
.\.venv\Scripts\cgstudio.exe index .
```

## How to return to default BM25 + Graph mode

Disable vector env vars again:

```env
VECTOR_INDEX_ENABLED=false
HYBRID_VECTOR_ENABLED=false
```

Then re-run:

```powershell
.\.venv\Scripts\cgstudio.exe index .
```

## Smoke reference only

The numbers below are current-machine smoke data only:

- CodeRankEmbed rebuild: about `35.74 s`
- CodeRankEmbed cache size after download: about `640 MB`

They are reference numbers, not a general SLA.
