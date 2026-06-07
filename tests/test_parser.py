from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.parsers.python_parser import PythonParser
from contextgraph_studio.services.indexer import index_repository


def test_python_parser_extracts_entities() -> None:
    content = (
        "import os\n\n"
        "def alpha(x: int) -> int:\n"
        "    \"\"\"alpha doc\"\"\"\n"
        "    return x\n\n"
        "class Beta:\n"
        "    \"\"\"beta doc\"\"\"\n"
        "    def gamma(self):\n"
        "        return 2\n"
    )
    result = PythonParser().parse("pkg/mod.py", content, "file-1")
    symbols = {entity.symbol_name for entity in result.entities}
    assert "pkg.mod.alpha" in symbols
    assert "pkg.mod.Beta" in symbols
    assert "pkg.mod.Beta.gamma" in symbols
    assert any(entity.docstring == "alpha doc" for entity in result.entities if entity.display_name == "alpha")
    assert any(relation.edge_type == "imports" for relation in result.relations)


def test_python_syntax_error_is_soft(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "broken.py").write_text("def broken(:\n    return 1\n", encoding="utf-8")

    settings = Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )
    result = index_repository(repo, settings)
    assert result["parse_error_count"] >= 1

    init_db(settings)
    with connect(settings.database_path) as connection:
        files = connection.execute("SELECT COUNT(*) AS c FROM files").fetchone()
        assert files["c"] == 1

