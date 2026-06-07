from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pytest


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """在工作区内提供可写临时目录，规避受限环境的系统 temp 权限问题。"""

    base = Path.cwd() / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{request.node.name}-{uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        rmtree(path, ignore_errors=True)
