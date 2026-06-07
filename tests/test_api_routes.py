from pathlib import Path

from fastapi.testclient import TestClient

import contextgraph_studio.api.main as api_main
from contextgraph_studio.config import Settings


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def build_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token(token: str) -> bool:\n    return token == 'ok'\n", encoding="utf-8")


def test_api_routes_smoke(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = tmp_path / "repo"
    build_repo(repo)
    settings = make_settings(tmp_path)
    monkeypatch.setattr(api_main, "settings", settings)

    with TestClient(api_main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}

        scan_response = client.post("/scan-repo", json={"path": str(repo)})
        assert scan_response.status_code == 200
        scan_payload = scan_response.json()
        assert scan_payload["status"] == "done"

        retrieve_response = client.post(
            "/retrieve-context",
            json={"query": "verify token", "repo_id": scan_payload["repo_id"], "max_tokens": 500, "trace": True},
        )
        assert retrieve_response.status_code == 200
        pack = retrieve_response.json()
        assert "bm25" in pack["retrieval_strategy"]

        trace_response = client.get(f"/traces/{pack['trace_id']}")
        assert trace_response.status_code == 200
        assert trace_response.json()["trace_id"] == pack["trace_id"]

        status_response = client.get(f"/scan-runs/{scan_payload['scan_run_id']}")
        assert status_response.status_code == 200
        assert status_response.json()["scan_run_id"] == scan_payload["scan_run_id"]


def test_api_routes_return_404_and_422(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = make_settings(tmp_path)
    monkeypatch.setattr(api_main, "settings", settings)

    with TestClient(api_main.app) as client:
        missing_scan = client.post("/scan-repo", json={"path": str(tmp_path / "missing")})
        assert missing_scan.status_code == 422
        assert missing_scan.json()["detail"]["code"] == "validation_error"

        missing_trace = client.get("/traces/missing-trace")
        assert missing_trace.status_code == 404
        assert missing_trace.json()["detail"]["code"] == "not_found"

        missing_run = client.get("/scan-runs/missing-scan")
        assert missing_run.status_code == 404
        assert missing_run.json()["detail"]["code"] == "not_found"

        empty_query = client.post("/retrieve-context", json={"query": "", "repo_id": "x"})
        assert empty_query.status_code == 422
