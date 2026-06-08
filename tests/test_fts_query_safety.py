from pathlib import Path

import contextgraph_studio.services.retriever as retriever_module
from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.retrieval.fts_query import NormalizedFtsQuery, normalize_fts_query
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import retrieve_context_debug, search_bm25_with_diagnostics


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
        vector_index_enabled=False,
        hybrid_vector_enabled=False,
        hybrid_graph_enabled=False,
        embedding_dimension=16,
    )


def test_normalize_fts_query_safely_splits_punctuation_and_keeps_useful_tokens() -> None:
    cases = {
        "astropy.modeling": ["astropy", "modeling"],
        "m.Linear1D": ["m", "Linear1D"],
        "foo.bar.baz": ["foo", "bar", "baz"],
        "src/auth.py": ["src", "auth", "py"],
        'config["database"]["host"]': ["config", "database", "host"],
        "中文 query": ["中文", "query"],
        "snake_case": ["snake_case"],
        "": [],
        "....::::": [],
    }

    for raw, expected in cases.items():
        normalized = normalize_fts_query(raw)
        assert normalized.tokens == expected
        assert "." not in normalized.normalized_query
        assert "[" not in normalized.normalized_query
        assert "*" not in normalized.normalized_query


def test_normalize_fts_query_caps_long_queries() -> None:
    normalized = normalize_fts_query(" ".join(f"token{i}" for i in range(200)))

    assert len(normalized.tokens) == 80
    assert normalized.tokens[0] == "token0"
    assert normalized.tokens[-1] == "token79"


def test_dotted_query_uses_bm25_without_fts_syntax_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "separable.py").write_text(
        "def separability_matrix(model):\n"
        "    return model\n\n"
        "def _separable(transform):\n"
        "    return separability_matrix(transform)\n",
        encoding="utf-8",
    )
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        result = search_bm25_with_diagnostics(
            connection,
            "astropy.modeling.separable separability_matrix m.Linear1D",
            str(indexed["repo_id"]),
            str(indexed["scan_run_id"]),
            10,
            category="source_code",
        )

    assert result.hits
    assert result.hits[0].file_path == "separable.py"
    assert result.diagnostics["fts_strategy"] == "normalized_match"
    assert result.diagnostics["fallback_used"] is False


def test_ranked_fallback_orders_related_chunks_when_match_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "z_unrelated.py").write_text("def unrelated():\n    return 'noise'\n", encoding="utf-8")
    (repo / "a_relevant.py").write_text(
        "def refresh_token_route():\n"
        "    return 'refresh token authentication route'\n",
        encoding="utf-8",
    )
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    def unsafe_normalizer(query: str) -> NormalizedFtsQuery:
        return NormalizedFtsQuery(
            original_query=query,
            normalized_query='"refresh".',
            tokens=["refresh", "token", "route"],
            strategy="normalized_match",
        )

    monkeypatch.setattr(retriever_module, "normalize_fts_query", unsafe_normalizer)
    with connect(settings.database_path) as connection:
        result = search_bm25_with_diagnostics(
            connection,
            "refresh.token route",
            str(indexed["repo_id"]),
            str(indexed["scan_run_id"]),
            10,
            category="source_code",
        )

    assert result.diagnostics["fallback_used"] is True
    assert str(result.diagnostics["fallback_reason"]).startswith("fts_error")
    assert result.hits[0].file_path == "a_relevant.py"
    assert result.hits[0].score > 0


def test_all_bm25_lanes_expose_fts_safety_diagnostics(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "service.py").write_text(
        "def read_database_host(config):\n"
        "    return config['database']['host']\n",
        encoding="utf-8",
    )
    (repo / "schema.sql").write_text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);\n", encoding="utf-8")
    (repo / "settings.json").write_text('{"database": {"host": "localhost", "port": 5432}}\n', encoding="utf-8")
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    _, general_debug = retrieve_context_debug(
        "service.read_database_host",
        settings,
        repo_id=str(indexed["repo_id"]),
        task_hint="general",
    )
    _, database_debug = retrieve_context_debug(
        "database.schema users.id",
        settings,
        repo_id=str(indexed["repo_id"]),
        task_hint="database",
    )
    _, config_debug = retrieve_context_debug(
        'config["database"]["host"]',
        settings,
        repo_id=str(indexed["repo_id"]),
        task_hint="configuration",
    )

    general_lanes = general_debug["route_diagnostics"]["bm25_lanes"]
    database_lanes = database_debug["route_diagnostics"]["bm25_lanes"]
    config_lanes = config_debug["route_diagnostics"]["bm25_lanes"]

    assert general_lanes["general"]["fts_strategy"] == "normalized_match"
    assert general_lanes["source_code"]["fts_strategy"] == "normalized_match"
    assert database_lanes["schema"]["fts_strategy"] == "normalized_match"
    assert config_lanes["config"]["fts_strategy"] == "normalized_match"
