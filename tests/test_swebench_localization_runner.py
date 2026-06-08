import json
import subprocess
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.eval.swebench_localization import run_swebench_localization


def git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
        swebench_cache_dir=tmp_path / "swebench-cache",
        swebench_min_free_bytes=0,
        vector_index_enabled=False,
        hybrid_vector_enabled=False,
        hybrid_graph_enabled=True,
        embedding_provider="deterministic",
        embedding_model="deterministic-sha256",
        embedding_dimension=16,
    )


def make_git_fixture(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "remote"
    repo.mkdir()
    git(["init"], repo)
    git(["config", "user.email", "test@example.com"], repo)
    git(["config", "user.name", "Test User"], repo)
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text(
        "def verify_refresh_token(token: str) -> bool:\n"
        "    # refresh token validation authentication route\n"
        "    return token.startswith('refresh-')\n",
        encoding="utf-8",
    )
    (repo / "src" / "routes.py").write_text(
        "from src.auth import verify_refresh_token\n\n"
        "def refresh_token_route(token: str) -> bool:\n"
        "    return verify_refresh_token(token)\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("Authentication refresh token route docs.\n", encoding="utf-8")
    git(["add", "."], repo)
    git(["commit", "-m", "base"], repo)
    return repo, git(["rev-parse", "HEAD"], repo)


def write_manifest(path: Path, repo: Path, commit: str) -> None:
    payload = {
        "dataset_name": "local_swebench_smoke",
        "source": "local_fixture",
        "total_instances": 1,
        "instances": [
            {
                "instance_id": "local__refresh-token",
                "repo": f"file://{repo.as_posix()}",
                "base_commit": commit,
                "query": "Add refresh token validation to the authentication route",
                "changed_files": [],
                "expected_files": ["src/auth.py", "src/routes.py"],
                "critical_files": ["src/auth.py"],
                "excluded_files": [],
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_localization_dry_run_skips_checkout_db_index_and_retrieval(tmp_path: Path) -> None:
    remote, commit = make_git_fixture(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, remote, commit)
    settings = make_settings(tmp_path)

    result = run_swebench_localization(
        settings,
        manifest_path=manifest_path,
        dry_run=True,
        output_dir=tmp_path / "reports",
    )

    case = result.case_results[0]
    assert result.dry_run is True
    assert case.status == "dry_run"
    assert "skipped" in (case.error or "")
    assert not Path(case.database_path).exists()
    assert not (settings.swebench_cache_dir / "repos").exists()
    assert not settings.database_path.exists()


def test_localization_uses_isolated_db_and_hits_local_fixture(tmp_path: Path) -> None:
    remote, commit = make_git_fixture(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, remote, commit)
    settings = make_settings(tmp_path)

    result = run_swebench_localization(
        settings,
        manifest_path=manifest_path,
        output_dir=tmp_path / "reports",
        config_names=["bm25_only", "bm25_graph"],
    )

    assert result.dry_run is False
    assert len(result.case_results) == 2
    assert Path(result.json_report_path).exists()
    assert Path(result.markdown_report_path).exists()
    assert not settings.database_path.exists()
    for case in result.case_results:
        assert case.status == "passed"
        assert Path(case.database_path).exists()
        assert Path(case.database_path).is_relative_to(settings.swebench_cache_dir.resolve())
        assert "src/auth.py" in case.retrieved_files
        assert case.critical_file_hit is True
    assert result.case_results[1].config_name == "bm25_graph"
