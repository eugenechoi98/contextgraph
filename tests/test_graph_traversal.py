from pathlib import Path

import pytest

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.graph.scorer import compute_graph_score
from contextgraph_studio.graph.traversal import expand_from_entities, graph_search, resolve_seed_entity_ids
from contextgraph_studio.services import indexer as indexer_module
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import retrieve_context


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_graph_traversal_supports_one_hop_two_hop_and_cycle_control(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("from b import b\n\ndef a():\n    return b()\n", encoding="utf-8")
    (repo / "b.py").write_text("from a import a\n\ndef b():\n    return a()\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    result = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        seed_ids = resolve_seed_entity_ids(connection, result["repo_id"], result["scan_run_id"], symbol="a.a")
        one_hop = expand_from_entities(connection, seed_ids, result["repo_id"], result["scan_run_id"], max_hops=1)
        two_hop = expand_from_entities(connection, seed_ids, result["repo_id"], result["scan_run_id"], max_hops=2)
        calls_only = expand_from_entities(
            connection,
            seed_ids,
            result["repo_id"],
            result["scan_run_id"],
            edge_types=["calls"],
            max_hops=2,
        )

    assert any(item.symbol_name == "b.b" and item.graph_distance == 1 for item in one_hop)
    assert any(item.symbol_name == "b.b" and item.graph_distance <= 2 for item in two_hop)
    assert len(two_hop) <= 2
    assert sum(1 for item in two_hop if item.symbol_name == "a.a") == 1
    assert all(item.edge_type in {"seed", "calls"} for item in calls_only)


def test_graph_traversal_handles_empty_seed_and_invalid_hops(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with pytest.raises(ValueError):
        graph_search(settings, symbol="missing", max_hops=-1)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    result = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        assert expand_from_entities(connection, [], result["repo_id"], result["scan_run_id"], max_hops=2) == []
        seed_ids = resolve_seed_entity_ids(connection, result["repo_id"], result["scan_run_id"], symbol="app.alpha")
        zero_hop = expand_from_entities(connection, seed_ids, result["repo_id"], result["scan_run_id"], max_hops=0)
    assert len(zero_hop) == 1
    assert zero_hop[0].edge_type == "seed"


def test_graph_search_respects_latest_successful_scan_and_deleted_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    util = repo / "util.py"
    util.write_text("def helper():\n    return 1\n", encoding="utf-8")
    auth = repo / "auth.py"
    auth.write_text("from util import helper\n\ndef verify_token():\n    return helper()\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    first = index_repository(repo, settings)
    first_hits = graph_search(settings, symbol="auth.verify_token", repo_id=first["repo_id"], max_hops=2)
    assert any(item.symbol_name == "util.helper" for item in first_hits)

    util.unlink()
    second = index_repository(repo, settings)
    second_hits = graph_search(settings, symbol="auth.verify_token", repo_id=second["repo_id"], max_hops=2)
    assert all(item.symbol_name != "util.helper" for item in second_hits)

    auth.write_text("def verify_token():\n    return False\n", encoding="utf-8")

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("forced graph failure")

    monkeypatch.setattr(indexer_module, "build_relations_for_scan", boom)
    with pytest.raises(RuntimeError):
        index_repository(repo, settings)

    latest_hits = graph_search(settings, symbol="auth.verify_token", repo_id=first["repo_id"], max_hops=2)
    assert all(item.symbol_name != "util.helper" for item in latest_hits)


def test_graph_search_is_repo_scoped_and_retrieve_stays_bm25(tmp_path: Path) -> None:
    repo_one = tmp_path / "repo_one"
    repo_one.mkdir()
    (repo_one / "service.py").write_text("def verify_token():\n    return True\n", encoding="utf-8")

    repo_two = tmp_path / "repo_two"
    repo_two.mkdir()
    (repo_two / "service.py").write_text("def verify_token():\n    return False\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    first = index_repository(repo_one, settings)
    second = index_repository(repo_two, settings)

    repo_one_hits = graph_search(settings, symbol="service.verify_token", repo_id=first["repo_id"], max_hops=0)
    repo_two_hits = graph_search(settings, symbol="service.verify_token", repo_id=second["repo_id"], max_hops=0)
    assert repo_one_hits[0].file_path == "service.py"
    assert repo_two_hits[0].file_path == "service.py"
    assert repo_one_hits[0].entity_id != repo_two_hits[0].entity_id

    pack = retrieve_context("verify token", settings, repo_id=first["repo_id"])
    assert pack.retrieval_strategy == ["bm25"]
    assert pack.graph_paths == []


def test_graph_score_formula_matches_expected_values() -> None:
    assert compute_graph_score("source_code", "seed", 1, "contains") == 0.5
    assert compute_graph_score("test", "seed", 1, "contains") == 0.4
    assert compute_graph_score("doc", "seed", 2, "imports") == pytest.approx(1 / 3 * 0.5)
    assert compute_graph_score("unknown", "seed", 1, "calls", weight=1.5) == pytest.approx(0.5 * 1.5 * 0.7)
