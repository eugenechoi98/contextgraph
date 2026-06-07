"""Task classification and retrieval planning."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from contextgraph_studio.config import Settings


@dataclass(slots=True)
class RetrievalPlan:
    """Retrieval plan derived from the task hint or query."""

    task_type: str
    token_budget: int
    bm25_queries: list[str]
    vector_query: str
    graph_edge_types: list[str]
    graph_hops: int
    weights: dict[str, float]
    priority_categories: list[str]
    priority_entity_types: list[str]
    search_mode: str


@lru_cache(maxsize=1)
def load_task_strategies(task_strategies_path: str) -> dict:
    """Read the task strategy configuration file."""

    with open(task_strategies_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_plan(
    query: str,
    settings: Settings,
    task_hint: str | None = None,
    max_tokens: int | None = None,
) -> RetrievalPlan:
    """Build a retrieval plan for the current query."""

    strategies = load_task_strategies(str(settings.task_strategies_path)).get("task_types", {})
    if task_hint and task_hint in strategies:
        return _build_retrieval_plan(task_hint, query, strategies[task_hint], max_tokens, "hint_driven")

    lowered = query.lower()
    best_type = "general"
    best_score = -1
    for task_type, config in strategies.items():
        keywords = config.get("keywords", [])
        score = sum(1 for keyword in keywords if keyword and keyword in lowered)
        if score > best_score:
            best_type = task_type
            best_score = score

    if best_score < 1:
        best_type = "general"

    return _build_retrieval_plan(
        best_type,
        query,
        strategies.get(best_type, {}),
        max_tokens,
        "keyword_match" if best_score > 0 else "fallback_general",
    )


def _build_retrieval_plan(
    task_type: str,
    query: str,
    config: dict,
    max_tokens: int | None,
    search_mode: str,
) -> RetrievalPlan:
    token_budget = max_tokens or int(config.get("default_token_budget", 4000))
    return RetrievalPlan(
        task_type=task_type,
        token_budget=token_budget,
        bm25_queries=_build_bm25_queries(query),
        vector_query=query.strip(),
        graph_edge_types=list(config.get("graph_expand_edge_types", [])),
        graph_hops=max(int(config.get("graph_hops", 1)), 0),
        weights={
            "bm25": float(config.get("bm25_weight", 0.4)),
            "vector": float(config.get("vector_weight", 0.35)),
            "graph": float(config.get("graph_weight", 0.25)),
        },
        priority_categories=list(config.get("priority_categories", [])),
        priority_entity_types=list(config.get("priority_entity_types", [])),
        search_mode=search_mode,
    )


def _build_bm25_queries(query: str) -> list[str]:
    normalized = query.strip()
    if not normalized:
        return []
    return [normalized]
