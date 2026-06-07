from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.domain import ScoredChunk
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import retrieve_context_debug


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
        "vector_index_enabled": False,
        "hybrid_vector_enabled": False,
        "hybrid_graph_enabled": True,
        "embedding_provider": "deterministic",
        "embedding_model": "deterministic-sha256",
        "embedding_dimension": 16,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_graph_diagnostics_reports_disabled_by_ablation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token(token: str) -> bool:\n    return token == 'ok'\n", encoding="utf-8")

    settings = make_settings(tmp_path, hybrid_graph_enabled=False)
    indexed = index_repository(repo, settings)
    _, debug = retrieve_context_debug("verify token", settings, repo_id=str(indexed["repo_id"]))

    assert debug["route_diagnostics"]["graph"]["executed"] is False
    assert debug["route_diagnostics"]["graph"]["reason"] == "disabled_by_ablation"


def test_graph_diagnostics_reports_no_entity_seed(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token(token: str) -> bool:\n    return token == 'ok'\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    def fake_bm25_recall(*args, **kwargs):  # type: ignore[no-untyped-def]
        return (
            [
                ScoredChunk(
                    chunk_id="seedless",
                    file_path="auth.py",
                    entity_id=None,
                    entity=None,
                    entity_type=None,
                    category="source_code",
                    chunk_kind="symbol",
                    line_start=1,
                    line_end=1,
                    score=1.0,
                    source="bm25",
                    tokens_estimate=10,
                )
            ],
            {},
        )

    monkeypatch.setattr("contextgraph_studio.services.retriever.run_bm25_recall", fake_bm25_recall)
    _, debug = retrieve_context_debug("verify token", settings, repo_id=str(indexed["repo_id"]))

    graph = debug["route_diagnostics"]["graph"]
    assert graph["executed"] is True
    assert graph["seed_count"] == 0
    assert graph["seed_entity_count"] == 0
    assert graph["reason"] == "no_entity_seed"


def test_graph_diagnostics_reports_no_relations(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "notes.txt").write_text("alpha retrieval note\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)
    with connect(settings.database_path) as connection:
        row = connection.execute(
            """
            SELECT e.id
            FROM entities e
            JOIN files f ON f.id = e.file_id
            WHERE f.scan_run_id = ? AND e.symbol_name = ?
            """,
            (indexed["scan_run_id"], "notes.txt"),
        ).fetchone()
    assert row is not None

    def fake_bm25_recall(*args, **kwargs):  # type: ignore[no-untyped-def]
        return (
            [
                ScoredChunk(
                    chunk_id="notes-seed",
                    file_path="notes.txt",
                    entity_id=row["id"],
                    entity="notes.txt",
                    entity_type="file",
                    category="doc",
                    chunk_kind="file_summary",
                    line_start=1,
                    line_end=1,
                    score=1.0,
                    source="bm25",
                    tokens_estimate=10,
                )
            ],
            {},
        )

    monkeypatch.setattr("contextgraph_studio.services.retriever.run_bm25_recall", fake_bm25_recall)
    _, debug = retrieve_context_debug("alpha", settings, repo_id=str(indexed["repo_id"]), task_hint="general")

    graph = debug["route_diagnostics"]["graph"]
    assert graph["executed"] is True
    assert graph["seed_count"] > 0
    assert graph["relations_examined"] == 0
    assert graph["reason"] == "no_relations"


def test_graph_diagnostics_reports_edge_type_filtered(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Chunking\n\nTune markdown sections here.\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)
    _, debug = retrieve_context_debug("Chunking markdown sections", settings, repo_id=str(indexed["repo_id"]), task_hint="general")

    graph = debug["route_diagnostics"]["graph"]
    assert graph["executed"] is True
    assert graph["seed_count"] > 0
    assert graph["relations_examined"] == 0
    assert graph["relations_filtered"] > 0
    assert graph["reason"] == "edge_type_filtered"


def test_graph_diagnostics_reports_no_chunk_mapping(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def normalize_token(token: str) -> str:\n"
        "    return token.strip()\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    cleaned = normalize_token(token)\n"
        "    return cleaned == 'ok'\n",
        encoding="utf-8",
    )

    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        row = connection.execute(
            """
            SELECT e.id
            FROM entities e
            JOIN files f ON f.id = e.file_id
            WHERE f.scan_run_id = ? AND e.symbol_name = ?
            """,
            (indexed["scan_run_id"], "auth.normalize_token"),
        ).fetchone()
        assert row is not None
        connection.execute(
            "DELETE FROM chunks WHERE scan_run_id = ? AND entity_id = ?",
            (indexed["scan_run_id"], row["id"]),
        )
        connection.commit()

    _, debug = retrieve_context_debug("verify token auth flow", settings, repo_id=str(indexed["repo_id"]), task_hint="security_auth")

    graph = debug["route_diagnostics"]["graph"]
    assert graph["expanded_entity_count"] > 0
    assert graph["mapped_chunk_count"] == 0
    assert graph["hit_count"] == 0
    assert graph["reason"] == "no_chunk_mapping"


def test_graph_diagnostics_reports_successful_traversal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def normalize_token(token: str) -> str:\n"
        "    return token.strip()\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    cleaned = normalize_token(token)\n"
        "    return cleaned == 'ok'\n",
        encoding="utf-8",
    )

    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)
    _, debug = retrieve_context_debug("verify token auth flow", settings, repo_id=str(indexed["repo_id"]), task_hint="security_auth")

    graph = debug["route_diagnostics"]["graph"]
    assert graph["relations_examined"] > 0
    assert graph["expanded_entity_count"] > 0
    assert graph["mapped_chunk_count"] > 0
    assert graph["hit_count"] > 0
    assert graph["reason"] is None
