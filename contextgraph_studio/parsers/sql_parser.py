"""Minimal structured SQL parser for CREATE statements."""

from __future__ import annotations

import hashlib
import re

from contextgraph_studio.domain import EntityRecord, ParseResult, RelationRecord


PARSER_VERSION = "sql-regex-v1"
IDENT_PART = r'(?:[A-Za-z_][\w$]*|"[^"]+"|\[[^\]]+\]|`[^`]+`)'
QUALIFIED_IDENT = rf"{IDENT_PART}(?:\s*\.\s*{IDENT_PART})*"
CREATE_TABLE_RE = re.compile(
    rf"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>{QUALIFIED_IDENT})(?=\s|\()",
    re.IGNORECASE | re.DOTALL,
)
CREATE_VIEW_RE = re.compile(
    rf"^\s*CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>{QUALIFIED_IDENT})(?=\s+AS\b|\s|$)",
    re.IGNORECASE | re.DOTALL,
)
CREATE_INDEX_RE = re.compile(
    rf"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>{QUALIFIED_IDENT})(?=\s+ON\b)\s+ON\s+(?P<table>{QUALIFIED_IDENT})(?=\s|\()",
    re.IGNORECASE | re.DOTALL,
)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_number_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _normalize_identifier(raw: str) -> str:
    parts = [part.strip() for part in re.split(r"\s*\.\s*", raw.strip()) if part.strip()]
    normalized: list[str] = []
    for part in parts:
        if (part.startswith('"') and part.endswith('"')) or (part.startswith("[") and part.endswith("]")) or (
            part.startswith("`") and part.endswith("`")
        ):
            normalized.append(part[1:-1])
        else:
            normalized.append(part)
    return ".".join(normalized)


def _split_sql_statements(content: str) -> list[tuple[str, int, int]]:
    statements: list[tuple[str, int, int]] = []
    start = 0
    depth = 0
    in_single = False
    in_double = False
    in_bracket = False
    i = 0
    while i < len(content):
        ch = content[i]
        nxt = content[i + 1] if i + 1 < len(content) else ""
        if not in_single and not in_double and not in_bracket and ch == "-" and nxt == "-":
            i += 2
            while i < len(content) and content[i] != "\n":
                i += 1
            continue
        if not in_single and not in_double and not in_bracket and ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(content) and not (content[i] == "*" and content[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch == "'" and not in_double and not in_bracket:
            in_single = not in_single
        elif ch == '"' and not in_single and not in_bracket:
            in_double = not in_double
        elif ch == "[" and not in_single and not in_double:
            in_bracket = True
        elif ch == "]" and in_bracket and not in_single and not in_double:
            in_bracket = False
        elif not in_single and not in_double and not in_bracket:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch == ";" and depth == 0:
                statement = content[start:i].strip()
                if statement:
                    statements.append((statement, start, i))
                start = i + 1
        i += 1
    tail = content[start:].strip()
    if tail:
        statements.append((tail, start, len(content)))
    normalized: list[tuple[str, int, int]] = []
    create_line_re = re.compile(r"(?im)^\s*CREATE\b")
    for statement, stmt_start, stmt_end in statements:
        create_positions = [match.start() for match in create_line_re.finditer(statement)]
        if len(create_positions) <= 1:
            normalized.append((statement, stmt_start, stmt_end))
            continue
        split_points = create_positions[1:]
        local_start = 0
        for split_at in split_points:
            part = statement[local_start:split_at].strip()
            if part:
                normalized.append((part, stmt_start + local_start, stmt_start + split_at))
            local_start = split_at
        tail_part = statement[local_start:].strip()
        if tail_part:
            normalized.append((tail_part, stmt_start + local_start, stmt_end))
    return normalized


class SqlParser:
    """Extract minimal SQL schema entities from CREATE statements."""

    def parse(self, file_path: str, content: str, file_id: str) -> ParseResult:
        del file_id
        entities: list[EntityRecord] = []
        relations: list[RelationRecord] = []
        parse_errors: list[str] = []

        for statement, start, end in _split_sql_statements(content):
            entity_type: str | None = None
            symbol_name: str | None = None
            match = CREATE_TABLE_RE.match(statement)
            if match:
                if statement.count("(") > statement.count(")"):
                    parse_errors.append(
                        f"{file_path}:{_line_number_at(content, start)}: unsupported or incomplete CREATE statement"
                    )
                    continue
                entity_type = "db_table"
                symbol_name = _normalize_identifier(match.group("name"))
            else:
                match = CREATE_VIEW_RE.match(statement)
                if match:
                    entity_type = "db_view"
                    symbol_name = _normalize_identifier(match.group("name"))
                else:
                    match = CREATE_INDEX_RE.match(statement)
                    if match:
                        entity_type = "db_index"
                        symbol_name = _normalize_identifier(match.group("name"))

            if entity_type and symbol_name:
                line_start = _line_number_at(content, start)
                line_end = _line_number_at(content, max(start, end - 1))
                entities.append(
                    EntityRecord(
                        entity_type=entity_type,
                        symbol_name=symbol_name,
                        display_name=symbol_name,
                        line_start=line_start,
                        line_end=line_end,
                        signature=statement.strip(),
                        docstring=None,
                        language="sql",
                        content_hash=_hash_text(statement),
                        parent_symbol_name=file_path,
                    )
                )
            elif re.match(r"^\s*CREATE\b", statement, re.IGNORECASE):
                parse_errors.append(f"{file_path}:{_line_number_at(content, start)}: unsupported or incomplete CREATE statement")

        return ParseResult(
            entities=entities,
            relations=relations,
            parse_errors=parse_errors,
            language="sql",
            parser_version=PARSER_VERSION,
        )
