from contextgraph_studio.indexing.embedder import resolve_embedding_model_profile


def test_minilm_profile_has_no_query_prompt_or_prefix() -> None:
    profile = resolve_embedding_model_profile("sentence-transformers/all-MiniLM-L6-v2")

    assert profile.query_prefix is None
    assert profile.query_prompt_name is None
    assert profile.document_prompt_name is None
    assert profile.trust_remote_code is False
    assert profile.code_specialized is False


def test_coderankembed_profile_uses_official_query_prefix() -> None:
    profile = resolve_embedding_model_profile("nomic-ai/CodeRankEmbed")

    assert profile.query_prefix == "Represent this query for searching relevant code: "
    assert profile.query_prompt_name is None
    assert profile.document_prompt_name is None
    assert profile.trust_remote_code is True
    assert profile.revision == "3c4b60807d71f79b43f3c4363786d9493691f8b1"
    assert profile.code_specialized is True


def test_nomic_embed_code_profile_uses_query_prompt() -> None:
    profile = resolve_embedding_model_profile("nomic-ai/nomic-embed-code")

    assert profile.query_prompt_name == "query"
    assert profile.query_prefix is None
    assert profile.document_prompt_name is None
    assert profile.code_specialized is True
