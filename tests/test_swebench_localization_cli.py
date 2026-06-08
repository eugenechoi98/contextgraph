import json
from pathlib import Path

from typer.testing import CliRunner

import contextgraph_studio.cli as cli_module
from tests.helpers import strip_ansi


runner = CliRunner()


def write_manifest(path: Path) -> None:
    payload = {
        "dataset_name": "dry_cli",
        "source": "local",
        "total_instances": 1,
        "instances": [
            {
                "instance_id": "local__cli",
                "repo": "file://C:/does/not/matter/in/dry/run",
                "base_commit": "a" * 40,
                "query": "refresh token route",
                "changed_files": [],
                "expected_files": ["src/auth.py"],
                "critical_files": ["src/auth.py"],
                "excluded_files": [],
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_swebench_localize_help() -> None:
    result = runner.invoke(cli_module.app, ["swebench-localize", "--help"])
    output = strip_ansi(result.stdout)

    assert result.exit_code == 0
    assert "--manifest" in output
    assert "--dry-run" in output


def test_swebench_localize_dry_run_cli_writes_reports(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)
    cache_dir = tmp_path / "cache"
    output_dir = tmp_path / "reports"

    result = runner.invoke(
        cli_module.app,
        [
            "swebench-localize",
            "--manifest",
            str(manifest_path),
            "--cache-dir",
            str(cache_dir),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["selected_instance_count"] == 1
    assert payload["case_result_count"] == 2
    assert Path(payload["json_report_path"]).exists()
    assert Path(payload["markdown_report_path"]).exists()
    assert not (cache_dir / "db").exists()
    assert not (cache_dir / "repos").exists()


def test_swebench_localize_rejects_more_than_three_instances(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path)

    result = runner.invoke(
        cli_module.app,
        ["swebench-localize", "--manifest", str(manifest_path), "--max-instances", "4", "--dry-run"],
    )

    assert result.exit_code == 1
    assert "between 1 and 3" in result.stderr
