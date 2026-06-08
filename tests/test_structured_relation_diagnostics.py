import json
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.graph.structured_diagnostics import audit_structured_relations, summarize_candidates
from contextgraph_studio.services.indexer import index_repository


FIXTURE_REPO = Path("tests/fixtures/sample_structured_repo")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
        vector_index_enabled=False,
        hybrid_vector_enabled=False,
        hybrid_graph_enabled=True,
        embedding_provider="deterministic",
        embedding_model="deterministic-sha256",
        embedding_dimension=16,
    )


def test_structured_relation_diagnostics_identifies_table_consumers_and_skips_natural_language(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    indexed = index_repository(FIXTURE_REPO, settings)

    with connect(settings.database_path) as connection:
        audit = audit_structured_relations(
            connection,
            repo_root=FIXTURE_REPO,
            repo_id=indexed["repo_id"],
            scan_run_id=indexed["scan_run_id"],
        )

    uses_table = audit["uses_table"]
    safe = [item for item in uses_table if item.safe_to_materialize]
    skipped = [item for item in uses_table if not item.safe_to_materialize]

    assert any(
        item.source_entity == "public.users"
        and item.candidate_consumer_entity == "src.user_repository.find_user_by_email"
        and item.match_type == "sql_string_table_name"
        and "FROM users" in item.matched_text
        for item in safe
    )
    assert any(
        item.source_entity == "public.users"
        and item.candidate_consumer_entity == "src.user_repository.update_account_status"
        and item.match_type == "sql_string_table_name"
        and "UPDATE users" in item.matched_text
        for item in safe
    )
    assert any(item.match_type == "table_name_constant" and item.matched_text == "users" for item in safe)
    assert any(
        item.candidate_consumer_file == "src/server.py"
        and item.match_type == "natural_language_string"
        and item.skip_reason == "not_sql_or_table_constant"
        for item in skipped
    )


def test_structured_relation_diagnostics_records_config_candidates_and_dynamic_skip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _copy_fixture(repo)
    config_loader = repo / "src" / "config_loader.py"
    config_loader.write_text(
        config_loader.read_text(encoding="utf-8")
        + "\n\n"
        + "def get_dynamic_config(config: dict, key: str):\n"
        + "    return config.get(key)\n",
        encoding="utf-8",
    )
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        audit = audit_structured_relations(
            connection,
            repo_root=repo,
            repo_id=indexed["repo_id"],
            scan_run_id=indexed["scan_run_id"],
        )

    configures = audit["configures"]
    safe = [item for item in configures if item.safe_to_materialize]

    assert any(
        item.source_entity == "database.host"
        and (item.candidate_consumer_entity or "").startswith("src.config_loader")
        and item.match_type == "config_key_access"
        for item in safe
    )
    assert any(
        item.source_entity == "api.timeout"
        and item.candidate_consumer_entity == "src.config_loader.get_api_timeout"
        and item.match_type == "config_key_access"
        for item in safe
    )
    assert all("get_dynamic_config" not in (item.candidate_consumer_entity or "") for item in safe)


def test_structured_relation_diagnostics_summary_and_json_report_payload(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    indexed = index_repository(FIXTURE_REPO, settings)

    with connect(settings.database_path) as connection:
        audit = audit_structured_relations(
            connection,
            repo_root=FIXTURE_REPO,
            repo_id=indexed["repo_id"],
            scan_run_id=indexed["scan_run_id"],
        )

    uses_summary = summarize_candidates(audit["uses_table"])
    config_summary = summarize_candidates(audit["configures"])
    payload = {
        "uses_table": [item.to_dict() for item in audit["uses_table"]],
        "configures": [item.to_dict() for item in audit["configures"]],
        "uses_table_summary": uses_summary,
        "configures_summary": config_summary,
    }

    assert uses_summary["safe_to_materialize_count"] >= 2
    assert config_summary["safe_to_materialize_count"] >= 2
    assert json.loads(json.dumps(payload))["uses_table_summary"]["candidate_count"] >= 3


def _copy_fixture(destination: Path) -> None:
    for source in FIXTURE_REPO.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(FIXTURE_REPO)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
