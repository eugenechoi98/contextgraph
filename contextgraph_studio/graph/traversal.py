"""K-hop 图遍历与 graph-search。"""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import asdict, dataclass

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.graph.scorer import compute_graph_score
from contextgraph_studio.services.retriever import resolve_repo_and_scan_run


@dataclass(slots=True)
class GraphSearchResult:
    """图检索结果。"""

    entity_id: str
    symbol_name: str | None
    file_path: str
    entity_type: str
    category: str
    line_start: int | None
    line_end: int | None
    graph_distance: int
    edge_type: str
    graph_score: float
    path: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_seed_entity_ids(
    connection: sqlite3.Connection,
    repo_id: str,
    scan_run_id: str,
    *,
    symbol: str | None = None,
    entity_id: str | None = None,
) -> list[str]:
    """把 symbol 或 entity_id 解析成最新 scan 的种子实体。"""

    if entity_id:
        row = connection.execute(
            """
            SELECT e.id
            FROM entities e
            JOIN files f ON f.id = e.file_id
            WHERE e.id = ? AND e.repo_id = ? AND f.scan_run_id = ?
            """,
            (entity_id, repo_id, scan_run_id),
        ).fetchone()
        if row is None:
            raise ValueError(f"Entity id not found in latest successful scan: {entity_id}")
        return [entity_id]

    if not symbol:
        return []

    exact_rows = connection.execute(
        """
        SELECT e.id
        FROM entities e
        JOIN files f ON f.id = e.file_id
        WHERE e.repo_id = ? AND f.scan_run_id = ? AND e.symbol_name = ?
        ORDER BY e.id
        """,
        (repo_id, scan_run_id, symbol),
    ).fetchall()
    if exact_rows:
        return [row["id"] for row in exact_rows]

    rows = connection.execute(
        """
        SELECT e.id, e.symbol_name, f.file_path
        FROM entities e
        JOIN files f ON f.id = e.file_id
        WHERE e.repo_id = ? AND f.scan_run_id = ? AND e.display_name = ?
        ORDER BY e.symbol_name
        """,
        (repo_id, scan_run_id, symbol),
    ).fetchall()
    if not rows:
        raise ValueError(f"Symbol not found in latest successful scan: {symbol}")
    if len(rows) > 1:
        candidates = ", ".join(f"{row['symbol_name']} ({row['file_path']})" for row in rows[:10])
        raise ValueError(f"Symbol '{symbol}' is ambiguous. Candidates: {candidates}")
    return [rows[0]["id"]]


def expand_from_entities(
    connection: sqlite3.Connection,
    seed_entity_ids: list[str],
    repo_id: str,
    scan_run_id: str,
    edge_types: list[str] | None = None,
    max_hops: int = 2,
) -> list[GraphSearchResult]:
    """从指定种子实体做 K-hop 扩展。"""

    if max_hops < 0:
        raise ValueError("max_hops must be greater than or equal to 0.")
    if not seed_entity_ids:
        return []

    allowed = set(edge_types or [])
    seed_rows = _load_entities(connection, seed_entity_ids, repo_id, scan_run_id)
    best_results: dict[str, GraphSearchResult] = {}
    queue = deque()

    for row in seed_rows:
        result = GraphSearchResult(
            entity_id=row["id"],
            symbol_name=row["symbol_name"],
            file_path=row["file_path"],
            entity_type=row["entity_type"],
            category=row["category"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            graph_distance=0,
            edge_type="seed",
            graph_score=1.0,
            path=row["symbol_name"] or row["file_path"],
        )
        best_results[row["id"]] = result
        queue.append((row, 0, [row["id"]], result.path))

    if max_hops == 0:
        return sorted(best_results.values(), key=lambda item: (-item.graph_score, item.path))

    while queue:
        current_row, hops, path_ids, path_text = queue.popleft()
        if hops >= max_hops:
            continue
        for relation in _load_outgoing_relations(connection, current_row["id"], scan_run_id, allowed):
            target_id = relation["to_entity_id"]
            if target_id in path_ids:
                continue
            target_row = _load_entities(connection, [target_id], repo_id, scan_run_id)
            if not target_row:
                continue
            target = target_row[0]
            distance = hops + 1
            score = compute_graph_score(
                target["category"],
                seed_entity_ids[0],
                distance,
                relation["edge_type"],
                relation["weight"],
            )
            next_path = f"{path_text} -[{relation['edge_type']}]-> {target['symbol_name'] or target['file_path']}"
            candidate = GraphSearchResult(
                entity_id=target["id"],
                symbol_name=target["symbol_name"],
                file_path=target["file_path"],
                entity_type=target["entity_type"],
                category=target["category"],
                line_start=target["line_start"],
                line_end=target["line_end"],
                graph_distance=distance,
                edge_type=relation["edge_type"],
                graph_score=score,
                path=next_path,
            )
            existing = best_results.get(target_id)
            if existing is None or score > existing.graph_score or (
                score == existing.graph_score and distance < existing.graph_distance
            ):
                best_results[target_id] = candidate
                queue.append((target, distance, [*path_ids, target_id], next_path))

    return sorted(
        best_results.values(),
        key=lambda item: (-item.graph_score, item.graph_distance, item.path),
    )


def graph_search(
    settings: Settings,
    *,
    symbol: str | None = None,
    entity_id: str | None = None,
    repo_id: str | None = None,
    edge_types: list[str] | None = None,
    max_hops: int = 2,
) -> list[GraphSearchResult]:
    """独立 graph-search 入口。"""

    if max_hops < 0:
        raise ValueError("max_hops must be greater than or equal to 0.")
    init_db(settings)
    with connect(settings.database_path) as connection:
        resolved_repo_id, scan_run_id = resolve_repo_and_scan_run(connection, repo_id)
        seed_ids = resolve_seed_entity_ids(
            connection,
            resolved_repo_id,
            scan_run_id,
            symbol=symbol,
            entity_id=entity_id,
        )
        return expand_from_entities(
            connection,
            seed_ids,
            resolved_repo_id,
            scan_run_id,
            edge_types=edge_types,
            max_hops=max_hops,
        )


def _load_entities(
    connection: sqlite3.Connection,
    entity_ids: list[str],
    repo_id: str,
    scan_run_id: str,
) -> list[sqlite3.Row]:
    if not entity_ids:
        return []
    placeholders = ", ".join("?" for _ in entity_ids)
    return connection.execute(
        f"""
        SELECT
            e.id,
            e.symbol_name,
            e.display_name,
            e.entity_type,
            e.line_start,
            e.line_end,
            f.file_path,
            f.category
        FROM entities e
        JOIN files f ON f.id = e.file_id
        WHERE e.repo_id = ? AND f.scan_run_id = ? AND e.id IN ({placeholders})
        """,
        [repo_id, scan_run_id, *entity_ids],
    ).fetchall()


def _load_outgoing_relations(
    connection: sqlite3.Connection,
    from_entity_id: str,
    scan_run_id: str,
    allowed_edge_types: set[str],
) -> list[sqlite3.Row]:
    if allowed_edge_types:
        placeholders = ", ".join("?" for _ in allowed_edge_types)
        return connection.execute(
            f"""
            SELECT from_entity_id, to_entity_id, edge_type, weight
            FROM relations
            WHERE scan_run_id = ? AND from_entity_id = ? AND edge_type IN ({placeholders})
            """,
            [scan_run_id, from_entity_id, *sorted(allowed_edge_types)],
        ).fetchall()
    return connection.execute(
        """
        SELECT from_entity_id, to_entity_id, edge_type, weight
        FROM relations
        WHERE scan_run_id = ? AND from_entity_id = ?
        """,
        (scan_run_id, from_entity_id),
    ).fetchall()
