"""FTS5 查询安全归一化。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)
MAX_QUERY_CHARS = 4000
MAX_TOKENS = 80
MAX_TOKEN_CHARS = 80


@dataclass(frozen=True, slots=True)
class NormalizedFtsQuery:
    """FTS 查询归一化结果。"""

    original_query: str
    normalized_query: str
    tokens: list[str]
    dropped_tokens: list[str] = field(default_factory=list)
    strategy: str = "normalized_match"
    truncated: bool = False


def normalize_fts_query(query: str) -> NormalizedFtsQuery:
    """把自然语言输入转换为安全的 FTS5 MATCH 表达式。"""

    original = query
    truncated = len(query) > MAX_QUERY_CHARS
    working = query[:MAX_QUERY_CHARS]
    tokens: list[str] = []
    dropped: list[str] = []
    seen: set[str] = set()

    for raw in TOKEN_RE.findall(working):
        token = raw.strip()
        if not token:
            continue
        if len(token) > MAX_TOKEN_CHARS:
            dropped.append(token)
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
        if len(tokens) >= MAX_TOKENS:
            break

    normalized = " OR ".join(f'"{token}"' for token in tokens)
    strategy = "normalized_match" if normalized else "empty_query"
    return NormalizedFtsQuery(
        original_query=original,
        normalized_query=normalized,
        tokens=tokens,
        dropped_tokens=dropped,
        strategy=strategy,
        truncated=truncated,
    )
