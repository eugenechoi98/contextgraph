"""SWE-bench 仓库隔离 checkout 管理。"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
_COMMIT_RE = re.compile(r"^[A-Fa-f0-9]{7,40}$")


class CheckoutRequest(BaseModel):
    """一次隔离 checkout 请求。"""

    model_config = ConfigDict(extra="forbid")

    repo: str = Field(..., min_length=1)
    base_commit: str = Field(..., min_length=7)
    instance_id: str = Field(..., min_length=1)
    cache_dir: Path
    allow_network: bool = False
    min_free_bytes: int = Field(default=5 * 1024 * 1024 * 1024, ge=0)

    @model_validator(mode="after")
    def _validate_commit(self) -> "CheckoutRequest":
        if not _COMMIT_RE.match(self.base_commit):
            raise ValueError("base_commit must be a 7-40 character git SHA.")
        return self


class CheckoutResult(BaseModel):
    """隔离 checkout 的结果。"""

    model_config = ConfigDict(extra="forbid")

    instance_id: str
    repo: str
    base_commit: str
    remote_url: str
    checkout_path: str
    cache_dir: str
    reused: bool
    disk_free_bytes: int
    network_mode: Literal["disabled", "enabled"]


def safe_instance_id(value: str) -> str:
    """把 instance_id 变成只能用于路径片段的安全名字。"""

    cleaned = _SAFE_ID_RE.sub("_", value.strip()).strip("._")
    if not cleaned:
        raise ValueError("instance_id does not contain a safe path segment.")
    return cleaned[:120]


def safe_repo_slug(repo: str) -> str:
    """把 repo 名称变成缓存目录片段。"""

    if repo.startswith("file://"):
        path = Path(repo.removeprefix("file://")).resolve()
        return safe_instance_id(path.name)
    if _GITHUB_REPO_RE.match(repo):
        return repo.replace("/", "__")
    raise ValueError("repo must be 'owner/name' or a file:// local fixture remote.")


def check_disk_gate(cache_dir: Path, min_free_bytes: int) -> int:
    """在 clone 前检查缓存盘剩余空间。"""

    probe = cache_dir
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free_bytes = shutil.disk_usage(probe).free
    if free_bytes < min_free_bytes:
        raise RuntimeError(
            f"Insufficient disk space for SWE-bench checkout: free={free_bytes}, required={min_free_bytes}."
        )
    return free_bytes


def checkout_repo_at_commit(request: CheckoutRequest) -> CheckoutResult:
    """浅 fetch 指定 base_commit，不做完整 clone fallback。"""

    cache_root = request.cache_dir.expanduser().resolve()
    free_bytes = check_disk_gate(cache_root, request.min_free_bytes)
    remote_url = _resolve_remote_url(request.repo, request.allow_network)
    checkout_path = (
        cache_root
        / "repos"
        / safe_repo_slug(request.repo)
        / request.base_commit.lower()
        / safe_instance_id(request.instance_id)
        / "checkout"
    ).resolve()
    _ensure_within(checkout_path, cache_root)

    if checkout_path.exists():
        current = _git(["rev-parse", "HEAD"], cwd=checkout_path).strip()
        if current.lower().startswith(request.base_commit.lower()):
            return _result(request, remote_url, checkout_path, cache_root, reused=True, free_bytes=free_bytes)
        raise RuntimeError(
            f"Existing checkout is not at requested commit: path={checkout_path}, head={current}, "
            f"expected={request.base_commit}."
        )

    checkout_path.mkdir(parents=True, exist_ok=False)
    _git(["init", str(checkout_path)], cwd=None)
    _git(["remote", "add", "origin", remote_url], cwd=checkout_path)
    _git(["fetch", "--depth", "1", "origin", request.base_commit], cwd=checkout_path)
    _git(["checkout", "--detach", "FETCH_HEAD"], cwd=checkout_path)
    current = _git(["rev-parse", "HEAD"], cwd=checkout_path).strip()
    if not current.lower().startswith(request.base_commit.lower()):
        raise RuntimeError(f"Fetched checkout HEAD mismatch: head={current}, expected={request.base_commit}.")
    return _result(request, remote_url, checkout_path, cache_root, reused=False, free_bytes=free_bytes)


def _resolve_remote_url(repo: str, allow_network: bool) -> str:
    if repo.startswith("file://"):
        local_path = Path(repo.removeprefix("file://")).resolve()
        if not local_path.exists():
            raise ValueError(f"Local fixture remote not found: {local_path}")
        return f"file://{local_path.as_posix()}"
    if not _GITHUB_REPO_RE.match(repo):
        raise ValueError("repo must be 'owner/name' or a file:// local fixture remote.")
    if not allow_network:
        raise RuntimeError("GitHub checkout requires allow_network=True.")
    return f"https://github.com/{repo}.git"


def _ensure_within(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Resolved checkout path escapes cache root: {path}") from exc


def _git(args: list[str], *, cwd: Path | None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()[:2000]
        stdout = completed.stdout.strip()[:1000]
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr or stdout}")
    return completed.stdout


def _result(
    request: CheckoutRequest,
    remote_url: str,
    checkout_path: Path,
    cache_root: Path,
    *,
    reused: bool,
    free_bytes: int,
) -> CheckoutResult:
    return CheckoutResult(
        instance_id=request.instance_id,
        repo=request.repo,
        base_commit=request.base_commit,
        remote_url=remote_url,
        checkout_path=str(checkout_path),
        cache_dir=str(cache_root),
        reused=reused,
        disk_free_bytes=free_bytes,
        network_mode="enabled" if request.allow_network else "disabled",
    )
