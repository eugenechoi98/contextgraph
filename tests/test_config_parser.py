from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.parsers.config_parser import PARSER_VERSION, ConfigParser


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_config_parser_extracts_json_yaml_and_toml_keys(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    parser = ConfigParser()

    json_result = parser.parse(
        "config.json",
        '{"database":{"host":"localhost","port":5432},"servers":[{"host":"api.internal"}]}',
        "file-1",
        "json",
        settings,
    )
    yaml_result = parser.parse("settings.yaml", "database:\n  host: localhost\n  port: 5432\n", "file-2", "yaml", settings)
    toml_result = parser.parse("pyproject.toml", '[database]\nhost = "localhost"\nport = 5432\n', "file-3", "toml", settings)

    json_symbols = {entity.symbol_name for entity in json_result.entities}
    yaml_symbols = {entity.symbol_name for entity in yaml_result.entities}
    toml_symbols = {entity.symbol_name for entity in toml_result.entities}

    assert json_result.parser_version == PARSER_VERSION
    assert "database" in json_symbols
    assert "database.host" in json_symbols
    assert "servers" in json_symbols
    assert "servers[]" in json_symbols
    assert "servers[].host" in json_symbols
    assert "database.host" in yaml_symbols
    assert "database.port" in yaml_symbols
    assert "database.host" in toml_symbols
    assert "database.port" in toml_symbols


def test_config_parser_masks_sensitive_values_and_enforces_limits(tmp_path: Path) -> None:
    settings = make_settings(tmp_path).model_copy(update={"config_parser_max_depth": 2, "config_parser_max_keys": 3})
    parser = ConfigParser()
    result = parser.parse(
        "config.json",
        '{"database":{"password":"super-secret","host":"localhost"},"nested":{"too":{"deep":true}}}',
        "file-1",
        "json",
        settings,
    )

    assert any(entity.symbol_name == "database.password" for entity in result.entities)
    sensitive_entity = next(entity for entity in result.entities if entity.symbol_name == "database.password")
    assert "super-secret" not in (sensitive_entity.signature or "")
    assert "[masked]" in (sensitive_entity.signature or "")
    assert result.parse_errors


def test_config_parser_yaml_soft_failure(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    parser = ConfigParser()
    result = parser.parse("broken.yaml", "service:\n  host: localhost\n  port: [1, 2\n", "file-1", "yaml", settings)
    assert result.entities == []
    assert result.parse_errors
