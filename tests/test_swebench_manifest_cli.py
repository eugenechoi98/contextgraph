import json
from pathlib import Path

from typer.testing import CliRunner

import contextgraph_studio.cli as cli_module
from tests.helpers import strip_ansi


runner = CliRunner()
FIXTURE = Path("tests/fixtures/swebench_lite_sample.jsonl")


def test_swebench_inspect_help() -> None:
    result = runner.invoke(cli_module.app, ["swebench-inspect", "--help"])
    output = strip_ansi(result.stdout)

    assert result.exit_code == 0
    assert "--dataset" in output
    assert "--allow-network" in output


def test_swebench_inspect_generates_json_and_markdown_without_db_or_clone(tmp_path: Path) -> None:
    output_dir = tmp_path / "manifests"

    result = runner.invoke(
        cli_module.app,
        [
            "swebench-inspect",
            "--dataset",
            str(FIXTURE),
            "--max-instances",
            "4",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    json_path = Path(payload["json_manifest_path"])
    markdown_path = Path(payload["markdown_manifest_path"])
    assert json_path.exists()
    assert markdown_path.exists()
    assert payload["instance_count"] == 4
    assert payload["critical_file_count"] >= 4
    assert payload["excluded_file_count"] == 1
    assert not (tmp_path / ".data").exists()
    assert not (tmp_path / "sample").exists()

    manifest = json.loads(json_path.read_text(encoding="utf-8"))
    assert manifest["total_instances"] == 4
    assert manifest["instances"][1]["excluded_files"] == ["package-lock.json"]
    assert "sample__rename-001" in markdown_path.read_text(encoding="utf-8")


def test_swebench_inspect_hf_requires_explicit_network() -> None:
    result = runner.invoke(cli_module.app, ["swebench-inspect", "--source", "hf", "--max-instances", "1"])

    assert result.exit_code == 1
    assert "allow_network=True" in result.stderr
