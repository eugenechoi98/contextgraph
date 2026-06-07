# ContextGraph Studio — Engineering Design Document v1.0

> **定位**：面向 AI Coding Agent（Claude Code / Codex / Cursor）的开源上下文检索基础设施。  
> **目标读者**：开发者自己，以及开源社区贡献者。  
> **阶段**：MVP（单机，本地 repo，Python 后端，MCP server 输出）

---

## 0. 产品边界与交付物

### MVP 必须交付
| 交付物 | 说明 |
|--------|------|
| `cgstudio index <path>` | CLI 索引命令，扫描本地 repo 并写入 SQLite |
| `cgstudio serve` | 启动 FastAPI + MCP server |
| MCP tool: `retrieve_context` | 输入 query+task_type，输出 Context Pack JSON |
| MCP tool: `scan_repo` | 触发/查询索引进度 |
| MCP tool: `get_trace` | 根据 trace_id 返回检索溯源信息 |
| Eval runner | `cgstudio eval --repo <path>` 跑 ablation，输出 Markdown 报告 |

### MVP 不做
- 自动改代码 / PR review
- 企业权限系统
- 完整 IDE 插件
- 多模态文档 OCR
- 分布式向量库
- 全语言支持（先支持 Python、TypeScript/JavaScript、Markdown、SQL、JSON/YAML）

---

## 1. 系统定位与用户流程

```
用户在 Claude Code / Cursor 写任务描述
  → MCP client 调用 retrieve_context(query, task_hint)
  → ContextGraph 返回 Context Pack（结构化 JSON）
  → AI Coding Agent 把 Required 文件加入 context window
  → Agent 编码，减少幻觉，减少遗漏关键文件
```

索引流程（独立触发，非实时）：
```
cgstudio index ./my-repo
  → 扫描文件 → 分类 → 解析 AST → chunking → embedding → 写 SQLite
  → 完成后打印 scan_run_id
```

---

## 2. 接口契约（先定接口，再写实现）

### 2.1 MCP Tool: retrieve_context

**输入**
```json
{
  "query": "Add JWT refresh token support to the auth flow",
  "task_hint": "auth",
  "repo_id": "myapp-v2",
  "max_tokens": 8000,
  "trace": true
}
```

**输出：Context Pack（固定 schema，不可随意扩展）**
```json
{
  "trace_id": "tr_abc123",
  "task_type": "security_auth",
  "retrieval_strategy": ["bm25", "vector", "graph"],
  "token_estimate": 6240,
  "required": [
    {
      "file_path": "src/auth/jwt_handler.py",
      "entity": "JWTHandler.verify_token",
      "reason": "Direct match: JWT token verification logic",
      "chunk_kind": "symbol",
      "line_start": 42,
      "line_end": 89,
      "score": 0.94,
      "graph_distance": 0
    }
  ],
  "supporting": [...],
  "graph_paths": [
    {
      "from": "src/routes/auth.py::login_route",
      "to": "src/auth/jwt_handler.py::JWTHandler.verify_token",
      "edge_type": "calls",
      "hops": 1
    }
  ],
  "risk_notes": [
    "src/middleware/auth_middleware.py may also need updating — calls verify_token"
  ],
  "suggested_tests": [
    "tests/test_jwt_handler.py::test_verify_expired_token"
  ]
}
```

> **规则**：schema 在 `contextgraph/models/context_pack.py` 中用 Pydantic 定义，所有下游模块必须返回这个模型实例，不允许返回 dict。

### 2.2 task_type 枚举（硬编码配置文件）

文件：`contextgraph/config/task_strategies.yaml`

```yaml
task_types:
  security_auth:
    keywords: ["auth", "jwt", "token", "session", "login", "oauth", "permission", "role"]
    priority_entity_types: ["api_route", "function", "class"]
    priority_categories: ["source_code", "test"]
    graph_expand_edge_types: ["calls", "imports"]
    graph_hops: 2
    required_relations: ["tests", "calls"]
    bm25_weight: 0.4
    vector_weight: 0.35
    graph_weight: 0.25

  database:
    keywords: ["migration", "schema", "model", "repository", "query", "orm"]
    priority_entity_types: ["db_table", "class", "function"]
    priority_categories: ["schema", "source_code", "test"]
    graph_expand_edge_types: ["uses_table", "calls"]
    graph_hops: 2
    bm25_weight: 0.3
    vector_weight: 0.3
    graph_weight: 0.4

  ui_component:
    keywords: ["component", "render", "props", "state", "hook", "style", "css"]
    priority_entity_types: ["function", "class"]
    priority_categories: ["source_code", "config"]
    graph_expand_edge_types: ["imports", "calls"]
    graph_hops: 1
    bm25_weight: 0.35
    vector_weight: 0.45
    graph_weight: 0.2

  refactor:
    keywords: ["refactor", "rename", "extract", "move", "restructure"]
    priority_entity_types: ["function", "class", "method"]
    graph_expand_edge_types: ["calls", "imports", "tests"]
    graph_hops: 2
    required_relations: ["callers", "tests"]
    bm25_weight: 0.25
    vector_weight: 0.35
    graph_weight: 0.4

  bug_fix:
    keywords: ["bug", "error", "exception", "crash", "fix", "issue"]
    priority_entity_types: ["function", "method"]
    graph_expand_edge_types: ["calls", "tests"]
    graph_hops: 2
    bm25_weight: 0.45
    vector_weight: 0.35
    graph_weight: 0.2

  api_endpoint:
    keywords: ["endpoint", "route", "handler", "request", "response", "middleware"]
    priority_entity_types: ["api_route", "function"]
    graph_expand_edge_types: ["route_to_handler", "calls", "uses_table"]
    graph_hops: 2
    bm25_weight: 0.4
    vector_weight: 0.3
    graph_weight: 0.3

  testing:
    keywords: ["test", "mock", "fixture", "assert", "coverage"]
    priority_entity_types: ["test_case", "function"]
    priority_categories: ["test", "source_code"]
    graph_expand_edge_types: ["tests", "calls"]
    graph_hops: 1
    bm25_weight: 0.35
    vector_weight: 0.4
    graph_weight: 0.25

  configuration:
    keywords: ["config", "env", "setting", "deploy", "docker", "ci"]
    priority_entity_types: ["config_key"]
    priority_categories: ["config", "doc"]
    graph_expand_edge_types: ["configures"]
    graph_hops: 1
    bm25_weight: 0.5
    vector_weight: 0.3
    graph_weight: 0.2

  general:
    keywords: []
    priority_entity_types: ["function", "class", "api_route"]
    graph_expand_edge_types: ["calls", "imports"]
    graph_hops: 1
    bm25_weight: 0.35
    vector_weight: 0.45
    graph_weight: 0.2
```

---

## 3. 数据模型（SQLite Schema）

### 3.1 核心表

```sql
-- 仓库注册
CREATE TABLE repositories (
  id TEXT PRIMARY KEY,          -- repo_id: "owner-repo-branch"
  local_path TEXT NOT NULL,
  remote_url TEXT,
  default_branch TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

-- 扫描任务（每次 index 一条）
CREATE TABLE scan_runs (
  id TEXT PRIMARY KEY,          -- UUID
  repo_id TEXT NOT NULL REFERENCES repositories(id),
  commit_sha TEXT,
  started_at INTEGER NOT NULL,
  finished_at INTEGER,
  status TEXT NOT NULL,         -- 'running' | 'done' | 'failed'
  stats_json TEXT               -- {"files":120,"chunks":890,"nodes":1200,"edges":3400}
);

-- 文件记录
CREATE TABLE files (
  id TEXT PRIMARY KEY,          -- UUID
  scan_run_id TEXT NOT NULL REFERENCES scan_runs(id),
  repo_id TEXT NOT NULL,
  file_path TEXT NOT NULL,      -- 相对路径，统一用 /
  language TEXT,                -- 'python' | 'typescript' | 'sql' | 'markdown' | ...
  category TEXT NOT NULL,       -- 'source_code' | 'test' | 'doc' | 'config' | 'schema' | 'generated' | 'asset'
  size_bytes INTEGER,
  line_count INTEGER,
  content_hash TEXT NOT NULL,   -- SHA256，用于增量更新去重
  is_excluded INTEGER DEFAULT 0 -- 被过滤掉的文件仍然记录，只是不建 chunk
);
CREATE INDEX idx_files_repo_path ON files(repo_id, file_path);
CREATE INDEX idx_files_hash ON files(content_hash);

-- 图节点（代码实体）
CREATE TABLE entities (
  id TEXT PRIMARY KEY,           -- UUID
  file_id TEXT NOT NULL REFERENCES files(id),
  repo_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,     -- 'file'|'module'|'class'|'function'|'method'|'api_route'|'db_table'|'config_key'|'test_case'|'doc_section'
  symbol_name TEXT,              -- 完整限定名，如 "AuthService.verify_token"
  display_name TEXT,             -- 短名，如 "verify_token"
  line_start INTEGER,
  line_end INTEGER,
  signature TEXT,                -- 函数签名/类声明
  docstring TEXT,
  language TEXT,
  content_hash TEXT
);
CREATE INDEX idx_entities_file ON entities(file_id);
CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_symbol ON entities(symbol_name);

-- 图边（代码关系）
CREATE TABLE relations (
  id TEXT PRIMARY KEY,
  scan_run_id TEXT NOT NULL,
  from_entity_id TEXT NOT NULL REFERENCES entities(id),
  to_entity_id TEXT NOT NULL REFERENCES entities(id),
  edge_type TEXT NOT NULL,   -- 'contains'|'imports'|'calls'|'tests'|'documents'|'route_to_handler'|'uses_table'|'configures'|'depends_on'|'inherits'
  is_directed INTEGER DEFAULT 1,
  weight REAL DEFAULT 1.0,   -- 调用频次/重要性权重，默认1.0
  meta_json TEXT             -- 额外信息，如调用次数、import alias
);
CREATE INDEX idx_relations_from ON relations(from_entity_id, edge_type);
CREATE INDEX idx_relations_to ON relations(to_entity_id, edge_type);

-- 检索单元（chunks）
CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  entity_id TEXT REFERENCES entities(id),
  file_id TEXT NOT NULL REFERENCES files(id),
  repo_id TEXT NOT NULL,
  scan_run_id TEXT NOT NULL,
  chunk_kind TEXT NOT NULL,      -- 'file_summary'|'symbol'|'doc_section'|'schema_unit'|'dir_summary'
  content TEXT NOT NULL,
  tokens_estimate INTEGER NOT NULL,
  line_start INTEGER,
  line_end INTEGER,
  content_hash TEXT NOT NULL,
  embedding_model TEXT,          -- 记录用什么模型生成 embedding，便于迁移
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_chunks_file ON chunks(file_id);
CREATE INDEX idx_chunks_entity ON chunks(entity_id);
CREATE INDEX idx_chunks_kind ON chunks(chunk_kind);

-- FTS5 虚拟表
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  content,
  symbol_name,
  file_path,
  content='chunks',
  content_rowid='rowid'
);

-- 检索 Trace
CREATE TABLE traces (
  id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL,
  query TEXT NOT NULL,
  task_type TEXT,
  retrieval_strategy_json TEXT,   -- ["bm25","vector","graph"]
  bm25_hits_json TEXT,
  vector_hits_json TEXT,
  graph_hits_json TEXT,
  reranker_scores_json TEXT,
  final_selection_json TEXT,
  filtered_out_json TEXT,
  token_estimate INTEGER,
  latency_ms INTEGER,
  index_version TEXT,             -- scan_run_id
  created_at INTEGER NOT NULL
);

-- Eval 记录
CREATE TABLE eval_runs (
  id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL,
  eval_dataset TEXT NOT NULL,     -- 数据集名，如 "swe-bench-lite"
  config_json TEXT,               -- ablation 配置
  results_json TEXT,              -- Recall@K, Precision@K, MRR, ...
  created_at INTEGER NOT NULL
);
```

### 3.2 向量存储

**MVP 方案（numpy + SQLite blob）**

```python
# 独立表存 embedding，chunk_id 关联 chunks 表
CREATE TABLE embeddings (
  chunk_id TEXT PRIMARY KEY REFERENCES chunks(id),
  embedding BLOB NOT NULL,        -- numpy float32 array，tobytes() 存储
  model TEXT NOT NULL,
  dim INTEGER NOT NULL
);
```

加载时：`np.frombuffer(row["embedding"], dtype=np.float32)`

**当 chunks > 50万时迁移到 LanceDB**（同一接口，只换底层）

---

## 4. 解析层设计

### 4.1 语言支持矩阵（MVP 范围）

| 语言 | 解析器 | 提取实体 | 提取关系 |
|------|--------|----------|----------|
| Python | `ast` (stdlib) | function, class, method, import | imports, calls (静态), inherits |
| TypeScript/JS | `tree-sitter-typescript` | function, class, method, api_route | imports, calls |
| SQL | 自研简单 regex+parser | db_table, db_view, db_index | — |
| Markdown | heading/link parser | doc_section | documents |
| JSON/YAML/TOML | stdlib | config_key | configures |

> 注意：`calls` 关系对动态语言只做静态近似，不保证完全准确。在 Context Pack 的 risk_notes 中标注。

### 4.2 Python AST 解析示例接口

```python
@dataclass
class ParseResult:
    entities: list[EntityRecord]
    relations: list[RelationRecord]
    parse_errors: list[str]      # 软错误，不中断流程
    language: str
    parser_version: str

class PythonParser:
    def parse(self, file_path: str, content: str, file_id: str) -> ParseResult:
        ...
```

### 4.3 Chunking 决策树

```
entity_type == 'function' or 'method'
  → token_count(body) <= 512?
      YES → 整体作为一个 symbol chunk
      NO  → class_header + 每个 method 各一个 chunk（保留类名上下文）

entity_type == 'class'
  → 生成 class_summary chunk（签名 + docstring + method 列表）
  → 每个 method 单独生成 symbol chunk（包含 class 名前缀）

entity_type == 'file'
  → 生成 file_summary chunk（路径、语言、分类、导出符号列表、import 列表）

directory
  → 目录下所有 file_summary 聚合 → dir_summary chunk（RAPTOR-like）

doc_section (Markdown)
  → heading 到下一个同级 heading 之间的内容 → doc_section chunk
  → 超过 1000 tokens 则按段落切割，保留 heading 前缀

schema_unit (SQL)
  → 每个 CREATE TABLE/VIEW/INDEX 各一个 schema_unit chunk
```

### 4.4 超长函数处理

```python
MAX_SYMBOL_TOKENS = 512

if token_count > MAX_SYMBOL_TOKENS:
    # 策略：截断 + 注释
    chunks = [
        make_chunk(content[:half], suffix="[truncated, part 1/2]"),
        make_chunk(content[half:], prefix=f"[continuation of {symbol_name}, part 2/2]"),
    ]
    # 两个 chunk 共享同一个 entity_id，在 Context Pack 组装时合并
```

---

## 5. 图谱设计

### 5.1 节点类型与属性

| 节点类型 | 关键属性 |
|----------|----------|
| `file` | path, language, category, size |
| `module` | symbol_name, exports |
| `class` | symbol_name, bases (继承列表) |
| `function` | symbol_name, signature, is_async |
| `method` | symbol_name, class_name, signature |
| `api_route` | method (GET/POST/...), path_pattern, handler |
| `db_table` | table_name, columns_json |
| `config_key` | key_path, value_type |
| `test_case` | symbol_name, targets_entity_id |
| `doc_section` | heading, level |

### 5.2 边类型、方向与权重规则

| 边类型 | 方向 | 初始权重 | 权重规则 |
|--------|------|----------|----------|
| `contains` | file → entity | 1.0 | 固定 |
| `imports` | file/module → file/module | 1.0 | 固定 |
| `calls` | function → function | 1.0 / call_count | call_count > 1 时权重 = min(call_count × 0.5, 3.0) |
| `tests` | test_case → entity | 1.5 | 测试关系重要性更高 |
| `documents` | doc_section → entity | 0.8 | 文档关联权重略低 |
| `route_to_handler` | api_route → function | 2.0 | 路由关系最关键 |
| `uses_table` | function/class → db_table | 1.5 | — |
| `configures` | config_key → entity | 1.0 | — |
| `inherits` | class → class | 1.5 | 继承关系重要 |

### 5.3 图节点评分（用于 RRF 融合）

图检索不产生自然排序分数，使用以下公式计算 graph_score：

```python
def compute_graph_score(node, seed_node_id, hop_distance, edge_type):
    base = 1.0 / (hop_distance + 1)          # 跳数衰减
    edge_bonus = EDGE_TYPE_WEIGHTS[edge_type]  # 见上表
    category_bonus = {
        "source_code": 1.0,
        "test": 0.8,
        "schema": 0.9,
        "config": 0.6,
        "doc": 0.5,
    }.get(node.category, 0.7)
    return base * edge_bonus * category_bonus
```

跳数限制：默认 2 跳（可在 task_strategies.yaml 中按 task_type 覆盖）。

### 5.4 跨语言边（MVP 可选）

Python API route → TypeScript fetch call 这类跨语言边无法静态确定，MVP 处理方式：

1. 提取所有 API route 的 path_pattern（如 `/api/auth/login`）
2. 提取 TS 代码中的 fetch/axios 字符串（正则）
3. 字符串匹配相似度 > 0.9 → 建 `cross_lang_calls` 边，权重 0.7
4. 在 Context Pack 的 `risk_notes` 标注"可能存在跨语言调用，建议人工确认"

---

## 6. Agentic Retrieval Planner 实现

### 6.1 两阶段设计

**第一阶段：Rule-based 分类（快速，无 LLM 调用）**

```python
class TaskParser:
    def classify(self, query: str, task_hint: str | None) -> TaskType:
        # 1. task_hint 直接映射（用户显式指定时优先）
        if task_hint and task_hint in TASK_TYPE_MAP:
            return TASK_TYPE_MAP[task_hint]

        # 2. 关键词打分
        query_lower = query.lower()
        scores = {}
        for task_type, config in task_strategies.items():
            score = sum(1 for kw in config.keywords if kw in query_lower)
            scores[task_type] = score

        best = max(scores, key=scores.get)
        if scores[best] >= 2:
            return best

        # 3. 降级到 general
        return "general"
```

**第二阶段：LLM 辅助（仅当规则置信度低时触发）**

```python
async def refine_with_llm(self, query: str, rule_result: TaskType) -> TaskType:
    # 仅在 rule 置信度低时调用，避免每次检索都多一次 LLM call
    prompt = TASK_CLASSIFICATION_PROMPT.format(query=query, candidates=TASK_TYPES)
    response = await llm_call(prompt, max_tokens=50)  # 只要求返回 task_type 字符串
    return response.strip()
```

> **成本控制**：LLM 分类调用只发生在规则置信度 < 2 的情况，实测约 10-20% 的 query 触发。

### 6.2 检索计划生成

```python
@dataclass
class RetrievalPlan:
    task_type: str
    bm25_queries: list[str]        # 关键词查询列表
    vector_query: str              # 向量查询文本（通常是原始 query）
    graph_seeds: list[str]         # 图遍历起始 symbol_name（从 BM25/vector 结果中提取）
    graph_edge_types: list[str]    # 允许遍历的边类型
    graph_hops: int
    weights: dict[str, float]      # {"bm25": 0.4, "vector": 0.35, "graph": 0.25}
    token_budget: int
    priority_categories: list[str]
    priority_entity_types: list[str]

def build_retrieval_plan(query, task_type_config, max_tokens) -> RetrievalPlan:
    # BM25 query 扩展：原始 query + 同义词/关键词（从 task_strategies 取）
    bm25_queries = [query] + extract_technical_terms(query)
    return RetrievalPlan(
        bm25_queries=bm25_queries,
        vector_query=query,
        graph_edge_types=task_type_config.graph_expand_edge_types,
        graph_hops=task_type_config.graph_hops,
        weights={
            "bm25": task_type_config.bm25_weight,
            "vector": task_type_config.vector_weight,
            "graph": task_type_config.graph_weight,
        },
        token_budget=max_tokens,
        ...
    )
```

---

## 7. 检索层实现

### 7.1 RRF 融合 + 图节点积分

```python
def rrf_fuse(
    bm25_results: list[ScoredChunk],
    vector_results: list[ScoredChunk],
    graph_results: list[ScoredChunk],   # 已用 compute_graph_score 打分
    weights: dict,
    k: int = 60
) -> list[ScoredChunk]:
    all_chunk_ids = set()
    for r in [bm25_results, vector_results, graph_results]:
        all_chunk_ids.update(c.id for c in r)

    scores = {}
    for chunk_id in all_chunk_ids:
        rrf_score = 0.0
        for result_list, source in [(bm25_results,"bm25"),(vector_results,"vector"),(graph_results,"graph")]:
            rank = next((i+1 for i,c in enumerate(result_list) if c.id==chunk_id), None)
            if rank:
                rrf_score += weights[source] * (1.0 / (k + rank))
        scores[chunk_id] = rrf_score

    return sorted(all_chunk_ids, key=lambda cid: scores[cid], reverse=True)
```

### 7.2 Cross-encoder Reranker（可选，后期）

MVP 先跳过 reranker，使用 RRF 输出直接进 Context Pack Builder。  
Reranker 接入点预留：在 `rrf_fuse` 之后，`build_context_pack` 之前插入。

```python
# 预留接口
class Reranker(Protocol):
    def rerank(self, query: str, chunks: list[ScoredChunk]) -> list[ScoredChunk]: ...

# MVP 默认
class IdentityReranker:
    def rerank(self, query, chunks): return chunks
```

### 7.3 Token Budget 管理

```python
def pack_within_budget(chunks, token_budget):
    packed = []
    used = 0
    for chunk in chunks:  # 已按 score 排序
        if used + chunk.tokens_estimate <= token_budget:
            packed.append(chunk)
            used += chunk.tokens_estimate
        else:
            # 尝试截断：如果是超大 chunk，取前 N tokens
            remaining = token_budget - used
            if remaining > 100:  # 至少 100 tokens 才值得截断
                packed.append(truncate_chunk(chunk, remaining))
            break
    return packed, used
```

---

## 8. Embedding 选型

### 推荐方案（按优先级）

| 方案 | 模型 | 优点 | 缺点 | 推荐场景 |
|------|------|------|------|----------|
| **首选** | `nomic-embed-code` | 开源，专为代码设计，Apache-2.0 | 需本地运行 | MVP 首选 |
| 备选 A | `voyage-code-2` | 效果最好 | 收费，API 调用 | 需要最高质量时 |
| 备选 B | `text-embedding-3-small` | 便宜，OpenAI 生态 | 非代码专用 | 已有 OpenAI 密钥时 |
| 离线 fallback | `sentence-transformers/all-MiniLM-L6-v2` | 完全离线，轻量 | 代码理解差 | 无网络环境 |

**embedding_model 字段记录在 chunks 和 embeddings 表中**，迁移模型时需要重新生成 embedding，不影响其他数据。

### 维度与存储估算

| 模型 | 维度 | 单 chunk 大小 | 10万 chunks |
|------|------|--------------|-------------|
| nomic-embed-code | 768 | 3KB | ~300MB |
| voyage-code-2 | 1024 | 4KB | ~400MB |
| MiniLM-L6-v2 | 384 | 1.5KB | ~150MB |

---

## 9. Eval 设计

### 9.1 Ground Truth 来源

**推荐：SWE-bench Lite**

每个 instance 包含：
- `repo` + `base_commit`：可以 checkout 到指定 commit
- `problem_statement`：task description
- `patch`：正确的 diff，从中提取 `changed_files` 作为 ground truth

```python
# 从 patch 提取 changed_files
def extract_changed_files(patch: str) -> list[str]:
    return re.findall(r'^--- a/(.*)', patch, re.MULTILINE)

# Eval 流程
for instance in swe_bench_lite:
    result = retrieve_context(instance.problem_statement, repo_id)
    retrieved_files = [c.file_path for c in result.required + result.supporting]
    ground_truth = extract_changed_files(instance.patch)
    record_eval_result(instance.id, retrieved_files, ground_truth)
```

**补充：自有 repo 标注数据集**

至少标注 20 个真实任务（自己写过的 issue + 对应改动文件），形成 `eval/fixtures/myrepo_golden.json`。

### 9.2 Eval 指标

```python
@dataclass
class EvalMetrics:
    recall_at_k: dict[int, float]       # {1: 0.45, 3: 0.72, 5: 0.81}
    precision_at_k: dict[int, float]
    mrr: float                           # Mean Reciprocal Rank
    critical_file_hit_rate: float        # ground truth 文件是否在 required 中
    false_positive_rate: float
    avg_token_count: float
    missed_critical_files: list[str]     # 分析漏召回的文件

# critical_file 定义：patch 中修改行数 >= 5 的文件
# 排除 lockfile、generated file
```

### 9.3 Ablation 矩阵

| 配置名 | BM25 | Vector | Graph | Dir Summary |
|--------|------|--------|-------|-------------|
| bm25_only | ✓ | — | — | — |
| vector_only | — | ✓ | — | — |
| graph_only | — | — | ✓ | — |
| bm25_vector | ✓ | ✓ | — | — |
| bm25_vector_graph | ✓ | ✓ | ✓ | — |
| full | ✓ | ✓ | ✓ | ✓ |

Eval 报告输出为 Markdown + JSON，自动生成对比表格。

---

## 10. 项目结构

```
contextgraph/
├── cli/
│   ├── main.py                  # typer CLI: index, serve, eval, trace
│   └── commands/
├── api/
│   ├── app.py                   # FastAPI 应用
│   ├── routes/
│   │   ├── retrieve.py
│   │   ├── scan.py
│   │   └── trace.py
│   └── mcp_server.py            # MCP tool 注册
├── config/
│   ├── task_strategies.yaml     # task_type 策略配置
│   └── settings.py              # Pydantic Settings
├── models/
│   ├── context_pack.py          # Pydantic: ContextPack, ChunkResult, ...
│   ├── entities.py              # EntityRecord, RelationRecord
│   └── trace.py                 # TraceRecord, EvalResult
├── intake/
│   ├── scanner.py               # 文件扫描、过滤
│   └── classifier.py            # source/test/doc/config 分类
├── parsers/
│   ├── base.py                  # Parser Protocol
│   ├── python_parser.py         # ast 解析
│   ├── typescript_parser.py     # tree-sitter
│   ├── sql_parser.py
│   ├── markdown_parser.py
│   └── config_parser.py
├── chunking/
│   ├── chunker.py               # 主 chunking 逻辑
│   └── token_counter.py         # tiktoken 估算
├── graph/
│   ├── builder.py               # 建图、边权重
│   ├── traversal.py             # K-hop 遍历，计算 graph_score
│   └── scorer.py
├── indexing/
│   ├── pipeline.py              # 编排：scan→parse→chunk→embed→store
│   ├── embedder.py              # embedding 接口 + 具体实现
│   └── store.py                 # SQLite 读写，向量存储
├── retrieval/
│   ├── planner.py               # TaskParser, RetrievalPlan
│   ├── bm25.py                  # FTS5 查询
│   ├── vector.py                # 向量检索
│   ├── graph_retriever.py       # 图检索
│   ├── fusion.py                # RRF + reranker 接口
│   └── context_pack_builder.py  # 组装最终输出
├── eval/
│   ├── runner.py                # ablation 跑批
│   ├── metrics.py               # Recall@K, MRR, ...
│   ├── datasets/
│   │   └── swe_bench_loader.py
│   └── fixtures/                # 自有标注数据
├── trace/
│   └── recorder.py              # TraceRecorder
└── db/
    ├── migrations/              # SQL 迁移文件
    ├── schema.sql
    └── connection.py            # SQLite 连接管理

tests/
├── unit/
│   ├── test_parsers.py
│   ├── test_chunker.py
│   ├── test_graph_builder.py
│   └── test_fusion.py
├── integration/
│   ├── test_index_pipeline.py
│   └── test_retrieve_e2e.py
└── fixtures/
    └── sample_repos/            # 小型测试 repo
```

---

## 11. MCP Server 实现规范

### 11.1 Tool 定义

```python
# contextgraph/api/mcp_server.py
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("contextgraph")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="retrieve_context",
            description="Retrieve relevant code context for an AI coding task. Returns a structured Context Pack with required files, supporting context, and graph relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The coding task or question"},
                    "task_hint": {
                        "type": "string",
                        "enum": ["auth", "database", "ui", "refactor", "bug_fix", "api", "testing", "config", "general"],
                        "description": "Optional task type hint to improve retrieval strategy"
                    },
                    "repo_id": {"type": "string", "description": "Repository ID from scan_repo"},
                    "max_tokens": {"type": "integer", "default": 8000},
                    "trace": {"type": "boolean", "default": True}
                },
                "required": ["query", "repo_id"]
            }
        ),
        Tool(
            name="scan_repo",
            description="Index a local repository or check indexing status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the repository"},
                    "scan_run_id": {"type": "string", "description": "Check status of existing scan"}
                }
            }
        ),
        Tool(
            name="get_trace",
            description="Retrieve retrieval trace for debugging and explainability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_id": {"type": "string"}
                },
                "required": ["trace_id"]
            }
        )
    ]
```

### 11.2 claude_desktop_config.json 示例（开源 README 提供）

```json
{
  "mcpServers": {
    "contextgraph": {
      "command": "uvx",
      "args": ["contextgraph-studio", "mcp"],
      "env": {
        "CGSTUDIO_DB_PATH": "~/.contextgraph/db.sqlite"
      }
    }
  }
}
```

---

## 12. 增量更新策略

```
每次 index 前：
1. 读取上次 scan_run 的 file content_hash
2. 对比当前文件 hash
3. 只对 changed/new 文件重新解析+chunk+embed
4. deleted 文件：标记 file.is_excluded=1，不删除数据（保留历史）
5. 更新 scan_run_id，新 chunk 写入时关联新 scan_run_id
6. 检索时默认只查最新 scan_run_id 的数据
```

**触发时机**（由用户/Claude Code 决定，不自动触发）：
- 手动 `cgstudio index`
- Claude Code 可通过 `scan_repo` MCP tool 触发

---

## 13. 开发里程碑

### Phase 1：基础管道（2-3周）
- [ ] SQLite schema + migration
- [ ] File scanner + classifier
- [ ] Python AST parser
- [ ] Structure-aware chunker
- [ ] SQLite FTS5 BM25 检索
- [ ] CLI: `index` + `search`（纯 BM25）
- [ ] 单元测试覆盖 parser + chunker

### Phase 2：向量 + 图谱（2-3周）
- [ ] Embedding 集成（nomic-embed-code）
- [ ] 向量检索（numpy cosine）
- [ ] Graph builder（SQLite edge table）
- [ ] Graph traversal + graph_score
- [ ] RRF 融合
- [ ] Context Pack Builder

### Phase 3：Planner + MCP（1-2周）
- [ ] TaskParser（rule-based）
- [ ] task_strategies.yaml 配置
- [ ] RetrievalPlan 生成
- [ ] FastAPI routes
- [ ] MCP server（retrieve_context, scan_repo, get_trace）
- [ ] Trace recorder

### Phase 4：Eval + TypeScript Parser（2周）
- [ ] SWE-bench Lite loader
- [ ] Ablation runner
- [ ] Metrics（Recall@K, MRR, critical_file_hit_rate）
- [ ] tree-sitter TypeScript parser
- [ ] Eval 报告（Markdown）

### Phase 5：开源准备（1周）
- [ ] README + Getting Started
- [ ] claude_desktop_config.json 示例
- [ ] GitHub Actions CI
- [ ] pyproject.toml（uvx 安装）
- [ ] 性能文档 + Eval 结果展示

---

## 14. 关键工程决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 数据库 | SQLite | 零依赖，开箱即用，开源用户友好 |
| 向量存储 | numpy blob in SQLite → LanceDB | MVP 简单，50万+ chunks 再迁移 |
| Graph DB | SQLite edge table → Neo4j/FalkorDB | 同上，先简单，有需要再迁移 |
| 主语言 | Python | AST 支持最好，AI 生态最完整 |
| MCP SDK | `modelcontextprotocol/python-sdk` | 官方 SDK，Claude Code 直接支持 |
| Embedding | nomic-embed-code | 开源+代码专用，Apache-2.0 可商用 |
| RRF k 参数 | 60（默认） | 学术标准默认值，eval 后调整 |
| token 计数 | tiktoken cl100k_base | 近似估算够用 |
| 异步策略 | asyncio + `asyncio.to_thread` | 解析是 CPU 密集，避免阻塞 event loop |
| Reranker | 预留接口，MVP 不实现 | 先验证 RRF 效果，避免过早复杂化 |

---

*文档版本：v1.0 | 适用阶段：MVP 开发*