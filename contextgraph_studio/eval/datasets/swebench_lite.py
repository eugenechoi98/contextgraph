"""SWE-bench Lite loading and manifest generation."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


OFFICIAL_DATASET = "princeton-nlp/SWE-bench_Lite"
LOCKFILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
}
EXCLUDED_DIR_PREFIXES = ("vendor/", "dist/", "build/", "generated/")


class SweBenchLiteInstance(BaseModel):
    """Minimal SWE-bench Lite instance used for manifest generation."""

    model_config = ConfigDict(extra="allow")

    instance_id: str = Field(..., min_length=1)
    repo: str = Field(..., min_length=1)
    base_commit: str = Field(..., min_length=1)
    problem_statement: str = Field(..., min_length=1)
    patch: str = Field(..., min_length=1)
    test_patch: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChangedFile(BaseModel):
    """One file touched by a SWE-bench patch."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    status: Literal["modified", "added", "deleted", "renamed"]
    added_lines: int
    deleted_lines: int
    changed_lines: int
    is_excluded: bool
    exclusion_reason: str | None = None
    old_file_path: str | None = None


class SweBenchGroundTruth(BaseModel):
    """Ground truth manifest for one SWE-bench Lite instance."""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    repo: str
    base_commit: str
    query: str
    changed_files: list[ChangedFile]
    expected_files: list[str]
    critical_files: list[str]
    excluded_files: list[str]


class SweBenchManifest(BaseModel):
    """SWE-bench Lite ground truth manifest."""

    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    source: str
    total_instances: int
    instances: list[SweBenchGroundTruth]

    @model_validator(mode="after")
    def _validate_count(self) -> "SweBenchManifest":
        if self.total_instances != len(self.instances):
            raise ValueError("total_instances must match the number of instances.")
        return self


def load_swebench_lite_local(
    dataset_path: Path,
    *,
    max_instances: int | None = None,
    instance_ids: set[str] | None = None,
) -> list[SweBenchLiteInstance]:
    """Load SWE-bench Lite-like rows from a local JSON or JSONL file."""

    if max_instances is not None and max_instances <= 0:
        raise ValueError("max_instances must be greater than 0.")
    suffix = dataset_path.suffix.lower()
    if suffix == ".jsonl":
        records = _load_jsonl(dataset_path)
    elif suffix == ".json":
        records = _load_json(dataset_path)
    else:
        raise ValueError("SWE-bench local dataset must be .json or .jsonl.")

    instances: list[SweBenchLiteInstance] = []
    for index, record in enumerate(records, start=1):
        try:
            instance = SweBenchLiteInstance.model_validate(record)
        except Exception as exc:
            raise ValueError(f"Invalid SWE-bench instance at record {index}: {exc}") from exc
        if instance_ids and instance.instance_id not in instance_ids:
            continue
        instances.append(instance)
        if max_instances is not None and len(instances) >= max_instances:
            break
    return instances


def load_swebench_lite_hf(
    *,
    split: str = "test",
    max_instances: int | None = None,
    instance_ids: set[str] | None = None,
    allow_network: bool = False,
    cache_dir: Path | None = None,
) -> list[SweBenchLiteInstance]:
    """Optionally load SWE-bench Lite from Hugging Face."""

    if not allow_network:
        raise RuntimeError("Hugging Face SWE-bench loading requires allow_network=True.")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install the optional 'swebench' extra to use the Hugging Face loader.") from exc

    try:
        dataset = load_dataset(OFFICIAL_DATASET, split=split, cache_dir=str(cache_dir) if cache_dir else None)
    except Exception as exc:
        raise RuntimeError(f"Failed to load {OFFICIAL_DATASET}: {exc}") from exc

    records = list(dataset)
    if instance_ids:
        records = [row for row in records if str(row.get("instance_id", "")) in instance_ids]
    if max_instances is not None:
        if max_instances <= 0:
            raise ValueError("max_instances must be greater than 0.")
        records = records[:max_instances]
    return [SweBenchLiteInstance.model_validate(row) for row in records]


def extract_changed_files_from_patch(
    patch: str,
    *,
    critical_changed_lines_threshold: int = 5,
) -> list[ChangedFile]:
    """Extract changed file stats from a unified git patch."""

    if critical_changed_lines_threshold <= 0:
        raise ValueError("critical_changed_lines_threshold must be greater than 0.")
    entries: list[_PatchEntry] = []
    current: _PatchEntry | None = None
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                entries.append(current)
            current = _PatchEntry.from_diff_header(line)
            in_hunk = False
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current.status_hint = "added"
            continue
        if line.startswith("deleted file mode"):
            current.status_hint = "deleted"
            continue
        if line.startswith("rename from "):
            current.rename_from = _normalize_patch_path(line.removeprefix("rename from ").strip())
            continue
        if line.startswith("rename to "):
            current.rename_to = _normalize_patch_path(line.removeprefix("rename to ").strip())
            continue
        if line.startswith("--- "):
            current.old_path = _normalize_patch_path(line.removeprefix("--- ").strip())
            in_hunk = False
            continue
        if line.startswith("+++ "):
            current.new_path = _normalize_patch_path(line.removeprefix("+++ ").strip())
            in_hunk = False
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current.added_lines += 1
        elif line.startswith("-") and not line.startswith("---"):
            current.deleted_lines += 1
    if current is not None:
        entries.append(current)
    if not entries and patch.strip():
        raise ValueError("Patch did not contain any 'diff --git' file sections.")
    return [_entry_to_changed_file(entry) for entry in entries]


def build_swebench_manifest(
    instances: list[SweBenchLiteInstance],
    *,
    critical_changed_lines_threshold: int = 5,
    dataset_name: str = "swebench_lite",
    source: str = "local",
) -> SweBenchManifest:
    """Build a ground truth manifest from SWE-bench Lite instances."""

    ground_truth: list[SweBenchGroundTruth] = []
    for instance in instances:
        changed_files = extract_changed_files_from_patch(
            instance.patch,
            critical_changed_lines_threshold=critical_changed_lines_threshold,
        )
        included = [item for item in changed_files if not item.is_excluded and item.status != "deleted"]
        expected_files = [item.file_path for item in included]
        critical_files = [
            item.file_path for item in included if item.changed_lines >= critical_changed_lines_threshold
        ]
        if included and not critical_files:
            most_changed = max(included, key=lambda item: (item.changed_lines, item.file_path))
            critical_files = [most_changed.file_path]
        ground_truth.append(
            SweBenchGroundTruth(
                instance_id=instance.instance_id,
                repo=instance.repo,
                base_commit=instance.base_commit,
                query=instance.problem_statement,
                changed_files=changed_files,
                expected_files=expected_files,
                critical_files=critical_files,
                excluded_files=[item.file_path for item in changed_files if item.is_excluded],
            )
        )
    return SweBenchManifest(
        dataset_name=dataset_name,
        source=source,
        total_instances=len(ground_truth),
        instances=ground_truth,
    )


def write_manifest_json(manifest: SweBenchManifest, output_path: Path) -> Path:
    """Write a SWE-bench manifest as JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def write_manifest_markdown(manifest: SweBenchManifest, output_path: Path) -> Path:
    """Write a SWE-bench manifest as Markdown."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SWE-bench Lite Manifest",
        "",
        f"- dataset: `{manifest.dataset_name}`",
        f"- source: `{manifest.source}`",
        f"- instance count: `{manifest.total_instances}`",
        "",
    ]
    for instance in manifest.instances:
        lines.extend(
            [
                f"## {instance.instance_id}",
                "",
                f"- repo: `{instance.repo}`",
                f"- base_commit: `{instance.base_commit}`",
                f"- problem: {instance.query.strip().splitlines()[0][:240]}",
                f"- changed files: `{', '.join(item.file_path for item in instance.changed_files)}`",
                f"- critical files: `{', '.join(instance.critical_files) if instance.critical_files else '(none)'}`",
                f"- excluded files: `{', '.join(instance.excluded_files) if instance.excluded_files else '(none)'}`",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def inspect_swebench_lite(
    *,
    dataset_path: Path | None,
    source: Literal["local", "hf"],
    split: str,
    max_instances: int | None,
    instance_ids: set[str] | None,
    output_dir: Path,
    allow_network: bool,
    critical_changed_lines_threshold: int,
) -> tuple[SweBenchManifest, Path, Path]:
    """Load SWE-bench instances and write JSON/Markdown manifests."""

    if source == "local":
        if dataset_path is None:
            raise ValueError("--dataset is required when --source=local.")
        instances = load_swebench_lite_local(
            dataset_path,
            max_instances=max_instances,
            instance_ids=instance_ids,
        )
        manifest_source = str(dataset_path)
    else:
        instances = load_swebench_lite_hf(
            split=split,
            max_instances=max_instances,
            instance_ids=instance_ids,
            allow_network=allow_network,
        )
        manifest_source = f"{OFFICIAL_DATASET}:{split}"
    manifest = build_swebench_manifest(
        instances,
        critical_changed_lines_threshold=critical_changed_lines_threshold,
        source=manifest_source,
    )
    json_path = write_manifest_json(manifest, output_dir / "swebench_lite_manifest.json")
    markdown_path = write_manifest_markdown(manifest, output_dir / "swebench_lite_manifest.md")
    return manifest, json_path, markdown_path


class _PatchEntry(BaseModel):
    old_path: str | None = None
    new_path: str | None = None
    rename_from: str | None = None
    rename_to: str | None = None
    status_hint: str | None = None
    added_lines: int = 0
    deleted_lines: int = 0

    @classmethod
    def from_diff_header(cls, line: str) -> "_PatchEntry":
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()
        old_path = _normalize_patch_path(parts[-2]) if len(parts) >= 4 else None
        new_path = _normalize_patch_path(parts[-1]) if len(parts) >= 4 else None
        return cls(old_path=old_path, new_path=new_path)


def _load_json(dataset_path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {dataset_path}: {exc}") from exc
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "instances" in payload and isinstance(payload["instances"], list):
        return payload["instances"]
    raise ValueError("SWE-bench JSON dataset must be a list or an object with an 'instances' list.")


def _load_jsonl(dataset_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid JSONL at line {line_number}: expected an object.")
        records.append(payload)
    return records


def _entry_to_changed_file(entry: _PatchEntry) -> ChangedFile:
    old_path = entry.rename_from or entry.old_path
    new_path = entry.rename_to or entry.new_path
    if entry.status_hint == "added" or old_path == "/dev/null":
        status = "added"
        file_path = new_path
    elif entry.status_hint == "deleted" or new_path == "/dev/null":
        status = "deleted"
        file_path = old_path
    elif entry.rename_from or entry.rename_to:
        status = "renamed"
        file_path = new_path
    else:
        status = "modified"
        file_path = new_path or old_path
    if not file_path or file_path == "/dev/null":
        raise ValueError("Patch file section is missing a usable file path.")
    normalized = _normalize_patch_path(file_path)
    is_excluded, reason = classify_excluded_file(normalized)
    return ChangedFile(
        file_path=normalized,
        old_file_path=_normalize_patch_path(old_path) if status == "renamed" and old_path else None,
        status=status,
        added_lines=entry.added_lines,
        deleted_lines=entry.deleted_lines,
        changed_lines=entry.added_lines + entry.deleted_lines,
        is_excluded=is_excluded,
        exclusion_reason=reason,
    )


def classify_excluded_file(file_path: str) -> tuple[bool, str | None]:
    """Return whether a changed file should be excluded from retrieval ground truth."""

    normalized = file_path.replace("\\", "/").lstrip("/")
    lowered = normalized.lower()
    name = lowered.rsplit("/", 1)[-1]
    if name in LOCKFILE_NAMES or lowered.endswith(".lock"):
        return True, "lockfile"
    if any(lowered.startswith(prefix) or f"/{prefix}" in lowered for prefix in EXCLUDED_DIR_PREFIXES):
        return True, "generated_or_vendor"
    if lowered.endswith(".min.js"):
        return True, "minified_generated_asset"
    return False, None


def _normalize_patch_path(path: str | None) -> str | None:
    if path is None:
        return None
    cleaned = path.strip().strip('"')
    if cleaned == "/dev/null":
        return cleaned
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    return cleaned.replace("\\", "/")
