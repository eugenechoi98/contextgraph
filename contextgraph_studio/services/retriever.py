"""Hybrid retrieval and Context Pack assembly."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import OrderedDict
from time import perf_counter
from uuid import uuid4

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.domain import ScoredChunk, SearchHit, utc_now_epoch
from contextgraph_studio.graph.scorer import compute_graph_score
from contextgraph_studio.models.context_pack import ChunkResult, ContextPack, GraphPath
from contextgraph_studio.retrieval.fusion import weighted_reciprocal_rank_fusion
from contextgraph_studio.retrieval.reranker import IdentityReranker
from contextgraph_studio.retrieval.token_budget import FilteredChunk, PackedSelection, pack_chunks
from contextgraph_studio.retrieval.vector import search_similar_chunks
from contextgraph_studio.services.planner import RetrievalPlan, build_plan
from contextgraph_studio.services.scan_resolver import resolve_repo_and_scan_run


TERM_RE = re.compile(r"[A-Za-z0-9_./-]+")


def normalize_query(query: str) -> str:
    """Collapse the query into an FTS-friendly OR expression."""

    terms = TERM_RE.findall(query)
    if not terms:
        return query
    return " OR ".join(dict.fromkeys(term.strip() for term in terms if term.strip()))


def fallback_terms(query: str) -> list[str]:
    """Build degraded lexical search terms."""

    ascii_terms = [term.strip() for term in TERM_RE.findall(query) if term.strip()]
    if ascii_terms:
        return list(dict.fromkeys(ascii_terms))
    stripped = query.strip()
    return [stripped] if stripped else []


def _rows_to_hits(rows: list[sqlite3.Row], reason: str) -> list[SearchHit]:
    return [
        SearchHit(
            chunk_id=row["chunk_id"],
            file_path=row["file_path"],
            entity_id=row["entity_id"],
            entity=row["entity"],
            entity_type=row["entity_type"],
            category=row["category"],
            reason=reason,
            chunk_kind=row["chunk_kind"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            score=float(row["score"]),
            tokens_estimate=int(row["tokens_estimate"]),
            content=row["content"],
        )
        for row in rows
    ]


def search_bm25(
    connection: sqlite3.Connection,
    query: str,
    repo_id: str,
    scan_run_id: str,
    top_k: int,
) -> list[SearchHit]:
    """Query the latest successful scan with BM25, then lexical fallback if needed."""

    normalized = normalize_query(query)
    try:
        rows = connection.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.entity_id,
                f.file_path,
                f.category,
                e.symbol_name AS entity,
                e.entity_type,
                c.chunk_kind,
                c.line_start,
                c.line_end,
                c.tokens_estimate,
                c.content,
                -bm25(chunks_fts, 8.0, 4.0, 1.0) AS score
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.chunk_id
            JOIN files f ON f.id = c.file_id
            LEFT JOIN entities e ON e.id = c.entity_id
            WHERE chunks_fts MATCH ?
              AND c.repo_id = ?
              AND c.scan_run_id = ?
            ORDER BY bm25(chunks_fts, 8.0, 4.0, 1.0)
            LIMIT ?
            """,
            (normalized, repo_id, scan_run_id, top_k),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if rows:
        return _rows_to_hits(rows, "BM25 match from latest successful scan")

    terms = fallback_terms(query)
    if not terms:
        return []

    where_clauses: list[str] = []
    params: list[str | int] = [repo_id, scan_run_id]
    for term in terms:
        where_clauses.append(
            "(lower(f.file_path) LIKE lower(?) OR lower(COALESCE(e.symbol_name, '')) LIKE lower(?) OR lower(c.content) LIKE lower(?))"
        )
        params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
    params.append(top_k)
    rows = connection.execute(
        f"""
        SELECT
            c.id AS chunk_id,
            c.entity_id,
            f.file_path,
            f.category,
            e.symbol_name AS entity,
            e.entity_type,
            c.chunk_kind,
            c.line_start,
            c.line_end,
            c.tokens_estimate,
            c.content,
            0.1 AS score
        FROM chunks c
        JOIN files f ON f.id = c.file_id
        LEFT JOIN entities e ON e.id = c.entity_id
        WHERE c.repo_id = ?
          AND c.scan_run_id = ?
          AND ({' OR '.join(where_clauses)})
        LIMIT ?
        """,
        params,
    ).fetchall()
    return _rows_to_hits(rows, "Fallback lexical match from latest successful scan")


def retrieve_context(
    query: str,
    settings: Settings,
    top_k: int | None = None,
    task_hint: str | None = None,
    max_tokens: int | None = None,
    repo_id: str | None = None,
    trace: bool = True,
) -> ContextPack:
    """Execute hybrid retrieval and return a Context Pack."""

    init_db(settings)
    started = perf_counter()
    plan = build_plan(query, settings, task_hint=task_hint, max_tokens=max_tokens)
    trace_id = str(uuid4())
    recall_top_k = top_k or settings.default_top_k
    route_warnings: list[str] = []

    with connect(settings.database_path) as connection:
        resolved_repo_id, scan_run_id = resolve_repo_and_scan_run(connection, repo_id)
        bm25_hits = run_bm25_recall(connection, plan, resolved_repo_id, scan_run_id, recall_top_k)

        vector_hits: list[ScoredChunk] = []
        if settings.hybrid_vector_enabled:
            try:
                vector_hits = run_vector_recall(plan, settings, resolved_repo_id, recall_top_k)
            except Exception as exc:
                route_warnings.append(f"Vector recall skipped: {exc}")

        graph_hits: list[ScoredChunk] = []
        if settings.hybrid_graph_enabled:
            try:
                seed_entity_ids = extract_graph_seed_entity_ids(
                    [*bm25_hits, *vector_hits],
                    limit=settings.graph_seed_limit,
                )
                graph_hits = run_graph_recall(
                    connection,
                    plan,
                    resolved_repo_id,
                    scan_run_id,
                    seed_entity_ids,
                    recall_top_k,
                )
            except Exception as exc:
                route_warnings.append(f"Graph recall skipped: {exc}")

        route_rankings = OrderedDict(
            (
                ("bm25", bm25_hits),
                ("vector", vector_hits),
                ("graph", graph_hits),
            )
        )
        active_rankings = OrderedDict((name, hits) for name, hits in route_rankings.items() if hits)
        fused = weighted_reciprocal_rank_fusion(active_rankings, plan.weights, k=settings.rrf_k) if active_rankings else []

        reranker = IdentityReranker()
        reranked = reranker.rerank(fused)
        packed = pack_chunks(
            reranked,
            token_budget=plan.token_budget,
            required_chunk_limit=settings.required_chunk_limit,
            priority_categories=plan.priority_categories,
            priority_entity_types=plan.priority_entity_types,
        )
        retrieval_strategy = list(active_rankings)
        pack = build_context_pack(
            trace_id=trace_id,
            plan=plan,
            retrieval_strategy=retrieval_strategy,
            packed=packed,
            route_warnings=route_warnings,
        )

        if trace:
            latency_ms = int((perf_counter() - started) * 1000)
            persist_trace(
                connection=connection,
                trace_id=trace_id,
                repo_id=resolved_repo_id,
                query=query,
                plan=plan,
                retrieval_strategy=retrieval_strategy,
                bm25_hits=bm25_hits,
                vector_hits=vector_hits,
                graph_hits=graph_hits,
                reranked_hits=reranked,
                filtered_out=packed.filtered_out,
                pack=pack,
                scan_run_id=scan_run_id,
                latency_ms=latency_ms,
                reranker_name=reranker.name,
            )
            connection.commit()
    return pack


def run_bm25_recall(
    connection: sqlite3.Connection,
    plan: RetrievalPlan,
    repo_id: str,
    scan_run_id: str,
    top_k: int,
) -> list[ScoredChunk]:
    """Run BM25 recall for one or more lexical queries."""

    merged: dict[str, ScoredChunk] = {}
    for query in plan.bm25_queries:
        for hit in search_bm25(connection, query, repo_id, scan_run_id, top_k):
            candidate = ScoredChunk(
                chunk_id=hit.chunk_id,
                file_path=hit.file_path,
                entity_id=hit.entity_id,
                entity=hit.entity,
                entity_type=hit.entity_type,
                category=hit.category,
                chunk_kind=hit.chunk_kind,
                line_start=hit.line_start,
                line_end=hit.line_end,
                score=hit.score,
                source="bm25",
                tokens_estimate=hit.tokens_estimate,
                graph_distance=0,
                reason=hit.reason,
                content=hit.content,
            )
            existing = merged.get(candidate.chunk_id)
            if existing is None or candidate.score > existing.score:
                merged[candidate.chunk_id] = candidate
    return sorted(merged.values(), key=lambda item: (-item.score, item.file_path, item.chunk_id))[:top_k]


def run_vector_recall(
    plan: RetrievalPlan,
    settings: Settings,
    repo_id: str,
    top_k: int,
) -> list[ScoredChunk]:
    """Run optional vector recall."""

    hits = search_similar_chunks(plan.vector_query, settings, repo_id=repo_id, top_k=top_k)
    return [
        ScoredChunk(
            chunk_id=hit.chunk_id,
            file_path=hit.file_path,
            entity_id=hit.entity_id,
            entity=hit.entity,
            entity_type=hit.entity_type,
            category=hit.category,
            chunk_kind=hit.chunk_kind,
            line_start=hit.line_start,
            line_end=hit.line_end,
            score=hit.score,
            source="vector",
            tokens_estimate=hit.tokens_estimate,
            graph_distance=0,
            reason=f"Vector similarity via {hit.provider}/{hit.model}",
            content=hit.content,
            provider=hit.provider,
            model=hit.model,
        )
        for hit in hits
    ]


def extract_graph_seed_entity_ids(candidates: list[ScoredChunk], *, limit: int) -> list[str]:
    """Extract graph seed entities from direct recall results."""

    if limit <= 0:
        raise ValueError("Graph seed limit must be greater than 0.")

    seeds: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.entity_id or candidate.entity_id in seen:
            continue
        seen.add(candidate.entity_id)
        seeds.append(candidate.entity_id)
        if len(seeds) >= limit:
            break
    return seeds


def run_graph_recall(
    connection: sqlite3.Connection,
    plan: RetrievalPlan,
    repo_id: str,
    scan_run_id: str,
    seed_entity_ids: list[str],
    top_k: int,
) -> list[ScoredChunk]:
    """Expand from seed entities and map graph hits back to chunks."""

    if not seed_entity_ids or plan.graph_hops <= 0:
        return []

    from contextgraph_studio.graph.traversal import expand_from_entities

    graph_results = expand_from_entities(
        connection,
        seed_entity_ids,
        repo_id,
        scan_run_id,
        edge_types=plan.graph_edge_types,
        max_hops=plan.graph_hops,
    )
    expanded = [result for result in graph_results if result.graph_distance > 0]
    expanded.extend(
        build_direct_graph_neighbors(
            connection,
            repo_id,
            scan_run_id,
            seed_entity_ids,
            plan.graph_edge_types,
        )
    )
    if not expanded:
        return []

    chunk_rows = load_chunks_for_entities(
        connection,
        repo_id,
        scan_run_id,
        [result.entity_id for result in expanded],
    )
    best_chunk_by_entity: dict[str, sqlite3.Row] = {}
    for row in chunk_rows:
        entity_id = row["entity_id"]
        if entity_id not in best_chunk_by_entity:
            best_chunk_by_entity[entity_id] = row

    hits: list[ScoredChunk] = []
    for result in expanded:
        row = best_chunk_by_entity.get(result.entity_id)
        if row is None:
            continue
        hits.append(
            ScoredChunk(
                chunk_id=row["chunk_id"],
                file_path=row["file_path"],
                entity_id=row["entity_id"],
                entity=row["entity"],
                entity_type=row["entity_type"],
                category=row["category"],
                chunk_kind=row["chunk_kind"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                score=result.graph_score,
                source="graph",
                tokens_estimate=int(row["tokens_estimate"]),
                graph_distance=result.graph_distance,
                reason=f"Graph expansion via {result.edge_type}",
                path=result.path,
                content=row["content"],
            )
        )

    deduped: dict[str, ScoredChunk] = {}
    for hit in hits:
        existing = deduped.get(hit.chunk_id)
        if existing is None or hit.score > existing.score:
            deduped[hit.chunk_id] = hit
    return sorted(
        deduped.values(),
        key=lambda item: (-item.score, item.graph_distance, item.file_path, item.chunk_id),
    )[:top_k]


def build_direct_graph_neighbors(
    connection: sqlite3.Connection,
    repo_id: str,
    scan_run_id: str,
    seed_entity_ids: list[str],
    edge_types: list[str],
) -> list[object]:
    """Collect direct graph edges from seeds, including seed-to-seed relations."""

    if not seed_entity_ids:
        return []
    edge_clause = ""
    params: list[object] = [scan_run_id, repo_id]
    placeholders = ", ".join("?" for _ in seed_entity_ids)
    if edge_types:
        edge_placeholders = ", ".join("?" for _ in edge_types)
        edge_clause = f" AND r.edge_type IN ({edge_placeholders})"
        params.extend(edge_types)
    params.extend(seed_entity_ids)
    rows = connection.execute(
        f"""
        SELECT
            r.from_entity_id,
            r.to_entity_id,
            r.edge_type,
            r.weight,
            src.symbol_name AS from_symbol,
            dst.symbol_name AS to_symbol,
            dst.entity_type,
            f.file_path,
            f.category,
            dst.line_start,
            dst.line_end
        FROM relations r
        JOIN entities src ON src.id = r.from_entity_id
        JOIN entities dst ON dst.id = r.to_entity_id
        JOIN files f ON f.id = dst.file_id
        WHERE r.scan_run_id = ?
          AND dst.repo_id = ?
          {edge_clause}
          AND r.from_entity_id IN ({placeholders})
        """,
        params,
    ).fetchall()
    results = []
    for row in rows:
        results.append(
            type(
                "DirectGraphResult",
                (),
                {
                    "entity_id": row["to_entity_id"],
                    "symbol_name": row["to_symbol"],
                    "file_path": row["file_path"],
                    "entity_type": row["entity_type"],
                    "category": row["category"],
                    "line_start": row["line_start"],
                    "line_end": row["line_end"],
                    "graph_distance": 1,
                    "edge_type": row["edge_type"],
                    "graph_score": compute_graph_score(
                        row["category"],
                        seed_entity_ids[0],
                        1,
                        row["edge_type"],
                        row["weight"],
                    ),
                    "path": f"{row['from_symbol'] or row['file_path']} -[{row['edge_type']}]-> {row['to_symbol'] or row['file_path']}",
                },
            )()
        )
    return results


def load_chunks_for_entities(
    connection: sqlite3.Connection,
    repo_id: str,
    scan_run_id: str,
    entity_ids: list[str],
) -> list[sqlite3.Row]:
    """Load representative chunks for a set of entities."""

    if not entity_ids:
        return []
    placeholders = ", ".join("?" for _ in entity_ids)
    return connection.execute(
        f"""
        SELECT
            c.id AS chunk_id,
            c.entity_id,
            c.chunk_kind,
            c.line_start,
            c.line_end,
            c.tokens_estimate,
            c.content,
            f.file_path,
            f.category,
            e.symbol_name AS entity,
            e.entity_type
        FROM chunks c
        JOIN files f ON f.id = c.file_id
        LEFT JOIN entities e ON e.id = c.entity_id
        WHERE c.repo_id = ?
          AND c.scan_run_id = ?
          AND c.entity_id IN ({placeholders})
        ORDER BY
            CASE c.chunk_kind WHEN 'summary' THEN 0 ELSE 1 END,
            COALESCE(c.line_start, 0),
            c.id
        """,
        [repo_id, scan_run_id, *entity_ids],
    ).fetchall()


def build_context_pack(
    *,
    trace_id: str,
    plan: RetrievalPlan,
    retrieval_strategy: list[str],
    packed: PackedSelection,
    route_warnings: list[str],
) -> ContextPack:
    """Build a Context Pack from packed retrieval candidates."""

    selected_hits = [*packed.required, *packed.supporting]
    return ContextPack(
        trace_id=trace_id,
        task_type=plan.task_type,
        retrieval_strategy=retrieval_strategy,
        token_estimate=packed.token_estimate,
        required=[chunk_to_result(hit) for hit in packed.required],
        supporting=[chunk_to_result(hit) for hit in packed.supporting],
        graph_paths=build_graph_paths(selected_hits),
        risk_notes=build_risk_notes(selected_hits, route_warnings),
        suggested_tests=build_suggested_tests(selected_hits),
    )


def chunk_to_result(hit: ScoredChunk) -> ChunkResult:
    """Convert an internal retrieval candidate to API/CLI output."""

    return ChunkResult(
        chunk_id=hit.chunk_id,
        file_path=hit.file_path,
        entity=hit.entity,
        reason=hit.reason or hit.source,
        source=hit.source,
        chunk_kind=hit.chunk_kind,
        line_start=hit.line_start,
        line_end=hit.line_end,
        score=hit.score,
        graph_distance=hit.graph_distance,
        provider=hit.provider,
        model=hit.model,
    )


def build_graph_paths(hits: list[ScoredChunk]) -> list[GraphPath]:
    """Build graph path metadata for selected graph-expanded chunks."""

    paths: list[GraphPath] = []
    seen: set[tuple[str, str, str, int]] = set()
    for hit in hits:
        if not hit.path or hit.graph_distance <= 0:
            continue
        segments = [segment.strip() for segment in hit.path.split("->") if segment.strip()]
        from_node = segments[0].split(" -[", 1)[0].strip() if segments else hit.entity or hit.file_path
        to_node = hit.entity or hit.file_path
        edge_type = hit.reason.removeprefix("Graph expansion via ").strip() if hit.reason else "graph"
        key = (from_node, to_node, edge_type, hit.graph_distance)
        if key in seen:
            continue
        seen.add(key)
        paths.append(GraphPath.model_validate({"from": from_node, "to": to_node, "edge_type": edge_type, "hops": hit.graph_distance}))
    return paths


def build_suggested_tests(hits: list[ScoredChunk]) -> list[str]:
    """Generate lightweight test suggestions from selected hits."""

    suggestions: list[str] = []
    for hit in hits[:3]:
        if "/test" in hit.file_path or "tests/" in hit.file_path:
            suggestions.append(f"Run targeted tests near {hit.file_path}.")
        else:
            suggestions.append(f"Add a regression test covering {hit.file_path}.")
    if not suggestions:
        suggestions.append("Add a smoke test for the retrieval path.")
    return suggestions


def build_risk_notes(hits: list[ScoredChunk], route_warnings: list[str]) -> list[str]:
    """Generate risk notes for the Context Pack."""

    notes = list(route_warnings)
    if any(hit.file_path.endswith(".md") for hit in hits):
        notes.append("Some hits come from documentation; verify implementation source of truth before editing.")
    if not hits:
        notes.append("No retrieval hits fit the current budget and enabled recall routes.")
    return notes


def persist_trace(
    *,
    connection: sqlite3.Connection,
    trace_id: str,
    repo_id: str,
    query: str,
    plan: RetrievalPlan,
    retrieval_strategy: list[str],
    bm25_hits: list[ScoredChunk],
    vector_hits: list[ScoredChunk],
    graph_hits: list[ScoredChunk],
    reranked_hits: list[ScoredChunk],
    filtered_out: list[FilteredChunk],
    pack: ContextPack,
    scan_run_id: str,
    latency_ms: int,
    reranker_name: str,
) -> None:
    """Persist a retrieval trace."""

    connection.execute(
        """
        INSERT INTO traces (
            id, repo_id, query, task_type, retrieval_strategy_json, bm25_hits_json,
            vector_hits_json, graph_hits_json, reranker_scores_json, final_selection_json,
            filtered_out_json, token_estimate, latency_ms, index_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trace_id,
            repo_id,
            query,
            plan.task_type,
            json.dumps(retrieval_strategy, ensure_ascii=False),
            json.dumps([trace_chunk(hit) for hit in bm25_hits], ensure_ascii=False),
            json.dumps([trace_chunk(hit) for hit in vector_hits], ensure_ascii=False),
            json.dumps([trace_chunk(hit) for hit in graph_hits], ensure_ascii=False),
            json.dumps(
                [
                    {
                        "chunk_id": hit.chunk_id,
                        "score": hit.score,
                        "reranker": reranker_name,
                    }
                    for hit in reranked_hits
                ],
                ensure_ascii=False,
            ),
            json.dumps(pack.model_dump(mode="json", by_alias=True), ensure_ascii=False),
            json.dumps([trace_filtered(item) for item in filtered_out], ensure_ascii=False),
            pack.token_estimate,
            latency_ms,
            scan_run_id,
            utc_now_epoch(),
        ),
    )


def trace_chunk(hit: ScoredChunk) -> dict[str, object]:
    """Convert a chunk candidate to a trace-safe JSON dict."""

    payload: dict[str, object] = {
        "chunk_id": hit.chunk_id,
        "file_path": hit.file_path,
        "entity_id": hit.entity_id,
        "entity": hit.entity,
        "chunk_kind": hit.chunk_kind,
        "line_start": hit.line_start,
        "line_end": hit.line_end,
        "score": hit.score,
        "source": hit.source,
        "graph_distance": hit.graph_distance,
        "reason": hit.reason,
    }
    if hit.path:
        payload["path"] = hit.path
    if hit.provider:
        payload["provider"] = hit.provider
    if hit.model:
        payload["model"] = hit.model
    return payload


def trace_filtered(item: FilteredChunk) -> dict[str, object]:
    """Convert a filtered chunk to trace JSON."""

    return {
        "chunk_id": item.chunk_id,
        "file_path": item.file_path,
        "source": item.source,
        "reason": item.reason,
        "score": item.score,
        "tokens_estimate": item.tokens_estimate,
    }


def get_trace(trace_id: str, settings: Settings) -> dict:
    """Read trace details."""

    init_db(settings)
    with connect(settings.database_path) as connection:
        row = connection.execute(
            "SELECT * FROM traces WHERE id = ?",
            (trace_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Trace not found: {trace_id}")

    result = dict(row)
    for json_column in (
        "retrieval_strategy_json",
        "bm25_hits_json",
        "vector_hits_json",
        "graph_hits_json",
        "reranker_scores_json",
        "final_selection_json",
        "filtered_out_json",
    ):
        value = result.get(json_column)
        result[json_column] = json.loads(value) if value else []
    return result
