"""扫描任务共享模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScanRepoRequest(BaseModel):
    """共享的 scan_repo 请求契约。"""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    repo_id: str | None = None
    scan_run_id: str | None = None
    with_vectors: bool | None = None


class ScanRepoResult(BaseModel):
    """共享的 scan_repo 响应契约。"""

    model_config = ConfigDict(extra="forbid")

    repo_id: str
    scan_run_id: str
    status: str
    started_at: int
    finished_at: int | None = None
    stats: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
