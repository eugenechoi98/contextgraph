from pathlib import Path

import pytest

from contextgraph_studio.eval.datasets.swebench_lite import (
    build_swebench_manifest,
    classify_excluded_file,
    extract_changed_files_from_patch,
    load_swebench_lite_local,
)


FIXTURE = Path("tests/fixtures/swebench_lite_sample.jsonl")


def test_patch_parser_handles_multi_file_and_ignores_headers() -> None:
    instance = load_swebench_lite_local(FIXTURE, instance_ids={"sample__auth-001"})[0]

    files = extract_changed_files_from_patch(instance.patch)
    by_path = {item.file_path: item for item in files}

    assert by_path["src/auth.py"].status == "modified"
    assert by_path["src/auth.py"].added_lines == 4
    assert by_path["src/auth.py"].deleted_lines == 1
    assert by_path["src/auth.py"].changed_lines == 5
    assert by_path["tests/test_auth.py"].added_lines == 3


def test_patch_parser_handles_lockfile_exclusion_and_critical_threshold() -> None:
    instance = load_swebench_lite_local(FIXTURE, instance_ids={"sample__lockfile-001"})[0]
    manifest = build_swebench_manifest([instance], critical_changed_lines_threshold=5)
    ground_truth = manifest.instances[0]

    assert "src/config.py" in ground_truth.expected_files
    assert "src/config.py" in ground_truth.critical_files
    assert "package-lock.json" in ground_truth.excluded_files
    lockfile = next(item for item in ground_truth.changed_files if item.file_path == "package-lock.json")
    assert lockfile.exclusion_reason == "lockfile"


def test_patch_parser_handles_added_deleted_and_critical_fallback() -> None:
    instance = load_swebench_lite_local(FIXTURE, instance_ids={"sample__add-delete-001"})[0]
    manifest = build_swebench_manifest([instance], critical_changed_lines_threshold=10)
    ground_truth = manifest.instances[0]
    by_path = {item.file_path: item for item in ground_truth.changed_files}

    assert by_path["src/new_module.py"].status == "added"
    assert by_path["src/removed_module.py"].status == "deleted"
    assert "src/removed_module.py" not in ground_truth.expected_files
    assert ground_truth.critical_files == ["src/new_module.py"]


def test_patch_parser_handles_rename_and_multi_hunk() -> None:
    instance = load_swebench_lite_local(FIXTURE, instance_ids={"sample__rename-001"})[0]

    files = extract_changed_files_from_patch(instance.patch)

    assert len(files) == 1
    renamed = files[0]
    assert renamed.status == "renamed"
    assert renamed.old_file_path == "src/old_name.py"
    assert renamed.file_path == "src/new_name.py"
    assert renamed.added_lines == 5
    assert renamed.deleted_lines == 3


def test_patch_parser_handles_paths_with_spaces() -> None:
    patch = (
        "diff --git \"a/src/file with space.py\" \"b/src/file with space.py\"\n"
        "--- \"a/src/file with space.py\"\n"
        "+++ \"b/src/file with space.py\"\n"
        "@@ -1 +1,2 @@\n"
        "-old = True\n"
        "+old = False\n"
        "+new = True\n"
    )

    files = extract_changed_files_from_patch(patch)

    assert files[0].file_path == "src/file with space.py"
    assert files[0].changed_lines == 3


def test_patch_parser_rejects_non_patch_text() -> None:
    with pytest.raises(ValueError, match="diff --git"):
        extract_changed_files_from_patch("this is not a patch")


def test_exclusion_rules_cover_generated_vendor_and_minified_files() -> None:
    assert classify_excluded_file("vendor/lib.py") == (True, "generated_or_vendor")
    assert classify_excluded_file("src/generated/client.py") == (True, "generated_or_vendor")
    assert classify_excluded_file("dist/app.min.js") == (True, "generated_or_vendor")
    assert classify_excluded_file("src/app.min.js") == (True, "minified_generated_asset")
    assert classify_excluded_file("tests/test_auth.py") == (False, None)
