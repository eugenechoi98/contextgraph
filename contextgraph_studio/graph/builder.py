"""Graph Builder：为当前 scan_run 重建 relations。"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from uuid import NAMESPACE_URL, uuid5

from contextgraph_studio.domain import SourceFile
from contextgraph_studio.parsers.python_parser import PythonParser
from contextgraph_studio.parsers.typescript_parser import TypeScriptParser


def _stable_relation_id(
    scan_run_id: str,
    from_entity_id: str,
    to_entity_id: str,
    edge_type: str,
) -> str:
    seed = "::".join([scan_run_id, "relation", from_entity_id, to_entity_id, edge_type])
    return str(uuid5(NAMESPACE_URL, seed))


def build_relations_for_scan(
    connection: sqlite3.Connection,
    repo_id: str,
    scan_run_id: str,
    source_files: list[SourceFile],
) -> int:
    """为当前 scan_run 重建整套 relations。"""

    connection.execute("DELETE FROM relations WHERE scan_run_id = ?", (scan_run_id,))
    entity_rows = connection.execute(
        """
        SELECT
            e.id,
            e.file_id,
            e.entity_type,
            e.symbol_name,
            e.display_name,
            e.line_start,
            e.line_end,
            e.signature,
            e.docstring,
            e.language,
            e.content_hash,
            f.file_path,
            f.category
        FROM entities e
        JOIN files f ON f.id = e.file_id
        WHERE e.repo_id = ? AND f.scan_run_id = ?
        """,
        (repo_id, scan_run_id),
    ).fetchall()

    symbol_map: dict[str, sqlite3.Row] = {}
    file_entities: dict[str, sqlite3.Row] = {}
    file_scoped_entities: dict[str, list[sqlite3.Row]] = defaultdict(list)
    display_name_map: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in entity_rows:
        symbol_name = row["symbol_name"]
        if symbol_name:
            symbol_map[symbol_name] = row
        if row["entity_type"] == "file":
            file_entities[row["file_path"]] = row
        file_scoped_entities[row["file_path"]].append(row)
        display_name_map[row["display_name"]].append(row)

    inserted_keys: set[tuple[str, str, str]] = set()
    inserted_count = 0

    def add_relation(
        from_row: sqlite3.Row,
        to_row: sqlite3.Row,
        edge_type: str,
        *,
        weight: float = 1.0,
        meta_json: str | None = None,
    ) -> None:
        nonlocal inserted_count
        if from_row["id"] == to_row["id"]:
            return
        key = (from_row["id"], to_row["id"], edge_type)
        if key in inserted_keys:
            return
        inserted_keys.add(key)
        connection.execute(
            """
            INSERT INTO relations (
                id, scan_run_id, from_entity_id, to_entity_id, edge_type, is_directed, weight, meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _stable_relation_id(scan_run_id, from_row["id"], to_row["id"], edge_type),
                scan_run_id,
                from_row["id"],
                to_row["id"],
                edge_type,
                1,
                weight,
                meta_json,
            ),
        )
        inserted_count += 1

    for row in entity_rows:
        file_row = file_entities.get(row["file_path"])
        if file_row and row["entity_type"] != "file":
            add_relation(file_row, row, "contains", weight=1.0)
        parent = _parent_entity_for_contains(row, symbol_map)
        if parent is not None:
            add_relation(parent, row, "contains", weight=1.0)

    for source_file in source_files:
        if source_file.is_excluded:
            continue
        parse_result = None
        current_module_symbol = _module_symbol_for_path(source_file.path)
        if source_file.language == "python":
            parse_result = PythonParser().parse(source_file.path, source_file.content, source_file.path)
            current_module_symbol = source_file.path.removesuffix(".py").replace("/", ".") or source_file.path
        elif source_file.language in {"typescript", "tsx", "javascript", "jsx"}:
            parse_result = TypeScriptParser().parse(source_file.path, source_file.content, source_file.path, source_file.language)
        if parse_result is None:
            continue
        if parse_result.parse_errors:
            continue
        for relation in parse_result.relations:
            from_row = _resolve_exact_symbol(symbol_map, relation.from_symbol_name)
            if from_row is None:
                continue
            target_row = None
            if relation.edge_type == "imports":
                target_row = _resolve_import_target(symbol_map, relation.to_symbol_name)
            elif relation.edge_type == "calls":
                target_row = _resolve_callable_target(
                    relation.to_symbol_name,
                    current_module_symbol,
                    symbol_map,
                    display_name_map,
                )
            elif relation.edge_type == "route_to_handler":
                target_row = _resolve_callable_target(
                    relation.to_symbol_name,
                    current_module_symbol,
                    symbol_map,
                    display_name_map,
                )
            elif relation.edge_type == "inherits":
                target_row = _resolve_inherits_target(
                    relation.to_symbol_name,
                    current_module_symbol,
                    symbol_map,
                    display_name_map,
                )
            if target_row is None or target_row["file_path"] == source_file.path and target_row["id"] == from_row["id"]:
                continue

            weight = relation.weight
            meta_json = relation.meta_json
            if relation.edge_type == "calls":
                call_count = _call_count(meta_json)
                weight = 1.0 if call_count <= 1 else min(call_count * 0.5, 3.0)
                meta_json = json.dumps(
                    {
                        **(json.loads(meta_json) if meta_json else {}),
                        "call_count": call_count,
                    },
                    ensure_ascii=False,
                )
            add_relation(from_row, target_row, relation.edge_type, weight=weight, meta_json=meta_json)

    return inserted_count


def _parent_entity_for_contains(
    row: sqlite3.Row,
    symbol_map: dict[str, sqlite3.Row],
) -> sqlite3.Row | None:
    symbol_name = row["symbol_name"] or ""
    if row["entity_type"] == "module":
        return None
    if row["entity_type"] == "api_route" and "::" in symbol_name:
        parent_symbol = symbol_name.split("::", 1)[0]
        return symbol_map.get(parent_symbol)
    if row["entity_type"] == "method" and "." in symbol_name:
        parent_symbol = symbol_name.rsplit(".", 1)[0]
        return symbol_map.get(parent_symbol)
    if row["entity_type"] == "module_assignment" and "." in symbol_name:
        parent_symbol = symbol_name.rsplit(".", 1)[0]
        return symbol_map.get(parent_symbol)
    if row["entity_type"] in {"class", "function"} and "." in symbol_name:
        parent_symbol = symbol_name.rsplit(".", 1)[0]
        return symbol_map.get(parent_symbol)
    return None


def _resolve_exact_symbol(
    symbol_map: dict[str, sqlite3.Row],
    symbol_name: str,
) -> sqlite3.Row | None:
    return symbol_map.get(symbol_name)


def _resolve_import_target(
    symbol_map: dict[str, sqlite3.Row],
    target_symbol: str,
) -> sqlite3.Row | None:
    exact = symbol_map.get(target_symbol)
    if exact is not None:
        return exact
    if "." in target_symbol:
        module_symbol = target_symbol.rsplit(".", 1)[0]
        return symbol_map.get(module_symbol)
    return None


def _resolve_callable_target(
    target_symbol: str,
    current_module_symbol: str,
    symbol_map: dict[str, sqlite3.Row],
    display_name_map: dict[str, list[sqlite3.Row]],
) -> sqlite3.Row | None:
    local_symbol = f"{current_module_symbol}.{target_symbol}"
    if local_symbol in symbol_map:
        return symbol_map[local_symbol]
    matches = [
        row
        for row in display_name_map.get(target_symbol, [])
        if row["entity_type"] in {"function", "method", "class"}
    ]
    if len(matches) == 1:
        return matches[0]
    exact = symbol_map.get(target_symbol)
    if exact is not None and exact["entity_type"] != "module":
        return exact
    return None


def _resolve_inherits_target(
    target_symbol: str,
    current_module_symbol: str,
    symbol_map: dict[str, sqlite3.Row],
    display_name_map: dict[str, list[sqlite3.Row]],
) -> sqlite3.Row | None:
    exact = symbol_map.get(target_symbol)
    if exact is not None:
        return exact
    local_symbol = f"{current_module_symbol}.{target_symbol}"
    if local_symbol in symbol_map:
        return symbol_map[local_symbol]
    matches = [row for row in display_name_map.get(target_symbol, []) if row["entity_type"] == "class"]
    if len(matches) == 1:
        return matches[0]
    return None


def _call_count(meta_json: str | None) -> int:
    if not meta_json:
        return 1
    try:
        payload = json.loads(meta_json)
    except json.JSONDecodeError:
        return 1
    value = payload.get("call_count", 1)
    return int(value) if isinstance(value, int | float) else 1


def _module_symbol_for_path(file_path: str) -> str:
    return file_path.rsplit(".", 1)[0] if "." in file_path else file_path
