"""Golden dataset、评测配置与报告模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _normalize_file_list(items: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip().replace("\\", "/")
        if not value:
            raise ValueError(f"{field_name} must not contain empty paths.")
        if value in seen:
            raise ValueError(f"{field_name} must not contain duplicates: {value}")
        seen.add(value)
        normalized.append(value)
    return normalized


class GoldenCase(BaseModel):
    """单条 golden case。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    task_hint: str | None = None
    repo_id: str | None = None
    expected_files: list[str]
    critical_files: list[str] = Field(default_factory=list)
    helpful_files: list[str] = Field(default_factory=list)
    intent_tags: list[str] = Field(default_factory=list)
    expects_tests: Literal["explicit", "implicit", "none"] = "implicit"
    notes: str = ""
    status: Literal["active", "draft"] = "active"

    @model_validator(mode="after")
    def _validate_lists(self) -> "GoldenCase":
        self.id = self.id.strip()
        self.query = self.query.strip()
        if not self.id:
            raise ValueError("Golden case id must not be empty.")
        if not self.query:
            raise ValueError("Golden case query must not be empty.")

        self.expected_files = _normalize_file_list(self.expected_files, field_name="expected_files")
        self.critical_files = _normalize_file_list(self.critical_files, field_name="critical_files")
        self.helpful_files = _normalize_file_list(self.helpful_files, field_name="helpful_files")
        self.intent_tags = [tag.strip() for tag in self.intent_tags if tag.strip()]

        if not self.expected_files:
            raise ValueError("expected_files must contain at least one file.")

        expected = set(self.expected_files)
        critical = set(self.critical_files)
        helpful = set(self.helpful_files)

        if not critical.issubset(expected):
            missing = sorted(critical - expected)
            raise ValueError(f"critical_files must be a subset of expected_files: {missing}")
        if expected & helpful:
            overlap = sorted(expected & helpful)
            raise ValueError(f"helpful_files must be disjoint from expected_files: {overlap}")

        return self


class GoldenDataset(BaseModel):
    """Golden dataset 文件。"""

    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(..., min_length=1)
    description: str | None = None
    cases: list[GoldenCase]

    @model_validator(mode="after")
    def _validate_cases(self) -> "GoldenDataset":
        if not self.cases:
            raise ValueError("Golden dataset must contain at least one case.")
        seen: set[str] = set()
        for case in self.cases:
            if case.id in seen:
                raise ValueError(f"Duplicate golden case id: {case.id}")
            seen.add(case.id)
        return self


class EvalConfig(BaseModel):
    """Ablation 配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    description: str
    bm25_enabled: bool = True
    vector_enabled: bool = False
    graph_enabled: bool = False


class CaseEvalResult(BaseModel):
    """单 case 评测结果。"""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    query: str
    task_hint: str | None = None
    expects_tests: Literal["explicit", "implicit", "none"]
    status: Literal["passed", "failed"]
    expected_files: list[str]
    critical_files: list[str]
    helpful_files: list[str]
    retrieved_files: list[str]
    expected_hits: list[str]
    helpful_hits: list[str]
    missed_critical_files: list[str]
    first_relevant_rank: int | None = None
    recall_at_k: dict[int, float]
    precision_at_k: dict[int, float]
    reciprocal_rank: float
    critical_file_all_hit: bool
    critical_file_any_hit: bool
    token_count: int | None = None
    latency_ms: int | None = None
    trace_id: str | None = None
    retrieval_strategy: list[str] = Field(default_factory=list)
    requested_routes: list[str] = Field(default_factory=list)
    executed_routes: list[str] = Field(default_factory=list)
    participating_routes: list[str] = Field(default_factory=list)
    effective_flags: dict[str, bool] = Field(default_factory=dict)
    route_diagnostics: dict[str, dict[str, object]] = Field(default_factory=dict)
    error: str | None = None


class EvalMetrics(BaseModel):
    """聚合指标。"""

    model_config = ConfigDict(extra="forbid")

    recall_at_k: dict[int, float]
    precision_at_k: dict[int, float]
    mrr: float
    critical_file_hit_rate: float
    critical_file_any_hit_rate: float
    expected_file_hit_rate: float
    helpful_file_hit_rate: float
    avg_token_count: float
    avg_latency_ms: float
    missed_critical_files: list[str]


class ConfigEvalResult(BaseModel):
    """单个 ablation config 的结果。"""

    model_config = ConfigDict(extra="forbid")

    config: EvalConfig
    metrics: EvalMetrics
    case_results: list[CaseEvalResult]
    passed_case_count: int
    failed_case_count: int


class EvalRunResult(BaseModel):
    """一次 eval run 的完整结果。"""

    model_config = ConfigDict(extra="forbid")

    eval_run_id: str
    repo_id: str
    scan_run_id: str
    dataset: str
    dataset_path: str
    created_at: int
    active_cases: int
    draft_cases: int
    embedding_provider: str
    embedding_model: str
    vector_quality_valid: bool
    vector_quality_note: str
    configs: list[ConfigEvalResult]
    json_report_path: str
    markdown_report_path: str
    latest_json_report_path: str
    latest_markdown_report_path: str
