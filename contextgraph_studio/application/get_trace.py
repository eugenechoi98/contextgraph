"""Trace 查询共享应用服务。"""

from __future__ import annotations

from dataclasses import dataclass

from contextgraph_studio.application.errors import NotFoundAppError
from contextgraph_studio.config import Settings
from contextgraph_studio.models.trace import GetTraceRequest, TraceRecord
from contextgraph_studio.services.retriever import get_trace


@dataclass(slots=True)
class GetTraceService:
    """统一封装 trace 查询入口。"""

    settings: Settings

    def execute(self, request: GetTraceRequest) -> TraceRecord:
        try:
            payload = get_trace(request.trace_id, self.settings)
        except KeyError as exc:
            raise NotFoundAppError(str(exc)) from exc
        return TraceRecord.model_validate(payload)
