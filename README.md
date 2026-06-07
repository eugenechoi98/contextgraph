# ContextGraph Studio

ContextGraph Studio 是一个面向 AI Coding Agent 的工程化上下文检索底座。当前正式工作区已经固定为 `D:\contextgraph-studio`。

## 当前能力

- repository / scan_run 正式索引主链
- Python AST parser 与结构化 chunking
- SQLite `files / entities / chunks / traces / embeddings / relations / eval_runs`
- FTS5 / BM25
- 可选 vector recall
- 可选 graph recall
- RRF 融合
- schema-first `ContextPack`
- CLI / FastAPI / MCP stdio server
- golden dataset eval runner
- eval ablation route diagnostics (`requested / executed / participating`)
- planner-driven source-code BM25 candidate lane

## Canonical Workspace

- 正式工作区：`D:\contextgraph-studio`
- 迁移来源快照：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`

后续开发、测试、index、eval、serve、mcp 只允许在 D 盘执行。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\cgstudio.exe init-db
.\.venv\Scripts\cgstudio.exe index .
.\.venv\Scripts\cgstudio.exe retrieve "verify token auth flow" --task-hint security_auth --max-tokens 8000 --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2
.\.venv\Scripts\cgstudio.exe eval --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2 --dataset eval\fixtures\contextgraph_golden.json --max-cases 5
```

## 当前验证状态

- `pytest --collect-only -q tests` -> `59 collected`
- `pytest tests` -> `67 passed`
- `cgstudio index .` -> `parse_errors = 0`
- `cgstudio eval ...` -> `failed_case_count = 0`

## 注意事项

- deterministic embedding 只用于离线开发与流程校验
- `vector_quality_valid=false` 是预期行为
- intake 默认排除 `.tmp*`、`tmp_pytest*`、`eval/fixtures`、`eval/reports`
- `chunking_001` 当前仍是 lexical miss，`chunker.py` 不在 BM25 top 30，因此本轮未启用 Code Seed Reserve
- `chunking_001` 已通过 source-code candidate lane 提升为 critical hit，但这不代表 graph 或 semantic vector 质量已被证明提升
