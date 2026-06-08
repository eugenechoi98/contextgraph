from pathlib import Path

from contextgraph_studio.services.classifier import classify_file


def test_classify_source_file() -> None:
    file_type, language = classify_file(Path("src/app/main.py"))
    assert file_type == "source_code"
    assert language == "python"


def test_classify_test_file() -> None:
    file_type, language = classify_file(Path("tests/test_api.py"))
    assert file_type == "test"
    assert language == "python"


def test_classify_config_file() -> None:
    file_type, language = classify_file(Path("config/settings.yaml"))
    assert file_type == "config"
    assert language == "yaml"

    file_type, language = classify_file(Path("db/schema.sql"))
    assert file_type == "schema"
    assert language == "sql"


def test_classify_typescript_and_js_test_variants() -> None:
    file_type, language = classify_file(Path("src/auth.spec.ts"))
    assert file_type == "test"
    assert language == "typescript"

    file_type, language = classify_file(Path("src/components/Login.test.tsx"))
    assert file_type == "test"
    assert language == "tsx"

    file_type, language = classify_file(Path("src/legacy.spec.jsx"))
    assert file_type == "test"
    assert language == "jsx"
