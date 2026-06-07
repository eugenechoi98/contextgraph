"""Trace 共享模型。"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from contextgraph_studio.models.context_pack import ContextPack


class GetTraceRequest(BaseModel):
    """共享的 get_trace 请求契约。"""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(..., min_length=1)


class TraceChunkHit(BaseModel):
    """Trace 中记录的召回命中。"""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    file_path: str
    entity_id: str | None = None
    entity: str | None = None
    chunk_kind: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    score: float
    source: str
    graph_distance: int = 0
    reason: str | None = None
    path: str | None = None
    provider: str | None = None
    model: str | None = None


class TraceRerankerScore(BaseModel):
    """Trace 中记录的 reranker 分数。"""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    score: float
    reranker: str


class TraceFilteredOut(BaseModel):
    """Trace 中被预算过滤掉的候选。"""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    file_path: str
    source: str
    reason: str
    score: float
    tokens_estimate: int


class TraceRecord(BaseModel):
    """结构化 trace 输出。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    trace_id: str = Field(
        validation_alias=AliasChoices("id", "trace_id"),
        serialization_alias="trace_id",
    )
    repo_id: str
    query: str
    task_type: str | None = None
    retrieval_strategy: list[str] = Field(
        validation_alias=AliasChoices("retrieval_strategy_json", "retrieval_strategy"),
        serialization_alias="retrieval_strategy",
    )
    bm25_hits: list[TraceChunkHit] = Field(
        default_factory=list,
        validation_alias=AliasChoices("bm25_hits_json", "bm25_hits"),
        serialization_alias="bm25_hits",
    )
    vector_hits: list[TraceChunkHit] = Field(
        default_factory=list,
        validation_alias=AliasChoices("vector_hits_json", "vector_hits"),
        serialization_alias="vector_hits",
    )
    graph_hits: list[TraceChunkHit] = Field(
        default_factory=list,
        validation_alias=AliasChoices("graph_hits_json", "graph_hits"),
        serialization_alias="graph_hits",
    )
    reranker_scores: list[TraceRerankerScore] = Field(
        default_factory=list,
        validation_alias=AliasChoices("reranker_scores_json", "reranker_scores"),
        serialization_alias="reranker_scores",
    )
    final_selection: ContextPack = Field(
        validation_alias=AliasChoices("final_selection_json", "final_selection"),
        serialization_alias="final_selection",
    )
    filtered_out: list[TraceFilteredOut] = Field(
        default_factory=list,
        validation_alias=AliasChoices("filtered_out_json", "filtered_out"),
        serialization_alias="filtered_out",
    )
    token_estimate: int | None = None
    latency_ms: int | None = None
    index_version: str | None = None
    created_at: int
