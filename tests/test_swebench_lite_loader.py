import json
import builtins
from pathlib import Path

import pytest

from contextgraph_studio.eval.datasets.swebench_lite import (
    load_swebench_lite_hf,
    load_swebench_lite_local,
)
import contextgraph_studio.eval.datasets.swebench_lite as swebench_lite_module


FIXTURE = Path("tests/fixtures/swebench_lite_sample.jsonl")


def test_load_swebench_jsonl_supports_limits_and_instance_filter() -> None:
    instances = load_swebench_lite_local(FIXTURE, max_instances=2)

    assert [item.instance_id for item in instances] == ["sample__auth-001", "sample__lockfile-001"]

    filtered = load_swebench_lite_local(FIXTURE, instance_ids={"sample__rename-001"})
    assert [item.instance_id for item in filtered] == ["sample__rename-001"]


def test_load_swebench_json_supports_list_and_instances_object(tmp_path: Path) -> None:
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()[:2]]
    list_path = tmp_path / "dataset.json"
    object_path = tmp_path / "dataset-object.json"
    list_path.write_text(json.dumps(rows), encoding="utf-8")
    object_path.write_text(json.dumps({"instances": rows}), encoding="utf-8")

    assert len(load_swebench_lite_local(list_path)) == 2
    assert len(load_swebench_lite_local(object_path)) == 2


def test_load_swebench_reports_missing_required_field(tmp_path: Path) -> None:
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(json.dumps({"instance_id": "bad"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="repo"):
        load_swebench_lite_local(dataset)


def test_load_swebench_reports_bad_jsonl_line_number(tmp_path: Path) -> None:
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text("{}\n{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 2"):
        load_swebench_lite_local(dataset)


def test_hf_loader_defaults_to_no_network() -> None:
    with pytest.raises(RuntimeError, match="allow_network=True"):
        load_swebench_lite_hf()


def test_hf_loader_falls_back_to_rows_api_without_optional_dependency(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "datasets":
            raise ImportError("missing datasets")
        return real_import(name, *args, **kwargs)

    class FakeResponse:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "rows": [
                        {
                            "row": {
                                "instance_id": "official__one",
                                "repo": "owner/project",
                                "base_commit": "a" * 40,
                                "problem_statement": "Fix refresh token routing.",
                                "patch": (
                                    "diff --git a/src/auth.py b/src/auth.py\n"
                                    "--- a/src/auth.py\n"
                                    "+++ b/src/auth.py\n"
                                    "@@ -1 +1 @@\n"
                                    "-old\n"
                                    "+new\n"
                                ),
                            }
                        }
                    ],
                    "num_rows_total": 1,
                },
                ensure_ascii=False,
            ).encode("utf-8")

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(swebench_lite_module, "urlopen", lambda *args, **kwargs: FakeResponse())

    instances = load_swebench_lite_hf(allow_network=True, max_instances=1)

    assert len(instances) == 1
    assert instances[0].instance_id == "official__one"
