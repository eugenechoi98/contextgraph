# DEPLOYMENT

## Canonical Workspace

唯一正式工作区：`D:\contextgraph-studio`

每轮开始前先执行：

```powershell
Get-Location
git rev-parse --show-toplevel
```

两者都必须指向 `D:\contextgraph-studio`。

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe serve --host 127.0.0.1 --port 8000
```

## 常用命令

```powershell
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe index .
.\.venv\Scripts\cgstudio.exe retrieve "verify token auth flow" --task-hint security_auth --max-tokens 8000 --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2
.\.venv\Scripts\cgstudio.exe eval --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2 --dataset eval\fixtures\contextgraph_golden.json
.\.venv\Scripts\python.exe -m pytest tests
```

## 当前数据库

- canonical DB：`.data/contextgraph.db`
- 当前正式 repo_id：`8bf02440-5d4e-5fa2-8916-a955c2c21fd2`
- 当前 DB 已从 C 快照主库迁入 D 盘

## 当前验证基线

- `pytest tests` -> `85 passed, 1 warning`
- `cgstudio index .` -> `parse_errors = 0`
- `cgstudio retrieve ...` -> `retrieval_strategy = ["bm25", "graph"]`
- `cgstudio eval ...` -> `13 active cases`, `failed_case_count = 0`

## Real Embedding Smoke Guardrails

- Use the project venv Python: `.\.venv\Scripts\python.exe`
- Keep model cache outside the repo, for example:
  - `D:\contextgraph-model-cache`
- When a real sentence-transformer smoke needs downloads on Windows, also redirect temp space off the system drive:
  - `TEMP`
  - `TMP`
  - `HF_HOME`
  - `SENTENCE_TRANSFORMERS_HOME`
- Do not write model cache, temp artifacts, or reports into Git-tracked paths.
- Back up `D:\contextgraph-studio\.data\contextgraph.db` before any canonical embedding rebuild.
- If `nomic-ai/nomic-embed-code` is not safely runnable locally, use `sentence-transformers/all-MiniLM-L6-v2` only as a lightweight semantic fallback baseline and record that scope explicitly in eval output.
- For `nomic-ai/CodeRankEmbed`:
  - pin revision `3c4b60807d71f79b43f3c4363786d9493691f8b1`
  - keep `EMBEDDING_TRUST_REMOTE_CODE=false` by default
  - only turn it on explicitly for reviewed CodeRankEmbed smoke / rebuild / eval runs
  - return to `EMBEDDING_LOCAL_FILES_ONLY=true` after the first download smoke

## 注意事项

- deterministic embedding only validates the pipeline and keeps `vector_quality_valid=false`
- the current real semantic fallback baseline records `vector_quality_valid=true` with scope `lightweight semantic fallback; not code-specialized`
- the current local code-specialized baseline records `vector_quality_valid=true` with scope `lightweight code-specialized local baseline`
- `eval/fixtures` 与 `eval/reports` 不会被索引
- `cgstudio mcp` 的协议可用性以 MCP stdio integration tests 为准
- `C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph` 仅保留为迁移来源快照，不再运行测试、index、eval、serve 或 mcp
