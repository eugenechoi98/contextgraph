"""Minimal structured config parser with sensitive-value masking."""

from __future__ import annotations

import hashlib
import json
import tomllib
from typing import Any

import yaml

from contextgraph_studio.config import Settings
from contextgraph_studio.domain import EntityRecord, ParseResult, RelationRecord


PARSER_VERSION = "config-structured-v1"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


def _is_sensitive(path: str, settings: Settings) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in settings.sensitive_key_markers)


def _safe_preview(value: Any, *, sensitive: bool) -> str | None:
    if sensitive:
        return None
    if isinstance(value, str):
        preview = value.strip()
        if not preview:
            return None
        return preview[:32]
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    return None


def _load_config(content: str, language: str) -> Any:
    if language == "json":
        return json.loads(content)
    if language == "yaml":
        return yaml.safe_load(content)
    if language == "toml":
        return tomllib.loads(content)
    raise ValueError(f"Unsupported config language: {language}")


class ConfigParser:
    """Extract config_key entities from JSON/YAML/TOML."""

    def parse(self, file_path: str, content: str, file_id: str, language: str, settings: Settings) -> ParseResult:
        del file_id
        entities: list[EntityRecord] = []
        relations: list[RelationRecord] = []
        parse_errors: list[str] = []
        try:
            payload = _load_config(content, language)
        except Exception as exc:
            return ParseResult(
                entities=[],
                relations=[],
                parse_errors=[f"{file_path}: {exc}"],
                language=language,
                parser_version=PARSER_VERSION,
            )

        if payload is None:
            payload = {}

        key_budget = {"count": 0, "truncated": False}

        def visit(value: Any, path: str, depth: int) -> None:
            if key_budget["count"] >= settings.config_parser_max_keys:
                key_budget["truncated"] = True
                return
            if depth > settings.config_parser_max_depth:
                key_budget["truncated"] = True
                return

            value_type = _value_type(value)
            sensitive = _is_sensitive(path, settings)
            preview = _safe_preview(value, sensitive=sensitive)
            metadata = [f"type={value_type}"]
            if isinstance(value, dict):
                metadata.append("nested=true")
            elif isinstance(value, list):
                metadata.append("nested=true")
            if sensitive:
                metadata.append("preview=[masked]")
            elif preview is not None:
                metadata.append(f"preview={preview}")

            entities.append(
                EntityRecord(
                    entity_type="config_key",
                    symbol_name=path,
                    display_name=path,
                    line_start=None,
                    line_end=None,
                    signature=f"config_key {path} ({', '.join(metadata)})",
                    docstring=None,
                    language=language,
                    content_hash=_hash_text(f"{path}|{value_type}|{preview or ''}|{sensitive}"),
                    parent_symbol_name=file_path,
                )
            )
            key_budget["count"] += 1
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    if not isinstance(child_key, str):
                        child_key = str(child_key)
                    visit(child_value, f"{path}.{child_key}" if path else child_key, depth + 1)
            elif isinstance(value, list):
                if not value:
                    return
                sample_path = f"{path}[]"
                sample_value = value[0]
                sample_type = _value_type(sample_value)
                entities.append(
                    EntityRecord(
                        entity_type="config_key",
                        symbol_name=sample_path,
                        display_name=sample_path,
                        line_start=None,
                        line_end=None,
                        signature=f"config_key {sample_path} (type={sample_type}, nested=true)",
                        docstring=None,
                        language=language,
                        content_hash=_hash_text(f"{sample_path}|{sample_type}"),
                        parent_symbol_name=file_path,
                    )
                )
                key_budget["count"] += 1
                if isinstance(sample_value, dict):
                    for child_key, child_value in sample_value.items():
                        child_key = str(child_key)
                        visit(child_value, f"{sample_path}.{child_key}", depth + 1)

        if isinstance(payload, dict):
            for key, value in payload.items():
                visit(value, str(key), 1)
        else:
            parse_errors.append(f"{file_path}: top-level config value must be an object/table")

        if key_budget["truncated"]:
            parse_errors.append(f"{file_path}: config extraction truncated by depth/key budget")

        return ParseResult(
            entities=entities,
            relations=relations,
            parse_errors=parse_errors,
            language=language,
            parser_version=PARSER_VERSION,
        )
