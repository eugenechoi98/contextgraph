from pathlib import Path

import pytest

from contextgraph_studio.application.errors import NotFoundAppError, ValidationAppError
from contextgraph_studio.application.get_trace import GetTraceService
from contextgraph_studio.application.retrieve_context import RetrieveContextService
from contextgraph_studio.application.scan_repo import ScanRepoService
from contextgraph_studio.config import Settings
from contextgraph_studio.models.context_pack import RetrieveContextRequest
from contextgraph_studio.models.scan import ScanRepoRequest
from contextgraph_studio.models.trace import GetTraceRequest
from contextgraph_studio.services import indexer as indexer_module


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
        "vector_index_enabled": False,
        "hybrid_vector_enabled": False,
        "hybrid_graph_enabled": True,
        "embedding_provider": "deterministic",
        "embedding_model": "deterministic-sha256",
        "embedding_dimension": 16,
        "embedding_batch_size": 8,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def build_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def normalize_token(token: str) -> str:\n"
        "    return token.strip()\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    cleaned = normalize_token(token)\n"
        "    return cleaned == 'ok'\n",
        encoding="utf-8",
    )


def test_retrieve_service_trace_true_and_false(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    settings = make_settings(tmp_path)
    scan_result = ScanRepoService(settings).execute(ScanRepoRequest(path=str(repo)))

    retrieve_service = RetrieveContextService(settings)
    pack = retrieve_service.execute(
        RetrieveContextRequest(
            query="verify token auth flow",
            repo_id=scan_result.repo_id,
            trace=True,
            max_tokens=500,
        )
    )
    assert pack.trace_id
    trace = GetTraceService(settings).execute(GetTraceRequest(trace_id=pack.trace_id))
    assert trace.repo_id == scan_result.repo_id

    no_trace_pack = retrieve_service.execute(
        RetrieveContextRequest(
            query="verify token auth flow",
            repo_id=scan_result.repo_id,
            trace=False,
            max_tokens=500,
        )
    )
    assert no_trace_pack.trace_id is None


def test_retrieve_service_rejects_invalid_input(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = RetrieveContextService(settings)
    with pytest.raises(ValidationAppError):
        service.execute(
            RetrieveContextRequest.model_construct(
                query="x",
                repo_id="missing",
                max_tokens=50,
                trace=True,
                top_k=None,
                task_hint=None,
            )
        )

    with pytest.raises(NotFoundAppError):
        service.execute(RetrieveContextRequest(query="verify token", repo_id="missing"))


def test_scan_repo_service_start_and_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    settings = make_settings(tmp_path)
    service = ScanRepoService(settings)

    result = service.execute(ScanRepoRequest(path=str(repo)))
    assert result.status == "done"
    status = service.get_status(result.scan_run_id)
    assert status.scan_run_id == result.scan_run_id


def test_scan_repo_service_rejects_missing_path_and_missing_scan(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    service = ScanRepoService(settings)

    with pytest.raises(ValidationAppError):
        service.execute(ScanRepoRequest(path=str(tmp_path / "missing")))

    with pytest.raises(NotFoundAppError):
        service.execute(ScanRepoRequest(scan_run_id="missing-scan"))


def test_scan_repo_service_returns_failed_status_with_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    settings = make_settings(tmp_path)
    service = ScanRepoService(settings)

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("forced index failure")

    monkeypatch.setattr(indexer_module, "_index_source_file", boom)
    result = service.execute(ScanRepoRequest(path=str(repo)))
    assert result.status == "failed"
    assert result.error == "forced index failure"


def test_get_trace_service_rejects_missing_trace(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with pytest.raises(NotFoundAppError):
        GetTraceService(settings).execute(GetTraceRequest(trace_id="missing-trace"))
