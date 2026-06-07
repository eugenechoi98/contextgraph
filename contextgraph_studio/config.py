"""项目配置。"""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """统一管理运行参数。"""

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTGRAPH_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    workspace_root: Path = Field(default_factory=Path.cwd)
    data_dir: Path = Field(default_factory=lambda: Path(".data"))
    database_path: Path = Field(
        default_factory=lambda: Path(".data/contextgraph.db"),
        validation_alias=AliasChoices("CGSTUDIO_DB_PATH", "CONTEXTGRAPH_DATABASE_PATH"),
    )
    task_strategies_path: Path = Field(default_factory=lambda: Path("config/task_strategies.yaml"))
    max_file_bytes: int = 512_000
    chunk_lines: int = 80
    chunk_overlap: int = 10
    default_top_k: int = 8
    bm25_general_candidate_limit: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices("BM25_GENERAL_CANDIDATE_LIMIT", "CONTEXTGRAPH_BM25_GENERAL_CANDIDATE_LIMIT"),
    )
    bm25_source_code_lane_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("BM25_SOURCE_CODE_LANE_ENABLED", "CONTEXTGRAPH_BM25_SOURCE_CODE_LANE_ENABLED"),
    )
    bm25_source_code_candidate_limit: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices("BM25_SOURCE_CODE_CANDIDATE_LIMIT", "CONTEXTGRAPH_BM25_SOURCE_CODE_CANDIDATE_LIMIT"),
    )
    bm25_lexical_expansion_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("BM25_LEXICAL_EXPANSION_ENABLED", "CONTEXTGRAPH_BM25_LEXICAL_EXPANSION_ENABLED"),
    )
    vector_index_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("VECTOR_INDEX_ENABLED", "CONTEXTGRAPH_VECTOR_INDEX_ENABLED"),
    )
    embedding_provider: str = Field(
        default="deterministic",
        validation_alias=AliasChoices("EMBEDDING_PROVIDER", "CONTEXTGRAPH_EMBEDDING_PROVIDER"),
    )
    embedding_model: str = Field(
        default="deterministic-sha256",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "CONTEXTGRAPH_EMBEDDING_MODEL"),
    )
    embedding_dimension: int = Field(
        default=768,
        ge=1,
        validation_alias=AliasChoices("EMBEDDING_DIMENSION", "CONTEXTGRAPH_EMBEDDING_DIMENSION"),
    )
    embedding_batch_size: int = Field(
        default=16,
        ge=1,
        validation_alias=AliasChoices("EMBEDDING_BATCH_SIZE", "CONTEXTGRAPH_EMBEDDING_BATCH_SIZE"),
    )
    hybrid_vector_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HYBRID_VECTOR_ENABLED", "CONTEXTGRAPH_HYBRID_VECTOR_ENABLED"),
    )
    hybrid_graph_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("HYBRID_GRAPH_ENABLED", "CONTEXTGRAPH_HYBRID_GRAPH_ENABLED"),
    )
    rrf_k: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices("RRF_K", "CONTEXTGRAPH_RRF_K"),
    )
    graph_seed_limit: int = Field(
        default=6,
        ge=1,
        validation_alias=AliasChoices("GRAPH_SEED_LIMIT", "CONTEXTGRAPH_GRAPH_SEED_LIMIT"),
    )
    required_chunk_limit: int = Field(
        default=3,
        ge=1,
        validation_alias=AliasChoices("REQUIRED_CHUNK_LIMIT", "CONTEXTGRAPH_REQUIRED_CHUNK_LIMIT"),
    )
    host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("CGSTUDIO_HOST", "CONTEXTGRAPH_HOST"),
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("CGSTUDIO_PORT", "CONTEXTGRAPH_PORT"),
    )
    log_level: str = Field(
        default="warning",
        validation_alias=AliasChoices("CGSTUDIO_LOG_LEVEL", "CONTEXTGRAPH_LOG_LEVEL"),
    )
    exclude_dirs: tuple[str, ...] = (
        ".git",
        ".venv",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".pytest_cache",
        "__pycache__",
    )
    exclude_dir_prefixes: tuple[str, ...] = (
        ".tmp",
        "tmp_pytest",
    )
    exclude_path_prefixes: tuple[str, ...] = (
        "eval/fixtures",
        "eval/reports",
    )
    text_extensions: tuple[str, ...] = (
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".sql",
        ".sh",
        ".ps1",
        ".css",
        ".html",
    )

    def ensure_directories(self) -> None:
        """确保运行目录存在。"""

        self.data_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """返回配置实例。"""

    return Settings()
