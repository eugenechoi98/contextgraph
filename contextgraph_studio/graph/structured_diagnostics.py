"""Read-only diagnostics for potential structured cross-file relations."""

from __future__ import annotations

import ast
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


SQL_TABLE_RE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][A-Za-z0-9_$.]*)", re.IGNORECASE)
SQL_KEYWORDS_RE = re.compile(r"\b(?:SELECT|UPDATE|INSERT|DELETE|FROM|JOIN|WHERE|SET)\b", re.IGNORECASE)


@dataclass(slots=True)
class StructuredRelationCandidate:
    """One potential relation found by static diagnostics."""

    source_entity: str
    source_entity_type: str
    source_file: str
    candidate_consumer_file: str | None
    candidate_consumer_entity: str | None
    match_type: str
    matched_text: str
    confidence: str
    safe_to_materialize: bool
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def audit_structured_relations(
    connection: sqlite3.Connection,
    *,
    repo_root: Path,
    repo_id: str,
    scan_run_id: str,
) -> dict[str, list[StructuredRelationCandidate]]:
    """Return read-only relation candidates for the current scan."""

    db_tables = _load_entities(connection, repo_id, scan_run_id, "db_table")
    config_keys = _load_entities(connection, repo_id, scan_run_id, "config_key")
    source_files = _load_source_files(connection, repo_id, scan_run_id)

    table_candidates: list[StructuredRelationCandidate] = []
    config_candidates: list[StructuredRelationCandidate] = []
    for source_file in source_files:
        path = repo_root / source_file["file_path"]
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        _attach_parents(tree)
        file_entities = _load_file_entities(connection, repo_id, scan_run_id, source_file["file_path"])
        content = path.read_text(encoding="utf-8")
        table_candidates.extend(_find_table_candidates(db_tables, source_file["file_path"], tree, file_entities))
        table_candidates.extend(_find_table_skips(db_tables, source_file["file_path"], tree, file_entities))
        config_candidates.extend(_find_config_candidates(config_keys, source_file["file_path"], tree, file_entities))
        config_candidates.extend(_find_config_skips(config_keys, source_file["file_path"], content))
    return {
        "uses_table": table_candidates,
        "configures": config_candidates,
    }


def summarize_candidates(candidates: list[StructuredRelationCandidate]) -> dict[str, int]:
    """Summarize candidate quality for reports and tests."""

    safe = sum(1 for item in candidates if item.safe_to_materialize)
    skipped = sum(1 for item in candidates if not item.safe_to_materialize)
    return {
        "candidate_count": len(candidates),
        "safe_to_materialize_count": safe,
        "skipped_count": skipped,
    }


def _load_entities(
    connection: sqlite3.Connection,
    repo_id: str,
    scan_run_id: str,
    entity_type: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT e.*, f.file_path
        FROM entities e
        JOIN files f ON f.id = e.file_id
        WHERE e.repo_id = ?
          AND f.scan_run_id = ?
          AND e.entity_type = ?
        ORDER BY f.file_path, e.symbol_name
        """,
        (repo_id, scan_run_id, entity_type),
    ).fetchall()


def _load_source_files(connection: sqlite3.Connection, repo_id: str, scan_run_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT file_path
        FROM files
        WHERE repo_id = ?
          AND scan_run_id = ?
          AND category = 'source_code'
          AND language = 'python'
        ORDER BY file_path
        """,
        (repo_id, scan_run_id),
    ).fetchall()


def _load_file_entities(
    connection: sqlite3.Connection,
    repo_id: str,
    scan_run_id: str,
    file_path: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT e.*
        FROM entities e
        JOIN files f ON f.id = e.file_id
        WHERE e.repo_id = ?
          AND f.scan_run_id = ?
          AND f.file_path = ?
        ORDER BY COALESCE(e.line_start, 0), COALESCE(e.line_end, 999999)
        """,
        (repo_id, scan_run_id, file_path),
    ).fetchall()


def _find_table_candidates(
    db_tables: list[sqlite3.Row],
    file_path: str,
    tree: ast.AST,
    file_entities: list[sqlite3.Row],
) -> list[StructuredRelationCandidate]:
    candidates: list[StructuredRelationCandidate] = []
    table_by_name = {_table_leaf(row["symbol_name"] or row["display_name"]): row for row in db_tables}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value.strip()
        consumer = _entity_for_lineno(file_entities, getattr(node, "lineno", None))
        if SQL_KEYWORDS_RE.search(text):
            for match in SQL_TABLE_RE.finditer(text):
                table_name = _table_leaf(match.group(1))
                table = table_by_name.get(table_name)
                if table is None:
                    continue
                candidates.append(
                    _candidate(table, file_path, consumer, "sql_string_table_name", match.group(0), True)
                )
            continue
        if text in table_by_name and _is_table_constant(node):
            candidates.append(_candidate(table_by_name[text], file_path, consumer, "table_name_constant", text, True))
    return candidates


def _find_table_skips(
    db_tables: list[sqlite3.Row],
    file_path: str,
    tree: ast.AST,
    file_entities: list[sqlite3.Row],
) -> list[StructuredRelationCandidate]:
    skipped: list[StructuredRelationCandidate] = []
    table_by_name = {_table_leaf(row["symbol_name"] or row["display_name"]): row for row in db_tables}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value.strip()
        if _is_known_sql_table_match(text, table_by_name) or _is_table_constant(node):
            continue
        for table_name, table in table_by_name.items():
            if _contains_word(text, table_name):
                consumer = _entity_for_lineno(file_entities, getattr(node, "lineno", None))
                skipped.append(
                    _candidate(
                        table,
                        file_path,
                        consumer,
                        "natural_language_string",
                        text,
                        False,
                        skip_reason="not_sql_or_table_constant",
                    )
                )
    return skipped


def _find_config_candidates(
    config_keys: list[sqlite3.Row],
    file_path: str,
    tree: ast.AST,
    file_entities: list[sqlite3.Row],
) -> list[StructuredRelationCandidate]:
    key_map = {row["symbol_name"] or row["display_name"]: row for row in config_keys}
    candidates: list[StructuredRelationCandidate] = []
    for node in ast.walk(tree):
        key_path = _extract_config_key_path(node)
        if key_path is None or key_path not in key_map:
            continue
        consumer = _entity_for_lineno(file_entities, getattr(node, "lineno", None))
        candidates.append(_candidate(key_map[key_path], file_path, consumer, "config_key_access", key_path, True))
    return candidates


def _find_config_skips(
    config_keys: list[sqlite3.Row],
    file_path: str,
    content: str,
) -> list[StructuredRelationCandidate]:
    skipped: list[StructuredRelationCandidate] = []
    lowered = content.lower()
    for key in config_keys:
        symbol = key["symbol_name"] or key["display_name"]
        parts = symbol.split(".")
        if len(parts) < 2:
            continue
        if all(part.lower().replace("[]", "") in lowered for part in parts):
            skipped.append(
                StructuredRelationCandidate(
                    source_entity=symbol,
                    source_entity_type=key["entity_type"],
                    source_file=key["file_path"],
                    candidate_consumer_file=file_path,
                    candidate_consumer_entity=None,
                    match_type="natural_language_config_terms",
                    matched_text=symbol,
                    confidence="low",
                    safe_to_materialize=False,
                    skip_reason="not_static_config_access",
                )
            )
    return skipped


def _extract_config_key_path(node: ast.AST) -> str | None:
    subscript_path = _extract_subscript_path(node)
    if subscript_path:
        return subscript_path
    return _extract_get_chain_path(node)


def _extract_subscript_path(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Subscript):
        key = _literal_key(current.slice)
        if key is None:
            return None
        parts.append(key)
        current = current.value
    if isinstance(current, ast.Name) and current.id == "config" and parts:
        return ".".join(reversed(parts))
    return None


def _extract_get_chain_path(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Call) and isinstance(current.func, ast.Attribute) and current.func.attr == "get":
        if not current.args:
            return None
        key = _literal_key(current.args[0])
        if key is None:
            return None
        parts.append(key)
        current = current.func.value
    if isinstance(current, ast.Name) and current.id == "config" and parts:
        return ".".join(reversed(parts))
    return None


def _literal_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_table_constant(node: ast.AST) -> bool:
    parent = getattr(node, "_parent", None)
    if not isinstance(parent, ast.Assign):
        return False
    return any(isinstance(target, ast.Name) and "TABLE" in target.id.upper() for target in parent.targets)


def _entity_for_lineno(file_entities: list[sqlite3.Row], lineno: int | None) -> sqlite3.Row | None:
    if lineno is None:
        return None
    best: sqlite3.Row | None = None
    for row in file_entities:
        if row["entity_type"] not in {"function", "method", "module"}:
            continue
        start = row["line_start"] or 0
        end = row["line_end"] or start
        if start <= lineno <= end:
            if best is None or (row["line_start"] or 0) >= (best["line_start"] or 0):
                best = row
    return best


def _candidate(
    structured_row: sqlite3.Row,
    consumer_file: str,
    consumer_row: sqlite3.Row | None,
    match_type: str,
    matched_text: str,
    safe_to_materialize: bool,
    *,
    skip_reason: str | None = None,
) -> StructuredRelationCandidate:
    return StructuredRelationCandidate(
        source_entity=structured_row["symbol_name"] or structured_row["display_name"],
        source_entity_type=structured_row["entity_type"],
        source_file=structured_row["file_path"],
        candidate_consumer_file=consumer_file,
        candidate_consumer_entity=consumer_row["symbol_name"] if consumer_row else None,
        match_type=match_type,
        matched_text=matched_text,
        confidence="high" if safe_to_materialize else "low",
        safe_to_materialize=safe_to_materialize,
        skip_reason=skip_reason,
    )


def _table_leaf(name: str) -> str:
    cleaned = name.strip().strip('"[]`')
    return cleaned.rsplit(".", 1)[-1]


def _contains_word(text: str, word: str) -> bool:
    return any(token == word.lower() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower()))


def _is_known_sql_table_match(text: str, table_by_name: dict[str, sqlite3.Row]) -> bool:
    return any(_table_leaf(match.group(1)) in table_by_name for match in SQL_TABLE_RE.finditer(text))


def _attach_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "_parent", parent)
