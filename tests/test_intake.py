from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.services.intake import should_skip


def test_should_skip_temp_and_eval_fixture_paths() -> None:
    settings = Settings()

    assert should_skip(Path(".tmp_debug_graph/a.py"), settings) is True
    assert should_skip(Path("tmp_pytest/output.txt"), settings) is True
    assert should_skip(Path("eval/fixtures/contextgraph_golden.json"), settings) is True
    assert should_skip(Path("eval/reports/latest_eval_report.json"), settings) is True
    assert should_skip(Path("tests/fixtures/sample_ts_repo/src/auth.ts"), settings) is True
    assert should_skip(Path("tests/fixtures/sample_structured_repo/schema.sql"), settings) is True
    assert should_skip(Path("contextgraph_studio/services/retriever.py"), settings) is False
