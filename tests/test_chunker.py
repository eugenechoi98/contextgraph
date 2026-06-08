from contextgraph_studio.config import Settings
from contextgraph_studio.domain import EntityRecord, ParseResult, SourceFile
from contextgraph_studio.services.chunker import chunk_source_file


def build_source(path: str, language: str, content: str, category: str = "source_code") -> SourceFile:
    return SourceFile(
        repo_id="repo-1",
        path=path,
        absolute_path=path,
        category=category,
        language=language,
        content_hash="abc",
        content=content,
        size_bytes=len(content.encode("utf-8")),
        line_count=len(content.splitlines()),
    )


def test_chunk_markdown_by_heading() -> None:
    source = build_source(
        "README.md",
        "markdown",
        "# Title\nintro\n## Usage\nmore",
        category="doc",
    )
    chunks = chunk_source_file(source, Settings())
    assert len(chunks) == 2
    assert chunks[0].chunk_kind == "doc_section"
    assert chunks[0].entity_symbol_name == "Title"
    assert chunks[1].entity_symbol_name == "Usage"


def test_chunk_python_entities() -> None:
    source = build_source(
        "app.py",
        "python",
        "def alpha():\n    return 1\n\nclass Beta:\n    def gamma(self):\n        return 2\n",
    )
    entities = [
        EntityRecord("module", "app", "app.py", 1, 6, None, None, "python", "mhash"),
        EntityRecord("function", "app.alpha", "alpha", 1, 2, "def alpha()", None, "python", "ahash", "app"),
        EntityRecord("class", "app.Beta", "Beta", 4, 6, "class Beta", None, "python", "chash", "app"),
        EntityRecord("method", "app.Beta.gamma", "gamma", 5, 6, "def gamma(self)", None, "python", "m2hash", "app.Beta"),
    ]
    parse_result = ParseResult(
        entities=entities,
        relations=[],
        parse_errors=[],
        language="python",
        parser_version="python-ast-v1",
    )
    chunks = chunk_source_file(source, Settings(), parse_result)
    assert any(chunk.chunk_kind == "file_summary" for chunk in chunks)
    assert any(chunk.entity_symbol_name == "app.alpha" for chunk in chunks)
    assert any(chunk.entity_symbol_name == "app.Beta.gamma" for chunk in chunks)
