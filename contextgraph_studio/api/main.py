"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from contextgraph_studio.api.schemas import RetrieveContextRequest, ScanRepoRequest
from contextgraph_studio.application.errors import (
    ApplicationError,
    ConflictAppError,
    InternalAppError,
    NotFoundAppError,
    ScanFailedAppError,
    ValidationAppError,
)
from contextgraph_studio.application.get_trace import GetTraceService
from contextgraph_studio.application.retrieve_context import RetrieveContextService
from contextgraph_studio.application.scan_repo import ScanRepoService
from contextgraph_studio.config import get_settings
from contextgraph_studio.db import init_db
from contextgraph_studio.models.context_pack import ContextPack
from contextgraph_studio.models.scan import ScanRepoResult
from contextgraph_studio.models.trace import GetTraceRequest, TraceRecord


settings = get_settings()
 

@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期：启动时初始化数据库。"""

    init_db(settings)
    yield


app = FastAPI(title="ContextGraph Studio", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """轻量健康检查。"""

    return {"status": "ok"}


@app.post("/retrieve-context", response_model=ContextPack)
@app.post("/api/context/retrieve", response_model=ContextPack, include_in_schema=False)
def api_retrieve_context(request: RetrieveContextRequest) -> ContextPack:
    """执行上下文检索。"""

    try:
        return RetrieveContextService(settings).execute(request)
    except ApplicationError as exc:
        raise _map_application_error(exc) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.post("/scan-repo", response_model=ScanRepoResult)
@app.post("/api/repos/index", response_model=ScanRepoResult, include_in_schema=False)
def api_scan_repo(request: ScanRepoRequest) -> ScanRepoResult:
    """触发同步索引。"""

    try:
        return ScanRepoService(settings).execute(request)
    except ApplicationError as exc:
        raise _map_application_error(exc) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.get("/scan-runs/{scan_run_id}", response_model=ScanRepoResult)
def api_get_scan_run(scan_run_id: str) -> ScanRepoResult:
    """查询已有 scan_run 状态。"""

    try:
        return ScanRepoService(settings).get_status(scan_run_id)
    except ApplicationError as exc:
        raise _map_application_error(exc) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.get("/traces/{trace_id}", response_model=TraceRecord)
@app.get("/api/traces/{trace_id}", response_model=TraceRecord, include_in_schema=False)
def api_get_trace(trace_id: str) -> TraceRecord:
    """读取 trace。"""

    try:
        return GetTraceService(settings).execute(GetTraceRequest(trace_id=trace_id))
    except ApplicationError as exc:
        raise _map_application_error(exc) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error.")


def _map_application_error(exc: ApplicationError) -> HTTPException:
    if isinstance(exc, NotFoundAppError):
        return HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, (ValidationAppError, ConflictAppError)):
        return HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, ScanFailedAppError):
        return HTTPException(status_code=500, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, InternalAppError):
        return HTTPException(status_code=500, detail={"code": exc.code, "message": exc.message})
    return HTTPException(status_code=500, detail={"code": "internal_error", "message": "Internal server error."})
