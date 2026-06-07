"""固定 Context Pack 契约。"""

from pydantic import BaseModel, ConfigDict, Field


class ChunkResult(BaseModel):
    """上下文包中的 chunk 结果。"""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    file_path: str
    entity: str | None = None
    reason: str
    source: str
    chunk_kind: str
    line_start: int | None = None
    line_end: int | None = None
    score: float
    graph_distance: int = 0
    provider: str | None = None
    model: str | None = None


class GraphPath(BaseModel):
    """图路径占位。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str = Field(alias="from")
    to: str
    edge_type: str
    hops: int


class ContextPack(BaseModel):
    """统一输出给 CLI / API / MCP 的 Context Pack。"""

    model_config = ConfigDict(extra="forbid")

    trace_id: str | None
    task_type: str
    retrieval_strategy: list[str]
    token_estimate: int
    required: list[ChunkResult]
    supporting: list[ChunkResult]
    graph_paths: list[GraphPath]
    risk_notes: list[str]
    suggested_tests: list[str]


class RetrieveContextRequest(BaseModel):
    """共享的检索请求契约。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1)
    task_hint: str | None = None
    repo_id: str | None = None
    max_tokens: int | None = Field(default=None, ge=100)
    trace: bool = True
    top_k: int | None = Field(default=None, ge=1, le=20)
