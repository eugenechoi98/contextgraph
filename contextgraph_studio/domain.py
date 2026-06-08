"""Internal domain models for indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now_epoch() -> int:
    """Return the current UTC timestamp in seconds."""

    return int(datetime.now(UTC).timestamp())


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""

    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class SourceFile:
    """Snapshot of a repository file during indexing."""

    repo_id: str
    path: str
    absolute_path: str
    category: str
    language: str
    content_hash: str
    content: str
    size_bytes: int
    line_count: int
    is_excluded: int = 0


@dataclass(slots=True)
class EntityRecord:
    """Entity emitted by a parser."""

    entity_type: str
    symbol_name: str | None
    display_name: str
    line_start: int | None
    line_end: int | None
    signature: str | None
    docstring: str | None
    language: str
    content_hash: str
    parent_symbol_name: str | None = None


@dataclass(slots=True)
class RelationRecord:
    """Relation emitted by a parser."""

    edge_type: str
    from_symbol_name: str
    to_symbol_name: str
    is_directed: int = 1
    weight: float = 1.0
    meta_json: str | None = None


@dataclass(slots=True)
class ParseResult:
    """Parsed file result."""

    entities: list[EntityRecord]
    relations: list[RelationRecord]
    parse_errors: list[str]
    language: str
    parser_version: str


@dataclass(slots=True)
class ChunkRecord:
    """Structured chunk record."""

    entity_symbol_name: str | None
    chunk_kind: str
    content: str
    tokens_estimate: int
    line_start: int | None
    line_end: int | None
    content_hash: str
    continuation_index: int = 0


@dataclass(slots=True)
class SearchHit:
    """Lexical retrieval hit."""

    chunk_id: str
    file_path: str
    entity_id: str | None
    entity: str | None
    entity_type: str | None
    category: str | None
    reason: str
    chunk_kind: str
    line_start: int | None
    line_end: int | None
    score: float
    tokens_estimate: int = 0
    graph_distance: int = 0
    content: str | None = None


@dataclass(slots=True)
class ScoredChunk:
    """Unified retrieval candidate across recall, fusion, and packing."""

    chunk_id: str
    file_path: str
    entity_id: str | None
    entity: str | None
    entity_type: str | None
    category: str | None
    chunk_kind: str
    line_start: int | None
    line_end: int | None
    score: float
    source: str
    tokens_estimate: int
    graph_distance: int = 0
    reason: str | None = None
    path: str | None = None
    content: str | None = None
    provider: str | None = None
    model: str | None = None


@dataclass(slots=True)
class IndexingStats:
    """Statistics for a scan run."""

    files: int = 0
    chunks: int = 0
    entities: int = 0
    relations: int = 0
    parse_errors: int = 0
    parse_errors_current_scan: int = 0
    parse_errors_reused: int = 0
    parse_errors_total_snapshot: int = 0
    reused_files: int = 0
    changed_files: int = 0
    new_files: int = 0
    deleted_files: int = 0
    vector_index_enabled: bool = False
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_revision: str | None = None
    embedding_dimension: int | None = None
    embedding_count: int = 0
    embedding_reused_count: int = 0
    embedding_generated_count: int = 0
    parse_error_messages: list[str] = field(default_factory=list)
    parse_error_messages_current_scan: list[str] = field(default_factory=list)
    parse_error_messages_reused: list[str] = field(default_factory=list)
