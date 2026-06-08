import json
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.eval.runner import run_eval
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.planner import build_plan
from contextgraph_studio.services.retriever import retrieve_context_debug


FIXTURE_REPO = Path("tests/fixtures/sample_structured_repo")
SECRET_VALUES = ("super-secret-password", "abc123secret", "hidden-value")


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
        "bm25_general_candidate_limit": 6,
        "bm25_source_code_candidate_limit": 4,
        "bm25_schema_candidate_limit": 4,
        "bm25_config_candidate_limit": 4,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_planner_resolves_database_and_configuration_strategies(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    database_hint = build_plan("anything", settings, task_hint="database")
    database_keywords = build_plan("change the users table database index", settings)
    configuration_hint = build_plan("anything", settings, task_hint="configuration")
    configuration_keywords = build_plan("change the database host configuration", settings)
    general = build_plan("small implementation cleanup", settings)
    docs = build_plan("update readme documentation guide", settings, task_hint="general")

    assert database_hint.task_type == "database"
    assert database_keywords.task_type == "database"
    assert database_hint.schema_lane_enabled is True
    assert database_hint.config_lane_enabled is False
    assert "schema" in database_hint.candidate_lanes
    assert database_hint.graph_edge_types == ["calls", "imports"]

    assert configuration_hint.task_type == "configuration"
    assert configuration_keywords.task_type == "configuration"
    assert configuration_hint.config_lane_enabled is True
    assert configuration_hint.schema_lane_enabled is False
    assert "config" in configuration_hint.candidate_lanes
    assert configuration_hint.graph_edge_types == ["calls", "imports"]

    assert general.task_type == "general"
    assert general.schema_lane_enabled is False
    assert general.config_lane_enabled is False
    assert docs.source_code_lane_enabled is False
    assert docs.schema_lane_enabled is False
    assert docs.config_lane_enabled is False


def test_structured_candidate_lanes_run_only_for_structured_tasks(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    indexed = index_repository(FIXTURE_REPO, settings)

    _, database_debug = retrieve_context_debug(
        "Update the users table email index",
        settings,
        repo_id=indexed["repo_id"],
        task_hint="database",
        top_k=18,
    )
    database_lanes = database_debug["route_diagnostics"]["bm25_lanes"]
    assert database_lanes["schema"]["executed"] is True
    assert database_lanes["schema_hit_count"] >= 1
    assert database_lanes["config"]["executed"] is False
    assert database_lanes["merged_hit_count"] <= 18

    _, configuration_debug = retrieve_context_debug(
        "Change the database host configuration",
        settings,
        repo_id=indexed["repo_id"],
        task_hint="configuration",
        top_k=18,
    )
    configuration_lanes = configuration_debug["route_diagnostics"]["bm25_lanes"]
    assert configuration_lanes["config"]["executed"] is True
    assert configuration_lanes["config_hit_count"] >= 1
    assert configuration_lanes["schema"]["executed"] is False
    assert configuration_lanes["merged_hit_count"] <= 18

    _, general_debug = retrieve_context_debug(
        "update parser implementation",
        settings,
        repo_id=indexed["repo_id"],
        task_hint="general",
        top_k=18,
    )
    general_lanes = general_debug["route_diagnostics"]["bm25_lanes"]
    assert general_lanes["schema"]["executed"] is False
    assert general_lanes["config"]["executed"] is False


def test_sensitive_values_do_not_enter_chunks_contextpack_trace_or_eval(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    indexed = index_repository(FIXTURE_REPO, settings)

    with connect(settings.database_path) as connection:
        chunk_text = "\n".join(
            row["content"]
            for row in connection.execute(
                "SELECT content FROM chunks WHERE repo_id = ?",
                (indexed["repo_id"],),
            ).fetchall()
        )
        fts_text = "\n".join(
            row["content"]
            for row in connection.execute(
                "SELECT content FROM chunks_fts WHERE repo_id = ?",
                (indexed["repo_id"],),
            ).fetchall()
        )

    for secret in SECRET_VALUES:
        assert secret not in chunk_text
        assert secret not in fts_text
    assert "database.password" in chunk_text

    pack, _ = retrieve_context_debug(
        "Change the database host configuration",
        settings,
        repo_id=indexed["repo_id"],
        task_hint="configuration",
        top_k=10,
    )
    pack_json = pack.model_dump_json(by_alias=True)
    for secret in SECRET_VALUES:
        assert secret not in pack_json

    with connect(settings.database_path) as connection:
        trace_rows = connection.execute(
            "SELECT * FROM traces WHERE repo_id = ? ORDER BY created_at DESC",
            (indexed["repo_id"],),
        ).fetchall()
    assert trace_rows
    trace_json = json.dumps([dict(row) for row in trace_rows], ensure_ascii=False)
    for secret in SECRET_VALUES:
        assert secret not in trace_json

    result = run_eval(
        settings,
        repo_id=indexed["repo_id"],
        dataset_path=Path("eval/fixtures/structured_golden.json"),
        config_names=["bm25_only", "bm25_graph"],
        output_dir=tmp_path / "reports",
    )
    report_json = Path(result.json_report_path).read_text(encoding="utf-8")
    assert result.active_cases == 4
    assert all(config.failed_case_count == 0 for config in result.configs)
    for config in result.configs:
        for case in config.case_results:
            lanes = case.route_diagnostics["bm25_lanes"]
            if case.task_hint == "database":
                assert lanes["schema"]["executed"] is True
            if case.task_hint == "configuration":
                assert lanes["config"]["executed"] is True
    for secret in SECRET_VALUES:
        assert secret not in report_json
