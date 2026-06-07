"""仓库扫描与文本读取。"""

from hashlib import sha256
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.domain import SourceFile
from contextgraph_studio.services.classifier import classify_file


def should_skip(path: Path, settings: Settings) -> bool:
    """根据目录、体积、路径前缀和后缀过滤文件。"""

    normalized = path.as_posix()
    if any(part in settings.exclude_dirs for part in path.parts):
        return True
    if any(part.startswith(prefix) for part in path.parts for prefix in settings.exclude_dir_prefixes):
        return True
    if any(normalized.startswith(prefix) for prefix in settings.exclude_path_prefixes):
        return True
    if path.suffix.lower() not in settings.text_extensions:
        return True
    return False


def read_text_file(path: Path) -> str:
    """读取文本文件，无法解码时直接跳过。"""

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def scan_repository(repo_root: Path, repo_id: str, settings: Settings) -> list[SourceFile]:
    """扫描仓库并返回可索引文件。"""

    files: list[SourceFile] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(repo_root)
        if should_skip(relative_path, settings):
            continue
        if path.stat().st_size > settings.max_file_bytes:
            continue
        content = read_text_file(path)
        if not content.strip():
            continue
        category, language = classify_file(relative_path)
        files.append(
            SourceFile(
                repo_id=repo_id,
                path=relative_path.as_posix(),
                absolute_path=str(path.resolve()),
                category=category,
                language=language,
                content_hash=sha256(content.encode("utf-8")).hexdigest(),
                content=content,
                size_bytes=path.stat().st_size,
                line_count=len(content.splitlines()),
            )
        )
    return files
