"""检索共享应用服务。"""

from __future__ import annotations

from dataclasses import dataclass

from contextgraph_studio.application.errors import NotFoundAppError, ValidationAppError
from contextgraph_studio.config import Settings
from contextgraph_studio.models.context_pack import ContextPack, RetrieveContextRequest
from contextgraph_studio.services.retriever import retrieve_context


@dataclass(slots=True)
class RetrieveContextService:
    """统一封装上下文检索入口。"""

    settings: Settings

    def execute(self, request: RetrieveContextRequest) -> ContextPack:
        query = request.query.strip()
        if not query:
            raise ValidationAppError("Query must not be empty.")
        if request.max_tokens is not None and request.max_tokens < 100:
            raise ValidationAppError("max_tokens must be greater than or equal to 100.")

        try:
            pack = retrieve_context(
                query,
                self.settings,
                request.top_k,
                task_hint=request.task_hint,
                max_tokens=request.max_tokens,
                repo_id=request.repo_id,
                trace=request.trace,
            )
        except KeyError as exc:
            raise NotFoundAppError(str(exc)) from exc
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc

        if not request.trace:
            return pack.model_copy(update={"trace_id": None})
        return pack
