"""Eval ablation 配置。"""

from __future__ import annotations

from contextgraph_studio.eval.models import EvalConfig


DEFAULT_EVAL_CONFIGS: tuple[EvalConfig, ...] = (
    EvalConfig(
        name="bm25_only",
        description="BM25 on, vector off, graph off.",
        bm25_enabled=True,
        vector_enabled=False,
        graph_enabled=False,
    ),
    EvalConfig(
        name="bm25_graph",
        description="BM25 on, vector off, graph on.",
        bm25_enabled=True,
        vector_enabled=False,
        graph_enabled=True,
    ),
    EvalConfig(
        name="bm25_vector",
        description="BM25 on, vector on, graph off.",
        bm25_enabled=True,
        vector_enabled=True,
        graph_enabled=False,
    ),
    EvalConfig(
        name="bm25_vector_graph",
        description="BM25 on, vector on, graph on.",
        bm25_enabled=True,
        vector_enabled=True,
        graph_enabled=True,
    ),
)


def list_eval_configs() -> list[EvalConfig]:
    """返回当前支持的 ablation configs。"""

    return list(DEFAULT_EVAL_CONFIGS)


def resolve_eval_configs(names: list[str] | None = None) -> list[EvalConfig]:
    """按名称筛选 ablation configs。"""

    all_configs = {config.name: config for config in DEFAULT_EVAL_CONFIGS}
    if not names:
        return list(DEFAULT_EVAL_CONFIGS)

    resolved: list[EvalConfig] = []
    for name in names:
        key = name.strip()
        if key not in all_configs:
            available = ", ".join(sorted(all_configs))
            raise ValueError(f"Unknown eval config '{name}'. Available: {available}")
        resolved.append(all_configs[key])
    return resolved
