"""Minimal reranker placeholders for early-stage retrieval."""

from __future__ import annotations

from dataclasses import replace

from contextgraph_studio.domain import ScoredChunk


class IdentityReranker:
    """No-op reranker used for offline development and trace completeness."""

    name = "identity"

    def rerank(self, candidates: list[ScoredChunk]) -> list[ScoredChunk]:
        return [replace(chunk) for chunk in candidates]
