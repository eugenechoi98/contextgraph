"""结构化 chunk 切分。"""

import hashlib
import re
from dataclasses import dataclass

from contextgraph_studio.config import Settings
from contextgraph_studio.domain import ChunkRecord, EntityRecord, ParseResult, SourceFile


MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
MAX_SYMBOL_TOKENS = 512


@dataclass(slots=True)
class MarkdownSection:
    """Markdown section 草稿。"""

    heading: str
    content: str
    line_start: int
    line_end: int


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。"""

    if not text.strip():
        return 0
    return max(1, len(text) // 4)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(source: SourceFile) -> list[MarkdownSection]:
    """按 heading 生成 Markdown section。"""

    lines = source.content.splitlines()
    sections: list[MarkdownSection] = []
    current_title = source.path
    current_lines: list[str] = []
    start_line = 1

    for index, line in enumerate(lines, start=1):
        match = MD_HEADING_RE.match(line)
        if match and current_lines:
            sections.append(
                MarkdownSection(
                    heading=current_title,
                    content="\n".join(current_lines).strip(),
                    line_start=start_line,
                    line_end=index - 1,
                )
            )
            current_lines = []
            start_line = index
        if match:
            current_title = match.group(2).strip()
        current_lines.append(line)

    if current_lines:
        sections.append(
            MarkdownSection(
                heading=current_title,
                content="\n".join(current_lines).strip(),
                line_start=start_line,
                line_end=len(lines),
            )
        )
    return sections


def build_file_summary(
    source: SourceFile,
    entities: list[EntityRecord],
    relations: list | None = None,
) -> str:
    """生成 file_summary 内容。"""

    exports = [
        entity.symbol_name
        for entity in entities
        if entity.entity_type in {"class", "function", "method"} and entity.symbol_name and (entity.signature or "").startswith("export ")
    ]
    imports = []
    if relations:
        imports = sorted(
            {
                relation.to_symbol_name
                for relation in relations
                if getattr(relation, "edge_type", None) == "imports" and getattr(relation, "to_symbol_name", None)
            }
        )
    symbols = [
        entity.symbol_name
        for entity in entities
        if entity.entity_type in {"class", "function", "method", "api_route"} and entity.symbol_name
    ]
    export_lines = "\n".join(f"- {item}" for item in exports[:24]) if exports else "- (no extracted exports)"
    import_lines = "\n".join(f"- {item}" for item in imports[:24]) if imports else "- (no extracted imports)"
    symbol_lines = "\n".join(f"- {item}" for item in symbols[:24]) if symbols else "- (no extracted symbols)"
    return (
        f"file_path: {source.path}\n"
        f"language: {source.language}\n"
        f"category: {source.category}\n"
        f"line_count: {source.line_count}\n"
        f"exports:\n{export_lines}\n"
        f"imports:\n{import_lines}\n"
        f"symbols:\n{symbol_lines}"
    )


def split_large_symbol(
    entity_symbol_name: str | None,
    content: str,
    line_start: int,
    max_tokens: int = MAX_SYMBOL_TOKENS,
) -> list[ChunkRecord]:
    """拆分超长 symbol chunk。"""

    tokens = estimate_tokens(content)
    lines = content.splitlines()
    line_end = line_start + max(0, len(lines) - 1)
    if tokens <= max_tokens:
        return [
            ChunkRecord(
                entity_symbol_name=entity_symbol_name,
                chunk_kind="symbol",
                content=content.strip(),
                tokens_estimate=tokens,
                line_start=line_start,
                line_end=line_end,
                content_hash=_hash_text(content),
            )
        ]

    midpoint = max(1, len(lines) // 2)
    parts = [
        (
            f"[continuation 1/2 of {entity_symbol_name}]\n" + "\n".join(lines[:midpoint]).strip(),
            line_start,
            line_start + max(0, midpoint - 1),
            1,
        ),
        (
            f"[continuation 2/2 of {entity_symbol_name}]\n" + "\n".join(lines[midpoint:]).strip(),
            line_start + midpoint,
            line_end,
            2,
        ),
    ]
    return [
        ChunkRecord(
            entity_symbol_name=entity_symbol_name,
            chunk_kind="symbol",
            content=part_content.strip(),
            tokens_estimate=estimate_tokens(part_content),
            line_start=part_start,
            line_end=part_end,
            content_hash=_hash_text(part_content),
            continuation_index=continuation_index,
        )
        for part_content, part_start, part_end, continuation_index in parts
        if part_content.strip()
    ]


def chunk_windowed(source: SourceFile, settings: Settings) -> list[ChunkRecord]:
    """通用窗口切分。"""

    lines = source.content.splitlines()
    chunks: list[ChunkRecord] = []
    start = 0
    while start < len(lines):
        end = min(start + settings.chunk_lines, len(lines))
        content = "\n".join(lines[start:end]).strip()
        if content:
            chunks.append(
                ChunkRecord(
                    entity_symbol_name=None,
                    chunk_kind="schema_unit" if source.category == "schema" else "file_summary",
                    content=content,
                    tokens_estimate=estimate_tokens(content),
                    line_start=start + 1,
                    line_end=end,
                    content_hash=_hash_text(content),
                )
            )
        if end == len(lines):
            break
        start = max(end - settings.chunk_overlap, start + 1)
    return chunks


def chunk_structured_source(source: SourceFile, parse_result: ParseResult) -> list[ChunkRecord]:
    """Generate chunks from extracted code entities."""

    chunks: list[ChunkRecord] = []
    lines = source.content.splitlines()
    entities = parse_result.entities
    file_summary = build_file_summary(source, entities, parse_result.relations)
    chunks.append(
        ChunkRecord(
            entity_symbol_name=source.path,
            chunk_kind="file_summary",
            content=file_summary,
            tokens_estimate=estimate_tokens(file_summary),
            line_start=1,
            line_end=max(1, len(lines)),
            content_hash=_hash_text(file_summary),
        )
    )

    class_methods: dict[str, list[EntityRecord]] = {}
    for entity in entities:
        if entity.entity_type == "method" and entity.parent_symbol_name:
            class_methods.setdefault(entity.parent_symbol_name, []).append(entity)

    for entity in entities:
        if entity.entity_type == "class":
            method_list = class_methods.get(entity.symbol_name or "", [])
            summary_lines = [entity.signature or entity.display_name]
            if entity.docstring:
                summary_lines.append(entity.docstring)
            if method_list:
                summary_lines.append("methods:")
                summary_lines.extend(f"- {method.symbol_name}" for method in method_list)
            summary = "\n".join(summary_lines).strip()
            chunks.append(
                ChunkRecord(
                    entity_symbol_name=entity.symbol_name,
                    chunk_kind="symbol",
                    content=summary,
                    tokens_estimate=estimate_tokens(summary),
                    line_start=entity.line_start,
                    line_end=entity.line_end,
                    content_hash=_hash_text(summary),
                )
            )
        elif entity.entity_type in {"function", "method"} and entity.line_start and entity.line_end:
            snippet = "\n".join(lines[entity.line_start - 1 : entity.line_end]).strip()
            chunks.extend(split_large_symbol(entity.symbol_name, snippet, entity.line_start))
        elif entity.entity_type == "api_route":
            route_content = entity.signature or entity.display_name
            chunks.append(
                ChunkRecord(
                    entity_symbol_name=entity.symbol_name,
                    chunk_kind="symbol",
                    content=route_content,
                    tokens_estimate=estimate_tokens(route_content),
                    line_start=entity.line_start,
                    line_end=entity.line_end,
                    content_hash=_hash_text(route_content),
                )
            )
    return chunks


def chunk_source_file(
    source: SourceFile,
    settings: Settings,
    parse_result: ParseResult | None = None,
) -> list[ChunkRecord]:
    """根据语言与实体选择切分策略。"""

    if source.language == "markdown":
        return [
            ChunkRecord(
                entity_symbol_name=section.heading,
                chunk_kind="doc_section",
                content=section.content,
                tokens_estimate=estimate_tokens(section.content),
                line_start=section.line_start,
                line_end=section.line_end,
                content_hash=_hash_text(section.content),
            )
            for section in chunk_markdown(source)
        ]
    if source.language in {"python", "typescript", "tsx", "javascript", "jsx"} and parse_result is not None:
        return chunk_structured_source(source, parse_result)
    return chunk_windowed(source, settings)
