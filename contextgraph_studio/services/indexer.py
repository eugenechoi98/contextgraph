"""正式索引主链。"""

import json
import sqlite3
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.domain import (
    ChunkRecord,
    EntityRecord,
    IndexingStats,
    ParseResult,
    SourceFile,
    utc_now_epoch,
)
from contextgraph_studio.graph.builder import build_relations_for_scan
from contextgraph_studio.indexing.vector_store import sync_embeddings_for_scan
from contextgraph_studio.parsers.python_parser import PythonParser
from contextgraph_studio.services.chunker import chunk_source_file
from contextgraph_studio.services.intake import scan_repository


def _stable_id(*parts: object) -> str:
    seed = "::".join(str(part) for part in parts)
    return str(uuid5(NAMESPACE_URL, seed))


def resolve_repo_id(repo_root: Path) -> str:
    """根据本地路径生成稳定 repo_id。"""

    return _stable_id("repo", str(repo_root.resolve()).replace("\\", "/"))


def upsert_repository(connection: sqlite3.Connection, repo_root: Path) -> str:
    """注册或更新 repository。"""

    repo_id = resolve_repo_id(repo_root)
    now = utc_now_epoch()
    connection.execute(
        """
        INSERT INTO repositories (id, local_path, remote_url, default_branch, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            local_path = excluded.local_path,
            updated_at = excluded.updated_at
        """,
        (repo_id, str(repo_root.resolve()), None, None, now, now),
    )
    return repo_id


def create_scan_run(connection: sqlite3.Connection, repo_id: str) -> str:
    """创建 running scan_run。"""

    scan_run_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO scan_runs (id, repo_id, commit_sha, started_at, finished_at, status, stats_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (scan_run_id, repo_id, None, utc_now_epoch(), None, "running", None),
    )
    return scan_run_id


def update_scan_run(
    connection: sqlite3.Connection,
    scan_run_id: str,
    status: str,
    stats: IndexingStats,
    error_message: str | None = None,
) -> None:
    """更新 scan_run 状态。"""

    connection.execute(
        """
        UPDATE scan_runs
        SET status = ?, finished_at = ?, stats_json = ?, error_message = ?
        WHERE id = ?
        """,
        (
            status,
            utc_now_epoch(),
            json.dumps(
                {
                    "files": stats.files,
                    "chunks": stats.chunks,
                    "entities": stats.entities,
                    "relations": stats.relations,
                    "parse_errors": stats.parse_errors,
                    "reused_files": stats.reused_files,
                    "changed_files": stats.changed_files,
                    "new_files": stats.new_files,
                    "deleted_files": stats.deleted_files,
                    "vector_index_enabled": stats.vector_index_enabled,
                    "embedding_provider": stats.embedding_provider,
                    "embedding_model": stats.embedding_model,
                    "embedding_revision": stats.embedding_revision,
                    "embedding_dimension": stats.embedding_dimension,
                    "embedding_count": stats.embedding_count,
                    "embedding_reused_count": stats.embedding_reused_count,
                    "embedding_generated_count": stats.embedding_generated_count,
                    "parse_error_messages": stats.parse_error_messages,
                },
                ensure_ascii=False,
            ),
            error_message,
            scan_run_id,
        ),
    )


def get_latest_successful_scan(
    connection: sqlite3.Connection,
    repo_id: str,
) -> sqlite3.Row | None:
    """读取指定 repo 最新成功 scan_run。"""

    return connection.execute(
        """
        SELECT id, repo_id, finished_at
        FROM scan_runs
        WHERE repo_id = ? AND status = 'done'
        ORDER BY finished_at DESC, started_at DESC
        LIMIT 1
        """,
        (repo_id,),
    ).fetchone()


def get_previous_files(connection: sqlite3.Connection, scan_run_id: str) -> dict[str, sqlite3.Row]:
    """读取上一版文件快照。"""

    rows = connection.execute(
        """
        SELECT *
        FROM files
        WHERE scan_run_id = ? AND is_excluded = 0
        """,
        (scan_run_id,),
    ).fetchall()
    return {row["file_path"]: row for row in rows}


def _insert_relation(
    connection: sqlite3.Connection,
    scan_run_id: str,
    from_entity_id: str,
    to_entity_id: str,
    edge_type: str,
    weight: float = 1.0,
    meta_json: str | None = None,
) -> None:
    relation_id = _stable_id(scan_run_id, "relation", from_entity_id, to_entity_id, edge_type)
    connection.execute(
        """
        INSERT INTO relations (
            id, scan_run_id, from_entity_id, to_entity_id, edge_type, is_directed, weight, meta_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (relation_id, scan_run_id, from_entity_id, to_entity_id, edge_type, 1, weight, meta_json),
    )


def _insert_file_row(
    connection: sqlite3.Connection,
    source_file: SourceFile,
    scan_run_id: str,
) -> str:
    file_id = _stable_id(scan_run_id, "file", source_file.path)
    connection.execute(
        """
        INSERT INTO files (
            id, scan_run_id, repo_id, file_path, language, category, size_bytes, line_count, content_hash, is_excluded
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            scan_run_id,
            source_file.repo_id,
            source_file.path,
            source_file.language,
            source_file.category,
            source_file.size_bytes,
            source_file.line_count,
            source_file.content_hash,
            source_file.is_excluded,
        ),
    )
    return file_id


def _insert_entity_row(
    connection: sqlite3.Connection,
    file_id: str,
    repo_id: str,
    scan_run_id: str,
    file_path: str,
    entity: EntityRecord,
) -> str:
    entity_id = _stable_id(
        scan_run_id,
        "entity",
        file_path,
        entity.entity_type,
        entity.symbol_name or entity.display_name,
        entity.line_start or 0,
        entity.line_end or 0,
    )
    connection.execute(
        """
        INSERT INTO entities (
            id, file_id, repo_id, entity_type, symbol_name, display_name,
            line_start, line_end, signature, docstring, language, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_id,
            file_id,
            repo_id,
            entity.entity_type,
            entity.symbol_name,
            entity.display_name,
            entity.line_start,
            entity.line_end,
            entity.signature,
            entity.docstring,
            entity.language,
            entity.content_hash,
        ),
    )
    return entity_id


def _insert_chunk_row(
    connection: sqlite3.Connection,
    chunk: ChunkRecord,
    entity_id: str | None,
    file_id: str,
    repo_id: str,
    scan_run_id: str,
    file_path: str,
) -> str:
    chunk_id = _stable_id(
        scan_run_id,
        "chunk",
        file_path,
        entity_id or "none",
        chunk.chunk_kind,
        chunk.line_start or 0,
        chunk.line_end or 0,
        chunk.continuation_index,
        chunk.content_hash,
    )
    connection.execute(
        """
        INSERT INTO chunks (
            id, entity_id, file_id, repo_id, scan_run_id, chunk_kind, content,
            tokens_estimate, line_start, line_end, content_hash, embedding_model, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            entity_id,
            file_id,
            repo_id,
            scan_run_id,
            chunk.chunk_kind,
            chunk.content,
            chunk.tokens_estimate,
            chunk.line_start,
            chunk.line_end,
            chunk.content_hash,
            None,
            utc_now_epoch(),
        ),
    )
    return chunk_id


def _copy_previous_snapshot(
    connection: sqlite3.Connection,
    previous_file_row: sqlite3.Row,
    new_scan_run_id: str,
    repo_id: str,
) -> tuple[int, int, int, int]:
    """把未变化文件复制到新快照。"""

    source_file = SourceFile(
        repo_id=repo_id,
        path=previous_file_row["file_path"],
        absolute_path=previous_file_row["file_path"],
        category=previous_file_row["category"],
        language=previous_file_row["language"],
        content_hash=previous_file_row["content_hash"],
        content="",
        size_bytes=previous_file_row["size_bytes"],
        line_count=previous_file_row["line_count"],
        is_excluded=previous_file_row["is_excluded"],
    )
    new_file_id = _insert_file_row(connection, source_file, new_scan_run_id)

    old_entities = connection.execute(
        "SELECT * FROM entities WHERE file_id = ?",
        (previous_file_row["id"],),
    ).fetchall()
    old_to_new_entity_ids: dict[str, str] = {}
    for row in old_entities:
        entity = EntityRecord(
            entity_type=row["entity_type"],
            symbol_name=row["symbol_name"],
            display_name=row["display_name"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            signature=row["signature"],
            docstring=row["docstring"],
            language=row["language"],
            content_hash=row["content_hash"],
        )
        new_entity_id = _insert_entity_row(
            connection,
            new_file_id,
            repo_id,
            new_scan_run_id,
            previous_file_row["file_path"],
            entity,
        )
        old_to_new_entity_ids[row["id"]] = new_entity_id

    old_chunks = connection.execute(
        "SELECT * FROM chunks WHERE file_id = ?",
        (previous_file_row["id"],),
    ).fetchall()
    chunk_count = 0
    for row in old_chunks:
        chunk = ChunkRecord(
            entity_symbol_name=None,
            chunk_kind=row["chunk_kind"],
            content=row["content"],
            tokens_estimate=row["tokens_estimate"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            content_hash=row["content_hash"],
            continuation_index=0,
        )
        _insert_chunk_row(
            connection,
            chunk,
            old_to_new_entity_ids.get(row["entity_id"]),
            new_file_id,
            repo_id,
            new_scan_run_id,
            previous_file_row["file_path"],
        )
        chunk_count += 1

    old_relations = connection.execute(
        """
        SELECT *
        FROM relations
        WHERE scan_run_id = ?
        """,
        (previous_file_row["scan_run_id"],),
    ).fetchall()
    relation_count = 0
    for row in old_relations:
        if row["from_entity_id"] in old_to_new_entity_ids and row["to_entity_id"] in old_to_new_entity_ids:
            _insert_relation(
                connection,
                new_scan_run_id,
                old_to_new_entity_ids[row["from_entity_id"]],
                old_to_new_entity_ids[row["to_entity_id"]],
                row["edge_type"],
                weight=row["weight"],
                meta_json=row["meta_json"],
            )
            relation_count += 1
    return 1, len(old_entities), chunk_count, relation_count


def _build_doc_entities_and_chunks(
    connection: sqlite3.Connection,
    source_file: SourceFile,
    file_id: str,
    scan_run_id: str,
    chunks: list[ChunkRecord],
    entity_ids: dict[str, str],
) -> tuple[int, int]:
    """为 Markdown section 创建 doc_section 实体。"""

    entity_count = 0
    chunk_count = 0
    for chunk in chunks:
        if chunk.chunk_kind != "doc_section" or not chunk.entity_symbol_name:
            continue
        doc_entity = EntityRecord(
            entity_type="doc_section",
            symbol_name=f"{source_file.path}::{chunk.entity_symbol_name}",
            display_name=chunk.entity_symbol_name,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            signature=None,
            docstring=None,
            language=source_file.language,
            content_hash=chunk.content_hash,
        )
        entity_id = _insert_entity_row(connection, file_id, source_file.repo_id, scan_run_id, source_file.path, doc_entity)
        entity_ids[doc_entity.symbol_name or doc_entity.display_name] = entity_id
        entity_count += 1
        _insert_chunk_row(connection, chunk, entity_id, file_id, source_file.repo_id, scan_run_id, source_file.path)
        chunk_count += 1
    return entity_count, chunk_count


def _index_source_file(
    connection: sqlite3.Connection,
    source_file: SourceFile,
    settings: Settings,
    scan_run_id: str,
) -> IndexingStats:
    """索引单个文件。"""

    stats = IndexingStats(files=1)
    file_id = _insert_file_row(connection, source_file, scan_run_id)

    file_entity = EntityRecord(
        entity_type="file",
        symbol_name=source_file.path,
        display_name=source_file.path.split("/")[-1],
        line_start=1,
        line_end=max(1, source_file.line_count),
        signature=None,
        docstring=None,
        language=source_file.language,
        content_hash=source_file.content_hash,
    )
    file_entity_id = _insert_entity_row(connection, file_id, source_file.repo_id, scan_run_id, source_file.path, file_entity)
    stats.entities += 1
    entity_ids: dict[str, str] = {source_file.path: file_entity_id}

    parse_result: ParseResult | None = None
    parsed_entities: list[EntityRecord] = []
    if source_file.language == "python":
        parse_result = PythonParser().parse(source_file.path, source_file.content, file_id)
        parsed_entities = parse_result.entities
        stats.parse_errors += len(parse_result.parse_errors)
        stats.parse_error_messages.extend(parse_result.parse_errors)

        for entity in parsed_entities:
            entity_id = _insert_entity_row(connection, file_id, source_file.repo_id, scan_run_id, source_file.path, entity)
            entity_ids[(entity.symbol_name or entity.display_name)] = entity_id
            stats.entities += 1

        for entity in parsed_entities:
            child_key = entity.symbol_name or entity.display_name
            parent_key = entity.parent_symbol_name or source_file.path
            if child_key in entity_ids and parent_key in entity_ids:
                _insert_relation(
                    connection,
                    scan_run_id,
                    entity_ids[parent_key],
                    entity_ids[child_key],
                    "contains",
                )
                stats.relations += 1

    chunks = chunk_source_file(source_file, settings, parsed_entities if source_file.language == "python" else None)

    if source_file.language == "markdown":
        entity_count, chunk_count = _build_doc_entities_and_chunks(
            connection,
            source_file,
            file_id,
            scan_run_id,
            chunks,
            entity_ids,
        )
        stats.entities += entity_count
        stats.chunks += chunk_count
        return stats

    for chunk in chunks:
        entity_id = entity_ids.get(chunk.entity_symbol_name or "", file_entity_id)
        _insert_chunk_row(connection, chunk, entity_id, file_id, source_file.repo_id, scan_run_id, source_file.path)
        stats.chunks += 1
    return stats


def sync_fts_for_latest_scan(connection: sqlite3.Connection, repo_id: str, scan_run_id: str) -> None:
    """让 FTS 只承载指定 repo 最新成功 scan_run 的可检索数据。"""

    connection.execute("DELETE FROM chunks_fts WHERE repo_id = ?", (repo_id,))
    connection.execute(
        """
        INSERT INTO chunks_fts (chunk_id, repo_id, scan_run_id, file_path, symbol_name, content)
        SELECT
            c.id,
            c.repo_id,
            c.scan_run_id,
            f.file_path,
            COALESCE(e.symbol_name, ''),
            c.content
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        LEFT JOIN entities e ON c.entity_id = e.id
        WHERE c.repo_id = ? AND c.scan_run_id = ?
        """,
        (repo_id, scan_run_id),
    )


def index_repository(repo_root: Path, settings: Settings) -> dict[str, int | str]:
    """索引仓库并生成最新 scan_run 快照。"""

    init_db(settings)
    repo_root = repo_root.resolve()
    with connect(settings.database_path) as connection:
        repo_id = upsert_repository(connection, repo_root)
        scan_run_id = create_scan_run(connection, repo_id)
        previous_scan = get_latest_successful_scan(connection, repo_id)
        connection.commit()

        stats = IndexingStats()
        try:
            source_files = scan_repository(repo_root, repo_id, settings)
            stats.vector_index_enabled = settings.vector_index_enabled
            previous_files = get_previous_files(connection, previous_scan["id"]) if previous_scan else {}
            current_paths = {source_file.path for source_file in source_files}
            stats.files = len(source_files)
            stats.deleted_files = len(set(previous_files) - current_paths)

            for source_file in sorted(source_files, key=lambda item: item.path):
                previous = previous_files.get(source_file.path)
                if previous is None:
                    stats.new_files += 1
                    partial = _index_source_file(connection, source_file, settings, scan_run_id)
                elif previous["content_hash"] == source_file.content_hash:
                    copied_files, copied_entities, copied_chunks, copied_relations = _copy_previous_snapshot(
                        connection,
                        previous,
                        scan_run_id,
                        repo_id,
                    )
                    stats.reused_files += copied_files
                    stats.entities += copied_entities
                    stats.chunks += copied_chunks
                    stats.relations += copied_relations
                    continue
                else:
                    stats.changed_files += 1
                    partial = _index_source_file(connection, source_file, settings, scan_run_id)

                stats.entities += partial.entities
                stats.chunks += partial.chunks
                stats.relations += partial.relations
                stats.parse_errors += partial.parse_errors
                stats.parse_error_messages.extend(partial.parse_error_messages)

            if settings.vector_index_enabled:
                vector_stats = sync_embeddings_for_scan(connection, settings, repo_id, scan_run_id)
                stats.embedding_provider = settings.embedding_provider
                stats.embedding_model = settings.embedding_model
                stats.embedding_revision = settings.embedding_revision
                stats.embedding_dimension = settings.embedding_dimension
                stats.embedding_count = stats.chunks
                stats.embedding_reused_count = vector_stats.reused_embeddings
                stats.embedding_generated_count = vector_stats.generated_embeddings
            stats.relations = build_relations_for_scan(connection, repo_id, scan_run_id, source_files)
            sync_fts_for_latest_scan(connection, repo_id, scan_run_id)
            update_scan_run(connection, scan_run_id, "done", stats)
            connection.commit()
        except Exception as exc:
            update_scan_run(connection, scan_run_id, "failed", stats, error_message=str(exc))
            connection.commit()
            raise

    return {
        "repo_id": repo_id,
        "scan_run_id": scan_run_id,
        "file_count": stats.files,
        "chunk_count": stats.chunks,
        "parse_error_count": stats.parse_errors,
        "vector_index_enabled": stats.vector_index_enabled,
        "embedding_provider": stats.embedding_provider,
        "embedding_model": stats.embedding_model,
        "embedding_revision": stats.embedding_revision,
        "embedding_dimension": stats.embedding_dimension,
        "embedding_count": stats.embedding_count,
        "embedding_reused_count": stats.embedding_reused_count,
        "embedding_generated_count": stats.embedding_generated_count,
    }
