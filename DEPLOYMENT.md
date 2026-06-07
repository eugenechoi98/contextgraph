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
.\.venv\Scripts\cgstudio.exe eval --repo-id 8bf02440-5d4e-5fa2-8916-a955c2c21fd2 --dataset eval\fixtures\contextgraph_golden.json --max-cases 5
.\.venv\Scripts\python.exe -m pytest tests
```

## 当前数据库

- canonical DB：`.data/contextgraph.db`
- 当前正式 repo_id：`8bf02440-5d4e-5fa2-8916-a955c2c21fd2`
- 当前 DB 已从 C 快照主库迁入 D 盘

## 当前验证基线

- `pytest --collect-only -q tests` -> `59 collected`
- `pytest tests` -> `59 passed`
- `cgstudio index .` -> `parse_errors = 0`
- `cgstudio retrieve ...` -> `retrieval_strategy = ["bm25", "graph"]`
- `cgstudio eval ... --max-cases 5` -> `failed_case_count = 0`

## 注意事项

- deterministic embedding 只用于离线开发和测试
- `vector_quality_valid=false` 是预期行为
- `eval/fixtures` 与 `eval/reports` 不会被索引
- `cgstudio mcp` 的协议可用性以 MCP stdio integration tests 为准
- `C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph` 仅保留为迁移来源快照，不再运行测试、index、eval、serve 或 mcp