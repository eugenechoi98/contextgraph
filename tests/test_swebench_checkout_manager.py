import subprocess
from pathlib import Path

import pytest

from contextgraph_studio.eval.datasets.repo_checkout import (
    CheckoutRequest,
    checkout_repo_at_commit,
    safe_instance_id,
    safe_repo_slug,
)


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


def make_remote_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "remote"
    repo.mkdir()
    git(["init"], repo)
    git(["config", "user.email", "test@example.com"], repo)
    git(["config", "user.name", "Test User"], repo)
    (repo / "src").mkdir()
    (repo / "src" / "auth.py").write_text("def verify_refresh_token():\n    return True\n", encoding="utf-8")
    git(["add", "."], repo)
    git(["commit", "-m", "base"], repo)
    return repo, git(["rev-parse", "HEAD"], repo)


def test_safe_path_segments_reject_unsafe_repo_slug() -> None:
    assert safe_instance_id("../django__case") == "django__case"
    assert safe_repo_slug("owner/project") == "owner__project"

    with pytest.raises(ValueError, match="owner/name"):
        safe_repo_slug("../project")


def test_checkout_rejects_github_repo_without_network(tmp_path: Path) -> None:
    request = CheckoutRequest(
        repo="django/django",
        base_commit="a" * 40,
        instance_id="django__case",
        cache_dir=tmp_path / "cache",
        allow_network=False,
        min_free_bytes=0,
    )

    with pytest.raises(RuntimeError, match="allow_network=True"):
        checkout_repo_at_commit(request)


def test_checkout_fetches_specific_local_commit_and_reuses_it(tmp_path: Path) -> None:
    remote, commit = make_remote_repo(tmp_path)
    request = CheckoutRequest(
        repo=f"file://{remote.as_posix()}",
        base_commit=commit,
        instance_id="local__refresh-token",
        cache_dir=tmp_path / "cache",
        allow_network=False,
        min_free_bytes=0,
    )

    first = checkout_repo_at_commit(request)
    second = checkout_repo_at_commit(request)

    assert Path(first.checkout_path).exists()
    assert git(["rev-parse", "HEAD"], Path(first.checkout_path)) == commit
    assert first.reused is False
    assert second.reused is True
    assert Path(first.checkout_path).is_relative_to((tmp_path / "cache").resolve())


def test_checkout_disk_gate_fails_before_clone(tmp_path: Path) -> None:
    remote, commit = make_remote_repo(tmp_path)
    request = CheckoutRequest(
        repo=f"file://{remote.as_posix()}",
        base_commit=commit,
        instance_id="local__disk",
        cache_dir=tmp_path / "cache",
        min_free_bytes=10**18,
    )

    with pytest.raises(RuntimeError, match="Insufficient disk space"):
        checkout_repo_at_commit(request)
    assert not (tmp_path / "cache" / "repos").exists()
