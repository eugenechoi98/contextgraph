"""Graph score 计算。"""

EDGE_TYPE_WEIGHTS: dict[str, float] = {
    "contains": 1.0,
    "imports": 1.0,
    "calls": 1.0,
    "tests": 1.5,
    "route_to_handler": 2.0,
    "inherits": 1.5,
}

CATEGORY_BONUS: dict[str, float] = {
    "source_code": 1.0,
    "test": 0.8,
    "schema": 0.9,
    "config": 0.6,
    "doc": 0.5,
}


def edge_bonus_for_relation(edge_type: str, weight: float | None = None) -> float:
    """返回图边的评分加成。"""

    if edge_type == "calls" and weight is not None:
        return weight
    return EDGE_TYPE_WEIGHTS.get(edge_type, 1.0)


def compute_graph_score(
    category: str,
    seed_node_id: str,
    hop_distance: int,
    edge_type: str,
    weight: float | None = None,
) -> float:
    """按设计文档公式计算 graph_score。"""

    del seed_node_id
    base = 1.0 / (hop_distance + 1)
    edge_bonus = edge_bonus_for_relation(edge_type, weight)
    category_bonus = CATEGORY_BONUS.get(category, 0.7)
    return base * edge_bonus * category_bonus
