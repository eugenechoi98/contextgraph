# ContextGraph Studio

ContextGraph Studio is local context-retrieval infrastructure for AI coding agents.

Repository: https://github.com/eugenechoi98/contextgraph

It indexes a repository, builds searchable code/document chunks, and returns a structured `ContextPack` through CLI, FastAPI, or MCP. It is not a general RAG chatbot and it does not include a chat UI.

Default mode does not require an LLM API key, does not download an embedding model, and does not require `trust_remote_code`.

## What It Is

ContextGraph Studio helps coding agents find the files, symbols, traces, and graph neighbors that matter for a development task.

Main entry points:

- CLI: `cgstudio index`, `cgstudio retrieve`, `cgstudio eval`
- API: FastAPI routes for scan, retrieve, trace, and health
- MCP: stdio tools for agent clients

## Why It Exists

Large coding tasks often fail because the agent misses the right files before it starts editing. ContextGraph Studio focuses on that earlier step: building a reproducible local index and returning a compact context pack that an agent can use.

## Core Capabilities

- Repository scanner with intake exclusions for eval fixtures, reports, temp files, caches, and generated outputs
- SQLite storage for files, entities, chunks, traces, eval runs, embeddings, and relations
- FTS5 BM25 retrieval
- Source-code, schema, and config candidate lanes
- Python AST parser, including module-level static assignment chunks
- TypeScript / TSX / JavaScript / JSX Tree-sitter parser
- SQL parser and JSON / YAML / TOML config parser
- Optional graph retrieval, weighted RRF fusion, and token budgeting
- Optional local vector search
- CLI, FastAPI, and MCP stdio integration
- Golden-dataset eval and lightweight SWE-bench Lite localization smoke

## Architecture Overview

```text
repository scan
  -> source classification
  -> parser layer
  -> structure-aware chunks
  -> SQLite / FTS5 / optional embeddings / graph relations
  -> BM25 / optional vector / optional graph recall
  -> weighted RRF
  -> token budget
  -> ContextPack
```

`files`, `entities`, and `chunks` are the content source of truth. `chunks_fts`, `embeddings`, `relations`, `traces`, and `eval_runs` are derived or supporting layers.

## Quick Start

Development install from a source checkout:

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe index .
.\.venv\Scripts\cgstudio.exe retrieve "verify token auth flow"
```

Linux / macOS:

```bash
python -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/cgstudio init-db
./.venv/bin/cgstudio index .
./.venv/bin/cgstudio retrieve "verify token auth flow"
```

PyPI publication is pending. Until then, release artifact validation uses a local wheel:

```powershell
python -m pip install <local-wheel>
cgstudio --help
```

Verified local `uvx` smoke:

```powershell
uvx --from <local-wheel> cgstudio --help
```

After PyPI publication, the planned command shape is:

```powershell
uvx --from contextgraph-studio cgstudio --help
```

## CLI Usage

Common commands:

```powershell
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe index .
.\.venv\Scripts\cgstudio.exe retrieve "update login route token verification" --task-hint api_endpoint --max-tokens 4000
.\.venv\Scripts\cgstudio.exe get-trace <trace-id>
.\.venv\Scripts\cgstudio.exe serve --host 127.0.0.1 --port 8000
```

Debug commands are also available for BM25, vector, and graph search.

## MCP Integration

ContextGraph Studio exposes a stdio MCP server:

```powershell
.\.venv\Scripts\cgstudio.exe mcp
```

Supported MCP tools:

- `retrieve_context`
- `scan_repo`
- `get_trace`

Example client config:

- [examples/mcp/claude_desktop_config.json](examples/mcp/claude_desktop_config.json)

Replace the `command` value with the absolute path to your local `cgstudio` executable.

MCP stdio protocol integration is tested with the official Python MCP SDK. Claude Code, Cursor, and other MCP-capable clients can use the same tools, but client-specific setup depends on your local installation.

## Optional Local Vector Search

Default mode is BM25 + Graph and performs no model download:

```env
VECTOR_INDEX_ENABLED=false
HYBRID_VECTOR_ENABLED=false
```

Recommended local code-specialized vector baseline:

- model: `nomic-ai/CodeRankEmbed`
- revision: `3c4b60807d71f79b43f3c4363786d9493691f8b1`
- cache location: outside this repository
- requires explicit `EMBEDDING_TRUST_REMOTE_CODE=true`

Lightweight fallback:

- `sentence-transformers/all-MiniLM-L6-v2`

Deferred high-resource target:

- `nomic-ai/nomic-embed-code`

## Eval

Run the local golden dataset:

```powershell
.\.venv\Scripts\cgstudio.exe eval --repo-id <repo-id> --dataset eval\fixtures\contextgraph_golden.json
```

Eval records route diagnostics so reports can distinguish requested, executed, and participating retrieval routes.

## SWE-bench Lite Localization

ContextGraph Studio includes a lightweight localization smoke, not the full SWE-bench harness.

It can inspect SWE-bench Lite rows and run up to three isolated localization cases:

```powershell
.\.venv\Scripts\cgstudio.exe swebench-localize `
  --manifest eval\manifests\generated\swebench_lite_manifest.json `
  --cache-dir <swebench-cache-dir> `
  --dry-run
```

Boundaries:

- no patch apply
- no Docker
- no target repository tests
- no dependency install in target repositories
- no full 300-case benchmark
- GitHub checkout requires explicit `--allow-network`
- SWE-bench cache and per-instance SQLite DBs must stay outside tracked source paths

Latest three-instance smoke recovered critical hits for Astropy, Django, and Matplotlib after adding Python module-level assignment chunks. See `eval/analysis/` for the detailed reports.

Early localization evidence:

- official SWE-bench Lite smoke sample: `3` instances
- critical hit rate: `3 / 3`
- Astropy rank: `1`
- Django rank: `7`
- Matplotlib rank: `2`

This is an early localization smoke, not a full SWE-bench Lite benchmark. It does not execute patches, run target tests, or use a Docker harness.

Current-machine performance evidence only:

- Astropy unchanged snapshot reuse improved from about `20.9 min` to about `4.4 min`
- relative improvement: about `79%`
- this is not a general SLA

## Security And Data Boundaries

Default behavior:

- does not execute target repository code
- does not install target repository dependencies
- does not run target repository tests
- does not apply patches
- does not run Docker
- does not download embeddings
- does not require API keys

Sensitive config and assignment handling is key-name based. Obvious sensitive names such as `password`, `secret`, `token`, `api_key`, `private_key`, and `credential` keep the key or symbol searchable but do not write raw values into chunks, traces, or ContextPacks.

## Known Limitations

- Parser coverage is intentionally minimal and static.
- TypeScript / JavaScript route detection only supports clear static Express-like patterns.
- SQL parsing covers small `CREATE` statement patterns.
- Config parsing uses simple path extraction for arrays such as `servers[].host`.
- Graph relation types such as `uses_table`, `configures`, and `cross_lang_calls` are not implemented yet.
- Optional vector quality depends on explicit local model configuration.

## Roadmap

Deferred items:

- `nomic-ai/nomic-embed-code` 7B local smoke
- `uses_table`
- `configures`
- `cross_lang_calls`
- complete 300-case SWE-bench Lite benchmark
- Docker harness
- patch apply
- target repository tests
- frontend Studio
- PyPI release

## Development

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

GitHub Actions CI runs a lightweight no-model validation:

- checkout
- setup Python
- `pip install -e .[dev]`
- `pytest tests`

Before publishing changes, check that generated DBs, reports, caches, `.env`, third-party checkouts, and model files are not tracked.

## License

MIT
