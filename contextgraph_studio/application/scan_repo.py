"""扫描共享应用服务。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from contextgraph_studio.application.errors import ConflictAppError, NotFoundAppError, ScanFailedAppError, ValidationAppError
from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.models.scan import ScanRepoRequest, ScanRepoResult
from contextgraph_studio.services.indexer import index_repository, resolve_repo_id


@dataclass(slots=True)
class ScanRepoService:
    """统一封装索引触发与状态查询入口。"""

    settings: Settings

    def execute(self, request: ScanRepoRequest) -> ScanRepoResult:
        if request.path and request.scan_run_id:
            raise ConflictAppError("Provide either path or scan_run_id, not both.")
        if not request.path and not request.scan_run_id:
            raise ValidationAppError("Either path or scan_run_id is required.")

        if request.scan_run_id:
            return self.get_status(request.scan_run_id)
        return self.start_scan(request)

    def start_scan(self, request: ScanRepoRequest) -> ScanRepoResult:
        assert request.path is not None
        repo_path = Path(request.path).expanduser()
        if not repo_path.exists():
            raise ValidationAppError("Repository path not found.")
        if not repo_path.is_dir():
            raise ValidationAppError("Repository path must be a directory.")

        resolved_repo_id = resolve_repo_id(repo_path.resolve())
        if request.repo_id and request.repo_id != resolved_repo_id:
            raise ValidationAppError("repo_id does not match the repository path.")

        settings = self._settings_for_scan(request.with_vectors)
        try:
            result = index_repository(repo_path, settings)
        except Exception as exc:
            scan_run_id = self._latest_scan_run_id_for_repo(settings, resolved_repo_id)
            if scan_run_id is None:
                raise ScanFailedAppError("Scan failed before a scan_run could be recorded.") from exc
            return self.get_status(scan_run_id, settings_override=settings)

        return self.get_status(str(result["scan_run_id"]), settings_override=settings)

    def get_status(self, scan_run_id: str, settings_override: Settings | None = None) -> ScanRepoResult:
        settings = settings_override or self.settings
        init_db(settings)
        with connect(settings.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, repo_id, status, started_at, finished_at, stats_json, error_message
                FROM scan_runs
                WHERE id = ?
                """,
                (scan_run_id,),
            ).fetchone()
        if row is None:
            raise NotFoundAppError(f"scan_run not found: {scan_run_id}")
        return ScanRepoResult(
            repo_id=row["repo_id"],
            scan_run_id=row["id"],
            status=row["status"],
            started_at=int(row["started_at"]),
            finished_at=int(row["finished_at"]) if row["finished_at"] is not None else None,
            stats=json.loads(row["stats_json"]) if row["stats_json"] else {},
            error=row["error_message"],
        )

    def _settings_for_scan(self, with_vectors: bool | None) -> Settings:
        if with_vectors is None:
            return self.settings
        return Settings(**{**self.settings.model_dump(), "vector_index_enabled": with_vectors})

    def _latest_scan_run_id_for_repo(self, settings: Settings, repo_id: str) -> str | None:
        init_db(settings)
        with connect(settings.database_path) as connection:
            row = connection.execute(
                """
                SELECT id
                FROM scan_runs
                WHERE repo_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (repo_id,),
            ).fetchone()
        return str(row["id"]) if row is not None else None
